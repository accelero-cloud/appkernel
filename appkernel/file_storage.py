"""
File storage module for AppKernel.

Provides pluggable storage backends (filesystem, GridFS), a chain-of-responsibility
validation pipeline, a ``FileRef`` metadata model, and a ``FileService`` that
registers upload/download/delete REST endpoints directly on the FastAPI app.

Typical usage::

    from appkernel import AppKernelEngine
    from appkernel.file_storage import (
        FilesystemBackend, GridFSBackend,
        SizeValidator, MimeTypeValidator, ExtensionValidator,
        FileService,
    )

    kernel = AppKernelEngine('my-app', cfg_dir='./config')

    # Build a validation chain
    chain = SizeValidator(max_bytes=10 * 1024 * 1024)       # 10 MB
    chain.set_next(MimeTypeValidator(['image/jpeg', 'image/png', 'application/pdf']))
    chain.set_next(ExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']))

    # Register the file service
    kernel.enable_file_storage(
        backend=FilesystemBackend('/var/uploads'),
        validation_chain=chain,
        url_base='/files',
    )

The service exposes four endpoints:
  - ``POST   /files/``              — upload (multipart/form-data, field name: ``file``)
  - ``GET    /files/{file_id}``     — retrieve metadata as JSON
  - ``GET    /files/{file_id}/content`` — download file bytes (streaming)
  - ``DELETE /files/{file_id}``     — delete file and its metadata
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, AsyncIterator, Optional, TYPE_CHECKING

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from .configuration import config
from .core import AppKernelException
from .fields import Required, Generator
from .generators import create_uuid_generator, date_now_generator
from .model import Model
from .repository import MongoRepository
from .validators import ValidationException
from .util import create_custom_error, AppJSONResponse as JSONResponse

if TYPE_CHECKING:
    from .engine import AppKernelEngine

logger = logging.getLogger(__name__)

_DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KB


# ---------------------------------------------------------------------------
# Module-level sync helpers (used with run_in_executor)
# ---------------------------------------------------------------------------

def _fs_write_file(path: str, data: bytes) -> None:
    with open(path, 'wb') as f:
        f.write(data)


def _fs_read_chunk(path: str, offset: int, size: int) -> bytes:
    with open(path, 'rb') as f:
        f.seek(offset)
        return f.read(size)


def _fs_delete(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _fs_exists(path: str) -> bool:
    return os.path.isfile(path)


def _fs_size(path: str) -> int:
    return os.path.getsize(path)


# ---------------------------------------------------------------------------
# Validation primitives
# ---------------------------------------------------------------------------

@dataclass
class ValidationContext:
    """Carries per-upload metadata through the validation chain.

    Validators may read and mutate this object.  ``actual_size`` is
    populated by :class:`SizeValidator` as bytes are consumed.

    Args:
        filename:      Original filename as reported by the client.
        content_type:  MIME type declared in the multipart Content-Type header.
        declared_size: ``Content-Length`` value from the request, or ``None``.
        actual_size:   Bytes transferred; set by :class:`SizeValidator` after
                       the stream is fully consumed.
    """
    filename: str
    content_type: str
    declared_size: Optional[int] = None
    actual_size: int = 0


class FileStorageException(AppKernelException):
    """Raised for storage-level errors (file not found, I/O failure, etc.)."""

    def __init__(self, message: str, http_code: int = 500) -> None:
        super().__init__(message)
        self.http_code = http_code
        self.status_code = http_code


class FileValidator(ABC):
    """Abstract base for chain-of-responsibility file validators.

    Build a validation chain with :meth:`add_next`.  You may call it
    repeatedly on the head — each call appends to the **tail** of the
    existing chain::

        chain = SizeValidator(max_bytes=5_000_000)
        chain.add_next(MimeTypeValidator(['image/jpeg', 'image/png']))
        chain.add_next(ExtensionValidator(['jpg', 'png']))

    Method chaining also works, because :meth:`add_next` returns the
    newly added validator::

        chain.add_next(MimeTypeValidator([...])).add_next(ExtensionValidator([...]))

    Both forms produce the same result:
    ``SizeValidator → MimeTypeValidator → ExtensionValidator``.

    Then validate an upload stream::

        validated_stream = await chain.validate(upload_stream, context)

    Each validator either inspects the ``context`` immediately (synchronous
    metadata check) or wraps the stream in a new async generator that
    performs byte-level inspection as the stream is consumed.  All validators
    propagate the (possibly wrapped) stream to the next link in the chain.

    Raise :class:`~appkernel.validators.ValidationException` to reject the
    upload.
    """

    def __init__(self) -> None:
        self._next: Optional[FileValidator] = None

    def add_next(self, validator: FileValidator) -> FileValidator:
        """Append *validator* to the tail of this chain and return it.

        Traverses to the last link with no successor and attaches *validator*
        there, so calling ``add_next`` multiple times on the same head always
        extends the chain rather than replacing an existing link::

            chain = SizeValidator()
            chain.add_next(MimeTypeValidator([...]))  # size → mime
            chain.add_next(ExtensionValidator([...]))  # size → mime → ext
        """
        tail = self
        while tail._next is not None:
            tail = tail._next
        tail._next = validator
        return validator

    async def validate(self, stream: AsyncIterator[bytes], context: ValidationContext) -> AsyncIterator[bytes]:
        """Run this validator and pass the (possibly wrapped) stream to the next link."""
        validated = await self._do_validate(stream, context)
        if self._next:
            return await self._next.validate(validated, context)
        return validated

    @abstractmethod
    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        """Validate and return the (possibly wrapped) stream.

        Implementations fall into three patterns:

        * **Metadata-only** — inspect ``context`` and either raise
          :class:`~appkernel.validators.ValidationException` or return
          ``stream`` unchanged (no buffering, no wrapping).
        * **Stream-wrapping** — return a new ``async def`` generator that
          yields chunks while counting or inspecting bytes.
        * **Buffering** — consume the entire stream, validate the buffered
          content, then yield it back.  Use sparingly (e.g. virus scanning).
        """


class SizeValidator(FileValidator):
    """Rejects uploads that exceed *max_bytes*.

    Wraps the stream to count bytes as they are consumed.  Sets
    ``context.actual_size`` after the stream is fully drained.

    Args:
        max_bytes: Maximum allowed upload size in bytes.
                   Defaults to 10 MiB.
    """

    def __init__(self, max_bytes: int = 10 * 1024 * 1024) -> None:
        super().__init__()
        self.max_bytes = max_bytes

    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        max_bytes = self.max_bytes

        async def _counted() -> AsyncIterator[bytes]:
            total = 0
            async for chunk in stream:
                total += len(chunk)
                if total > max_bytes:
                    raise ValidationException(
                        f'Upload too large: {total} bytes exceeds the {max_bytes}-byte limit.'
                    )
                yield chunk
            context.actual_size = total

        return _counted()


class MimeTypeValidator(FileValidator):
    """Rejects uploads whose declared Content-Type is not in *allowed_types*.

    This is a metadata-only validator — the stream is not wrapped.  The
    MIME type is read from ``context.content_type``, which is set from the
    multipart part header.  Pair with :class:`MagicByteValidator` to also
    verify the file's actual content.

    Args:
        allowed_types: Allowed MIME type strings,
                       e.g. ``['image/jpeg', 'application/pdf']``.
    """

    def __init__(self, allowed_types: list[str]) -> None:
        super().__init__()
        self.allowed_types = allowed_types

    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        if context.content_type not in self.allowed_types:
            raise ValidationException(
                f'Content type {context.content_type!r} is not allowed. '
                f'Permitted types: {self.allowed_types}'
            )
        return stream


class ExtensionValidator(FileValidator):
    """Rejects uploads whose filename extension is not in *allowed_extensions*.

    This is a metadata-only validator — the stream is not wrapped.

    Args:
        allowed_extensions: Allowed extensions without leading dot,
                            e.g. ``['jpg', 'png', 'pdf']``.
                            Comparison is case-insensitive.
    """

    def __init__(self, allowed_extensions: list[str]) -> None:
        super().__init__()
        self.allowed_extensions = [e.lower().lstrip('.') for e in allowed_extensions]

    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        name = context.filename or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext not in self.allowed_extensions:
            raise ValidationException(
                f'File extension {ext!r} is not allowed. '
                f'Permitted extensions: {self.allowed_extensions}'
            )
        return stream


class MagicByteValidator(FileValidator):
    """Verifies that the file's leading bytes match the declared MIME type.

    Guards against clients sending a malicious file (e.g. an executable)
    with a benign Content-Type header.  Wraps the stream — the first chunk
    is inspected before being passed downstream.

    Built-in signatures cover JPEG, PNG, GIF, PDF, and ZIP.  Extend by
    subclassing and overriding :attr:`SIGNATURES`.

    Files whose declared MIME type has no known signature are passed through
    without inspection.
    """

    SIGNATURES: dict[str, list[bytes]] = {
        'image/jpeg': [b'\xff\xd8\xff'],
        'image/png':  [b'\x89PNG\r\n\x1a\n'],
        'image/gif':  [b'GIF87a', b'GIF89a'],
        'application/pdf': [b'%PDF'],
        'application/zip': [b'PK\x03\x04'],
    }

    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        expected_sigs = self.SIGNATURES.get(context.content_type)
        inspected = False

        async def _inspect() -> AsyncIterator[bytes]:
            nonlocal inspected
            async for chunk in stream:
                if not inspected:
                    inspected = True
                    if expected_sigs and not any(chunk.startswith(sig) for sig in expected_sigs):
                        raise ValidationException(
                            f'File content does not match the declared content type '
                            f'{context.content_type!r}.'
                        )
                yield chunk

        return _inspect()


class VirusScanValidator(FileValidator):
    """Optional ClamAV virus scanner via ``pyclamd``.

    Buffers the entire upload, submits it to a running ``clamd`` daemon,
    and re-streams the data if the scan is clean.  If ``pyclamd`` is not
    installed the upload passes through without scanning.

    Install extras: ``pip install pyclamd`` and run ``clamd`` locally.

    Args:
        clamd_host: Host where ``clamd`` is listening. Defaults to
                    ``'localhost'``.
        clamd_port: TCP port for ``clamd``. Defaults to ``3310``.
    """

    def __init__(self, clamd_host: str = 'localhost', clamd_port: int = 3310) -> None:
        super().__init__()
        self.clamd_host = clamd_host
        self.clamd_port = clamd_port

    async def _do_validate(
        self,
        stream: AsyncIterator[bytes],
        context: ValidationContext,
    ) -> AsyncIterator[bytes]:
        chunks: list[bytes] = []
        async for chunk in stream:
            chunks.append(chunk)
        data = b''.join(chunks)

        try:
            import pyclamd  # type: ignore[import]
            cd = pyclamd.ClamdNetworkSocket(host=self.clamd_host, port=self.clamd_port)
            result = cd.scan_stream(data)
            if result:
                virus_name = next(iter(result.values()))[1]
                raise ValidationException(f'Virus detected: {virus_name}')
        except ImportError:
            logger.debug('pyclamd not installed — virus scanning skipped.')
        except ValidationException:
            raise
        except Exception as exc:
            logger.warning(f'VirusScanValidator: clamd connection failed — {exc}')

        async def _replay() -> AsyncIterator[bytes]:
            yield data

        return _replay()


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    """Abstract base class for file storage backends.

    Implement this to add a new backend (e.g. AWS S3, Azure Blob Storage).
    All methods are async; blocking I/O must be delegated to a thread pool
    via ``asyncio.get_event_loop().run_in_executor()``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier stored in :class:`FileRef`.storage_backend."""

    @abstractmethod
    async def store(self, stream: AsyncIterator[bytes], file_ref: FileRef) -> str:
        """Persist *stream* and return a *storage_ref* string.

        The *storage_ref* is an opaque handle used to retrieve or delete the
        file later.  Implementations must raise if an error occurs — partial
        writes must be cleaned up before raising.
        """

    @abstractmethod
    async def retrieve(self, storage_ref: str) -> tuple[AsyncIterator[bytes], int]:
        """Return ``(async_stream, file_size_bytes)`` for *storage_ref*.

        Raises :class:`FileStorageException` (404) if the file does not exist.
        """

    @abstractmethod
    async def delete(self, storage_ref: str) -> None:
        """Delete the file identified by *storage_ref*.  No-op if not found."""

    @abstractmethod
    async def exists(self, storage_ref: str) -> bool:
        """Return ``True`` if *storage_ref* points to an existing file."""


class FilesystemBackend(StorageBackend):
    """Stores files as UUID-named binary blobs in a local directory.

    Suitable for single-instance deployments or development.  For
    multi-instance deployments mount a shared network filesystem (NFS/EFS)
    or switch to :class:`GridFSBackend` / a cloud object store.

    Files are buffered in memory before being written atomically to disk.
    The :class:`SizeValidator` should always precede this backend to cap
    memory usage during upload.

    Args:
        base_path:  Absolute path to the directory where files are stored.
                    Created automatically if it does not exist.
        chunk_size: Bytes per chunk when streaming files on download.
                    Defaults to 64 KiB.
    """

    def __init__(self, base_path: str, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> None:
        self.base_path = base_path
        self.chunk_size = chunk_size
        os.makedirs(base_path, exist_ok=True)

    @property
    def name(self) -> str:
        return 'filesystem'

    def _safe_path(self, storage_ref: str) -> str:
        """Return the full path, rejecting any non-UUID storage references."""
        if not re.match(r'^[0-9a-f\-]{36}$', storage_ref):
            raise FileStorageException(
                f'Invalid storage reference: {storage_ref!r}', http_code=400
            )
        return os.path.join(self.base_path, storage_ref)

    async def store(self, stream: AsyncIterator[bytes], file_ref: FileRef) -> str:
        storage_ref = str(uuid.uuid4())
        path = self._safe_path(storage_ref)
        loop = asyncio.get_event_loop()
        buffer = bytearray()
        async for chunk in stream:
            buffer.extend(chunk)
        await loop.run_in_executor(None, _fs_write_file, path, bytes(buffer))
        return storage_ref

    async def retrieve(self, storage_ref: str) -> tuple[AsyncIterator[bytes], int]:
        path = self._safe_path(storage_ref)
        loop = asyncio.get_event_loop()
        if not await loop.run_in_executor(None, _fs_exists, path):
            raise FileStorageException(f'File not found: {storage_ref}', http_code=404)
        size = await loop.run_in_executor(None, _fs_size, path)
        chunk_size = self.chunk_size

        async def _stream() -> AsyncIterator[bytes]:
            offset = 0
            while True:
                chunk = await loop.run_in_executor(None, _fs_read_chunk, path, offset, chunk_size)
                if not chunk:
                    break
                yield chunk
                offset += len(chunk)

        return _stream(), size

    async def delete(self, storage_ref: str) -> None:
        path = self._safe_path(storage_ref)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _fs_delete, path)

    async def exists(self, storage_ref: str) -> bool:
        path = self._safe_path(storage_ref)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fs_exists, path)


class GridFSBackend(StorageBackend):
    """Stores files in MongoDB's GridFS using Motor's async driver.

    GridFS splits files into 255 KiB chunks stored in ``<bucket>.files``
    and ``<bucket>.chunks`` collections.  Suitable for files up to ~100 MB.
    The database connection is read from ``config.mongo_database`` (set by
    :class:`~appkernel.engine.AppKernelEngine` at startup).

    Advantages over :class:`FilesystemBackend`:
      - Replicated across MongoDB replica set members.
      - Works transparently in multi-instance deployments.

    Limitations:
      - ~20–30 % storage overhead versus raw disk.
      - No efficient byte-range (seek) support.
      - Not suitable for very large files (> 100 MB).

    Args:
        bucket_name: GridFS bucket name. Defaults to ``'fs'``.
        chunk_size:  GridFS chunk size in bytes. Defaults to 255 KiB.
    """

    def __init__(self, bucket_name: str = 'fs', chunk_size: int = 255 * 1024) -> None:
        self._bucket_name = bucket_name
        self._chunk_size = chunk_size

    @property
    def name(self) -> str:
        return 'gridfs'

    def _get_bucket(self):
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        return AsyncIOMotorGridFSBucket(
            config.mongo_database,
            bucket_name=self._bucket_name,
            chunk_size_bytes=self._chunk_size,
        )

    async def store(self, stream: AsyncIterator[bytes], file_ref: FileRef) -> str:
        bucket = self._get_bucket()
        grid_in = bucket.open_upload_stream(
            file_ref.original_filename,
            metadata={
                'content_type': file_ref.content_type,
                'file_ref_id': file_ref.id,
            },
        )
        try:
            async for chunk in stream:
                await grid_in.write(chunk)
            await grid_in.close()
        except Exception:
            with contextlib.suppress(Exception):
                await grid_in.close()
            raise
        return str(grid_in._id)

    async def retrieve(self, storage_ref: str) -> tuple[AsyncIterator[bytes], int]:
        from bson import ObjectId
        bucket = self._get_bucket()
        try:
            grid_out = await bucket.open_download_stream(ObjectId(storage_ref))
        except Exception as exc:
            raise FileStorageException(
                f'File not found: {storage_ref}', http_code=404
            ) from exc
        size = grid_out.length

        async def _stream() -> AsyncIterator[bytes]:
            while True:
                chunk = await grid_out.readchunk()
                if not chunk:
                    break
                yield chunk

        return _stream(), size

    async def delete(self, storage_ref: str) -> None:
        from bson import ObjectId
        bucket = self._get_bucket()
        with contextlib.suppress(Exception):
            await bucket.delete(ObjectId(storage_ref))

    async def exists(self, storage_ref: str) -> bool:
        from bson import ObjectId
        bucket = self._get_bucket()
        cursor = bucket.find({'_id': ObjectId(storage_ref)})
        docs = await cursor.to_list(length=1)
        return len(docs) > 0


# ---------------------------------------------------------------------------
# FileRef metadata model
# ---------------------------------------------------------------------------

class FileRef(Model, MongoRepository):
    """MongoDB document that stores file metadata.

    The actual file bytes live in the :class:`StorageBackend`.
    ``FileRef`` records only the metadata needed to locate, describe,
    and serve the file.

    Fields:
        id:                Auto-generated prefixed UUID (``F<uuid>``).
        original_filename: Client-supplied filename (path-stripped for safety).
        storage_backend:   Backend identifier (``'filesystem'`` or ``'gridfs'``).
        storage_ref:       Opaque handle for the backend (path fragment or
                           GridFS ObjectId string).
        content_type:      MIME type as declared by the client.
        size:              File size in bytes (set after upload completes).
        owner_id:          Optional reference to the uploading user's id.
        created_at:        Upload timestamp (auto-generated).
        metadata:          Application-defined key/value pairs.
    """

    id: Annotated[str | None, Required(), Generator(create_uuid_generator('F'))] = None
    original_filename: Annotated[str | None, Required()] = None
    storage_backend: Annotated[str | None, Required()] = None
    storage_ref: str | None = None
    content_type: str | None = None
    size: int | None = None
    owner_id: str | None = None
    created_at: Annotated[datetime | None, Generator(date_now_generator)] = None
    metadata: dict | None = None


# ---------------------------------------------------------------------------
# HTTP handler helpers
# ---------------------------------------------------------------------------

async def _stream_upload(upload_file: Any, chunk_size: int) -> AsyncIterator[bytes]:
    """Yield chunks from a Starlette/FastAPI UploadFile object."""
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        yield chunk


async def _handle_upload(
    request: Request,
    backend: StorageBackend,
    chain: Optional[FileValidator],
    chunk_size: int,
) -> Response:
    content_type_header = request.headers.get('content-type', '')
    if 'multipart/form-data' not in content_type_header:
        return create_custom_error(415, 'Expected a multipart/form-data request with a "file" field.')

    form = None
    try:
        form = await request.form()
        file_field = form.get('file')
        if file_field is None:
            return create_custom_error(400, 'Missing "file" field in the uploaded form data.')
        if not hasattr(file_field, 'filename'):
            return create_custom_error(400, 'The "file" field must be a file upload, not a text value.')

        original_filename = os.path.basename(file_field.filename or 'unnamed')
        upload_content_type = file_field.content_type or 'application/octet-stream'

        declared_size: Optional[int] = None
        cl = request.headers.get('content-length')
        if cl:
            with contextlib.suppress(ValueError):
                declared_size = int(cl)

        context = ValidationContext(
            filename=original_filename,
            content_type=upload_content_type,
            declared_size=declared_size,
        )

        file_ref = FileRef(
            original_filename=original_filename,
            content_type=upload_content_type,
            storage_backend=backend.name,
        )
        file_ref.finalise_and_validate()

        stream = _stream_upload(file_field, chunk_size)
        if chain:
            stream = await chain.validate(stream, context)

        storage_ref = await backend.store(stream, file_ref)
        file_ref.storage_ref = storage_ref
        file_ref.size = context.actual_size
        await file_ref.save()

        return JSONResponse(content=Model.to_dict(file_ref), status_code=201)

    except ValidationException as exc:
        return create_custom_error(422, str(exc))
    except FileStorageException as exc:
        return create_custom_error(exc.http_code, str(exc))
    except Exception as exc:
        logger.exception('Unexpected error during file upload')
        return create_custom_error(500, str(exc))
    finally:
        if form is not None:
            with contextlib.suppress(Exception):
                await form.close()


async def _handle_get_metadata(file_id: str) -> Response:
    try:
        file_ref = await FileRef.find_by_id(file_id)
        if file_ref is None:
            return create_custom_error(404, f'FileRef {file_id!r} not found.')
        return JSONResponse(content=Model.to_dict(file_ref), status_code=200)
    except FileStorageException as exc:
        return create_custom_error(exc.http_code, str(exc))
    except Exception as exc:
        logger.exception('Unexpected error retrieving file metadata')
        return create_custom_error(500, str(exc))


async def _handle_download(file_id: str, backend: StorageBackend) -> Response:
    try:
        file_ref = await FileRef.find_by_id(file_id)
        if file_ref is None:
            return create_custom_error(404, f'FileRef {file_id!r} not found.')
        if not file_ref.storage_ref:
            return create_custom_error(404, f'File {file_id!r} has no storage reference.')

        stream, size = await backend.retrieve(file_ref.storage_ref)
        headers: dict[str, str] = {
            'Content-Disposition': f'attachment; filename="{file_ref.original_filename}"',
        }
        if size:
            headers['Content-Length'] = str(size)

        return StreamingResponse(
            stream,
            media_type=file_ref.content_type or 'application/octet-stream',
            headers=headers,
        )
    except FileStorageException as exc:
        return create_custom_error(exc.http_code, str(exc))
    except Exception as exc:
        logger.exception('Unexpected error during file download')
        return create_custom_error(500, str(exc))


async def _handle_delete(file_id: str, backend: StorageBackend) -> Response:
    try:
        file_ref = await FileRef.find_by_id(file_id)
        if file_ref is None:
            return create_custom_error(404, f'FileRef {file_id!r} not found.')

        if file_ref.storage_ref:
            await backend.delete(file_ref.storage_ref)
        await file_ref.delete()

        return JSONResponse(content={'deleted': file_id}, status_code=200)
    except FileStorageException as exc:
        return create_custom_error(exc.http_code, str(exc))
    except Exception as exc:
        logger.exception('Unexpected error during file deletion')
        return create_custom_error(500, str(exc))


# ---------------------------------------------------------------------------
# FileService
# ---------------------------------------------------------------------------

class FileService:
    """Registers file upload, download, metadata, and delete routes on a FastAPI app.

    Do not instantiate directly — use :meth:`AppKernelEngine.enable_file_storage`::

        kernel.enable_file_storage(
            backend=GridFSBackend(),
            validation_chain=chain,
            url_base='/uploads',
        )

    Args:
        backend:          :class:`StorageBackend` instance that handles
                          physical storage.
        validation_chain: Head of a :class:`FileValidator` chain.  Pass
                          ``None`` to skip validation entirely (not
                          recommended for production).
        chunk_size:       Read buffer size used when streaming UploadFile
                          objects.  Defaults to 64 KiB.
    """

    def __init__(
        self,
        backend: StorageBackend,
        validation_chain: Optional[FileValidator] = None,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> None:
        self.backend = backend
        self._chain = validation_chain
        self._chunk_size = chunk_size

    def register(
        self,
        app: Any,
        url_base: str = '/files',
        tags: Optional[list[str]] = None,
    ) -> None:
        """Register upload/download/metadata/delete routes on *app*.

        Called automatically by :meth:`AppKernelEngine.enable_file_storage`.
        The four endpoints registered are:

        =========  ============================  ==============================
        Method     Path                          Description
        =========  ============================  ==============================
        ``POST``   ``{url_base}/``               Upload (multipart/form-data)
        ``GET``    ``{url_base}/{file_id}``       Retrieve metadata JSON
        ``GET``    ``{url_base}/{file_id}/content`` Download file bytes
        ``DELETE`` ``{url_base}/{file_id}``       Delete file and metadata
        =========  ============================  ==============================

        Args:
            app:      FastAPI application instance.
            url_base: URL prefix for the four routes.
            tags:     OpenAPI tags applied to the registered routes.
        """
        base = '/' + url_base.strip('/')
        backend = self.backend
        chain = self._chain
        chunk_size = self._chunk_size
        route_tags = tags or ['files']

        @app.post(f'{base}/', include_in_schema=False, tags=route_tags)
        async def upload_file(request: Request) -> Response:
            """Upload a file via multipart/form-data (field name: ``file``)."""
            return await _handle_upload(request, backend, chain, chunk_size)

        # Register /content BEFORE /{file_id} so FastAPI matches the more-specific path first
        @app.get(f'{base}/{{file_id}}/content', include_in_schema=False, tags=route_tags)
        async def download_file(file_id: str) -> Response:
            """Stream file bytes as a binary download."""
            return await _handle_download(file_id, backend)

        @app.get(f'{base}/{{file_id}}', include_in_schema=False, tags=route_tags)
        async def get_file_metadata(file_id: str) -> Response:
            """Return the :class:`FileRef` metadata document as JSON."""
            return await _handle_get_metadata(file_id)

        @app.delete(f'{base}/{{file_id}}', include_in_schema=False, tags=route_tags)
        async def delete_file(file_id: str) -> Response:
            """Delete the file and its metadata record."""
            return await _handle_delete(file_id, backend)

        logger.info(
            'FileService registered: POST/GET/DELETE %s/ using %s backend',
            base,
            backend.name,
        )
