Role Based Access Management
=============================

* :ref:`JWT Token`
* :ref:`Setup`
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

The token payload will look like::

    {
        "created": "2018-07-08T20:29:23.154563",
        "description": "test description",
        "id": "Ue92d3b52-dd8b-4f10-a496-31b342b19cc9",
        "name": "test user",
        "roles": ["Admin", "User", "Operator"]
    }

The token is digitally signed with RS256.

Setup
-----

JWT tokens require an RSA key pair. Generate one using OpenSSL and place the files in ``{config-folder}/keys``::

    # Generate private key
    openssl genpkey -out appkernel.pem -algorithm rsa -pkeyopt rsa_keygen_bits:2048
    # Derive the public key
    openssl rsa -in appkernel.pem -out mykey.pub -pubout


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
