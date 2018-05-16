.. _api:

API
===

App Kernel Engine
-----------------
.. module:: appkernel

The main application class, which exposes the Service classes, manages Repositories and applies security.

.. autoclass:: AppKernelEngine
    :members:
    :inherited-members:

Model
-----
The base class to be extended by all Domain objects (Models). It has a set of useful methods, such as JSON marshaling, metadata (json schema) generation and validation.
Example: ::

    class User(Model):
            id = Parameter(str)
            name = Parameter(str, required=True, index=UniqueIndex)
            email = Parameter(str, validators=Email, index=UniqueIndex)
            password = Parameter(str, validators=NotEmpty,
                                 to_value_converter=password_hasher(), omit=True)
.. autoclass:: Model
    :members:
    :inherited-members:

Parameter
---------
.. autoclass:: Parameter
    :special-members: __init__
    :members:
    :inherited-members:

Validators
----------

The base Validator class
`````````````````````````
.. autoclass:: Validator
    :special-members: __init__
    :members:
    :inherited-members:

Not Empty Validator
````````````````````````````
.. autoclass:: NotEmpty
    :special-members: __init__
    :members:
    :inherited-members:


Regular Expression Validator
````````````````````````````
.. autoclass:: Regexp
    :special-members: __init__
    :members:
    :inherited-members:

Email Validator
````````````````````````````
.. autoclass:: Email
    :special-members: __init__
    :members:
    :inherited-members:

Minimum Validator
````````````````````````````
.. autoclass:: Min
    :special-members: __init__
    :members:
    :inherited-members:

Maximum Validator
````````````````````````````
.. autoclass:: Max
    :special-members: __init__
    :members:
    :inherited-members:

Past Validator
````````````````````````````
.. autoclass:: Past
    :special-members: __init__
    :members:
    :inherited-members:

Future Validator
````````````````````````````
.. autoclass:: Future
    :special-members: __init__
    :members:
    :inherited-members:


Unique Value Validator
````````````````````````````
.. autoclass:: Unique
    :special-members: __init__
    :members:
    :inherited-members:


Repository
----------
The current implementation is the MongoRepository.
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
-------------------
.. autoclass:: AuditableRepository
    :members:
    :inherited-members:

MongoQuery
----------
.. autoclass:: MongoQuery
    :special-members: __init__
    :members:
    :inherited-members:

Service
-------
.. autoclass:: Service
    :special-members: __init__
    :members:
    :inherited-members:
