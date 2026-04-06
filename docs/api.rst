.. _api:

API Definition
==============

App Kernel Engine
-----------------
.. module:: appkernel

Bootstraps and manages the FastAPI application. Initialises MongoDB, registers models as REST services,
sets up security and locale middleware, and starts the Uvicorn server.

Example::

    from appkernel import AppKernelEngine, Model, MongoRepository
    from typing import Annotated
    from appkernel import Required, Generator, create_uuid_generator

    class User(Model, MongoRepository):
        id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required()] = None

    kernel = AppKernelEngine('my-service')
    kernel.register(User, methods=['GET', 'POST', 'PUT', 'DELETE'])
    kernel.run()

.. autoclass:: AppKernelEngine
    :members:
    :inherited-members:

Model
-----

The base class for all domain objects. Provides JSON serialisation, metadata generation, validation,
and list manipulation helpers. Extend with :class:`MongoRepository` or :class:`AuditableRepository`
for persistence.

.. autoclass:: Model
    :members:
    :inherited-members:

Field Metadata
--------------

Fields are declared using Python's ``typing.Annotated`` with one or more metadata markers.
All fields should default to ``None`` — the deferred validation pattern runs validation explicitly
via ``finalise_and_validate()`` or implicitly via ``save()`` / ``dumps()``.

Example::

    from typing import Annotated
    from pydantic import Field
    from appkernel import Required, Generator, Converter, Default, Validators, Marshal
    from appkernel import MongoIndex, MongoUniqueIndex, MongoTextIndex
    from appkernel import create_uuid_generator, content_hasher, Email, NotEmpty

    class User(Model, MongoRepository):
        id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required(), MongoUniqueIndex()] = None
        email: Annotated[str | None, Validators(Email), MongoUniqueIndex()] = None
        password: Annotated[str | None, Validators(NotEmpty), Converter(content_hasher()), Field(exclude=True)] = None

Required marker
```````````````
.. autoclass:: Required

Generator marker
````````````````
.. autoclass:: Generator

Converter marker
````````````````
.. autoclass:: Converter

Default marker
``````````````
.. autoclass:: Default

Validators marker
`````````````````
.. autoclass:: Validators

Marshal marker
``````````````
.. autoclass:: Marshal

MongoDB index markers
``````````````````````
.. autoclass:: MongoIndex
.. autoclass:: MongoUniqueIndex
.. autoclass:: MongoTextIndex

Validators
----------

The base Validator class
`````````````````````````
.. autoclass:: Validator
    :special-members: __init__
    :members:
    :inherited-members:

Not Empty
`````````
.. autoclass:: NotEmpty
    :special-members: __init__
    :members:
    :inherited-members:

Regular Expression
``````````````````
.. autoclass:: Regexp
    :special-members: __init__
    :members:
    :inherited-members:

Email
`````
.. autoclass:: Email
    :special-members: __init__
    :members:
    :inherited-members:

Minimum
```````
.. autoclass:: Min
    :special-members: __init__
    :members:
    :inherited-members:

Maximum
```````
.. autoclass:: Max
    :special-members: __init__
    :members:
    :inherited-members:

Past
````
.. autoclass:: Past
    :special-members: __init__
    :members:
    :inherited-members:

Future
``````
.. autoclass:: Future
    :special-members: __init__
    :members:
    :inherited-members:

Unique
``````
.. autoclass:: Unique
    :special-members: __init__
    :members:
    :inherited-members:


Generators
----------

UUID Generator
``````````````
.. autofunction:: create_uuid_generator

Date generator
``````````````
.. autofunction:: date_now_generator

Password hasher
```````````````
.. autofunction:: content_hasher

Repository
----------
.. autoclass:: Repository
    :special-members: __init__
    :members:
    :inherited-members:

Query
-----
.. autoclass:: Query
    :special-members: __init__
    :members:
    :inherited-members:

MongoRepository
---------------
.. autoclass:: MongoRepository
    :members: version_check, add_schema_validation, create_index, create_text_index, create_unique_index, get_collection
    :inherited-members:

Auditable Repository
--------------------
.. autoclass:: AuditableRepository
    :members:

MongoQuery
----------
.. autoclass:: MongoQuery
    :special-members: __init__
    :members:
