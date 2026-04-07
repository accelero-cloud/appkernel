File Storage
============

* :ref:`Overview <fs-overview>`
* :ref:`Quick Start <fs-quick-start>`
* :ref:`Storage Backends <fs-backends>`
* :ref:`Validation Chain <fs-validation>`
* :ref:`FileRef Metadata Model <fs-fileref>`
* :ref:`REST Endpoints <fs-endpoints>`
* :ref:`Security <fs-security>`
* :ref:`Adding a Custom Backend <fs-custom-backend>`
* :ref:`Adding a Custom Validator <fs-custom-validator>`
* :ref:`Performance and Sizing Guidance <fs-performance>`
* :ref:`Tradeoffs Summary <fs-tradeoffs>`

.. _fs-overview:

Overview
--------

AppKernel provides pluggable, streaming file upload and download via the
``appkernel.file_storage`` module.  Three concerns are separated cleanly:

1. **Storage backend** — where bytes live (local filesystem or MongoDB GridFS,
   extensible to S3 / Azure Blob / GCS).
2. **Validation chain** — a *chain of responsibility* that inspects each upload
   before bytes reach the backend.  Built-in validators cover file size, MIME
   type, file extension, and magic-byte verification.
3. **FileRef model** — a MongoDB document that stores metadata (filename, MIME
   type, backend identifier, storage reference, size, owner) independently of
   the physical bytes.

.. _fs-quick-start:

Quick Start
-----------

Enable file storage after creating the engine::

    from appkernel import AppKernelEngine
    from appkernel.file_storage import (
        FilesystemBackend,
        SizeValidator, MimeTypeValidator, ExtensionValidator,
    )

    kernel = AppKernelEngine('my-app', cfg_dir='./config')

    # Build a validation chain (order matters — first added runs first)
    chain = SizeValidator(max_bytes=10 * 1024 * 1024)   # 10 MB hard limit
    chain.add_next(MimeTypeValidator(['image/jpeg', 'image/png', 'application/pdf']))
    chain.add_next(ExtensionValidator(['jpg', 'jpeg', 'png', 'pdf']))

    kernel.enable_file_storage(
        backend=FilesystemBackend('/var/uploads'),
        validation_chain=chain,
        url_base='/files',
    )
    kernel.run()

This registers four REST endpoints under ``/files/`` (see :ref:`fs-endpoints`).

Upload a file::

    curl -X POST http://localhost:5000/files/ \
         -F "file=@photo.jpg;type=image/jpeg"

Download it::

    curl http://localhost:5000/files/<id>/content --output photo.jpg

.. _fs-backends:

Storage Backends
----------------

FilesystemBackend
~~~~~~~~~~~~~~~~~

Stores files as UUID-named binary blobs in a local directory::

    from appkernel.file_storage import FilesystemBackend

    backend = FilesystemBackend(
        base_path='/var/uploads',  # created automatically if missing
        chunk_size=64 * 1024,      # read chunk size on download (64 KiB)
    )

**Path traversal protection** — storage references are validated as
``/^[0-9a-f\-]{36}$/`` (UUID format).  Any non-UUID reference raises
:class:`~appkernel.file_storage.FileStorageException` with HTTP 400.

**Concurrency warning** — file state is local to the process.  For
multi-instance deployments, mount a shared filesystem (NFS / AWS EFS) or
switch to :class:`~appkernel.file_storage.GridFSBackend`.

GridFSBackend
~~~~~~~~~~~~~

Stores files in MongoDB's GridFS::

    from appkernel.file_storage import GridFSBackend

    backend = GridFSBackend(
        bucket_name='fs',           # GridFS bucket (default: 'fs')
        chunk_size=255 * 1024,      # GridFS chunk size (default: 255 KiB)
    )

The database connection is read from ``config.mongo_database``, which is
set automatically by :class:`~appkernel.engine.AppKernelEngine` at startup.
No extra configuration is needed.

GridFS advantages:

* Replicated across all MongoDB replica-set members.
* Works transparently with multiple app instances.
* File metadata is queryable alongside application data.

GridFS limitations:

* ~20–30 % storage overhead versus raw disk.
* No efficient byte-range (seek) support — unsuitable for video seeking.
* Practical limit ~100 MB per file.

.. _fs-validation:

Validation Chain
----------------

Validators implement the *chain of responsibility* pattern.  Each validator
receives the upload stream, may inspect or wrap it, and passes the result to
the next link.  Raise
:class:`~appkernel.validators.ValidationException` to reject the upload with
HTTP 422.

Built-in Validators
~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Validator
     - When it runs
     - Description
   * - ``SizeValidator(max_bytes)``
     - During stream consumption
     - Wraps the stream to count bytes.  Raises if the running total exceeds
       *max_bytes*.  Sets ``context.actual_size`` when the stream is fully
       drained.  **Always add this first** to cap memory usage during
       buffering.
   * - ``MimeTypeValidator(allowed_types)``
     - Before storage starts
     - Checks ``context.content_type`` against the allowed list.  Rejects
       immediately if the declared MIME type is not permitted.
   * - ``ExtensionValidator(allowed_extensions)``
     - Before storage starts
     - Checks the filename extension in ``context.filename``.  Comparison
       is case-insensitive and leading dots are stripped.
   * - ``MagicByteValidator()``
     - On first chunk
     - Verifies that the file's leading bytes match the declared MIME type.
       Covers JPEG, PNG, GIF, PDF, ZIP.  Files with an unknown MIME type
       pass through without inspection.  Pair with ``MimeTypeValidator`` for
       defence in depth.
   * - ``VirusScanValidator(host, port)``
     - After full buffering
     - Buffers the upload and submits it to a running ``clamd`` daemon via
       ``pyclamd``.  Silently skipped if ``pyclamd`` is not installed or
       ``clamd`` is unreachable.  Install extras: ``pip install pyclamd``.

Building a Chain
~~~~~~~~~~~~~~~~

Use :meth:`~appkernel.file_storage.FileValidator.add_next` to extend the
chain.  Each call traverses to the tail and appends there, so you may call
it repeatedly on the head::

    from appkernel.file_storage import (
        SizeValidator, MimeTypeValidator, ExtensionValidator, MagicByteValidator,
    )

    chain = SizeValidator(max_bytes=5 * 1024 * 1024)
    chain.add_next(MimeTypeValidator(['image/jpeg', 'image/png']))
    chain.add_next(ExtensionValidator(['jpg', 'jpeg', 'png']))
    chain.add_next(MagicByteValidator())

Method chaining also works because :meth:`add_next` returns the newly added
validator::

    chain = SizeValidator(max_bytes=5 * 1024 * 1024)
    chain.add_next(MimeTypeValidator(['image/jpeg', 'image/png'])) \
         .add_next(ExtensionValidator(['jpg', 'jpeg', 'png'])) \
         .add_next(MagicByteValidator())

Both forms produce the identical chain:
``SizeValidator → MimeTypeValidator → ExtensionValidator → MagicByteValidator``.

Pass the head to ``enable_file_storage()``::

    kernel.enable_file_storage(backend=backend, validation_chain=chain)

ValidationContext
~~~~~~~~~~~~~~~~~

:class:`~appkernel.file_storage.ValidationContext` is a mutable dataclass
passed through the chain.  Validators may read and write it:

.. code-block:: python

    @dataclass
    class ValidationContext:
        filename: str          # client-supplied filename (path-stripped)
        content_type: str      # MIME type from multipart Content-Type header
        declared_size: int | None  # Content-Length from request
        actual_size: int       # set by SizeValidator after stream is drained

.. _fs-fileref:

FileRef Metadata Model
----------------------

Every upload creates a :class:`~appkernel.file_storage.FileRef` document in
MongoDB::

    {
        "_type":             "FileRef",
        "id":                "F3a1b2c3d-...",
        "original_filename": "photo.jpg",
        "storage_backend":   "filesystem",
        "storage_ref":       "a1b2c3d4-...",   # UUID (filesystem) or ObjectId (gridfs)
        "content_type":      "image/jpeg",
        "size":              204800,
        "owner_id":          null,
        "created_at":        "2026-04-07T12:00:00",
        "metadata":          null
    }

``owner_id`` and ``metadata`` are application-defined.  Set them before
calling ``save()`` in a custom upload handler if needed.

Because ``FileRef`` extends :class:`~appkernel.MongoRepository` it supports
the standard AppKernel query DSL::

    # Find all uploads owned by a user
    refs = await FileRef.find(FileRef.owner_id == user_id)

    # Delete all records for a backend
    await FileRef.delete(FileRef.storage_backend == 'gridfs')

.. _fs-endpoints:

REST Endpoints
--------------

All four endpoints are registered at the ``url_base`` prefix (default ``/files``).

.. list-table::
   :header-rows: 1
   :widths: 10 35 55

   * - Method
     - Path
     - Description
   * - ``POST``
     - ``/files/``
     - Upload a file.  Send as ``multipart/form-data`` with field name
       ``file``.  Returns HTTP 201 with the :class:`FileRef` JSON on
       success.  Returns HTTP 422 if validation fails, 415 if the request
       is not multipart, 400 if the ``file`` field is missing.
   * - ``GET``
     - ``/files/{file_id}``
     - Retrieve the :class:`FileRef` metadata document.  Returns HTTP 200
       or 404.
   * - ``GET``
     - ``/files/{file_id}/content``
     - Stream the file bytes.  Returns HTTP 200 with
       ``Content-Disposition: attachment`` and ``Content-Length`` headers.
       The response is a true streaming response — no buffering.
   * - ``DELETE``
     - ``/files/{file_id}``
     - Delete the file from the backend and remove the :class:`FileRef`
       document.  Returns HTTP 200 ``{"deleted": "<id>"}`` or 404.

Upload example (curl)::

    curl -X POST http://localhost:5000/files/ \
         -F "file=@report.pdf;type=application/pdf"

Upload example (Python httpx)::

    import httpx
    with open('report.pdf', 'rb') as f:
        rsp = httpx.post(
            'http://localhost:5000/files/',
            files={'file': ('report.pdf', f, 'application/pdf')},
        )
    file_id = rsp.json()['id']

Download example::

    curl http://localhost:5000/files/{file_id}/content --output report.pdf

.. _fs-security:

Security
--------

The file endpoints are **public by default**.  To require authentication,
call ``enable_security()`` before ``enable_file_storage()`` and configure
RBAC on the registered routes, or wrap the endpoints in a FastAPI dependency.

Built-in security measures (always active):

* **Path traversal prevention** — ``FilesystemBackend`` rejects any storage
  reference that is not a UUID.  Client-supplied filenames are stripped to the
  basename (``os.path.basename``) before storage.
* **MIME / extension validation** — use :class:`MimeTypeValidator` and
  :class:`ExtensionValidator` to restrict acceptable file types.
* **Magic-byte verification** — use :class:`MagicByteValidator` to verify
  that file content matches the declared MIME type (defends against
  polyglot files).
* **Size cap** — always add :class:`SizeValidator` as the first link to
  prevent memory exhaustion and denial-of-service via large uploads.

.. _fs-custom-backend:

Adding a Custom Backend
-----------------------

Subclass :class:`~appkernel.file_storage.StorageBackend` and implement the
five abstract methods::

    from appkernel.file_storage import StorageBackend, FileStorageException

    class S3Backend(StorageBackend):
        def __init__(self, bucket: str):
            import boto3
            self._s3 = boto3.client('s3')
            self._bucket = bucket

        @property
        def name(self) -> str:
            return 's3'

        async def store(self, stream, file_ref):
            import asyncio, uuid
            key = str(uuid.uuid4())
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._s3.put_object,
                dict(Bucket=self._bucket, Key=key, Body=b''.join(chunks))
            )
            return key

        async def retrieve(self, storage_ref):
            import asyncio
            loop = asyncio.get_event_loop()
            obj = await loop.run_in_executor(
                None,
                lambda: self._s3.get_object(Bucket=self._bucket, Key=storage_ref)
            )
            size = obj['ContentLength']
            body = obj['Body']

            async def _stream():
                while True:
                    chunk = await loop.run_in_executor(None, body.read, 65536)
                    if not chunk:
                        break
                    yield chunk

            return _stream(), size

        async def delete(self, storage_ref):
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._s3.delete_object(Bucket=self._bucket, Key=storage_ref)
            )

        async def exists(self, storage_ref):
            import asyncio, botocore
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._s3.head_object(Bucket=self._bucket, Key=storage_ref)
                )
                return True
            except botocore.exceptions.ClientError:
                return False

    kernel.enable_file_storage(backend=S3Backend('my-bucket'), validation_chain=chain)

.. _fs-custom-validator:

Adding a Custom Validator
-------------------------

Subclass :class:`~appkernel.file_storage.FileValidator` and implement
``_do_validate``::

    from appkernel.file_storage import FileValidator
    from appkernel.validators import ValidationException

    class ContentWordValidator(FileValidator):
        \"\"\"Reject text files that contain forbidden words.\"\"\"

        def __init__(self, forbidden: list[str]) -> None:
            super().__init__()
            self._forbidden = [w.lower() for w in forbidden]

        async def _do_validate(self, stream, context):
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            text = b''.join(chunks).decode('utf-8', errors='replace').lower()
            for word in self._forbidden:
                if word in text:
                    raise ValidationException(f'Content contains forbidden word: {word!r}')

            async def _replay():
                yield b''.join(chunks)

            return _replay()

    chain = SizeValidator(max_bytes=1_000_000)
    chain.add_next(ContentWordValidator(['malware', 'exploit']))

.. _fs-performance:

Performance and Sizing Guidance
--------------------------------

Upload memory usage
~~~~~~~~~~~~~~~~~~~

Both backends buffer the upload in memory before writing to the storage
layer.  The :class:`SizeValidator` is the primary memory guard — always
configure it to a value appropriate for your available heap:

============  ==================  ===========================================
Heap budget   max_bytes setting   Notes
============  ==================  ===========================================
< 512 MiB     ≤ 10 MiB            Development / low-traffic
512 MiB–2 GiB ≤ 50 MiB            General purpose
> 2 GiB       ≤ 200 MiB           Media or document upload services
============  ==================  ===========================================

For uploads beyond ~200 MiB, use a cloud object-store backend with
server-side multipart upload (S3 / GCS) so that bytes are never buffered in
the application process.

Download streaming
~~~~~~~~~~~~~~~~~~

Downloads are always streamed in chunks (default 64 KiB) — no file is
loaded fully into memory.  The ``Content-Length`` header is set from the
stored size, enabling clients to show progress bars.

GridFS chunk size
~~~~~~~~~~~~~~~~~

The default GridFS chunk size is 255 KiB (matching the MongoDB driver
default).  Increasing it (e.g. to 1 MiB) reduces the number of documents in
the ``chunks`` collection and can improve read throughput for large files,
at the cost of more memory per chunk.

.. _fs-tradeoffs:

Tradeoffs Summary
-----------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 15 30

   * - Property
     - FilesystemBackend
     - GridFSBackend
     - S3 / Object store
     - Notes
   * - Setup complexity
     - Low
     - Low
     - Medium
     - S3 requires IAM, bucket policy, presigned URL handling
   * - Multi-instance safe
     - No (w/o NFS)
     - Yes
     - Yes
     - Filesystem requires shared mount for HA
   * - Byte-range / seek
     - Yes
     - Poor
     - Yes
     - GridFS is block-oriented; seeking requires skipping chunks
   * - Max practical file size
     - Disk-bound
     - ~100 MB
     - Unlimited
     - GridFS metadata overhead grows with file size
   * - Cost
     - Cheap
     - MongoDB storage
     - Cheapest at scale
     - GridFS uses extra collections
   * - Auth integration
     - Manual
     - Via FileRef RBAC
     - Presigned URLs
     - AppKernel RBAC applies uniformly to all backends
