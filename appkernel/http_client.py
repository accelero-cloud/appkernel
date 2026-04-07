from __future__ import annotations

import json as _json
import mimetypes
import os
import re
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Coroutine

import httpx

from appkernel import Model, AppKernelException
from appkernel.core import MessageType
from appkernel.model import _get_custom_class


# Matches both  filename="foo.pdf"  and  filename*=UTF-8''foo.pdf
_CD_FILENAME_RE = re.compile(
    r"filename\*?=(?:UTF-8'')?[\"']?([^\"';\r\n]+)",
    re.IGNORECASE,
)


def _filename_from_headers(headers: Any, fallback_url: str) -> str:
    """Extract a filename from a Content-Disposition header.

    Falls back to the last non-empty path segment of *fallback_url* when the
    header is absent or carries no ``filename=`` parameter.
    """
    cd = headers.get('content-disposition', '')
    if cd:
        m = _CD_FILENAME_RE.search(cd)
        if m:
            return m.group(1).strip().strip('"\'')
    # Derive from URL last segment
    segment = fallback_url.rstrip('/').rsplit('/', 1)[-1]
    return segment or 'download'


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreakerConfig:
    """Configuration for the per-upstream circuit breaker.

    The circuit breaker protects against cascading failures when a downstream
    service becomes slow or unavailable. It tracks consecutive 5xx / network
    errors per upstream and short-circuits calls once the failure threshold is
    reached, returning HTTP 503 immediately rather than exhausting the
    connection pool.

    States:
    - CLOSED (normal): requests flow through; failures are counted.
    - OPEN (tripped): requests fail immediately with CircuitOpenError (503);
      no network call is made.
    - HALF_OPEN (probing): after ``recovery_timeout`` seconds, one probe
      request is let through. On success the circuit closes; on failure it
      re-opens.

    Only 5xx and network errors count as failures. 4xx client errors do not
    trip the circuit — they are the caller's fault, not the upstream's.

    Default profile: trip after 5 consecutive failures, probe after 30 s.
    """
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1


class CircuitState(Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitOpenError(AppKernelException):
    """Raised when a call is rejected because the circuit breaker is OPEN."""

    def __init__(self, upstream: str) -> None:
        super().__init__(
            f"Circuit breaker OPEN for '{upstream}' — upstream is unavailable. "
            "Retry after the recovery timeout."
        )
        self.status_code: int = 503
        self.upstream_service: str = upstream


class CircuitBreaker:
    """Thread-safe three-state circuit breaker for a single upstream service.

    Uses a ``threading.Lock`` so it is safe both in asyncio tasks (GIL) and
    in threaded environments without event-loop binding issues.
    """

    def __init__(self, cfg: CircuitBreakerConfig, name: str = 'upstream') -> None:
        self._cfg = cfg
        self._name = name
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._half_open_calls: int = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def _should_allow(self) -> bool:
        """Return True if the next request should proceed; False for fast-fail."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self._cfg.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    return True  # first probe
                return False
            # HALF_OPEN: allow only up to half_open_max_calls concurrent probes
            if self._half_open_calls < self._cfg.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if (self._state == CircuitState.HALF_OPEN
                    or self._failure_count >= self._cfg.failure_threshold):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._failure_count = 0

    async def call(self, coro: Coroutine) -> Any:
        """Execute *coro*, recording success/failure and enforcing the open state."""
        if not self._should_allow():
            raise CircuitOpenError(self._name)
        try:
            result = await coro
            self.record_success()
            return result
        except RequestHandlingException as exc:
            # Only count server-side / network failures, not client errors.
            if exc.status_code >= 500:
                self.record_failure()
            raise


# ---------------------------------------------------------------------------
# Connection pool and timeout configuration
# ---------------------------------------------------------------------------

@dataclass
class HttpClientConfig:
    """Connection pool, timeout, and circuit-breaker configuration for
    inter-service HTTP calls.

    Pool sizing guidance:
    - max_connections: total simultaneous connections (active + queued). Set to
      your expected peak concurrency; requests queue once this is reached.
    - max_keepalive_connections: idle connections held open for reuse. Set to
      steady-state concurrency — excess idle connections waste file descriptors
      on both client and upstream server.
    - keepalive_expiry: seconds before an idle connection is proactively closed.
      Keep below the upstream server's own keep-alive timeout (typically 30–75s)
      to avoid reusing a connection the server has already closed.

    Timeout guidance:
    - connect_timeout: max seconds to establish a TCP+TLS connection.
    - read_timeout: max seconds to wait for the first response byte after sending.
    - write_timeout: max seconds to finish sending the request body.
    - pool_timeout: max seconds to wait for a connection slot in the pool when
      max_connections is exhausted. Acts as backpressure — raise it to queue
      requests, lower it to fail fast.

    Circuit breaker:
    - circuit_breaker: set a CircuitBreakerConfig to enable a circuit breaker
      for all proxies created via HttpClientFactory. Individual proxies may
      override this. Defaults to None (disabled).

    Default profile: medium-traffic (20–100 req/s to each upstream service).
    """
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    connect_timeout: float = 2.0
    read_timeout: float = 10.0
    write_timeout: float = 5.0
    pool_timeout: float = 5.0
    circuit_breaker: CircuitBreakerConfig | None = None


# ---------------------------------------------------------------------------
# Module-level singleton — one AsyncClient shared for the process lifetime.
# Initialised on first use with default config or explicitly by AppKernelEngine.
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None
_default_circuit_config: CircuitBreakerConfig | None = None

# Sentinel: distinguishes "not provided" from explicit None (disabled).
_SENTINEL = object()


def configure_http_client(cfg: HttpClientConfig | None = None) -> None:
    """Initialise (or replace) the shared AsyncClient with the given config.
    Called by AppKernelEngine at startup; falls back to HttpClientConfig defaults
    on first use if never called explicitly.
    """
    global _http_client, _default_circuit_config
    c = cfg or HttpClientConfig()
    _default_circuit_config = c.circuit_breaker
    _http_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=c.max_connections,
            max_keepalive_connections=c.max_keepalive_connections,
            keepalive_expiry=c.keepalive_expiry,
        ),
        timeout=httpx.Timeout(
            connect=c.connect_timeout,
            read=c.read_timeout,
            write=c.write_timeout,
            pool=c.pool_timeout,
        ),
    )


def _reset_default_circuit_config() -> None:
    """Reset the global circuit-breaker default. Used in tests."""
    global _default_circuit_config
    _default_circuit_config = None


async def close_http_client() -> None:
    """Gracefully close the shared AsyncClient. Called by AppKernelEngine on shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, initialising with defaults on first use."""
    global _http_client
    if _http_client is None:
        configure_http_client()
    return _http_client


class RequestHandlingException(AppKernelException):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code: int = status_code
        self.upstream_service: str | None = None


class RequestWrapper:

    # todo: retry, request timing,
    # todo: post to unknown url brings to infinite time...
    def __init__(self, url: str, circuit: CircuitBreaker | None = None) -> None:
        self.url = url
        self._circuit = circuit

    @staticmethod
    def get_headers(auth_header: str | None = None, accept_language: str | None = 'en') -> dict[str, str]:
        """
        Build request headers.
        :param auth_header: Optional Authorization header value
        :param accept_language: Accept-Language value, defaults to 'en'
        :return: headers dict
        """
        headers: dict[str, str] = {}
        if auth_header:
            headers['Authorization'] = auth_header
        headers['Accept-Language'] = accept_language or 'en'
        return headers

    async def __do_request(self, method: str, **kwargs: Any) -> tuple[int, Any]:
        try:
            path_ext = kwargs.pop('path_extension')
            if path_ext:
                endpoint_url = f'{self.url.rstrip("/")}/{path_ext.lstrip("/")}'
            else:
                endpoint_url = self.url
            response = await _get_client().request(method, endpoint_url, **kwargs)
            if 200 <= response.status_code <= 299:
                try:
                    response_object = response.json()
                except ValueError:
                    response_object = {'result': response.text}
                if '_type' in response_object and response_object.get('_type') not in ['OperationResult',
                                                                                       'ErrorMessage']:
                    type_class = _get_custom_class(response_object.pop('_type'))
                    return response.status_code, Model.from_dict(response_object, type_class)
                else:
                    return response.status_code, response_object
        except Exception as exc:
            raise RequestHandlingException(500, str(exc))
        else:
            content = response.json()
            if '_type' in content and content.get('_type') == MessageType.ErrorMessage.name:
                msg = content.get('message')
                upstream = content.get('upstream_service', self.url.rstrip('/').split('/').pop())
                exc = RequestHandlingException(response.status_code, msg)
                exc.upstream_service = upstream
                raise exc
            else:
                raise RequestHandlingException(response.status_code, 'Error while calling service.')

    async def __execute(self, method: str, **kwargs: Any) -> tuple[int, Any]:
        coro = self.__do_request(method, **kwargs)
        if self._circuit:
            return await self._circuit.call(coro)
        return await coro

    @staticmethod
    def _serialize(payload: Any) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, Model):
            return payload.dumps()
        if isinstance(payload, dict):
            return _json.dumps(payload)
        return payload

    async def post(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('POST',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def get(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('GET',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def put(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('PUT',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def patch(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('PATCH',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def delete(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('DELETE',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    # ------------------------------------------------------------------
    # File upload / download helpers
    # ------------------------------------------------------------------

    def _build_url(self, path_extension: str | None) -> str:
        if path_extension:
            return f'{self.url.rstrip("/")}/{path_extension.lstrip("/")}'
        return self.url

    async def __do_binary_request(self, path_extension: str | None, **kwargs: Any) -> tuple[int, bytes]:
        try:
            response = await _get_client().request('GET', self._build_url(path_extension), **kwargs)
            if 200 <= response.status_code <= 299:
                return response.status_code, response.content
        except Exception as exc:
            raise RequestHandlingException(500, str(exc))
        else:
            try:
                content = response.json()
            except Exception:
                content = {}
            if '_type' in content and content.get('_type') == MessageType.ErrorMessage.name:
                msg = content.get('message')
                upstream = content.get('upstream_service', self.url.rstrip('/').split('/').pop())
                err = RequestHandlingException(response.status_code, msg)
                err.upstream_service = upstream
                raise err
            raise RequestHandlingException(response.status_code, 'Error while downloading from service.')

    async def __execute_binary(self, path_extension: str | None, **kwargs: Any) -> tuple[int, bytes]:
        coro = self.__do_binary_request(path_extension, **kwargs)
        if self._circuit:
            return await self._circuit.call(coro)
        return await coro

    async def upload(
        self,
        file: Any,
        filename: str | None = None,
        content_type: str = 'application/octet-stream',
        path_extension: str | None = None,
        timeout: int = 60,
    ) -> tuple[int, Any]:
        """Upload a file to the upstream service as ``multipart/form-data``.

        :param file: File content — ``bytes``, a file-like object opened in
            binary mode, or a path string.
        :param filename: Original filename sent in the multipart part header.
            Defaults to ``'upload'`` when omitted.
        :param content_type: MIME type of the file part.  Defaults to
            ``'application/octet-stream'``.
        :param path_extension: Optional sub-path appended to the wrapper URL.
        :param timeout: Per-request timeout in seconds.  Uploads can be large,
            so the default (60 s) is higher than for regular requests.
        :returns: ``(status_code, body)`` — same semantics as :meth:`post`.
        :raises RequestHandlingException: On non-2xx responses or network errors.
        """
        files = {'file': (filename or 'upload', file, content_type)}
        return await self.__execute('POST',
                                    path_extension=path_extension,
                                    files=files,
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def download(
        self,
        path_extension: str | None = None,
        timeout: int = 30,
    ) -> tuple[int, bytes]:
        """Download a file from the upstream service and return its raw bytes.

        The entire response body is buffered in memory.  For large files use
        :meth:`stream_download` instead to avoid high memory usage.

        :param path_extension: Optional sub-path appended to the wrapper URL.
        :param timeout: Per-request timeout in seconds.
        :returns: ``(status_code, bytes)`` tuple.
        :raises RequestHandlingException: On non-2xx responses or network errors.
        """
        return await self.__execute_binary(
            path_extension,
            headers=self.get_headers(),
            timeout=timeout,
            follow_redirects=True,
        )

    async def stream_download(
        self,
        path_extension: str | None = None,
        chunk_size: int = 65536,
        timeout: int = 30,
    ) -> AsyncIterator[bytes]:
        """Stream a file download from the upstream service chunk by chunk.

        Unlike :meth:`download`, no full-file buffer is held in memory — bytes
        are yielded as they arrive from the network.  Suitable for large files
        or when the caller writes chunks directly to disk or a streaming
        response.

        :param path_extension: Optional sub-path appended to the wrapper URL.
        :param chunk_size: Read buffer size in bytes (default 64 KiB).
        :param timeout: Per-request timeout in seconds.
        :returns: Async generator of ``bytes`` chunks.
        :raises CircuitOpenError: If the circuit breaker is OPEN before the
            request is sent.
        :raises RequestHandlingException: On non-2xx responses or network errors.
        """
        endpoint_url = self._build_url(path_extension)

        if self._circuit and not self._circuit._should_allow():
            raise CircuitOpenError(self._circuit._name)

        try:
            async with _get_client().stream(
                'GET',
                endpoint_url,
                headers=self.get_headers(),
                timeout=timeout,
                follow_redirects=True,
            ) as response:
                if not (200 <= response.status_code <= 299):
                    if self._circuit and response.status_code >= 500:
                        self._circuit.record_failure()
                    raise RequestHandlingException(
                        response.status_code,
                        f'Upstream returned {response.status_code}',
                    )
                if self._circuit:
                    self._circuit.record_success()
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk
        except RequestHandlingException:
            raise
        except Exception as exc:
            if self._circuit:
                self._circuit.record_failure()
            raise RequestHandlingException(500, str(exc))

    async def download_to(
        self,
        dest: str,
        path_extension: str | None = None,
        chunk_size: int = 65536,
        timeout: int = 30,
    ) -> str:
        """Stream a file download and save it to the local filesystem.

        The save path is resolved as follows:

        * If *dest* is an existing directory (or ends with ``os.sep``), the
          filename is taken from the ``Content-Disposition`` response header.
          When the header is absent, the last path segment of the upstream URL
          is used instead.
        * Otherwise *dest* is treated as the full target file path.

        :param dest: Destination file path or an existing directory.
        :param path_extension: Optional sub-path appended to the wrapper URL.
        :param chunk_size: Read buffer size in bytes (default 64 KiB).
        :param timeout: Per-request timeout in seconds.
        :returns: Absolute path of the saved file.
        :raises CircuitOpenError: If the circuit breaker is OPEN.
        :raises RequestHandlingException: On non-2xx responses or network errors.
        """
        endpoint_url = self._build_url(path_extension)

        if self._circuit and not self._circuit._should_allow():
            raise CircuitOpenError(self._circuit._name)

        try:
            async with _get_client().stream(
                'GET',
                endpoint_url,
                headers=self.get_headers(),
                timeout=timeout,
                follow_redirects=True,
            ) as response:
                if not (200 <= response.status_code <= 299):
                    if self._circuit and response.status_code >= 500:
                        self._circuit.record_failure()
                    raise RequestHandlingException(
                        response.status_code,
                        f'Upstream returned {response.status_code}',
                    )
                if self._circuit:
                    self._circuit.record_success()

                if os.path.isdir(dest) or dest.endswith(os.sep):
                    filename = _filename_from_headers(response.headers, endpoint_url)
                    save_path = os.path.join(dest, filename)
                else:
                    save_path = dest

                with open(save_path, 'wb') as fh:
                    async for chunk in response.aiter_bytes(chunk_size):
                        fh.write(chunk)

                return os.path.abspath(save_path)
        except RequestHandlingException:
            raise
        except Exception as exc:
            if self._circuit:
                self._circuit.record_failure()
            raise RequestHandlingException(500, str(exc))

    async def upload_from(
        self,
        local_path: str,
        filename: str | None = None,
        content_type: str | None = None,
        path_extension: str | None = None,
        timeout: int = 60,
    ) -> tuple[int, Any]:
        """Upload a local file to the upstream service.

        The filename and MIME type are inferred from *local_path* when not
        supplied explicitly:

        * ``filename`` defaults to ``os.path.basename(local_path)``.
        * ``content_type`` is guessed via :func:`mimetypes.guess_type`;
          falls back to ``'application/octet-stream'`` for unknown extensions.

        :param local_path: Path to the file to upload.
        :param filename: Override the filename sent in the multipart header.
        :param content_type: Override the MIME type sent in the multipart
            header.
        :param path_extension: Optional sub-path appended to the wrapper URL.
        :param timeout: Per-request timeout in seconds.
        :returns: ``(status_code, body)`` — same semantics as :meth:`upload`.
        :raises RequestHandlingException: On non-2xx responses or network errors.
        :raises OSError: If *local_path* cannot be opened.
        """
        resolved_filename = filename or os.path.basename(local_path)
        if content_type is None:
            guessed, _ = mimetypes.guess_type(local_path)
            content_type = guessed or 'application/octet-stream'
        with open(local_path, 'rb') as fh:
            return await self.upload(
                fh,
                filename=resolved_filename,
                content_type=content_type,
                path_extension=path_extension,
                timeout=timeout,
            )


class HttpClientServiceProxy:

    def __init__(self, root_url: str, circuit_breaker: CircuitBreakerConfig | None | object = _SENTINEL) -> None:
        self.root_url = root_url.rstrip('/')
        if circuit_breaker is _SENTINEL:
            cb_cfg = _default_circuit_config   # inherit global default (may be None)
        else:
            cb_cfg = circuit_breaker           # explicit value, including None (disabled)
        self._circuit: CircuitBreaker | None = (
            CircuitBreaker(cb_cfg, name=self.root_url) if cb_cfg else None
        )

    def wrap(self, resource_path: str) -> RequestWrapper:
        return RequestWrapper(f'{self.root_url}/{resource_path.lstrip("/")}', circuit=self._circuit)

    def __getattr__(self, item: str) -> RequestWrapper:
        if isinstance(item, str):
            return RequestWrapper(f'{self.root_url}/{item}/', circuit=self._circuit)


class HttpClientFactory:

    @staticmethod
    def get(
        root_url: str,
        circuit_breaker: CircuitBreakerConfig | None | object = _SENTINEL,
    ) -> HttpClientServiceProxy:
        return HttpClientServiceProxy(root_url=root_url, circuit_breaker=circuit_breaker)
