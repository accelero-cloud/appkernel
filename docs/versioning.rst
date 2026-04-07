API Versioning
==============

AppKernel supports evolving REST APIs through URL path versioning, view model
projection, and deprecation signalling.  This tutorial walks through a
complete example: a ``User`` resource that gains a structured ``address``
field between v1 and v2.


The core tension
----------------

AppKernel's ``Model`` class serves two roles: it is both the MongoDB
persistence schema *and* the API response shape.  These two concerns evolve
at different speeds and for different reasons, so a clean versioning strategy
separates them deliberately:

* **One persistence model** — the ``MongoRepository`` model tracks what is
  stored in MongoDB.  It absorbs all schema changes over time.
* **Per-version view models** — thin ``Model`` subclasses (no repository
  mixin) that project the exact shape each API version exposes to clients.
* **Per-version service classes** — ``@resource`` / ``@action`` controllers
  that load from the persistence model and return the correct view model.

This keeps the database schema as a single source of truth while letting API
contracts evolve independently.


URL versioning
--------------

The ``url_base`` parameter on :meth:`~appkernel.AppKernelEngine.register` is
the primary versioning mechanism.  It prefixes every route generated for that
service::

    kernel.register(User, url_base='/v1/', methods=['GET', 'POST'])
    # → GET /v1/users/, POST /v1/users/, GET /v1/users/{object_id}, …

    kernel.register(UserV2Service(), url_base='/v2/', tags=['v2'])
    # → GET /v2/users/{user_id}

Clients pin to a specific version prefix and are unaffected by changes to
other versions.  Old versions can be removed by simply stopping their
registration.


Complete example
----------------

Step 1 — Persistence model (shared across all versions)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The persistence model accumulates every field that has ever existed.  New
fields use :class:`~appkernel.Default` so that old documents (which lack the
field) still deserialize cleanly::

    from typing import Annotated
    from appkernel import (
        Model, MongoRepository,
        Required, Generator, Validators, Default,
        create_uuid_generator, NotEmpty,
    )

    class Address(Model):
        street: Annotated[str | None, Required(), Validators(NotEmpty())] = None
        city:   Annotated[str | None, Required(), Validators(NotEmpty())] = None

    class User(Model, MongoRepository):
        id:      Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        name:    Annotated[str | None, Required(), Validators(NotEmpty())] = None
        # address was added in v2; old documents will have address=None
        address: Annotated[Address | None, Default(None)] = None

Step 2 — V1 view model and service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The v1 view exposes only ``id`` and ``name``.  The ``from_user`` factory
method converts the persistence model to the v1 shape::

    class UserV1(Model):
        id:   str | None = None
        name: str | None = None

        @classmethod
        def from_user(cls, user: User) -> 'UserV1':
            return cls(id=user.id, name=user.name)


    class UserV1Service:

        @resource(
            method='GET',
            path='./<user_id>',
            summary='Get a user (v1)',
            response_model=UserV1,
        )
        def get_user(self, user_id) -> UserV1:
            user = User.where(User.id == user_id).find_one()
            return UserV1.from_user(user)

        @resource(
            method='POST',
            summary='Create a user (v1)',
            request_model=UserV1,
            response_model=UserV1,
        )
        def create_user(self, payload) -> UserV1:
            user = User(name=payload.get('name'))
            user.save()
            return UserV1.from_user(user)

Step 3 — V2 view model and service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The v2 view adds the ``address`` field.  The service class is registered at a
different URL prefix::

    class UserV2(Model):
        id:      str | None = None
        name:    str | None = None
        address: Address | None = None

        @classmethod
        def from_user(cls, user: User) -> 'UserV2':
            return cls(id=user.id, name=user.name, address=user.address)


    class UserV2Service:

        @resource(
            method='GET',
            path='./<user_id>',
            summary='Get a user (v2)',
            response_model=UserV2,
        )
        def get_user(self, user_id) -> UserV2:
            user = User.where(User.id == user_id).find_one()
            return UserV2.from_user(user)

        @resource(
            method='POST',
            summary='Create a user (v2)',
            request_model=UserV2,
            response_model=UserV2,
        )
        def create_user(self, payload) -> UserV2:
            user = User(name=payload.get('name'), address=payload.get('address'))
            user.save()
            return UserV2.from_user(user)

Step 4 — Registration with version tags
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    kernel = AppKernelEngine('my-app', cfg_dir='./config')

    kernel.register(UserV1Service(), url_base='/v1/', tags=['v1'])
    kernel.register(UserV2Service(), url_base='/v2/', tags=['v2'])

    kernel.enable_openapi(title='My API', version='2.0.0')
    kernel.run()

The ``tags`` kwarg on ``register()`` applies the tag to every endpoint of
that service registration.  In Swagger UI, v1 and v2 endpoints appear as
separate groups.

The resulting routes are::

    GET  /v1/users/{user_id}   → UserV1Service.get_user
    POST /v1/users/            → UserV1Service.create_user
    GET  /v2/users/{user_id}   → UserV2Service.get_user
    POST /v2/users/            → UserV2Service.create_user


Deprecating a version
---------------------

Mark individual endpoints as deprecated using the ``deprecated=True`` kwarg.
This has no effect on runtime behaviour — it signals to API consumers (via
the OpenAPI spec and Swagger UI) that the endpoint will be removed::

    class UserV1Service:

        @resource(
            method='GET',
            path='./<user_id>',
            deprecated=True,
            summary='Deprecated — use GET /v2/users/{user_id} instead',
            response_model=UserV1,
        )
        def get_user(self, user_id) -> UserV1:
            ...

In the generated OpenAPI spec the operation gains ``"deprecated": true``,
which Swagger UI renders with a strikethrough.

To retire a version completely, remove its ``register()`` call.  The routes
will no longer be registered and all endpoints vanish from the spec.


Tags and the OpenAPI spec
-------------------------

Registration-level tags and per-decorator tags are merged, with registration
tags listed first::

    class PaymentService:

        @resource(method='POST', path='/pay', tags=['internal'])
        def pay(self): ...

    kernel.register(PaymentService(), url_base='/v1/', tags=['v1'])
    # → tags for /v1/paymentservice/pay: ['v1', 'internal']

This lets you apply a version tag globally at registration time and add
fine-grained grouping tags per endpoint without duplication.


MongoDB schema evolution
------------------------

Because MongoDB is schemaless, adding a field to the persistence model is
safe: old documents simply return ``None`` for the new field.  Use
:class:`~appkernel.Default` to supply a sensible fallback::

    # Before v2
    class User(Model, MongoRepository):
        name: Annotated[str | None, Required()] = None

    # After v2 — old documents have address=None, new ones carry an Address
    class User(Model, MongoRepository):
        name:    Annotated[str | None, Required()] = None
        address: Annotated[Address | None, Default(None)] = None

For type changes (e.g. ``address`` was a plain string, now it is an embedded
object), implement a custom :class:`~appkernel.Marshaller` that handles both
formats on read::

    from appkernel import Marshaller, Marshal
    from typing import Annotated

    class AddressUpgradeMarshaller(Marshaller):
        def from_wire(self, value):
            if isinstance(value, str):
                # Legacy document — promote bare string to Address object
                return Address(street=value, city='Unknown')
            return value  # already an Address dict from a v2 document

    class User(Model, MongoRepository):
        address: Annotated[Address | None, Marshal(AddressUpgradeMarshaller)] = None

This avoids bulk migration scripts for simple type widening.  Documents are
upgraded transparently on the first read after deployment.


What not to do
--------------

**Don't give each version its own MongoRepository model.**  ``UserV1`` and
``UserV2`` as separate ``MongoRepository`` subclasses means two MongoDB
collections that diverge forever and require data duplication.

**Don't use query-parameter versioning** (``/users/?version=2``).  It
requires middleware changes, cannot be cleanly represented in OpenAPI, and
makes URL bookmarking unreliable.

**Don't version for additive-only changes.**  Adding a nullable field or a
new optional endpoint is backward compatible.  Reserve version bumps for
breaking changes: removed fields, renamed fields, or changed types that
cannot be handled by a ``Default`` or ``Marshaller``.
