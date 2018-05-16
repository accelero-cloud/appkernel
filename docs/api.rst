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
-----
.. autoclass:: Parameter
    :special-members: __init__
    :members:
    :inherited-members: