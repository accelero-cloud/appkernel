## Repository

#### Features
- [ ] validation and schema management
- [x] validation on the data model using multiple custom validators
- [x] builtin converters for serialising or deserialising the model to various other formats
- [x] automated marshaling of objects to and from json
- [x] basic CRUD operations
- [x] audited fields (created, updated)
- [ ] index management on the database
- [x] automatically generate prefixed database ID
- [ ] simplified logging
- [ ] REST services
- [ ] HATEOAS actions on model
- [ ] graphql support
- [ ] swagger support
- [ ] scheduler and background task executor
- [ ] basic authentication and JWT token support
- [ ] OAUTH
- [ ] rate limiting and circuit breaker

## Creating a small task manager application

Create a simple task and persist it in the database.
```python
from appkernel.model import *
from appkernel.repository import *

class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=uui_generator('U'))
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