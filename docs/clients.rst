Transparent REST Client Proxies
================================

AppKernel provides a lightweight HTTP client layer for inter-service calls.
A shared ``httpx.AsyncClient`` connection pool is managed by the engine and
reused across all outgoing requests.

* :ref:`Basic usage`
* :ref:`Connection pool configuration`
* :ref:`Circuit breaker`

Basic usage
-----------

:class:`HttpClientFactory` creates a proxy bound to an upstream service's
base URL. Attribute access and ``wrap()`` return a :class:`RequestWrapper`
for a specific resource path::

    from appkernel import HttpClientFactory

    payments = HttpClientFactory.get('http://payments.svc')

    # Attribute access — calls http://payments.svc/authorisations/
    code, result = await payments.authorisations.post(payload)

    # wrap() — explicit path
    code, result = await payments.wrap('/refunds/12345').get()

All methods (``get``, ``post``, ``put``, ``patch``, ``delete``) accept:

- ``payload`` — a :class:`Model` instance, dict, or raw string body;
- ``path_extension`` — appended to the wrapper URL before the call;
- ``timeout`` — per-request timeout in seconds (default 3 s).

On success the response body is deserialised:

- If the body contains ``_type``, AppKernel attempts to reconstruct the
  corresponding :class:`Model` subclass.
- ``OperationResult`` and ``ErrorMessage`` types are returned as plain dicts.
- Non-JSON bodies are returned as ``{'result': text}``.

On a non-2xx response :class:`RequestHandlingException` is raised with the
upstream status code.

Connection pool configuration
------------------------------

Pass an :class:`HttpClientConfig` to :class:`AppKernelEngine` to control pool
and timeout behaviour::

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

The client is initialised at startup and closed gracefully on shutdown.
See :class:`HttpClientConfig` for full parameter reference and sizing guidance.

Circuit breaker
---------------

Without a circuit breaker, a slow or failing downstream service will hold
connections open until they time out and exhaust the pool, causing cascading
failures across all upstreams. The circuit breaker detects repeated failures
and short-circuits calls immediately, returning HTTP 503 instead of queuing
work against an unavailable service.

How it works
............

The circuit breaker operates per proxy (per upstream service) with three states:

- **CLOSED** (normal): requests flow through; consecutive 5xx and network
  errors are counted.
- **OPEN** (tripped): once ``failure_threshold`` consecutive failures are
  recorded, the circuit opens. All further calls raise :class:`CircuitOpenError`
  (HTTP 503) immediately — no network connection is attempted.
- **HALF_OPEN** (probing): after ``recovery_timeout`` seconds, one probe
  request is allowed through. A successful probe closes the circuit; a failed
  probe re-opens it.

Only 5xx and network errors count as failures. 4xx client errors do not trip
the circuit — they indicate a bad request, not an unhealthy upstream.

Enabling a global default
.........................

Set ``circuit_breaker`` on :class:`HttpClientConfig` to enable a circuit
breaker for every proxy created by :class:`HttpClientFactory`::

    from appkernel import AppKernelEngine, HttpClientConfig, CircuitBreakerConfig

    kernel = AppKernelEngine(
        'my-app',
        http_client_config=HttpClientConfig(
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5,    # trips after 5 consecutive 5xx/network errors
                recovery_timeout=30.0,  # seconds before probing the upstream
                half_open_max_calls=1,  # probe requests allowed before deciding
            )
        )
    )

Per-proxy override
..................

Override (or disable) the circuit breaker for a specific upstream::

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

Handling CircuitOpenError
.........................

:class:`CircuitOpenError` is a subclass of :class:`AppKernelException` with
``status_code = 503``. Catch it to implement fallback logic::

    from appkernel import CircuitOpenError
    from appkernel.http_client import RequestHandlingException

    try:
        code, result = await payments.authorisations.post(payload)
    except CircuitOpenError as exc:
        # Circuit is open — return a cached result or queue for retry
        logger.warning('Payments unavailable: %s', exc)
        result = {'status': 'pending'}
    except RequestHandlingException as exc:
        # Other HTTP / network error
        raise

CircuitBreakerConfig reference
...............................

+-------------------------+----------+-----------------------------------------------+
| Parameter               | Default  | Description                                   |
+=========================+==========+===============================================+
| ``failure_threshold``   | ``5``    | Consecutive 5xx/network errors to trip open.  |
+-------------------------+----------+-----------------------------------------------+
| ``recovery_timeout``    | ``30.0`` | Seconds before moving to HALF_OPEN.           |
+-------------------------+----------+-----------------------------------------------+
| ``half_open_max_calls`` | ``1``    | Probe requests allowed in HALF_OPEN state.    |
+-------------------------+----------+-----------------------------------------------+

Sizing guidance:

- **Low-latency critical path** (e.g. auth, payments): lower ``failure_threshold``
  (2–3) and longer ``recovery_timeout`` (60 s) to fail fast and give the
  upstream time to recover.
- **Background / non-critical calls**: higher ``failure_threshold`` (10+) and
  shorter ``recovery_timeout`` (10–15 s) to tolerate transient blips.
- **Multi-instance deployments**: the circuit breaker state is in-process.
  Each instance maintains its own state independently. For shared state across
  instances, use a Redis-backed circuit breaker library.
