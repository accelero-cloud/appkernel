# appkernel - a microservice framework
License: [Apache 2](docs/license.md)

**Work in progress / documentation is a progress**

**Python micro-services made easy**: a beautiful and opinionated micro-service framework which enables you
to deliver a REST application from zero to production within minutes (no kiddin' literally within minutes).
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
That was easy, isn't it? now one can use curl or other rest client to create/delete tasks. It features validation, JSON serialisation, database persistency, strategies for automatic data generation.


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

### How can I use it?
TBD;

### What is the current state?
TBD;