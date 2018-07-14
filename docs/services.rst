Services
========

.. warning::
    Work in progress section of documentation.


* :ref:`REST endpoints over HTTP`
* :ref:`Full range of CRUD operations`
* :ref:`Filtering and Sorting`
* :ref:`Pagination`
* :ref:`Custom resource endpoints`
* :ref:`HATEOAS`
* :ref:`Shema and metadata`
* :ref:`Powered by Flask`

REST endpoints over HTTP
````````````````````````
Exposing your models over HTTP/REST is easy and :ref:`Custom resource endpoints` are supported as well.

Let's assume that we have created a User class extending the :class:`Model` and the :class:`Service`. Now we'd like to expose it as a REST endpoint: ::

    class User(Model, MongoRepository, Service):
        ...

    if __name__ == '__main__':
        app = Flask(__name__)
        kernel = AppKernelEngine('demo app', app=app)
        kernel.register(User)
        kernel.run()

The `register` method from the above example will expose the `User` entity at `http://localhost/users` with the GET method supported by default.
In case we would like to add support for the rest of the HTTP methods (pun intended), we would need to explicitly specify them in the `register` method
(for more details check out the :ref:`Full range of CRUD operations` section). ::

    kernel.register(User methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])

Securing service access is also no-brainer: ::

    kernel.enable_security()
    user_service = kernel.register(User methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])

The configuration above will permit the access of the GET method to all clients authenticated with the role `user`, however it requires the role
`admin` for the rest of the HTTP methods.
Check out the details in the :ref:`Role Based Access Management` section for more details.


Full range of CRUD operations
`````````````````````````````
Appkernel follows the REST convention for CRUD ((CR)eate(U)pdate(D)elete) operations:

* GET: to retrieve all, some or one model instance (entity);
* POST: to create a new entity or update an existing one;
* PUT: to replace an existing model instance;
* PATCH: to add or remove selected properties from an existing model instance;
* DELETE: to delete an existing model instance;

The path is automatically created from the class-name by convention.

Examples: ::

    kernel.register(User)

This will expose the User model under: `http://localhost/user`.

The user with ID 12345678912 will be accessible at: `http://localhost/user/12345678912`

In case you would like to use a path prefix (eg. for verioning the API) you can register the model with a `url_base` segment: ::

    kernel.register(User, url_base='/api/v1/')

In this case the User model is available at `http://localhost/api/v1/user` and `http://localhost/api/v1/user/12345678912` respectively.

Let's check out one example with `curls -X get http://localhost/api/v1/user/U9dbd7a25-8059-4005-8067-09093d9e4b06`::

    {
        "_links": {
            "collection": {
                "href": "/users/",
                "methods": "GET"
            },
            "self": {
                "href": "/users/U9dbd7a25-8059-4005-8067-09093d9e4b06",
                "methods": [
                    "GET"
                ]
            }
        },
        "_type": "User",
        "created": "2018-06-22T21:59:34.812000",
        "id": "U9dbd7a25-8059-4005-8067-09093d9e4b06",
        "name": "some_user"
    }

In case the ID is not found in the database, a 404 Not found error will be returned. ::

    Response: 404 NOT FOUND -> {
        "_type": "ErrorMessage",
        "code": 404,
        "message": "Document with id 1234 is not found."
    }

Delete Model
............

Deleting an object is simple as well. Only that the method needs to be changed from GET to DELETE in the request. ::

    curl -X DELETE http://localhost/U9dbd7a25-8059-4005-8067-09093d9e4b06
    Response: 200 OK -> {
        "_type": "OperationResult",
        "result": 1
    }

Create (POST)
.............

Use json body for creating new instances: ::

    curl -X POST --data {"birth_date": "1980-06-30T00:00:00", "description": "some description", "name": "some_user", "password": "some_pass", "roles": ["User", "Admin", "Operator"]} http://localhost/users/

    Response: 201 CREATED -> {
        "_type": "OperationResult",
        "result": "U956c0b3c-cf5d-4bf5-beef-370cd7217383"
    }

Alternatively you can send data as multi-part form data: ::

    curl -X POST \
        -F name="some_user" \
        -F description="soe" \
        -F password="some pass" \
        -F birth_date="1980-06-30T00:00:00" \
        -F roles=["User", "Admin", "Operator"] \
        http://localhost/users

    Response: 201 CREATED ->
    {
        "_type": "OperationResult",
        "result": "U0054c3b6-dc0a-43ef-a10f-1ff705e90c36"
    }

Filtering and Sorting
`````````````````````
Query parameters are added to the end of the URL with a '?' mark. You can use any of the properties defined on the Model class.
You can chain multiple parameters with the '&' (and) mark.

Between
.......
Search users with a birth date between date: ::

    curl http://localhost/users/?birth_date=>1980-06-30&birth_date=<1985-08-01&logic=AND


Contains
........
Search for users which contain `Jane` in the name property: ::

    curl http://localhost/users/?name=~Jane

You can also search values within an array ::

    curl http://localhost/users/?roles=~Admin

In
..

Search value within an array: ::

    curl http://localhost/users/?name=[Jane,John]

Or
..

You can search for `Jane` or `John`: ::

    curl http://localhost/users/?name=Jane&name=John&logic=OR
or: ::

    curl http://localhost/users/?name=~Jane&&enabled=false

Not equal
.........
Search all users which does not contain `Max` in the name property: ::

    curl http://localhost/users/?name=!Max

Using Mongo query expression
............................

Native Mongo Queries can be always provided as query parameters: ::

    curl http://localhost/users/?query={"$or":[{"name":"John"}, {"name":"Jane"}]}

Sort
....
Sorting the result set is also easy, by using the `sort_by` expression: ::

    curl http://localhost/users/?birth_date=>1980-06-30&sort_by=birth_date

Additionally you can specify the sort order: ::

    curl http://localhost/users/?birth_date=>1980-06-30&sort_by=sequence&sort_order=DESC


Pagination
``````````

Pagination is supported with the use of `page` and `page_size`: ::

    curl http://localhost/users/?page=1&page_size=5

... and of course sorting can be used in combination with pagination: ::

    curl http://localhost/users/?page=1&page_size=5&sort_by=sequence&sort_order=DESC

Mongo Aggregation Pipeline
..........................

Additionally to native queries, `Aggregation Pipeline`_ is supported too: ::

    curl http://localhost/users/aggregate/?pipe=[{"$match":{"name": "Jane"}}]


.. Aggregation Pipeline_: https://docs.mongodb.com/manual/aggregation/

Custom resource endpoints
`````````````````````````
The built-in CRUD operations might be a good start for your application, however we would quickly run into situation where
custom functionality needs to be exposed to the API consumers.
In such cases the `@link` decorator comes handy. Let's suppose we need to provide the result of a specific method on the User: ::

    class User(Model, MongoRepository, Service):
        ...

        @link(require=Anonymous())
        def get_description(self):
            return self.description

And we're ready to go, you have a new endpoint returning the description property of the value and any user with the role `Anonymous` can access it: ::

    curl http://localhost/users/U32268472-d9e3-46d9-86a2-a80926bd770b/get_description

Now one can argue, that this example is not utterly useful, a statement which in this case might not be very far from the common perception. However there's
much more into it. Let's say that we'd like to enable the user and the admin to change the password for the User: ::

        @link(http_method='POST', require=[CurrentSubject(), Role('admin')])
        def change_password(self, current_password, new_password):
            if not pbkdf2_sha256.verify(current_password, self.password):
                raise ServiceException(403, _('Current password is not correct'))
            else:
                self.password = new_password
                self.save()
            return _('Password changed')

The :class:`CurrentSubject` and :class:`Role` authority controls who can access the method:

- **CurrentSubject**: in case the JWT token subject is identical with the model id, the access to the method is granted;
- **Role**: enables any user having the required role type call the method;

HATEOAS
```````
By default `HATEOAS`_ support is enabled when a domain object is registered with Appkernel (`kernel.register(User)`). This means the return
result-set includes browseable urls, exposing the existing methods to your API consumer. ::

    {
      "_links": {
        "change_password": {
          "args": [
            "current_password",
            "new_password"
          ],
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
          "methods": [
            "GET",
            "PUT",
            "POST",
            "PATCH",
            "DELETE"
          ]
        }
      },
      "_type": "User",
      "created": "2018-07-08T16:05:25.539000",
      "description": "test description",
      "id": "Ua4453112-0e7a-4f10-b95b-0d9b88493193",
      "name": "test user",
      "roles": [
        "Admin",
        "User",
        "Operator"
      ]
    }

Would you not want to use the HATEOAS feature, you can chose to disable it at the Model registration phase `kernel.register(User, enable_hateoas=False)`.

.. _HATEOAS: https://en.wikipedia.org/wiki/HATEOAS

Shema and metadata
``````````````````
All models provide JSON schema and a metatada to help frontend UI generation and data validation in frontends.
Accessing the JSON schema is easy by calling **"http://root_url/{model_name}/schema"** ::

    curl http://localhost/users/schema

Accessing the metadata by calling **"http://root_url/{model_name}/meta"** is easy too: ::

    curl http://localhost/users/meta

Powered by Flask
````````````````
The REST service engine uses Flask_ under the hood, therefore the reference to the flask app is always available at `kernel.app`.

.. Flask_: http://flask.pocoo.org/