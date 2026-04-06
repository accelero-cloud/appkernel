Services
========

* :ref:`REST endpoints over HTTP`
* :ref:`Full range of CRUD operations`
* :ref:`Filtering and Sorting`
* :ref:`Pagination`
* :ref:`Custom resource endpoints`
* :ref:`HATEOAS`
* :ref:`HTTP Method Hooks`
* :ref:`Schema and metadata`
* :ref:`Powered by FastAPI`

REST endpoints over HTTP
````````````````````````

Exposing a model over HTTP/REST requires a single call to ``kernel.register()``. Custom endpoints are supported via the ``@action`` decorator.

Assuming you have a User class extending :class:`Model`::

    class User(Model, MongoRepository):
        ...

    if __name__ == '__main__':
        kernel = AppKernelEngine('demo app')
        kernel.register(User)
        kernel.run()

By default, ``register()`` exposes the resource with the GET method only. To enable the full set of HTTP methods::

    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])

Securing access to a resource is equally straightforward::

    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all() \
        .require(Role('user'), methods='GET') \
        .require(Role('admin'), methods=['PUT', 'POST', 'PATCH', 'DELETE'])

This configuration grants GET access to authenticated users with the ``user`` role, and write access to those with the ``admin`` role.
See the :ref:`Role Based Access Management` section for details.


Full range of CRUD operations
`````````````````````````````

AppKernel follows the REST convention for CRUD operations:

* **GET**: retrieve all, some, or one model instance;
* **POST**: create a new instance or update an existing one;
* **PUT**: replace an existing instance;
* **PATCH**: add or remove selected fields from an existing instance;
* **DELETE**: delete an existing instance;

The URL path is derived from the class name by convention.

Examples::

    kernel.register(User)

Exposes the User model at ``http://localhost/users/``.
An individual user with ID 12345678912 is accessible at ``http://localhost/users/12345678912``.

To add a URL prefix (e.g. for API versioning)::

    kernel.register(User, url_base='/api/v1/')

The User model is then available at ``http://localhost/api/v1/users/``.

Example response for ``GET /api/v1/users/U9dbd7a25-8059-4005-8067-09093d9e4b06``::

    {
        "_links": {
            "collection": {
                "href": "/users/",
                "methods": "GET"
            },
            "self": {
                "href": "/users/U9dbd7a25-8059-4005-8067-09093d9e4b06",
                "methods": ["GET"]
            }
        },
        "_type": "User",
        "created": "2018-06-22T21:59:34.812000",
        "id": "U9dbd7a25-8059-4005-8067-09093d9e4b06",
        "name": "some_user"
    }

If the ID is not found, a 404 is returned::

    404 NOT FOUND -> {
        "_type": "ErrorMessage",
        "code": 404,
        "message": "Document with id 1234 is not found."
    }

Delete Model
............

::

    curl -X DELETE http://localhost/users/U9dbd7a25-8059-4005-8067-09093d9e4b06
    200 OK -> {
        "_type": "OperationResult",
        "result": 1
    }

Create (POST)
.............

Submit a JSON body to create a new instance::

    curl -X POST \
        -H "Content-Type: application/json" \
        -d '{"birth_date": "1980-06-30T00:00:00", "name": "some_user", "password": "some_pass", "roles": ["User", "Admin"]}' \
        http://localhost/users/

    201 CREATED -> {
        "_type": "OperationResult",
        "result": "U956c0b3c-cf5d-4bf5-beef-370cd7217383"
    }

Multi-part form data is also accepted::

    curl -X POST \
        -F name="some_user" \
        -F password="some pass" \
        -F birth_date="1980-06-30T00:00:00" \
        http://localhost/users/

    201 CREATED -> {
        "_type": "OperationResult",
        "result": "U0054c3b6-dc0a-43ef-a10f-1ff705e90c36"
    }

Filtering and Sorting
`````````````````````

Add query parameters after ``?``. Multiple parameters are joined with ``&``.

Between
.......

Users with a birth date in a given range::

    curl "http://localhost/users/?birth_date=>1980-06-30&birth_date=<1985-08-01&logic=AND"

Contains
........

Users whose name contains 'Jane'::

    curl "http://localhost/users/?name=~Jane"

Match values in an array::

    curl "http://localhost/users/?roles=~Admin"

In
..

Match one of several values::

    curl "http://localhost/users/?name=[Jane,John]"

Or
..

Match either of two values::

    curl "http://localhost/users/?name=Jane&name=John&logic=OR"

Not equal
.........

All users whose name is not 'Max'::

    curl "http://localhost/users/?name=!Max"

Native MongoDB query
....................

Pass a raw MongoDB query expression::

    curl "http://localhost/users/?query={\"$or\":[{\"name\":\"John\"},{\"name\":\"Jane\"}]}"

Sort
....

Sort by field::

    curl "http://localhost/users/?birth_date=>1980-06-30&sort_by=birth_date"

Specify sort order::

    curl "http://localhost/users/?birth_date=>1980-06-30&sort_by=sequence&sort_order=DESC"


Pagination
``````````

Use ``page`` and ``page_size``::

    curl "http://localhost/users/?page=1&page_size=5"

Combined with sorting::

    curl "http://localhost/users/?page=1&page_size=5&sort_by=sequence&sort_order=DESC"

MongoDB Aggregation Pipeline
............................

::

    curl "http://localhost/users/aggregate/?pipe=[{\"$match\":{\"name\":\"Jane\"}}]"

.. _Aggregation Pipeline: https://docs.mongodb.com/manual/aggregation/

Custom resource endpoints
`````````````````````````

The ``@action`` decorator exposes custom methods as REST endpoints. The decorator accepts an HTTP method
and an optional ``require`` list of permission objects::

    class User(Model, MongoRepository):
        ...

        @action(require=Anonymous())
        def get_description(self):
            return self.description

The method is accessible at::

    curl http://localhost/users/U32268472-d9e3-46d9-86a2-a80926bd770b/get_description

A more complete example — allowing users and admins to change passwords::

    @action(method='POST', require=[CurrentSubject(), Role('admin')])
    def change_password(self, current_password, new_password):
        if not pbkdf2_sha256.verify(current_password, self.password):
            raise ServiceException(403, _('Current password is not correct'))
        self.password = new_password
        self.save()
        return _('Password changed')

The permission objects used with ``require``:

- **CurrentSubject**: grants access when the JWT token subject matches the model's ``id``;
- **Role**: grants access to any user holding the specified role;

HATEOAS
```````

HATEOAS_ support is enabled by default when a model is registered. Each response includes a ``_links`` section
with browseable URLs that describe the available methods::

    {
      "_links": {
        "change_password": {
          "args": ["current_password", "new_password"],
          "href": "/users/Ua4453112-0e7a-4f10-b95b-0d9b88493193/change_password",
          "methods": "POST"
        },
        "collection": {
          "href": "/users/",
          "methods": "GET"
        },
        "get_description": {
          "href": "/users/Ua4453112-0e7a-4f10-b95b-0d9b88493193/get_description",
          "methods": "GET"
        },
        "self": {
          "href": "/users/Ua4453112-0e7a-4f10-b95b-0d9b88493193",
          "methods": ["GET", "PUT", "POST", "PATCH", "DELETE"]
        }
      },
      "_type": "User",
      "id": "Ua4453112-0e7a-4f10-b95b-0d9b88493193",
      "name": "test user",
      "roles": ["Admin", "User", "Operator"]
    }

To disable HATEOAS for a specific resource::

    kernel.register(User, enable_hateoas=False)

.. _HATEOAS: https://en.wikipedia.org/wiki/HATEOAS

HTTP Method Hooks
``````````````````

Implement ``before_<method>`` or ``after_<method>`` class methods to hook into the request lifecycle.
The hook receives the deserialised model instance via ``kwargs['model']``::

    @classmethod
    def before_post(cls, *args, **kwargs):
        order = kwargs['model']
        # Perform pre-save business logic here

Schema and metadata
``````````````````

All models expose a JSON schema endpoint and a proprietary metadata endpoint.

JSON schema (usable for client-side validation)::

    curl http://localhost/users/schema

UI metadata (optimised for frontend rendering)::

    curl http://localhost/users/meta

Powered by FastAPI
``````````````````

The REST service engine is built on FastAPI_ and served by Uvicorn_. The underlying ``FastAPI`` application
instance is always accessible at ``kernel.app`` for advanced customisation::

    from fastapi import FastAPI
    kernel = AppKernelEngine('my-service')
    app: FastAPI = kernel.app

.. _FastAPI: https://fastapi.tiangolo.com/
.. _Uvicorn: https://www.uvicorn.org/
