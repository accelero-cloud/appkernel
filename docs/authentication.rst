Role Based Access Management
=============================

* :ref:`JWT Token`
* :ref:`Setup`
* :ref:`Key Path Configuration`
* :ref:`Role based authorisation`

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
