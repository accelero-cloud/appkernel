Rate Limiting
=============

* :ref:`Overview`
* :ref:`Quick Start`
* :ref:`Configuration Reference`
* :ref:`Per-Endpoint Limits`
* :ref:`Excluding Paths`
* :ref:`Proxy and Load Balancer Deployments`
* :ref:`Multi-Instance Deployments`

Overview
--------

AppKernel ships with built-in rate limiting to protect against brute-force
login attempts, credential stuffing, and API enumeration. The throttle runs as
a Starlette middleware that sits in front of the security middleware, stopping
excessive traffic before JWT validation is even attempted.

The implementation uses a **fixed-window counter** per client IP and endpoint
group. All state is held in-process — no external dependency is required. See
:ref:`Multi-Instance Deployments` if you run more than one instance behind a
load balancer.

Quick Start
-----------

Enable rate limiting after registering security::

    from appkernel import AppKernelEngine

    kernel = AppKernelEngine('my-app', cfg_dir='./config')
    kernel.enable_security()       # add JWT/RBAC middleware
    kernel.enable_rate_limiting()  # add rate-limit middleware (runs first)
    kernel.register(User, methods=['GET', 'POST', 'PUT', 'DELETE'])
    kernel.run()

With the defaults, each client IP is allowed **100 requests per 60-second
window** across the entire API surface. Requests that exceed the limit receive::

    HTTP 429 Too Many Requests
    Retry-After: 43

    {
        "_type": "ErrorMessage",
        "code": 429,
        "message": "Too many requests. Please slow down and retry after the indicated delay."
    }

The ``Retry-After`` value is the number of seconds remaining in the current
window.

.. important::

   Always call ``enable_rate_limiting()`` **after** ``enable_security()``.
   Starlette applies middlewares in reverse registration order (last added =
   outermost = first to execute). Adding rate limiting last ensures it runs
   before authentication, so brute-force attempts are stopped without incurring
   the cost of JWT validation.

Configuration Reference
-----------------------

Pass a :class:`~appkernel.RateLimitConfig` instance to customise behaviour::

    from appkernel import AppKernelEngine, RateLimitConfig

    kernel.enable_rate_limiting(
        RateLimitConfig(
            requests_per_window=100,     # global limit per client IP
            window_seconds=60,           # window length in seconds
            endpoint_limits={},          # per-prefix overrides (see below)
            exclude_paths=[],            # paths that bypass limiting
            trust_proxy_headers=False,   # honour X-Forwarded-For
        )
    )

.. list-table::
   :header-rows: 1
   :widths: 25 10 65

   * - Parameter
     - Default
     - Description
   * - ``requests_per_window``
     - 100
     - Maximum requests a single IP may make within ``window_seconds``.
       Exceeded requests receive HTTP 429.
   * - ``window_seconds``
     - 60
     - Duration of the counting window. The counter resets when the window
       expires — it does **not** slide continuously.
   * - ``endpoint_limits``
     - ``{}``
     - Per-path-prefix overrides. First matching prefix wins. See
       :ref:`Per-Endpoint Limits`.
   * - ``exclude_paths``
     - ``[]``
     - Path prefixes that bypass rate limiting entirely. See
       :ref:`Excluding Paths`.
   * - ``trust_proxy_headers``
     - ``False``
     - When ``True``, the client IP is read from ``X-Forwarded-For`` rather
       than the TCP peer address. Enable only behind a trusted reverse proxy.
       See :ref:`Proxy and Load Balancer Deployments`.

Recommended profiles:

============  ======================  ========================
Traffic       requests_per_window     window_seconds
============  ======================  ========================
Low / auth    10–20                   60
Medium        100                     60 (default)
High          500                     60
============  ======================  ========================

Per-Endpoint Limits
-------------------

Authentication endpoints typically need tighter limits than the general API.
Use ``endpoint_limits`` to override the global limit for specific path prefixes::

    kernel.enable_rate_limiting(
        RateLimitConfig(
            requests_per_window=200,          # generous global limit
            endpoint_limits={
                '/auth': 10,                  # brute-force protection
                '/users/change_password': 5,  # password-reset protection
                '/admin': 20,                 # admin surface
            }
        )
    )

The first matching prefix wins, so order matters for overlapping prefixes.
Requests whose path does not match any prefix fall back to
``requests_per_window``.

Excluding Paths
---------------

Health checks, readiness probes, and metrics endpoints should not be rate
limited as they are called by infrastructure at high frequency::

    kernel.enable_rate_limiting(
        RateLimitConfig(
            exclude_paths=['/health', '/ready', '/metrics']
        )
    )

Prefix matching is used — ``'/health'`` excludes ``/health``, ``/health/live``,
and ``/healthz``.

Proxy and Load Balancer Deployments
-------------------------------------

When AppKernel runs behind a reverse proxy (nginx, AWS ALB, Cloudflare), the
TCP peer address seen by the application is the proxy IP, not the real client
IP. All requests would share a single rate-limit bucket, making the throttle
ineffective.

Set ``trust_proxy_headers=True`` to read the real IP from the first address in
the ``X-Forwarded-For`` header::

    kernel.enable_rate_limiting(
        RateLimitConfig(trust_proxy_headers=True)
    )

.. warning::

   Only enable ``trust_proxy_headers`` when AppKernel sits behind a proxy that
   you control and that strips or overwrites ``X-Forwarded-For``. If the header
   can be set by end users, an attacker can forge any IP and trivially bypass
   per-IP limits.

Multi-Instance Deployments
---------------------------

The default limiter stores all counters in the memory of the running process.
If you run multiple AppKernel instances behind a load balancer, each instance
tracks its own counters independently — a client could hit every instance at
the configured limit, effectively multiplying their allowed throughput by the
number of instances.

For multi-instance deployments, replace the in-process limiter with a
Redis-backed implementation. The middleware accepts any object that implements
the same ``check(request) -> (allowed, retry_after)`` interface as
:class:`~appkernel.rate_limit.RateLimiter`::

    from appkernel.rate_limit import RateLimitConfig, RateLimitMiddleware

    class RedisRateLimiter:
        def __init__(self, redis_client, cfg: RateLimitConfig):
            self._redis = redis_client
            self._cfg = cfg

        def check(self, request) -> tuple[bool, int]:
            # implement sliding window in Redis using INCR + EXPIRE
            ...

    limiter = RedisRateLimiter(redis_client, RateLimitConfig(requests_per_window=100))
    kernel.app.add_middleware(RateLimitMiddleware, limiter=limiter)
