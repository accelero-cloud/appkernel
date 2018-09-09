# appkernel - microservices made easy


![alt build_status](https://travis-ci.org/accelero-cloud/appkernel.svg?branch=master "build status")
![alt issues](https://img.shields.io/github/issues/accelero-cloud/appkernel.svg "Open issues")
![alt coverage](https://codecov.io/gh/accelero-cloud/appkernel/branch/master/graph/badge.svg "code coverage")
![GitHub license](https://img.shields.io/github/license/accelero-cloud/appkernel.svg "license")

## What is Appkernel?
A REST API  framework, which enables micro-service development from zero to production within minutes (no kidding: literally within minutes).

**It provides data serialisation, transformation, validation, security, ORM, RPC and service mash functions out of the box** ([check out the roadmap for more details](docs/roadmap.md)).
- [Full documentation on Read The Docs](http://appkernel.readthedocs.io/en/latest/)

**Give a vote on [awesome-python](https://github.com/vinta/awesome-python/pull/1103)** if you like the project, so it gets added to the list of RESTful python frameworks. **Only 16 more votes are missing :)**

## Installation

```bash
    pip install appkernel
```

## Crash Course
Let's build an awseome mini identity service:
```python
class User(Model, MongoRepository):
    id = Property(str)
    name = Property(str, index=UniqueIndex)
    email = Property(str, validators=[Email], index=UniqueIndex)
    password = Property(str, converter=content_hasher(), omit=True)
    roles = Property(list, sub_type=str, default_value=['Login'])

    @classmethod
    def before_post(cls, *args, **kwargs):
        user = kwargs.get('model')
        print(f'going to create the following user: {user}')

kernel = AppKernelEngine(__name__, app=Flask(__name__))

if __name__ == '__main__':
    # let's expose the user resource
    kernel.register(User)

    # let's create a sample user
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()
    # and we are all set
    kernel.run()
```
That's all folks, our user service is ready to roll, the entity is saved, we can re-load the object from the database, or we can request its json schema for validation, or metadata to generate an SPA (Single Page Application).
Of course validation and some more goodies are built-in as well :)

### Retrieving our our User, using HTTP requests

**GET request**:
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

Adding extra and secure methods using the `@action` decorator is easy as well:

```python
@action(method='POST', require=[CurrentSubject(), Role('admin')])
def change_password(self, current_password, new_password):
    if not pbkdf2_sha256.verify(current_password, self.password):
        raise ServiceException(403, _('Current password is not correct'))
    else:
        self.password = new_password
        self.save()
    return _('Password changed')
```

The example above exposes the `http://base_url/users/<user_id>/change_password` endpoint and allows the user with admin
role or the user with the current user_id to call it.

Create additional hooks, which are called before and after a HTTP method is executed, by simply adding
a static method to the `Model` class following the convention: `before_{http_method}` and `after_{http_method}`:

**Example**:
```python
@classmethod
def before_post(cls, *args, **kwargs):
    user = kwargs.get('model')
    print(f'going to create this user: {user}')
```

or inspect (and alter) the already persisted object:

```python
@classmethod
def after_post(cls, *args, **kwargs):
    user = kwargs.get('model')
    print(f'this user was created: {user}')
```

We can also call other services using the built-in REST client proxy. In the snippet bellow we call the `reservations` endpoint
on the Inventory service, by POST-ing a `Reservation` object.

```python
    client = HttpClientServiceProxy('http://127.0.0.1:5000/')
    status_code, rsp_dict = client.reservations.post(Reservation(order_id=order.id, products=order.products))
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

Atomic updates:
```python
# reserve 10 products with product code TRS abd size M
query = StockInventory.where((StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.M))
for _ in range(10):
    ...
    query.update(available=StockInventory.available - 1, reserved=StockInventory.reserved + 1)
```

One could extend the *AuditedMongoRepository* mixin instead of the *MongoRepository* and we would end up with 3 extra fields:
- **inserted**: the date-time of insertion;
- **updated**: the date-time of the last update;
- **version**: the number of versions stored for this document;

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
### Security is also part of the mix

The following snippet shows the declarative way of access control:
```python
user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])
```

1. user_service.deny_all(): by default access to all methods is forbidden;
2. require(Role('user'), methods='GET'): GET methods can be used by users having the Role: user (basic login role);
3. require(Role('admin'), methods=['PUT', 'POST', 'PATCH', 'DELETE']): one needs the Role: admin in order to call other http methods;

[I want to know the current status of the project](docs/roadmap.md)

[For more details feel free to check out the documentation](http://appkernel.readthedocs.io)

## What are we building here?
The vision of the project is to provide you with a full-fledged [microservice chassis](http://microservices.io/microservices/news/2016/02/21/microservice-chassis.html),
as defined by Chris Richardson.

## How does it helps you?
We've spent the time on analysing the stack, made the hard choices for you in terms of Database/ORM/Security/Rate Limiting and so on, so
you don't have to. You can focus entirely on delivering business value from day one and being the rockstar of your project.

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
