"""Tests for appkernel.file_storage.

Covers:
  - FilesystemBackend: store / retrieve / delete / exists
  - GridFSBackend: store / retrieve / delete / exists
  - Validation chain: SizeValidator, MimeTypeValidator, ExtensionValidator,
    MagicByteValidator
  - HTTP endpoints: upload, download, get-metadata, delete
  - Error paths: oversized upload, wrong MIME type, wrong extension, bad magic bytes

Requires MongoDB on localhost:27017.
"""
from __future__ import annotations

import io
import os
import tempfile
from typing import AsyncIterator

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.testclient import TestClient

from appkernel import AppKernelEngine
from appkernel.configuration import config
from appkernel.file_storage import (
    ExtensionValidator,
    FileRef,
    FileService,
    FileStorageException,
    FilesystemBackend,
    GridFSBackend,
    MagicByteValidator,
    MimeTypeValidator,
    SizeValidator,
    ValidationContext,
)
from tests.utils import run_async

# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------

kernel: AppKernelEngine | None = None
client: TestClient | None = None
_tmp_dir: str | None = None
_gridfs_backend: GridFSBackend | None = None


def setup_module(module):
    global kernel, client, _tmp_dir, _gridfs_backend
    _tmp_dir = tempfile.mkdtemp(prefix='appkernel_file_test_')

    kernel = AppKernelEngine('file-storage-test', development=True)

    _gridfs_backend = GridFSBackend(bucket_name='test_fs')

    chain = SizeValidator(max_bytes=512)  # tiny limit to test rejection
    chain.add_next(MimeTypeValidator(['text/plain', 'image/jpeg', 'image/png'])) \
         .add_next(ExtensionValidator(['txt', 'jpg', 'jpeg', 'png']))

    kernel.enable_file_storage(
        backend=FilesystemBackend(_tmp_dir),
        validation_chain=chain,
        url_base='/files',
    )
    client = TestClient(kernel.app, raise_server_exceptions=False)


def setup_function(function):
    run_async(FileRef.delete_all())


# ---------------------------------------------------------------------------
# Async stream helpers
# ---------------------------------------------------------------------------

async def _bytes_stream(data: bytes, chunk_size: int = 64) -> AsyncIterator[bytes]:
    for i in range(0, max(len(data), 1), chunk_size):
        yield data[i:i + chunk_size]


# ---------------------------------------------------------------------------
# FilesystemBackend unit tests
# ---------------------------------------------------------------------------

def test_filesystem_store_and_retrieve():
    tmp = tempfile.mkdtemp()
    backend = FilesystemBackend(tmp)
    content = b'Hello, filesystem backend!'

    async def _run():
        file_ref = FileRef(
            original_filename='hello.txt',
            content_type='text/plain',
            storage_backend='filesystem',
        )
        file_ref.finalise_and_validate()
        ref = await backend.store(_bytes_stream(content), file_ref)
        assert ref
        stream, size = await backend.retrieve(ref)
        chunks = [c async for c in stream]
        assert b''.join(chunks) == content
        assert size == len(content)

    run_async(_run())


def test_filesystem_delete():
    tmp = tempfile.mkdtemp()
    backend = FilesystemBackend(tmp)
    content = b'delete me'

    async def _run():
        file_ref = FileRef(
            original_filename='del.txt',
            content_type='text/plain',
            storage_backend='filesystem',
        )
        file_ref.finalise_and_validate()
        ref = await backend.store(_bytes_stream(content), file_ref)
        assert await backend.exists(ref)
        await backend.delete(ref)
        assert not await backend.exists(ref)

    run_async(_run())


def test_filesystem_retrieve_missing_raises():
    tmp = tempfile.mkdtemp()
    backend = FilesystemBackend(tmp)

    async def _run():
        with pytest.raises(FileStorageException) as exc_info:
            await backend.retrieve('00000000-0000-0000-0000-000000000000')
        assert exc_info.value.http_code == 404

    run_async(_run())


def test_filesystem_path_traversal_rejected():
    tmp = tempfile.mkdtemp()
    backend = FilesystemBackend(tmp)

    async def _run():
        with pytest.raises(FileStorageException) as exc_info:
            await backend.retrieve('../etc/passwd')
        assert exc_info.value.http_code == 400

    run_async(_run())


# ---------------------------------------------------------------------------
# GridFSBackend unit tests
# ---------------------------------------------------------------------------

def test_gridfs_store_and_retrieve():
    backend = GridFSBackend(bucket_name='test_fs_unit')
    content = b'GridFS content here'

    async def _run():
        file_ref = FileRef(
            original_filename='gridfs_test.txt',
            content_type='text/plain',
            storage_backend='gridfs',
        )
        file_ref.finalise_and_validate()
        ref = await backend.store(_bytes_stream(content), file_ref)
        assert ref

        stream, size = await backend.retrieve(ref)
        chunks = [c async for c in stream]
        assert b''.join(chunks) == content
        assert size == len(content)

    run_async(_run())


def test_gridfs_delete():
    backend = GridFSBackend(bucket_name='test_fs_delete')
    content = b'to be deleted from gridfs'

    async def _run():
        file_ref = FileRef(
            original_filename='del.txt',
            content_type='text/plain',
            storage_backend='gridfs',
        )
        file_ref.finalise_and_validate()
        ref = await backend.store(_bytes_stream(content), file_ref)
        assert await backend.exists(ref)
        await backend.delete(ref)
        assert not await backend.exists(ref)

    run_async(_run())


def test_gridfs_retrieve_missing_raises():
    backend = GridFSBackend(bucket_name='test_fs_missing')

    async def _run():
        with pytest.raises(FileStorageException) as exc_info:
            await backend.retrieve('507f1f77bcf86cd799439011')
        assert exc_info.value.http_code == 404

    run_async(_run())


# ---------------------------------------------------------------------------
# Validation chain unit tests
# ---------------------------------------------------------------------------

def test_size_validator_passes():
    validator = SizeValidator(max_bytes=100)

    async def _run():
        ctx = ValidationContext(filename='f.txt', content_type='text/plain')
        stream = await validator.validate(_bytes_stream(b'x' * 50), ctx)
        consumed = [c async for c in stream]
        assert b''.join(consumed) == b'x' * 50
        assert ctx.actual_size == 50

    run_async(_run())


def test_size_validator_rejects_oversized():
    from appkernel.validators import ValidationException
    validator = SizeValidator(max_bytes=10)

    async def _run():
        ctx = ValidationContext(filename='big.txt', content_type='text/plain')
        stream = await validator.validate(_bytes_stream(b'x' * 20), ctx)
        with pytest.raises(ValidationException):
            [c async for c in stream]

    run_async(_run())


def test_mime_type_validator_passes():
    validator = MimeTypeValidator(['text/plain'])

    async def _run():
        ctx = ValidationContext(filename='f.txt', content_type='text/plain')
        stream = await validator.validate(_bytes_stream(b'hello'), ctx)
        assert b''.join([c async for c in stream]) == b'hello'

    run_async(_run())


def test_mime_type_validator_rejects():
    from appkernel.validators import ValidationException
    validator = MimeTypeValidator(['text/plain'])

    async def _run():
        ctx = ValidationContext(filename='f.exe', content_type='application/octet-stream')
        with pytest.raises(ValidationException):
            await validator.validate(_bytes_stream(b'MZ'), ctx)

    run_async(_run())


def test_extension_validator_passes():
    validator = ExtensionValidator(['txt', 'csv'])

    async def _run():
        ctx = ValidationContext(filename='data.txt', content_type='text/plain')
        stream = await validator.validate(_bytes_stream(b'data'), ctx)
        assert b''.join([c async for c in stream]) == b'data'

    run_async(_run())


def test_extension_validator_rejects():
    from appkernel.validators import ValidationException
    validator = ExtensionValidator(['txt'])

    async def _run():
        ctx = ValidationContext(filename='evil.exe', content_type='text/plain')
        with pytest.raises(ValidationException):
            await validator.validate(_bytes_stream(b'data'), ctx)

    run_async(_run())


def test_magic_byte_validator_passes_known_type():
    validator = MagicByteValidator()
    png_magic = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100

    async def _run():
        ctx = ValidationContext(filename='img.png', content_type='image/png')
        stream = await validator.validate(_bytes_stream(png_magic), ctx)
        result = b''.join([c async for c in stream])
        assert result == png_magic

    run_async(_run())


def test_magic_byte_validator_rejects_mismatch():
    from appkernel.validators import ValidationException
    validator = MagicByteValidator()

    async def _run():
        ctx = ValidationContext(filename='not_a_png.png', content_type='image/png')
        # EXE magic bytes, not PNG
        stream = await validator.validate(_bytes_stream(b'MZ\x00\x00\x00'), ctx)
        with pytest.raises(ValidationException):
            [c async for c in stream]

    run_async(_run())


def test_magic_byte_validator_passes_unknown_type():
    """Files with unknown MIME types should pass through without inspection."""
    validator = MagicByteValidator()

    async def _run():
        ctx = ValidationContext(filename='file.xyz', content_type='application/x-custom')
        stream = await validator.validate(_bytes_stream(b'any bytes'), ctx)
        result = b''.join([c async for c in stream])
        assert result == b'any bytes'

    run_async(_run())


def test_validation_chain_order():
    """Full chain: size → mime → extension."""
    from appkernel.validators import ValidationException

    chain = SizeValidator(max_bytes=200)
    chain.add_next(MimeTypeValidator(['text/plain'])).add_next(ExtensionValidator(['txt']))

    async def _run():
        # valid upload
        ctx = ValidationContext(filename='ok.txt', content_type='text/plain')
        stream = await chain.validate(_bytes_stream(b'valid content'), ctx)
        assert b''.join([c async for c in stream]) == b'valid content'

        # rejected by extension
        ctx2 = ValidationContext(filename='bad.exe', content_type='text/plain')
        with pytest.raises(ValidationException):
            await chain.validate(_bytes_stream(b'data'), ctx2)

        # rejected by mime type
        ctx3 = ValidationContext(filename='ok.txt', content_type='application/octet-stream')
        with pytest.raises(ValidationException):
            await chain.validate(_bytes_stream(b'data'), ctx3)

    run_async(_run())


# ---------------------------------------------------------------------------
# HTTP endpoint tests (FilesystemBackend, 512-byte limit)
# ---------------------------------------------------------------------------

def _upload(filename: str, content: bytes, content_type: str = 'text/plain'):
    return client.post(
        '/files/',
        files={'file': (filename, io.BytesIO(content), content_type)},
    )


def test_upload_returns_201_and_file_ref():
    rsp = _upload('hello.txt', b'Hello, world!')
    assert rsp.status_code == 201
    data = rsp.json()
    assert 'FileRef' in data['_type']
    assert data['original_filename'] == 'hello.txt'
    assert data['content_type'] == 'text/plain'
    assert data['size'] == len(b'Hello, world!')
    assert data['storage_backend'] == 'filesystem'
    assert data['id']
    assert data['storage_ref']
    assert data['created_at']


def test_upload_rejects_oversized_file():
    big = b'x' * 600  # exceeds 512-byte limit
    rsp = _upload('big.txt', big)
    assert rsp.status_code == 422


def test_upload_rejects_wrong_mime_type():
    rsp = _upload('data.txt', b'hello', content_type='application/octet-stream')
    assert rsp.status_code == 422


def test_upload_rejects_wrong_extension():
    rsp = _upload('script.exe', b'hello', content_type='text/plain')
    assert rsp.status_code == 422


def test_upload_missing_file_field():
    # Send multipart but with a different field name (not 'file')
    rsp = client.post('/files/', files={'other': ('other.txt', io.BytesIO(b'data'), 'text/plain')})
    assert rsp.status_code == 400


def test_upload_non_multipart_request():
    rsp = client.post('/files/', content=b'raw bytes', headers={'content-type': 'application/octet-stream'})
    assert rsp.status_code == 415


def test_get_metadata_after_upload():
    upload_rsp = _upload('meta.txt', b'metadata test')
    assert upload_rsp.status_code == 201
    file_id = upload_rsp.json()['id']

    rsp = client.get(f'/files/{file_id}')
    assert rsp.status_code == 200
    data = rsp.json()
    assert data['id'] == file_id
    assert data['original_filename'] == 'meta.txt'


def test_get_metadata_not_found():
    rsp = client.get('/files/F00000000-nonexistent')
    assert rsp.status_code == 404


def test_download_after_upload():
    content = b'download me please'
    upload_rsp = _upload('download.txt', content)
    assert upload_rsp.status_code == 201
    file_id = upload_rsp.json()['id']

    rsp = client.get(f'/files/{file_id}/content')
    assert rsp.status_code == 200
    assert rsp.content == content
    assert 'download.txt' in rsp.headers.get('content-disposition', '')


def test_download_not_found():
    rsp = client.get('/files/F00000000-missing/content')
    assert rsp.status_code == 404


def test_delete_after_upload():
    upload_rsp = _upload('todelete.txt', b'bye')
    assert upload_rsp.status_code == 201
    file_id = upload_rsp.json()['id']

    del_rsp = client.delete(f'/files/{file_id}')
    assert del_rsp.status_code == 200
    assert del_rsp.json()['deleted'] == file_id

    # Verify gone from metadata store
    meta_rsp = client.get(f'/files/{file_id}')
    assert meta_rsp.status_code == 404


def test_delete_not_found():
    rsp = client.delete('/files/F00000000-missing')
    assert rsp.status_code == 404


def test_upload_path_traversal_in_filename_is_sanitised():
    """Filenames with path separators must be stripped to just the basename."""
    rsp = _upload('../../../safe/file.txt', b'safe content')
    assert rsp.status_code == 201
    data = rsp.json()
    # Path separators and traversal segments must be stripped
    assert '/' not in data['original_filename']
    assert '..' not in data['original_filename']
    assert data['original_filename'] == 'file.txt'


def test_file_ref_metadata_persists_in_mongo():
    """FileRef records must survive a round-trip through MongoDB."""
    rsp = _upload('persist.txt', b'persisted data')
    assert rsp.status_code == 201
    file_id = rsp.json()['id']

    async def _check():
        ref = await FileRef.find_by_id(file_id)
        assert ref is not None
        assert ref.original_filename == 'persist.txt'
        assert ref.size == len(b'persisted data')

    run_async(_check())
