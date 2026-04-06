Repositories
============

The AppKernel repository API is influenced by `peewee`_, a small and elegant Python ORM for relational databases.
The key difference is that AppKernel's repository is optimised for (and currently only implemented for) MongoDB.
A custom repository implementation for SQL or any other database is possible by extending the :class:`Repository` base class.

.. _peewee: http://docs.peewee-orm.com/

* :ref:`Basic CRUD (Created, Update, Delete) operations`
* :ref:`Query expressions`
* :ref:`Advanced Functionality`
* :ref:`Auditable Repository`
* :ref:`Index management`
* :ref:`Schema Installation`
* :ref:`Aggregation Pipeline`

Basic CRUD (Created, Update, Delete) operations
------------------------------------------------

.. note::
    You can follow all examples in Python's interactive interpreter using the imports below.

The following setup connects to a local MongoDB instance and creates a database named **tutorial**.
In a full application, use :class:`AppKernelEngine` instead — it handles MongoDB initialisation automatically::

    from appkernel import AppKernelEngine
    kernel = AppKernelEngine('tutorial', enable_defaults=True)

For use in development or production, choose one of two configuration options:

Default configuration
.....................
When :class:`AppKernelEngine` is initialised with ``enable_defaults=True``, it connects to MongoDB on
``localhost`` and uses the database name **app**::

    kernel = AppKernelEngine('demo', enable_defaults=True)

File-based configuration
........................

On initialisation, AppKernel looks for a ``cfg.yml`` file. The following keys configure the database connection::

    appkernel:
      mongo:
        host: localhost
        db: appkernel

The ``host`` value accepts a full ``mongodb://`` connection string including credentials.

Building a base model structure
...............................

Let's create a simple project-management model with tasks::

    from datetime import datetime
    from enum import Enum
    from typing import Annotated
    from appkernel import (
        Model, MongoRepository, AuditableRepository,
        Required, Generator, Default, Validators,
        NotEmpty, Past,
        date_now_generator,
    )

    class Priority(Enum):
        HIGH = 1
        MEDIUM = 2
        LOW = 3

    class Task(Model, MongoRepository):
        name: Annotated[str | None, Required(), Validators(NotEmpty)] = None
        description: Annotated[str | None, Validators(NotEmpty)] = None
        completed: Annotated[bool | None, Required(), Default(False)] = None
        created: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None
        closed_date: Annotated[datetime | None, Validators(Past)] = None
        priority: Annotated[Priority | None, Required(), Default(Priority.MEDIUM)] = None

        def complete(self):
            self.completed = True
            self.closed_date = datetime.now()

    class Project(Model, AuditableRepository):
        id: str | None = None
        name: Annotated[str | None, Required(), Validators(NotEmpty)] = None
        tasks: list[Task] | None = None
        created: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None


Saving and updating
...................

Define a project with some tasks::

    project = Project(name='some test project')
    project.append_to(tasks=Task(name='finish the documentation', priority=Priority.HIGH))
    # Add multiple tasks at once
    project.append_to(tasks=[Task(name='finish all todos'), Task(name='complete the unit tests')])

    project.save()
    print(project.dumps(pretty_print=True))

Output::

    {
        "id": "OBJ_5b142be00df7a9647023f0b1",
        "created": "2018-06-03T19:54:06.830307",
        "name": "some test project",
        "tasks": [
            {
                "completed": false,
                "created": "2018-06-03T19:53:38.149125",
                "name": "finish the documentation",
                "priority": "HIGH"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041349",
                "name": "finish all todos",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041380",
                "name": "complete the unit tests",
                "priority": "MEDIUM"
            }
        ]
    }

Complete the first task::

    project.tasks[0].complete()
    project.save()
    print(project.dumps(pretty_print=True))

Notice ``completed`` is now ``true``, ``closed_date`` is set, and ``AuditableRepository``
has incremented the ``version`` and updated the ``updated`` timestamp::

    {
        "created": "2018-06-11T23:17:57.050000",
        "id": "OBJ_5b1ee7050df7a9087e0e8952",
        "inserted": "2018-06-11T23:17:57.050000",
        "name": "some test project",
        "tasks": [
            {
                "closed_date": "2018-06-11T23:19:39.345000",
                "completed": true,
                "created": "2018-06-11T23:17:57.050000",
                "name": "finish the documentation",
                "priority": "HIGH"
            },
            ...
        ],
        "updated": "2018-06-11T23:19:46.428000",
        "version": 2
    }


Auditable Repository
....................

:class:`AuditableRepository` automatically adds three fields to every document:

- *inserted*: the date and time the document was first created;
- *updated*: the date and time of the most recent update;
- *version*: the number of times the document has been updated;

Use :class:`MongoRepository` when you do not need audit metadata.

Delete objects
..............

Count documents::

    Project.count()
    1

Delete a single document::

    project.delete()
    1

Delete all documents in the collection::

    Project.delete_all()

Querying data
.............

AppKernel provides a query DSL built on operator overloading. The query can be passed to:

* **find** — returns a generator to iterate over the matching documents;
* **find_one** — returns the first match or ``None``;
* **where** — returns a :class:`Query` object for chaining (e.g. ``sort_by``);

A simple query::

    prj = Project.find_one(Project.name == 'some test project')
    print(prj.dumps(pretty_print=True))

Search across a nested array using dot-path chaining::

    prj = Project.find_one(Project.tasks.name % 'finish')

Alternatively, use bracket notation for element matching::

    prj2 = Project.find_one(Project.tasks[Task.name == 'finish the documentation'])

Iterate over all documents::

    for project in Project.find():
        print(project)

Iterate over matching documents::

    for prj in Project.find(Project.name == 'some test project'):
        print(prj.dumps(pretty_print=True))

Sort the result::

    query = Project.where(Project.name == 'some test project').sort_by(Project.created.asc())
    for prj in query.find():
        print(prj.dumps(pretty_print=True))

Compound expressions::

    from datetime import datetime, date
    yesterday = datetime.combine(date(2018, 6, 10), datetime.min.time())
    today = datetime.combine(date(2018, 6, 11), datetime.min.time())
    prj = Project.find_one((Project.created > yesterday) & (Project.created < today))

Pagination
..........

The following query returns the first 10 projects::

    for prj in Project.find(page=0, page_size=10):
        print(prj)

Query expressions
-----------------

Find by ID
''''''''''

::

    prj = Project.find_by_id('5b1ee9930df7a9087e0e8953')

Exact match
'''''''''''

::

    prj = Project.find_one(Project.name == 'Project A')

Not equal
'''''''''

::

    projects = Project.find(Project.name != 'Project A')

OR
''

::

    prj = Project.find_one((Project.name == 'Project A') | (Project.name == 'Project B'))

AND
'''

::

    from datetime import timedelta
    yesterday = datetime.now() - timedelta(days=1)
    prj = Project.find_one((Project.name == 'Project A') & (Project.created > yesterday))

Empty array
'''''''''''

Find all projects with no tasks::

    prj = Project.find_one(Project.tasks == None)

Contains
''''''''

Find all projects with at least one task whose name contains 'finish'::

    prj = Project.find_one(Project.tasks.name % 'finish')

Find all users who have the roles Admin **and** Operator::

    User.find(User.roles % ['Admin', 'Operator'])

Field does not exist
''''''''''''''''''''

::

    User.find(User.description == None)

Field exists (not None)
'''''''''''''''''''''''

::

    User.find(User.description != None)

Range query
'''''''''''

::

    yesterday = datetime.now() - timedelta(days=1)
    tomorrow = datetime.now() + timedelta(days=1)
    projects = Project.find((Project.created > yesterday) & (Project.created < tomorrow))

Query with custom properties
''''''''''''''''''''''''''''

Query on fields that exist in the database but are not declared on the model (e.g. audit fields added by :class:`AuditableRepository`)::

    project = Project.find_one(Project.custom_property('version') == 2)


Advanced Functionality
----------------------

Atomic updates
..............

Avoid the read-modify-write cycle for counter updates. The naive approach is slow and prone to race conditions::

    # DON'T DO THIS — vulnerable to concurrent modification
    for stock in Stock.find((Stock.product.code == 'BTX') & (Stock.product.size == ProductSize.L)):
        if stock.available > 0:
            stock.available -= 1
            stock.reserved += 1
            stock.save()
        else:
            raise ReservationException('Not enough products on stock.')

Use ``update()`` instead for a single atomic operation::

    query = Stock.where((Stock.product.code == 'BTX') & (Stock.product.size == ProductSize.L))
    res = query.update(available=Stock.available - quantity, reserved=Stock.reserved + quantity)
    if res == 0:
        raise ReservationException('No stock available for code BTX, size L.')
    elif res > 1:
        raise ReservationException(f'Multiple items reserved ({res}).')

Native queries
..............

For complex queries not covered by the DSL, fall back to native MongoDB syntax::

    for p in Project.find_by_query({'counter': {'$gte': 0, '$lt': 10}}):
        print(f'Project: {p.name}, counter: {p.counter}')

You can also obtain a reference to the underlying `PyMongo`_ :class:`Collection`::

    mongo_document = Project.get_collection().find_one(filter)

.. _PyMongo: https://api.mongodb.com/python/current/

Bulk insert
...........

Insert (or upsert) multiple documents at once::

    def create_user_batch(count=50):
        return [
            User()
                .update(name=f'user_{i}')
                .update(password='default password')
                .append_to(roles=['Admin', 'User', 'Operator'])
            for i in range(1, count + 1)
        ]

    ids = User.bulk_insert(create_user_batch())

Dropping the collection
.......................

::

    User.get_collection().drop()

Check index information
.......................

::

    idx_info = User.get_collection().index_information()

Index management
----------------

Indexes speed up queries on specific fields. Declare indexes directly in the field's ``Annotated[]`` metadata::

    from appkernel import MongoIndex, MongoUniqueIndex, MongoTextIndex

    class Project(Model, AuditableRepository):
        name: Annotated[str | None, Required(), Validators(NotEmpty), MongoUniqueIndex()] = None
        created: Annotated[datetime | None, Required(), Generator(date_now_generator), MongoIndex()] = None

    Project.init_indexes()

``MongoUniqueIndex`` on ``name`` prevents duplicate project names. ``MongoIndex`` on ``created`` speeds up queries and sorting by creation date.

Built-in index types
....................

- **MongoIndex**: standard index to speed up queries (note: indexes also slow down inserts, so use them selectively);
- **MongoUniqueIndex**: unique constraint — only one document per unique value is allowed;
- **MongoTextIndex**: full-text search index for string fields;

For more details, see the `MongoDB indexes documentation`_.

.. _MongoDB indexes documentation: https://docs.mongodb.com/manual/indexes/

Schema Installation
-------------------

MongoDB supports JSON Schema validation to enforce data integrity on inserts and updates.
AppKernel can generate and install this schema for you::

    Project.add_schema_validation(validation_action='error')

The ``validation_action`` parameter accepts:

- ``'error'``: rejects invalid documents;
- ``'warning'``: logs a warning but allows the operation;

Supported Repository Types
--------------------------

All repositories extend the :class:`Repository` base class:

- :class:`MongoRepository` — standard CRUD and query access to MongoDB;
- :class:`AuditableRepository` — extends MongoRepository with automatic ``inserted``, ``updated``, and ``version`` fields;

Aggregation Pipeline
....................

MongoDB's `Aggregation Pipeline`_ is accessible via the collection reference::

    pipeline = [{'$match': ...}, {'$group': ...}]
    Project.get_collection().aggregate(pipeline)

.. _Aggregation Pipeline: https://docs.mongodb.com/manual/aggregation/
