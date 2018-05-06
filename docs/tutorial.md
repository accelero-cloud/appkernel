## Creating a small task manager application

Create a simple task and persist it in the database.
```python
from appkernel.model import *
from appkernel.repository import *

class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=uui_generator('T'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str, required=True, validators=[NotEmpty])
    tags = Parameter(list, sub_type=str)
    completed = Parameter(bool, required=True, default_value=False)
    created = Parameter(datetime, required=True, generator=date_now_generator)
    closed_date = Parameter(datetime, validators=[Past])

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()
```

#### Base Concepts
Query methods which refer to the whole collection are all class-methods (eg. t = Task.find_by_id() vs. t.delete()).

###
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
