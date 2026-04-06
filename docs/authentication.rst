Role Based Access Management
=============================

* :ref:`JWT Token`
* :ref:`Setup`
* :ref:`Key Path Configuration`
* :ref:`Role based authorisation`
* :ref:`CORS`
* :ref:`CSRF`

JWT Token
---------

AppKernel uses `JWT tokens`_ (RS256) for authentication and authorisation. To issue tokens, add the
:class:`IdentityMixin` to a model that has an ``id`` and a ``roles`` field::

    from typing import Annotated
    from appkernel import Model, MongoRepository, IdentityMixin, Required, Generator, create_uuid_generator

    class User(Model, MongoRepository, IdentityMixin):
        id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
        roles: list[str] | None = None

With this, each User instance exposes an ``auth_token`` property::

    print(f'token: {user.auth_token}')

The token is digitally signed with RS256 and includes an ``aud`` claim set to the
``app_id`` passed to ``AppKernelEngine``. Tokens issued by one service are rejected
by all other services, preventing cross-service token replay.

Setup
-----

JWT tokens require an RSA key pair. Generate one using OpenSSL::

    # Generate private key
    openssl genpkey -out appkernel.pem -algorithm rsa -pkeyopt rsa_keygen_bits:2048
    # Derive the public key
    openssl rsa -in appkernel.pem -out appkernel.pub -pubout

By default AppKernel looks for these files at ``{config-folder}/keys/appkernel.pem``
and ``{config-folder}/keys/appkernel.pub``. See :ref:`Key Path Configuration` to
override this location.

Key Path Configuration
----------------------

The private and public key paths are resolved in the following priority order:

**1. Environment variables (highest priority)**

Set ``APPKERNEL_PRIVATE_KEY_PATH`` and ``APPKERNEL_PUBLIC_KEY_PATH`` to absolute
file paths. This is the recommended approach for production and container deployments::

    export APPKERNEL_PRIVATE_KEY_PATH=/run/secrets/appkernel.pem
    export APPKERNEL_PUBLIC_KEY_PATH=/run/secrets/appkernel.pub

With Docker or Kubernetes, mount the key files as secrets and point the env vars
at the mount path.

**2. Configuration file (cfg.yml)**

Add ``private_key_path`` and ``public_key_path`` under ``appkernel.security``::

    appkernel:
      security:
        private_key_path: /etc/myapp/keys/private.pem
        public_key_path: /etc/myapp/keys/public.pub

**3. Default path (fallback)**

If neither env vars nor cfg.yml entries are set, AppKernel loads keys from::

    {config-folder}/keys/appkernel.pem
    {config-folder}/keys/appkernel.pub

where ``{config-folder}`` is the ``cfg_dir`` argument passed to ``AppKernelEngine``.

Role based authorisation
------------------------

Configure access control after registering a model::

    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all() \
        .require(Role('user'), methods='GET') \
        .require(Role('admin'), methods=['PUT', 'POST', 'PATCH', 'DELETE'])

Once secured, requests must include a valid JWT token in the ``Authorization`` header::

    Authorization: Bearer eyJhbGciOiJSUzI1...Mjc0MzEzNDd9.

For custom action endpoints, pass a ``require`` list to the ``@action`` decorator::

    @action(method='POST', require=[CurrentSubject(), Role('admin')])
    def change_password(self, current_password, new_password):
        ...

Available permission types:

- **Role** — grants access to any user holding the specified role;
- **Anonymous** — grants access to unauthenticated users;
- **Denied** — explicitly denies access; assign to resources that must never be reachable;
- **CurrentSubject** — grants access when the JWT token subject matches the model's ``id`` (useful for users modifying their own data);

.. _JWT tokens: https://jwt.io/


CORS
----

Cross-Origin Resource Sharing (CORS) controls whether browser-based JavaScript
on one origin (e.g. ``https://app.example.com``) may call an API on a different
origin (e.g. ``https://api.example.com``). Without CORS headers the browser
blocks the response, even though the server processed the request.

AppKernel adds no CORS headers by default. Call ``enable_cors()`` to opt in::

    from appkernel import AppKernelEngine, CorsConfig

    kernel = AppKernelEngine('my-app', cfg_dir='./config')
    kernel.enable_security()
    kernel.enable_rate_limiting()
    # enable_cors() must be called LAST so it executes first and handles
    # OPTIONS preflight before security / rate-limiting checks run.
    kernel.enable_cors(CorsConfig(
        allow_origins=['https://app.example.com'],
    ))

Middleware ordering
...................

FastAPI / Starlette executes middleware in reverse registration order — the
last middleware added runs first. ``enable_cors()`` must therefore be called
**after** ``enable_security()`` and ``enable_rate_limiting()`` so that:

1. CORS middleware handles preflight ``OPTIONS`` requests (and returns 200)
   before the security middleware rejects them as unauthenticated.
2. CORS headers are injected on every response, including 4xx and 5xx errors.

CorsConfig reference
....................

+----------------------+--------------------------------------------------+----------------------------+
| Parameter            | Default                                          | Description                |
+======================+==================================================+============================+
| ``allow_origins``    | ``[]`` (same-origin only)                        | Permitted origin list.     |
|                      |                                                  | Use ``['*']`` with         |
|                      |                                                  | ``allow_credentials=False``|
|                      |                                                  | only.                      |
+----------------------+--------------------------------------------------+----------------------------+
| ``allow_methods``    | ``GET POST PUT PATCH DELETE OPTIONS``            | Permitted HTTP methods.    |
+----------------------+--------------------------------------------------+----------------------------+
| ``allow_headers``    | ``Authorization Content-Type Accept-Language``   | Permitted request headers. |
+----------------------+--------------------------------------------------+----------------------------+
| ``allow_credentials``| ``False``                                        | Set ``True`` to send       |
|                      |                                                  | ``Access-Control-Allow-    |
|                      |                                                  | Credentials: true``.       |
|                      |                                                  | Requires explicit origins. |
+----------------------+--------------------------------------------------+----------------------------+
| ``expose_headers``   | ``[]``                                           | Response headers JS may    |
|                      |                                                  | read.                      |
+----------------------+--------------------------------------------------+----------------------------+
| ``max_age``          | ``600``                                          | Preflight cache lifetime   |
|                      |                                                  | in seconds.                |
+----------------------+--------------------------------------------------+----------------------------+

Security notes
..............

- **Never use** ``allow_origins=['*']`` in production — it allows any website
  to read API responses from a logged-in user's browser session.
- ``allow_origins=['*']`` combined with ``allow_credentials=True`` is rejected
  at startup with ``ValueError`` (browsers refuse this combination anyway).
- Restrict ``allow_headers`` to the minimum your frontend actually sends.
  Broad header allowlists increase the attack surface for header injection.

CSRF
----

Cross-Site Request Forgery (CSRF) tricks a victim's browser into sending an
authenticated request to your API from a malicious page. The attack works
because browsers automatically attach cookies to cross-origin requests.

**AppKernel's current auth model (JWT in the** ``Authorization`` **header)
is not vulnerable to CSRF.** Browsers do not auto-attach custom headers to
cross-origin requests, so an attacker's page cannot issue an authenticated
request without first stealing the token (which would be XSS, a different
attack). No CSRF protection is required for header-based JWT APIs.

CSRF protection is required only if you introduce cookie-based authentication.
If you add cookie sessions or store JWTs in cookies, adopt one of the following
mitigations before the feature ships:

**Option A — SameSite cookie attribute (recommended for most cases)**

Set ``SameSite=Strict`` (or ``SameSite=Lax``) on the auth cookie::

    # Example when setting a cookie in a FastAPI response
    response.set_cookie(
        key='session',
        value=token,
        httponly=True,
        samesite='strict',   # browser refuses to send on cross-origin requests
        secure=True,         # HTTPS only
    )

``SameSite=Strict`` blocks the cookie on all cross-origin requests, including
OAuth redirect flows. Use ``SameSite=Lax`` if you need OAuth to work; it still
blocks cross-origin POST/PUT/DELETE but permits top-level navigations.

**Option B — Double-submit cookie pattern**

Alongside the HttpOnly session cookie, issue a second readable CSRF token
cookie. The client echoes this token in a custom request header (e.g.
``X-CSRF-Token``). The server rejects any state-changing request that lacks
the matching header. This is compatible with OAuth flows but adds a round-trip.

**Option C — Origin / Referer validation**

In a middleware, reject state-changing requests (POST, PUT, PATCH, DELETE)
whose ``Origin`` or ``Referer`` header does not match the known API hostname.
Lightweight and stateless but not universally reliable (some proxies strip
``Referer``).

Decision matrix
...............

+------------------------------+------------+----------------------------------------------+
| Auth mechanism               | CSRF risk  | Recommended mitigation                       |
+==============================+============+==============================================+
| JWT in ``Authorization``     | **None**   | Nothing required                             |
| header                       |            |                                              |
+------------------------------+------------+----------------------------------------------+
| JWT in ``HttpOnly`` cookie   | High       | ``SameSite=Strict`` + ``Secure`` on cookie   |
+------------------------------+------------+----------------------------------------------+
| Session cookie (OAuth, etc.) | High       | ``SameSite=Lax`` + double-submit if needed   |
+------------------------------+------------+----------------------------------------------+
