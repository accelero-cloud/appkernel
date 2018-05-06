# appkernel - microservices made easy
License: [Apache 2](docs/license.md)

**Work in progress / documentation is a progress**

**Python micro-services made easy**: a beautiful micro-service framework ("for humans") enabling you
to deliver a REST enabled micro-service from zero to production within minutes (literally within minutes).

```python
class User(Model, MongoRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    email = Parameter(str, required=True, validators=[Email, NotEmpty])
    password = Parameter(str, required=True, validators=[NotEmpty],
                         to_value_converter=create_password_hasher(rounds=10), omit=True)
    roles = Parameter(list, sub_type=str, default_value=['Login'])

application_id = 'task_management_app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)

if __name__ == '__main__':
    kernel.register(User)
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()
    kernel.run()
```
That's all folks, our user service is ready to roll, the entity is saved, we can load the saved object, as well we can request its json schema :)

The result of the Mongo query: db.getCollection('Users').find({})
```json
﻿{
    "_id" : "Ucf1368d8-b51a-4da0-b5c0-ef17eb2ba7b9",
    "email" : "test@accelero.cloud",
    "inserted" : ISODate("2018-05-06T22:57:11.742Z"),
    "name" : "Test User",
    "password" : "$pbkdf2-sha256$10$k5ISAqD0Xotxbg3hPCckBA$Kqssb.bTTHWj0clZZZavJBqWttHq0ePsYdGEJYXWyDk",
    "roles" : [
        "Login"
    ],
    "updated" : ISODate("2018-05-06T22:57:11.742Z"),
    "version" : 1
}
```
### Let's try to retrieve it via REST

**Rest request**:
```bash
curl -i -X GET \
 'http://127.0.0.1:5000/users/'
```
**And the result**:
```json
{
  "_items": [
    {
      "_type": "User",
      "email": "test@accelero.cloud",
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
  },
  "_type": "User"
}
```
### Features of the REST endpoint

- GET /users/12345 - retrieve a User object by its database ID
- GET /users/?name=Jane&email=jane@accelero.cloud - retrieve the User object by attribute query
- GET /users/?name=Jane&name=John&logic=OR - retrieve the User object using an OR query
- GET /users/?roles=~Admin - retrieve all users which have the role Admin
- GET /users/?name=[Jane,John] - retrieve all user with the name Jane or John
- GET /users/?inserted=>2018-01-01&inserted=<2018-12-31 - return all users created in 2018
- GET /users/?page=1&page_size=5&sort_by=inserted&sort_order=DESC - return the first page of 5 elements
- GET /users/?query={"$or":[{"name":", {"name":"Jona"}]} - return users filtered by native Mongo Query
- GET /users/meta - retrieve the metadata of the User class
- GET /users/schema - return the Json Schema of the User class

Additionally the following HTTP methods are supported:
- POST: create a new user (or updates existing one by replacing it) using a json payload or multipart form data
- PATCH: add or updates some fields on the User object
- PUT: replaces a User object

### A few features of the built-in ORM functions
- user = User.where(name=='Some username').find_one() - find one single user matching the query parameter;
- user = User.where(User.roles % 'Admin').find(page=0, page_size=5) - return the first 5 users which have the role "Admin"
- user_generator = Project.find_by_query({'name': 'user name'}) -use native Mongo Query

## Implicit features
- user.finalise_and_validate()

For more details feel free to check out the documentation :)

## Where are we gonna go?
The vision of the project is to provide you with a full-fledged [microservice chassis](http://microservices.io/microservices/news/2016/02/21/microservice-chassis.html),
as defined by Chris Richardson.


Currently supported (and fully tested) features:
- REST endpoints over HTTP
- Full range of CRUD operations
- Customizable resource endpoints
- Customizable, multiple item endpoints
- Filtering and Sorting
- Pagination
- Data Validation
- Extensible Data Validation
- Default Values
- Projections
- Embedded Resource Serialization
- Custom ID Fields
- MongoDB Aggregation Framework
- Powered by Flask

## Why Appkernel?
We've spent the time on analysing the stack, made the hard choices for you in terms of Database/ORM/Security/Rate Limiting and so on, so
you don't have to. You can focus entirely on your logic and become the rockstar hero delivering business value on day one of your project.

## Crash course
*Because a short example tells more than a thousands of words*: let's create a simple task management application which stores tasks in MongoDB and exposes them via a RESTful service (create, retrieve, delete).

### Define the model
```python
class Task(Model, AuditableRepository, Service):
    id = Parameter(str, required=True)
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str)
    tags = Parameter(list, sub_type=str)
    completed = Parameter(bool, required=True, default_value=False)
    closed_date = Parameter(datetime, validators=[Past])

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        """
        Mark the task complete and set the completion date to now;
        """
        self.completed = True
        self.closed_date = datetime.now()
```
### Use the builtin fluent-factory api to create and save new objects
```python
    task = Task().update(name='develop appkernel',
                         description='deliver the first version and spread the word.') \
        .append_to(tags=['fun', 'important'])
    task.save()
```
This will create the following document in MongoDB:
```
{
    "_id" : "U7b7453b8-6ed3-42e5-917f-86a657285279",
    "updated" : ISODate("2018-04-07T17:49:10.777Z"),
    "description" : "deliver the first version and spread the word.",
    "tags" : [
        "fun",
        "important"
    ],
    "completed" : false,
    "name" : "develop appkernel",
    "version" : 1,
    "inserted" : ISODate("2018-04-07T17:49:10.777Z")
}
```
Mind the **version**, **inserted** and **updated** fields. These are added automagically, because our model have extended the AuditableRepository class.
In case you don't need those extra fields, you can extend MongoRepository instead.

That's all folks ;)

### Expose the model over HTTP as a REST service
```python
app = Flask(__name__)
kernel = AppKernelEngine('test_app', app=app)

def init_app():
    kernel.register(Task)
    kernel.run()

if __name__ == '__main__':
    init_app()
```
Now we are ready to call the endpoint. Let's use curl for the sake of simplicity:
```bash
curl -i -X GET \
 'http://127.0.0.1:5000/tasks/'
```
And here's the return value:
```json
[
  {
    "completed": false,
    "description": "deliver the first version and spread the word.",
    "id": "U7b7453b8-6ed3-42e5-917f-86a657285279",
    "inserted": "2018-04-07T17:49:10.777000",
    "name": "develop appkernel",
    "tags": [
      "fun",
      "important"
    ],
    "type": "Task",
    "updated": "2018-04-07T17:49:10.777000",
    "version": 1
  }
]
```
Mind a new property, called **type**. This can be used by the client application in order to decide which parser of parsing method to use for this object.

That was easy, isn't it? now one can use curl or other rest client to create/delete and further modify tasks. It features validation, JSON serialisation, database persistency, strategies for automatic data generation.

[I want to know more. Bring me to the tutorial](docs/tutorial.md)

### Why did we built this?
* We had the need to build a myriad of small services in our daily business, ranging from data-aggregation pipelines, to housekeeping services and
other process automation services. These do share similar requirements and the underlying infrastructure needed to be rebuilt and tested over and over again. The question arose:
what if we avoid spending valuable time on the boilerplate and focus only on the fun part?

* Often time takes a substantial effort to make a valuable internal hack or proof of concept presentable to customers, until it reaches the maturity in terms reliability, fault
tolerance and security. What if all these non-functional requirements would be taken care by an underlying platform?

* There are several initiatives out there (Flask Admin, Flask Rest Extension and so), which do target parts of the problem, but they either need substantial effort to make them play nice together, either they feel complicated and uneasy to use.
We wanted something simple and beautiful, which we love working with.

These were the major driving question, which lead to the development of App Kernel.

### How does it works?

AppKernel is built around the concepts of Domain Driven Design. You can start the project by laying out the model.
The first step is to define the validation and data generations rules. For making life easier, one can also set default values.
Than one can extend several built-in classes in order to augment the model with extended functionality:
* extending the Repository class (or its descendants) adds and ORM persistency capability to the model;
* extending the Service class (or its descendants) add the capablity to expose the model over REST services;

### How can I use it?
TBD;

### What is the current state?
TBD;