from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from appkernel.util import create_custom_error


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for AppKernel's inbound request throttle.

    AppKernel uses a fixed-window counter per client IP and endpoint. All state
    is held in-process — this is intentional for zero-dependency simplicity but
    means limits are not shared across multiple instances. For multi-instance
    deployments, replace the limiter with a Redis-backed implementation and pass
    it to ``enable_rate_limiting()``.

    Args:
        requests_per_window: Maximum requests a single client IP may make within
            ``window_seconds``. Applies globally unless overridden by
            ``endpoint_limits``. Default: 100 (medium-traffic profile).
        window_seconds: Duration of each counting window in seconds. After the
            window expires the counter resets. Default: 60.
        endpoint_limits: Per-path-prefix overrides. Keys are URL prefixes (e.g.
            ``'/auth'``); values replace the global limit for any request whose
            path starts with that prefix. First matching prefix wins. Use this
            to tighten limits on authentication endpoints::

                endpoint_limits={'/auth': 10, '/admin': 20}

        exclude_paths: Paths that bypass rate limiting entirely (health checks,
            metrics, etc.). Exact prefix match. Default: empty list.
        trust_proxy_headers: When ``True``, the client IP is taken from the
            first address in the ``X-Forwarded-For`` header rather than the TCP
            peer address. Enable only when AppKernel sits behind a trusted
            reverse proxy — an untrusted caller can forge this header and bypass
            per-IP limits. Default: ``False``.

    Traffic profiles:

    ============  ======================  ==========================
    Profile       requests_per_window     notes
    ============  ======================  ==========================
    Low           20                      strict / auth-only surface
    Medium        100                     default
    High          500                     internal / trusted callers
    ============  ======================  ==========================
    """
    requests_per_window: int = 100
    window_seconds: int = 60
    endpoint_limits: dict[str, int] = field(default_factory=dict)
    exclude_paths: list[str] = field(default_factory=list)
    trust_proxy_headers: bool = False


class RateLimiter:
    """Fixed-window, in-process rate limiter.

    State is a plain dict keyed by ``"{client_ip}:{path_prefix}"`` containing
    ``(hit_count, window_start_monotonic)``. The dict is accessed only between
    ``await`` points so no explicit lock is needed under CPython's GIL.
    Expired entries are evicted lazily on access.
    """

    def __init__(self, cfg: RateLimitConfig) -> None:
        self._cfg = cfg
        # {key: [count, window_start]}  — list for in-place mutation
        self._counters: dict[str, list[Any]] = {}

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self._cfg.endpoint_limits.items():
            if path.startswith(prefix):
                return limit
        return self._cfg.requests_per_window

    @staticmethod
    def _client_ip(request: Request, trust_proxy: bool) -> str:
        if trust_proxy:
            forwarded = request.headers.get('X-Forwarded-For', '')
            if forwarded:
                return forwarded.split(',')[0].strip()
        if request.client is not None:
            return request.client.host
        return 'unknown'

    def check(self, request: Request) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``.
        ``retry_after_seconds`` is 0 when the request is allowed.
        """
        path = request.url.path

        for prefix in self._cfg.exclude_paths:
            if path.startswith(prefix):
                return True, 0

        limit = self._limit_for(path)
        client = self._client_ip(request, self._cfg.trust_proxy_headers)
        # Use only the first two path segments as the counter key so that
        # /users/id1 and /users/id2 share a counter (path params vary per call).
        path_key = '/'.join(path.split('/')[:3])
        key = f'{client}:{path_key}'

        now = time.monotonic()
        window = self._cfg.window_seconds
        entry = self._counters.get(key)

        if entry is None or (now - entry[1]) >= window:
            self._counters[key] = [1, now]
            return True, 0

        entry[0] += 1
        if entry[0] > limit:
            retry_after = int(window - (now - entry[1])) + 1
            return False, retry_after

        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces rate limits using ``RateLimiter``.

    Returns HTTP 429 with a ``Retry-After`` header and a standard AppKernel
    error body when the limit is exceeded. Add this before the security
    middleware so that brute-force and enumeration attacks are stopped before
    JWT validation is attempted.
    """

    def __init__(self, app: Any, limiter: RateLimiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        allowed, retry_after = self.limiter.check(request)
        if not allowed:
            response = create_custom_error(
                429, 'Too many requests. Please slow down and retry after the indicated delay.'
            )
            response.headers['Retry-After'] = str(retry_after)
            return response
        return await call_next(request)
