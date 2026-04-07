OpenAPI Support
===============

AppKernel generates a live **OpenAPI 3.1.0** specification from your registered
services. Call :meth:`~appkernel.AppKernelEngine.enable_openapi` **after**
registering all services::

    from appkernel import AppKernelEngine, HttpClientConfig

    kernel = AppKernelEngine('my-app', cfg_dir='./config')
    kernel.register(User, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    kernel.enable_openapi(title='My API', version='1.0.0')
    kernel.run()

This exposes three endpoints:

* ``/openapi.json`` — the machine-readable OpenAPI 3.1.0 specification.
* ``/docs`` — Swagger UI (interactive browser).
* ``/redoc`` — ReDoc documentation browser.

To suppress the UI endpoints and serve only the raw spec::

    kernel.enable_openapi(include_docs=False)

The ``tags`` parameter on :meth:`~appkernel.AppKernelEngine.register` applies
a tag to every endpoint of that registration, which is useful for grouping
all endpoints of an API version together::

    kernel.register(UserV1Service(), url_base='/v1/', tags=['v1'])
    kernel.register(UserV2Service(), url_base='/v2/', tags=['v2'])

Registration tags are merged with per-decorator tags, with registration tags
listed first.  See :doc:`versioning` for a full walkthrough.

``enable_openapi`` returns ``self`` and can be chained::

    kernel.register(User).deny_all().require(Role('user'), methods='GET')
    kernel.enable_openapi(title='My API').run()


Decorator metadata
------------------

All ``@action`` and ``@resource`` decorators accept optional OpenAPI kwargs.
They do not affect runtime behaviour — they are used only for documentation.

.. list-table::
   :widths: 22 78
   :header-rows: 1

   * - Kwarg
     - Purpose
   * - ``summary``
     - Short operation summary (shown as the title in Swagger UI).
   * - ``tags``
     - List of tag strings used to group operations (e.g. ``['Payments', 'v2']``).
   * - ``request_model``
     - Explicit :class:`~appkernel.Model` subclass for the request body schema.
       Overrides type-hint inference.
   * - ``response_model``
     - Explicit :class:`~appkernel.Model` subclass for the 200/201 response schema.
       Overrides type-hint inference.
   * - ``query_params``
     - List of query parameter names to document (e.g. ``['start', 'stop']``).
   * - ``deprecated``
     - ``True`` marks the operation as deprecated in the spec (renders with
       strikethrough in Swagger UI). Has no effect on runtime behaviour.

Example::

    class PaymentService:

        @resource(
            method='POST',
            summary='Authorise a payment',
            tags=['Payments'],
            request_model=Payment,
            response_model=Payment,
        )
        def authorise(self, payload):
            ...

        @resource(
            method='GET',
            query_params=['start', 'stop'],
            summary='List payments in a date range',
            tags=['Payments'],
        )
        def list_payments(self, start=None, stop=None):
            ...

        @resource(
            method='POST',
            path='/legacy-pay',
            deprecated=True,
            summary='Deprecated — use POST /payments/pay instead',
        )
        def legacy_pay(self, payload):
            ...


Type-hint inference
-------------------

When ``request_model`` or ``response_model`` are omitted, AppKernel inspects
the method's type annotations to infer schemas automatically::

    class UserService:

        @resource(method='POST')
        def create_user(self, user: User) -> User:
            ...

The first non-``self`` parameter typed as a :class:`~appkernel.Model` subclass
becomes the request body schema.  The ``-> ReturnType`` annotation becomes the
200/201 response schema.

When a method has no type hints, the schema falls back to
``{"type": "object"}``.  Add type hints or use explicit ``request_model`` /
``response_model`` kwargs to get precise documentation.

Priority order for schema resolution:

1. Explicit ``request_model`` / ``response_model`` decorator kwarg.
2. Type-hint inference from the method signature.
3. Model class (for CRUD routes registered with :meth:`~appkernel.AppKernelEngine.register`).
4. ``{"type": "object"}`` fallback.


Validator constraints
---------------------

Model field schemas are built by :meth:`~appkernel.Model.get_json_schema` and
include constraints derived from validator metadata:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Validator
     - OpenAPI constraint
   * - ``Min(n)`` on ``int`` / ``float``
     - ``"minimum": n``
   * - ``Max(n)`` on ``int`` / ``float``
     - ``"maximum": n``
   * - ``Min(n)`` on ``str``
     - ``"minLength": n``
   * - ``Max(n)`` on ``str``
     - ``"maxLength": n``
   * - ``Regexp(pattern)``
     - ``"pattern": pattern``
   * - ``Email()``
     - ``"format": "email"``
   * - ``NotEmpty()`` on ``list``
     - ``"minItems": 1``
   * - ``Unique()`` on ``list``
     - ``"uniqueItems": true``


Response envelope
-----------------

Collection responses (``GET /resources/``) are wrapped in the AppKernel
envelope::

    {
        "_type":  "list",
        "_items": [ { ... }, { ... } ],
        "_links": { "self": { "href": "/resources/" } }
    }

The generated spec documents collection GET responses with an inline schema::

    {
        "type": "object",
        "properties": {
            "_type":  { "type": "string" },
            "_items": { "type": "array", "items": { "$ref": "#/components/schemas/User" } },
            "_links": { "type": "object" }
        }
    }

Single-item GET, POST, and PUT responses reference the model schema directly
(``{"$ref": "#/components/schemas/User"}``).  DELETE responses document the
``OperationResult`` shape with a ``result`` count field.


Query DSL
---------

AppKernel supports a rich URL query DSL for collection endpoints that cannot
be fully expressed as standard OpenAPI parameters::

    GET /users/?name=~john        # name contains 'john'
    GET /users/?sequence=>10      # sequence greater than 10
    GET /users/?roles:[Admin,User] # roles in the given list

These are documented as freeform ``string`` query parameters.  The standard
pagination and query parameters (``page``, ``page_size``, ``sort_by``,
``sort_order``, ``query``) are added automatically to every collection GET
route.

Full DSL syntax is described in :doc:`repositories`.


Programmatic usage
------------------

The generator can also be invoked directly without registering HTTP routes::

    from appkernel.openapi import OpenAPISchemaGenerator

    generator = OpenAPISchemaGenerator(title='My API', version='1.0.0')
    spec = generator.generate()

    import json
    print(json.dumps(spec, indent=2))
