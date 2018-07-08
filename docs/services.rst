Services
========
The vision of the project is to provide you with a full-fledged microservice chassis, as defined by Chris Richardson.

.. warning::
    Work in progress section of documentation.


* :ref:`REST endpoints over HTTP`
* :ref:`Full range of CRUD operations`
* :ref:`Filtering and Sorting`
* :ref:`Pagination`
* :ref:`Embedded Resource Serialization`
* :ref:`Projections`
* :ref:`Custom resource endpoints`
* :ref:`HATEOAS`
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

The `register` method from the above example will expose the `User` entity at `http://localhost/users` with the GET method supported by default (list all, some or one user).
In case you would like to add support for the rest of the HTTP methods (pun intended) - so you can create new users or delete existing ones - you would need to explicitly specify them in the `register` method body
(for more details check out the :ref:`Full range of CRUD operations` section). ::

    kernel.register(User methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])

Securing service access is also no-brainer: ::

    kernel.enable_security()
    user_service = kernel.register(User methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])

The configuration above will permit the access of the GET method to all clients authenticated with the role `user`, however it requires the role
`admin` for the rest of the HTTP methods.
Check out the details in the :ref:`Role Based Access Management` section.


Full range of CRUD operations
`````````````````````````````
Appkernel follows the REST convention for CRUD ((CR)eate(U)pdate(D)elete) operations. Use the method:

* GET: to retrieve all, some or one model instance (entity);
* POST: to create a new entity or update an existing one;
* PUT: to replace an existing model instance;
* PATCH: to add or remove selected properties from an existing model instance;
* DELETE: to delete an existing model instance;

The url path is the lowercase class-name by convention (possibly prefixed with the `url_base` segment.
Examples: ::

    kernel.register(User)

Will expose the User model under: `http://localhost/user`.
The user with ID 12345678912 will be accessible at: `http://localhost/user/12345678912`

In case you would like to use a path prefix (eg. for verioning the API) you can register the model with a `url_base` segment: ::

    kernel.register(User, url_base='/api/v1/')

In this case the Use model is available at `http://localhost/api/v1/user` and `http://localhost/api/v1/user/12345678912` respectively.
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

Deleting an object is as simple is returning it. Only the method needs to be changed from GET to DELETE. ::

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

    curl -X GET http://localhost/users/?birth_date=>1980-06-30&birth_date=<1985-08-01&logic=AND


Contains
........
Search for users which contain `Jane` in the name property: ::

    curl -X GET http://localhost/users/?name=~Jane

You can also search values within an array ::

    curl -X GET http://localhost/users/?roles=~Admin

In
..

Search value within an array: ::

    curl -X GET http://localhost/users/?name=[Jane,John]

Or
..

You can search for `Jane` or `John`: ::

    curl -X GET http://localhost/users/?name=Jane&name=John&logic=OR
or: ::

    curl -X GET http://localhost/users/?name=~Jane&&enabled=false

Not equal
.........
Search all users which does not contain `Max` in the name property: ::

    curl -X GET http://localhost/users/?name=!Max

Using Mongo query expression
............................

Native Mongo Queries can be always provided as query parameters: ::

    curl -X GET http://localhost/users/?query={"$or":[{"name":"John"}, {"name":"Jane"}]}

Sort
....
Sorting the result set is also easy, by using the `sort_by` expression: ::

    curl -X GET http://localhost/users/?birth_date=>1980-06-30&sort_by=birth_date

Additionally you can specify the sort order: ::

    curl -X GET http://localhost/users/?birth_date=>1980-06-30&sort_by=sequence&sort_order=DESC


Pagination
``````````

Pagination is supported with the use of `page` and `page_size`: ::

    curl -X GET http://localhost/users/?page=1&page_size=5

... and of course sorting can be used in combination with pagination: ::

    curl -X GET http://localhost/users/?page=1&page_size=5&sort_by=sequence&sort_order=DESC

Mongo Aggregation Pipeline
..........................

Additionally to native queries, `Aggregation Pipeline`_ is supported too: ::

    curl -X GET http://localhost/users/aggregate/?pipe=[{"$match":{"name": "Jane"}}]

.. Aggregation Pipeline_: https://docs.mongodb.com/manual/aggregation/

Custom resource endpoints
`````````````````````````
The built-in CRUD operations might be a good start, however you;


HATEOAS
```````

Powered by Flask
````````````````
