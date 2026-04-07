Transparent REST Client Proxies
================================

AppKernel provides a lightweight async HTTP client layer for inter-service
calls.  A single ``httpx.AsyncClient`` connection pool is created at startup
and reused for the lifetime of the process.

* :ref:`Overview <cl-overview>`
* :ref:`Basic usage <cl-basic>`
* :ref:`URL construction <cl-urls>`
* :ref:`Request methods <cl-methods>`
* :ref:`File upload and download <cl-files>`
* :ref:`Authentication <cl-auth>`
* :ref:`Response deserialization <cl-response>`
* :ref:`Error handling <cl-errors>`
* :ref:`Connection pool configuration <cl-pool>`
* :ref:`Circuit breaker <cl-circuit>`

.. _cl-overview:

Overview
--------

Three classes form the client layer:

* **HttpClientFactory** — entry point.  Call ``get(root_url)`` to obtain a
  proxy bound to an upstream service.
* **HttpClientServiceProxy** — per-upstream proxy.  Builds
  :class:`RequestWrapper` instances via attribute access or ``wrap()``.
* **RequestWrapper** — per-resource wrapper.  Exposes ``get``, ``post``,
  ``put``, ``patch``, and ``delete`` as async methods.

All HTTP I/O goes through a single ``httpx.AsyncClient`` singleton so
connections are pooled and reused across calls.

.. _cl-basic:

Basic usage
-----------

::

    from appkernel import HttpClientFactory

    payments = HttpClientFactory.get('http://payments.svc')

    # POST to http://payments.svc/authorisations/
    code, result = await payments.authorisations.post(payload)

    # GET http://payments.svc/refunds/12345
    code, result = await payments.wrap('/refunds/12345').get()

.. _cl-urls:

URL construction
----------------

There are two ways to get a :class:`RequestWrapper` from a proxy.

**Attribute access** appends the attribute name with a trailing slash::

    payments.authorisations
    # → RequestWrapper('http://payments.svc/authorisations/')

    payments.charges
    # → RequestWrapper('http://payments.svc/charges/')

**wrap()** gives explicit control over the path.  No trailing slash is added::

    payments.wrap('/refunds/12345')
    # → RequestWrapper('http://payments.svc/refunds/12345')

    payments.wrap('charges/')
    # → RequestWrapper('http://payments.svc/charges/')

**path_extension** on a method call appends a sub-path to the wrapper's URL
at call time::

    wrapper = payments.wrap('/refunds')
    code, result = await wrapper.get(path_extension='12345/items')
    # GET http://payments.svc/refunds/12345/items

Leading and trailing slashes are normalised — ``rstrip('/')`` on the base and
``lstrip('/')`` on the extension — so double slashes are never produced.

.. _cl-methods:

Request methods
---------------

All five HTTP methods are available on :class:`RequestWrapper`::

    code, result = await wrapper.get(path_extension=None, timeout=3)
    code, result = await wrapper.post(payload, path_extension=None, timeout=3)
    code, result = await wrapper.put(payload, path_extension=None, timeout=3)
    code, result = await wrapper.patch(payload, path_extension=None, timeout=3)
    code, result = await wrapper.delete(payload, path_extension=None, timeout=3)

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Parameter
     - Default
     - Description
   * - ``payload``
     - ``None``
     - Request body.  A :class:`~appkernel.Model` instance is serialised with
       ``dumps()``.  A ``dict`` is serialised with ``json.dumps()``.  Any
       other value is sent as-is (string / bytes).
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.  See :ref:`cl-urls`.
   * - ``timeout``
     - ``3``
     - Per-request timeout in seconds, overriding the pool-level read timeout.

All methods follow redirects automatically (``follow_redirects=True``).

.. _cl-files:

File upload and download
------------------------

Three dedicated methods handle binary file transfer.  They share the same
URL-construction rules and circuit-breaker integration as the standard HTTP
methods.

upload()
~~~~~~~~

Sends a file as ``multipart/form-data`` (field name ``file``) with a POST
request.  The response is deserialised using the same JSON logic as
:meth:`~RequestWrapper.post` — returning a :class:`~appkernel.Model`
instance if ``_type`` is present, or a plain ``dict`` otherwise::

    from appkernel import HttpClientFactory

    files_svc = HttpClientFactory.get('http://files.svc')

    with open('photo.jpg', 'rb') as fh:
        code, ref = await files_svc.wrap('/files/').upload(
            fh,
            filename='photo.jpg',
            content_type='image/jpeg',
        )
    # code = 201, ref = FileRef(id='F…', original_filename='photo.jpg', …)

    # Bytes are also accepted directly
    code, ref = await files_svc.wrap('/files/').upload(
        b'\xff\xd8\xff\xe0…',
        filename='photo.jpg',
        content_type='image/jpeg',
    )

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Parameter
     - Default
     - Description
   * - ``file``
     - *(required)*
     - File content.  Accepts ``bytes``, a binary file-like object, or a path
       string.
   * - ``filename``
     - ``'upload'``
     - Original filename sent in the multipart part header.
   * - ``content_type``
     - ``'application/octet-stream'``
     - MIME type of the file part.
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.  See :ref:`cl-urls`.
   * - ``timeout``
     - ``60``
     - Per-request timeout in seconds.  Higher default than regular requests
       to accommodate large uploads.

download()
~~~~~~~~~~

Fetches a file and returns its raw bytes::

    code, data = await files_svc.wrap('/files/F123/content').download()
    # code = 200, data = b'…raw bytes…'

    with open('photo.jpg', 'wb') as fh:
        fh.write(data)

The entire body is buffered in memory.  For large files use
:meth:`~RequestWrapper.stream_download` to avoid high memory usage.

.. list-table::
   :header-rows: 1
   :widths: 22 10 68

   * - Parameter
     - Default
     - Description
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.
   * - ``timeout``
     - ``30``
     - Per-request timeout in seconds.

Returns ``(status_code: int, body: bytes)``.

stream_download()
~~~~~~~~~~~~~~~~~

An async generator that yields the response body in chunks.  No full-file
buffer is held in memory, making it suitable for large files or when bytes
are piped directly to a :class:`~starlette.responses.StreamingResponse`::

    async for chunk in files_svc.wrap('/files/F123/content').stream_download(
        chunk_size=65536,
    ):
        await writer.write(chunk)

    # Pipe into a FastAPI StreamingResponse
    from starlette.responses import StreamingResponse

    return StreamingResponse(
        files_svc.wrap('/files/F123/content').stream_download(),
        media_type='application/octet-stream',
    )

.. list-table::
   :header-rows: 1
   :widths: 22 10 68

   * - Parameter
     - Default
     - Description
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.
   * - ``chunk_size``
     - ``65536``
     - Read buffer size in bytes (64 KiB).
   * - ``timeout``
     - ``30``
     - Per-request timeout in seconds.

Raises :class:`~appkernel.CircuitOpenError` immediately (before any network
call) when the circuit breaker is OPEN.  Raises
:class:`~appkernel.http_client.RequestHandlingException` on non-2xx
responses or network errors.

download_to()
~~~~~~~~~~~~~

Convenience wrapper around :meth:`stream_download` that saves the file
directly to the local filesystem without any intermediate buffer::

    # Save to an explicit file path
    path = await files_svc.wrap('/files/F123/content').download_to('/tmp/report.pdf')

    # Save to a directory — filename resolved from Content-Disposition
    path = await files_svc.wrap('/files/F123/content').download_to('/tmp/downloads/')
    # → '/tmp/downloads/report.pdf'  (or last URL segment as fallback)

The filename resolution rules when *dest* is a directory (or ends with
``os.sep``):

1. Use the ``filename=`` parameter from the ``Content-Disposition`` response
   header (handles both ``filename="foo"`` and ``filename*=UTF-8''foo``).
2. Fall back to the last non-empty path segment of the upstream URL.

.. list-table::
   :header-rows: 1
   :widths: 22 10 68

   * - Parameter
     - Default
     - Description
   * - ``dest``
     - *(required)*
     - Destination file path, or an existing directory.
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.
   * - ``chunk_size``
     - ``65536``
     - Read buffer size in bytes (64 KiB).
   * - ``timeout``
     - ``30``
     - Per-request timeout in seconds.

Returns the absolute path of the saved file.

upload_from()
~~~~~~~~~~~~~

Convenience wrapper around :meth:`upload` that reads a file from the local
filesystem.  The filename and MIME type are inferred from the path when not
provided explicitly::

    # Infer filename ('report.pdf') and content type ('application/pdf')
    code, ref = await files_svc.wrap('/files/').upload_from('/tmp/report.pdf')

    # Override both
    code, ref = await files_svc.wrap('/files/').upload_from(
        '/tmp/data.bin',
        filename='firmware-v2.bin',
        content_type='application/octet-stream',
    )

Inference rules:

* **filename** — ``os.path.basename(local_path)``
* **content_type** — :func:`mimetypes.guess_type`; falls back to
  ``'application/octet-stream'`` for unknown extensions

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Parameter
     - Default
     - Description
   * - ``local_path``
     - *(required)*
     - Path to the local file to upload.
   * - ``filename``
     - basename of ``local_path``
     - Override the filename sent in the multipart header.
   * - ``content_type``
     - guessed from extension
     - Override the MIME type sent in the multipart header.
   * - ``path_extension``
     - ``None``
     - Sub-path appended to the wrapper URL.
   * - ``timeout``
     - ``60``
     - Per-request timeout in seconds.

Returns ``(status_code, body)`` — same semantics as :meth:`upload`.
Raises :class:`OSError` if *local_path* cannot be opened.

.. _cl-auth:

Authentication
--------------

:meth:`RequestWrapper.get_headers` is a ``@staticmethod`` that builds a
headers dict with an optional ``Authorization`` value and an
``Accept-Language`` header::

    from appkernel.http_client import RequestWrapper

    headers = RequestWrapper.get_headers(
        auth_header='Bearer <token>',
        accept_language='en',
    )
    # {'Authorization': 'Bearer <token>', 'Accept-Language': 'en'}

.. note::

   The built-in ``get``, ``post``, ``put``, ``patch``, and ``delete`` methods
   call ``get_headers()`` internally without an ``auth_header``, so they send
   no ``Authorization`` header by default.  To inject per-request auth,
   subclass :class:`RequestWrapper` and override ``get_headers``::

       class AuthenticatedWrapper(RequestWrapper):
           def __init__(self, url, token, circuit=None):
               super().__init__(url, circuit)
               self._token = token

           def get_headers(self, auth_header=None, accept_language='en'):
               return {
                   'Authorization': f'Bearer {self._token}',
                   'Accept-Language': accept_language or 'en',
               }

   Alternatively, configure the shared ``httpx.AsyncClient`` with default
   auth headers by calling :func:`~appkernel.http_client.configure_http_client`
   with a pre-configured client before the engine starts.

.. _cl-response:

Response deserialization
------------------------

On a **2xx** response the body is parsed as follows:

1. If the body is valid JSON and contains a ``_type`` key that is **not**
   ``'OperationResult'`` or ``'ErrorMessage'``, AppKernel looks up the
   corresponding :class:`~appkernel.Model` subclass and reconstructs the
   object via :meth:`~appkernel.Model.from_dict`.  The ``_type`` key is
   removed from the dict before reconstruction.
2. If ``_type`` is ``'OperationResult'`` or ``'ErrorMessage'``, or if there
   is no ``_type`` key, the response is returned as a plain ``dict``.
3. If the body is **not** valid JSON, it is returned as
   ``{'result': response_text}``.

Both paths return a ``(status_code: int, body: Model | dict)`` tuple.

Example — reconstructed Model::

    code, user = await users.wrap('/users/U123').get()
    # code = 200, user = User(id='U123', name='Alice', ...)
    assert isinstance(user, User)

Example — plain dict (list response or OperationResult)::

    code, data = await users.users.get()
    # code = 200, data = {'_items': [...], '_links': {...}}

.. _cl-errors:

Error handling
--------------

Any **non-2xx** response or network exception raises
:class:`~appkernel.http_client.RequestHandlingException`.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Attribute
     - Description
   * - ``status_code``
     - HTTP status code from the upstream response (or ``500`` for network
       errors).
   * - ``message``
     - Error message.  If the upstream body is an AppKernel
       ``ErrorMessage`` JSON object the ``message`` field is extracted;
       otherwise a generic string is used.
   * - ``upstream_service``
     - Set to the ``upstream_service`` field from the upstream body, or
       falls back to the last path segment of the upstream URL.

::

    from appkernel.http_client import RequestHandlingException, CircuitOpenError

    try:
        code, result = await payments.authorisations.post(payload)
    except CircuitOpenError as exc:
        # Circuit is open — upstream unavailable
        logger.warning('Payments unavailable: %s', exc)
        return cached_result
    except RequestHandlingException as exc:
        logger.error('Upstream error %s: %s', exc.status_code, exc.message)
        raise

.. _cl-pool:

Connection pool configuration
------------------------------

Pass an :class:`~appkernel.HttpClientConfig` to
:class:`~appkernel.engine.AppKernelEngine` to control pool and timeout
behaviour::

    from appkernel import AppKernelEngine, HttpClientConfig

    kernel = AppKernelEngine(
        'my-app',
        http_client_config=HttpClientConfig(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
            connect_timeout=2.0,
            read_timeout=10.0,
            write_timeout=5.0,
            pool_timeout=5.0,
        )
    )

The client is initialised at startup and closed gracefully on shutdown via
FastAPI's lifespan.

.. list-table::
   :header-rows: 1
   :widths: 28 12 60

   * - Parameter
     - Default
     - Description
   * - ``max_connections``
     - ``100``
     - Total simultaneous connections (active + queued).  Requests queue once
       this limit is reached.
   * - ``max_keepalive_connections``
     - ``20``
     - Idle connections held open for reuse.  Set to steady-state concurrency.
   * - ``keepalive_expiry``
     - ``30.0``
     - Seconds before an idle connection is proactively closed.  Keep below
       the upstream server's keep-alive timeout (typically 30–75 s).
   * - ``connect_timeout``
     - ``2.0``
     - Max seconds to establish a TCP + TLS connection.
   * - ``read_timeout``
     - ``10.0``
     - Max seconds to wait for the first response byte after the request is
       sent.
   * - ``write_timeout``
     - ``5.0``
     - Max seconds to finish sending the request body.
   * - ``pool_timeout``
     - ``5.0``
     - Max seconds to wait for a connection slot when ``max_connections`` is
       exhausted.  Acts as backpressure — raise to queue, lower to fail fast.

Recommended pool profiles:

============  ==================  ============================
Traffic       max_connections     max_keepalive_connections
============  ==================  ============================
Low (< 20/s)  20                  5
Medium        100                 20 (default)
High (> 100/s) 200–500            50–100
============  ==================  ============================

.. _cl-circuit:

Circuit breaker
---------------

Without a circuit breaker, a slow downstream service holds connections open
until they time out, exhausting the pool and causing cascading failures.  The
circuit breaker detects repeated failures and short-circuits calls immediately,
returning HTTP 503 instead of queuing work against an unavailable service.

States
......

Each proxy maintains an independent circuit breaker with three states:

- **CLOSED** (normal) — requests flow through.  Consecutive 5xx and network
  errors are counted toward ``failure_threshold``.
- **OPEN** (tripped) — once ``failure_threshold`` consecutive failures are
  recorded, the circuit opens.  All further calls raise
  :class:`~appkernel.CircuitOpenError` (``status_code = 503``) immediately;
  no network connection is attempted.
- **HALF_OPEN** (probing) — after ``recovery_timeout`` seconds, up to
  ``half_open_max_calls`` probe requests are allowed through.  A successful
  probe closes the circuit; a failed probe re-opens it.

Only 5xx and network errors count.  4xx client errors do not trip the
circuit — they indicate a bad request, not an unhealthy upstream.

The circuit breaker state is **in-process** — each app instance maintains its
own state independently.

Enabling a global default
.........................

Set ``circuit_breaker`` on :class:`~appkernel.HttpClientConfig` to apply the
same breaker to every proxy created by :class:`~appkernel.HttpClientFactory`::

    from appkernel import AppKernelEngine, HttpClientConfig, CircuitBreakerConfig

    kernel = AppKernelEngine(
        'my-app',
        http_client_config=HttpClientConfig(
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5,    # trip after 5 consecutive failures
                recovery_timeout=30.0,  # probe after 30 s
                half_open_max_calls=1,  # one probe request at a time
            )
        )
    )

Per-proxy override
..................

Pass ``circuit_breaker`` to :meth:`HttpClientFactory.get` to override (or
disable) the global default for a specific upstream::

    from appkernel import HttpClientFactory, CircuitBreakerConfig

    # Stricter threshold for a critical payment service
    payments = HttpClientFactory.get(
        'http://payments.svc',
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=60.0),
    )

    # Disable the breaker entirely for an internal metrics endpoint
    metrics = HttpClientFactory.get('http://metrics.svc', circuit_breaker=None)

Passing ``circuit_breaker=None`` explicitly disables the breaker for that
proxy even when a global default is configured.

CircuitBreakerConfig reference
...............................

.. list-table::
   :header-rows: 1
   :widths: 28 12 60

   * - Parameter
     - Default
     - Description
   * - ``failure_threshold``
     - ``5``
     - Consecutive 5xx / network errors before the circuit opens.
   * - ``recovery_timeout``
     - ``30.0``
     - Seconds in OPEN state before moving to HALF_OPEN and allowing a probe.
   * - ``half_open_max_calls``
     - ``1``
     - Probe requests allowed concurrently in HALF_OPEN before the outcome is
       decided.

Sizing guidance:

- **Critical path** (auth, payments): lower ``failure_threshold`` (2–3) and
  longer ``recovery_timeout`` (60 s) — fail fast, give the upstream time to
  recover.
- **Background / non-critical calls**: higher ``failure_threshold`` (10+) and
  shorter ``recovery_timeout`` (10–15 s) — tolerate transient blips without
  opening the circuit.
