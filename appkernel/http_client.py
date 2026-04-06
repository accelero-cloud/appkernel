from __future__ import annotations

import json as _json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Coroutine

import httpx

from appkernel import Model, AppKernelException
from appkernel.core import MessageType
from appkernel.model import _get_custom_class


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
