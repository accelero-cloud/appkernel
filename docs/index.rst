Welcome to AppKernel — API development made easy!
==================================================

What is AppKernel?
------------------

A super-easy-to-use API framework that takes you from zero to a production-ready REST service in minutes. No, really — minutes.

**It provides data serialisation, transformation, validation, security, ORM, RPC, and service mesh functions out of the box**
(`check out the roadmap for more details <roadmap>`_).

The codebase requires Python 3.12+ and is thoroughly tested on every push.


Read the docs :)
================
.. include:: contents.rst.inc

****

Crash Course (TL;DR)
--------------------

Let's build a minimal identity service::

    from typing import Annotated
    from appkernel import (
        AppKernelEngine, Model, MongoRepository,
        Required, Generator, Validators, Converter, Default,
        Email, NotEmpty, create_uuid_generator, content_hasher,
    )
    from appkernel import MongoUniqueIndex

    class User(Model, MongoRepository):
        id:       Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        name:     Annotated[str | None, Required(), MongoUniqueIndex()] = None
        email:    Annotated[str | None, Validators(Email), MongoUniqueIndex()] = None
        password: Annotated[str | None, Validators(NotEmpty), Converter(content_hasher())] = None
        roles:    Annotated[list[str] | None, Default(['Login'])] = None

    kernel = AppKernelEngine('demo app')

    if __name__ == '__main__':
        kernel.register(User, methods=['GET', 'POST'])

        user = User(name='Test User', email='test@example.com', password='some pass')
        user.save()

        kernel.run()

Test it with curl::

   curl -i -X GET 'http://127.0.0.1:5000/users/'

And check out the result::

   {
     "_items": [
       {
         "_type": "appkernel.User",
         "email": "test@example.com",
         "id": "U0590e790-46cf-42a0-bdca-07b0694d08e2",
         "name": "Test User",
         "roles": [
           "Login"
         ]
       }
     ],
     "_links": {
       "self": {
         "href": "/users/"
       }
     }
   }

That's it — the user is saved, retrievable by ID, and the service automatically exposes JSON schema and UI metadata endpoints. Validation, indexing, and password hashing are all wired in.

Quick overview of notable features
===================================

Built-in query DSL
-------------------

Find one user matching a field value::

   user = User.where(User.name == 'Some Username').find_one()

Return the first five users with the 'Admin' role::

   users = User.where(User.roles % 'Admin').find(page=0, page_size=5)

Or use a native MongoDB query when the DSL isn't enough::

   users = User.find_by_query({'name': 'user name'})

Useful things baked into the Model
------------------------------------

Auto-generate a prefixed UUID::

   id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None
   # → U-0590e790-46cf-42a0-bdca-07b0694d08e2

Add a unique index to a field::

   name: Annotated[str | None, Required(), MongoUniqueIndex()] = None

Validate an email address::

   email: Annotated[str | None, Validators(Email)] = None

Validate at the database level too::

   User.add_schema_validation(validation_action='error')

Hash a password and hide it from JSON output::

   password: Annotated[str | None, Converter(content_hasher(rounds=10)), Field(exclude=True)] = None

Run all generators and validators explicitly (usually not needed — ``save()`` and ``dumps()`` do this automatically)::

   user.finalise_and_validate()


Role-based access control
--------------------------

Attach security rules immediately after registering a service::

    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all() \
        .require(Role('user'), methods='GET') \
        .require(Role('admin'), methods=['PUT', 'POST', 'PATCH', 'DELETE'])

GET is open to any authenticated user with the ``user`` role; write operations require ``admin``.

JWT tokens
..........

To issue tokens, mix :class:`IdentityMixin` into any model that has an ``id``
and a ``roles`` field.  The ``auth_token`` property generates a signed JWT
(RS256) on demand — no extra controller needed::

    class User(Model, MongoRepository, IdentityMixin):
        id:    Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        roles: list[str] | None = None

    user = User.where(User.name == 'Alice').find_one()
    token = user.auth_token   # ready to send in an Authorization: Bearer header

All roles from the model are embedded in the token payload.  Tokens are
audience-scoped to the ``app_id`` passed to ``AppKernelEngine``, so a token
issued by one service is rejected by all others.

See :ref:`Role Based Access Management` for key setup, RBAC configuration, CORS, and CSRF guidance.
