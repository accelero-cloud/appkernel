# appkernel - microservices made easy
License: [Apache 2](docs/license.md)

**Work in progress / documentation in progress**

## What is Appkernel?
A beautiful micro-service framework ("for humans"), enabling you to deliver a REST enabled micro-service from zero to production within minutes (literally within minutes).

## What's in it for you?
We've spent the time on analysing the stack, made the hard choices for you in terms of Database/ORM/Security/Rate Limiting and so on, so
you don't have to. You can focus entirely on delivering the business value on day one and enjoy being the rockstar of your project.

## Crash Course
Let's build a mini identity service:
```python
class User(Model, AuditedMongoRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty], index=UniqueIndex)
    email = Parameter(str, required=True, validators=[Email, NotEmpty], index=UniqueIndex)
    password = Parameter(str, required=True, validators=[NotEmpty],
                         to_value_converter=create_password_hasher(rounds=10), omit=True)
    roles = Parameter(list, sub_type=str, default_value=['Login'])

application_id = 'identity management app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)

if __name__ == '__main__':
    kernel.register(User)
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()
    kernel.run()
```
That's all folks, our user service is ready to roll, the entity is saved, we can re-load the object from the database, or we can request its json schema, metadata.
Of course validation and some more goodies are built-in as well :)

**Let's issue a Mongo query**: *db.getCollection('Users').find({})* ...**and checkout the result:**
```bash
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
Due to the AuditedMongoRepository mixin, which we've added to the User model, we ended up with 3 extra fields:
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
  }
}
```
### Some features of the REST endpoint

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

### A few features of the built-in ORM function
Find one single user matching the query parameter:
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

## Some more extras
Generate the ID value automatically using a uuid generator and a prefix 'U':
```python
id = Parameter(..., generator=uuid_generator('U'))
```
Add a Unique index to the User's name property:
```python
name = Parameter(..., index=UniqueIndex)
```
Validate the e-mail property, using the NotEmpty and Email validators
```python
email = Parameter(..., validators=[Email, NotEmpty])
```
Add schema validation to the database:
```python
User.add_schema_validation(validation_action='error')
```
Hash the password and omit this attribute from the json representation:
```python
password = Parameter(..., to_value_converter=create_password_hasher(rounds=10), omit=True)
```
Run the generators and validate the object (usually not needed, since it is implicitly called by save and dumps methods):
```python
user.finalise_and_validate()
```
[I want to know more. Bring me to the tutorial](docs/tutorial.md)

For more details feel free to check out the documentation :)

## What is getting built here?
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