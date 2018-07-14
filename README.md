# appkernel - microservices made easy


![alt build_status](https://travis-ci.org/accelero-cloud/appkernel.svg?branch=master "build status")
![alt issues](https://img.shields.io/github/issues/accelero-cloud/appkernel.svg "Open issues")
![GitHub license](https://img.shields.io/github/license/accelero-cloud/appkernel.svg "license")

## What is Appkernel?
A beautiful python framework "for humans", enabling you to deliver a REST enabled micro-services from zero to production within minutes (no kidding: literally within minutes).

- [Full documentation on Read The Docs](http://appkernel.readthedocs.io/en/latest/)
- [Roadmap](docs/roadmap.md)

## How does it helps you?
We've spent the time on analysing the stack, made the hard choices for you in terms of Database/ORM/Security/Rate Limiting and so on, so
you don't have to. You can focus entirely on delivering business value from day one and being the rockstar of your project.

License: [Apache 2](docs/license.md)

## Crash Course
Let's build a mini identity service:
```python
class User(Model, MongoRepository, Service):
    id = Property(str)
    name = Property(str, validators=[NotEmpty], index=UniqueIndex)
    email = Property(str, validators=[Email, NotEmpty], index=UniqueIndex)
    password = Property(str, validators=[NotEmpty],
                         converter=content_hasher(), omit=True)
    roles = Property(list, sub_type=str, default_value=['Login'])

application_id = 'identity management app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)

if __name__ == '__main__':
    kernel.register(User)

    # let's create a sample user
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()

    kernel.run()
```
That's all folks, our user service is ready to roll, the entity is saved, we can re-load the object from the database, or we can request its json schema for validation, or metadata to generate an SPA (Single Page Application).
Of course validation and some more goodies are built-in as well :)

**Let's issue a MongoDB query**: *db.getCollection('Users').find({})* ...**and check the result:**
```bash
﻿{
    "_id" : "cf1368d8-b51a-4da0-b5c0-ef17eb2ba7b9",
    "email" : "test@accelero.cloud",
    "name" : "Test User",
    "password" : "$pbkdf2-sha256$10$k5ISAqD0Xotxbg3hPCckBA$Kqssb.bTTHWj0clZZZavJBqWttHq0ePsYdGEJYXWyDk",
    "roles" : [
        "Login"
    ]
}
```

One could add the *AuditedMongoRepository* mixin instead of the *MongoRepository* to the *User* model and we would end up with 3 extra fields:
- **inserted**: the date-time of insertion;
- **updated**: the date-time of the last update;
- **version**: the number of versions stored for this document;

### Let's try to retrieve our User, using an HTTP request

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
      "email": "test@appkernel.cloud",
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
```
### Some features of the REST endpoint

- GET /users/12345 - retrieve a User object by its database ID;
- GET /users/?name=Jane&email=jane@appkernel.cloud - retrieve the User named Jane with e-mail address jane@appkernel.cloud;
- GET /users/?name=Jane&name=John&logic=OR - retrieve Jane or John;
- GET /users/?roles=~Admin - retrieve all users which have the role Admin;
- GET /users/?name=[Jane,John] - retrieve all user with the name Jane or John;
- GET /users/?inserted=>2018-01-01&inserted=<2018-12-31 - return all users created in 2018;
- GET /users/?page=1&page_size=5&sort_by=inserted&sort_order=DESC - return the first page of 5 elements;
- GET /users/?query={"$or":[{"name": "Jane"}, {"name":"John"}]} - return users filtered with a native Mongo Query;
- GET /users/meta - retrieve the metadata of the User class for constructing self-generating SPAs;
- GET /users/schema - return the Json Schema of the User class used for validating objects;

Additionally the following HTTP methods are supported:
- POST: create a new user (or updates existing one by replacing it) using a json payload or multipart form data
- PATCH: add or updates some fields on the User object
- PUT: replaces a User object

### A few features of the built-in ORM function
Find one single user matching the query Property:
```python
user = User.where(name=='Some username').find_one()
```
Return the first 5 users which have the role "Admin":
```python
user_generator = User.where(User.roles % 'Admin').find(page=0, page_size=5)
```
Or use native Mongo Query:
```python
user_generator = Project.find_by_query({'name': 'user name'})
```

## Some more extras baked into the Model
Generate the ID value automatically using a uuid generator and a prefix 'U':
```python
id = Property(..., generator=uuid_generator('U'))
```
Add a Unique index to the User's name property:
```python
name = Property(..., index=UniqueIndex)
```
Validate the e-mail property, using the NotEmpty and Email validators
```python
email = Property(..., validators=[Email, NotEmpty])
```
Add schema validation to the database:
```python
User.add_schema_validation(validation_action='error')
```
Hash the password and omit this attribute from the json representation:
```python
password = Property(..., converter=content_hasher(rounds=10), omit=True)
```
Run the generators on the attributes and validate the object (usually not needed, since it is implicitly called by save and dumps methods):
```python
user.finalise_and_validate()
```
[I want to know the current status of the project](docs/roadmap.md)

[For more details feel free to check out the documentation](http://appkernel.readthedocs.io)

## What are we building here?
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

### Contribute
Be part of the development: [contribute to the project :)](docs/contributors.md)

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
