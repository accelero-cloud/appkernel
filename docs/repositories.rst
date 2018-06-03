Repositories
============

.. warning::
    Work in progress section of documentation

The repository API is influenced by **peewee**, a nice and small python API focusing on relational databases (sqlite, MySQL, PostgreSQL). The major
difference in **Appkernel** optimised (and till this time) implemented only for MongoDB.

* :ref:`Basic CRUD (Created, Update, Delete) operations`
* :ref:`Queries`
* :ref:`Auditable Repository`
* :ref:`Index management`
* :ref:`Schema Installation`
* :ref:`MongoDB Aggregation Pipeline`

Basic CRUD (Created, Update, Delete) operations
-----------------------------------------------

.. note::
    You can follow all the examples in the Python's interactive interpreter using the imports and the configuration snippet from below.

 ::

    from appkernel import Model, MongoRepository, Property, password_hasher, create_uuid_generator, Email, AuditableRepository, NotEmpty, date_now_generator, Past
    from appkernel.configuration import config
    from pymongo import MongoClient
    from enum import Enum
    from datetime import datetime

    config.mongo_database=MongoClient(host='localhost')['tutorial']

We need some model classes which we will use throughout the page: ::

    class Priority(Enum):
        HIGH = 1
        MEDIUM = 2
        LOW = 3

    class Task(Model, MongoRepository):
        name = Property(str, required=True, validators=[NotEmpty])
        description = Property(str, validators=[NotEmpty])
        completed = Property(bool, required=True, default_value=False)
        created = Property(datetime, required=True, generator=date_now_generator)
        closed_date = Property(datetime, validators=[Past])
        priority = Property(Priority, required=True, default_value=Priority.MEDIUM)

        def complete(self):
            self.completed = True
            self.closed_date = datetime.now()

    class Project(Model, AuditableRepository):
        id = Property(str)
        name = Property(str, required=True, validators=[NotEmpty()])
        tasks = Property(list, sub_type=Task)
        created = Property(datetime, required=True, generator=date_now_generator)

Now we are ready to create a small project: ::

    project = Project(name='some test project')
    project.append_to(tasks=Task(name='finish the documentation', priority=Priority.HIGH))
    # ore if you like one-liners, you can add multiple tasks at once
    project.append_to(tasks=[Task(name='finish all todos'), Task(name='complete the unit tests')])

    project.save()
    print(project.dumps(pretty_print=True))

And the output looks simply amazing: ::
    {
        "id": "OBJ_5b142be00df7a9647023f0b1",
        "created": "2018-06-03T19:54:06.830307",
        "name": "some test project",
        "tasks": [
            {
                "completed": false,
                "created": "2018-06-03T19:53:38.149125",
                "name": "finish the documentation",
                "priority": "MEDIUM"
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

Let's search for the : ::

    reloaded_project = Project.where(Project.tasks.name % 'finish').find_one()
    print(reloaded_project.dumps(pretty_print=True))

Generates the following output: ::

    {
        "created": "2018-06-03T19:54:06.830000",
        "id": "OBJ_5b142be00df7a9647023f0b1",
        "inserted": "2018-06-03T19:56:48.794000",
        "name": "some test project",
        "tasks": [
            {
                "completed": false,
                "created": "2018-06-03T19:53:38.149000",
                "name": "finish the documentation",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041000",
                "name": "finish all todos",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041000",
                "name": "complete the unit tests",
                "priority": "MEDIUM"
            }
        ],
        "updated": "2018-06-03T19:56:48.794000",
        "version": 1
    }

You might have observed that there are a few extra fields, which we didn't defined on the model. This happens due to the **AuditableRepository** class we
extended in the very beginning. This will bring a few additionalf features to the mix:

- *inserted*:
- *updated*:
- *version*:

    ::

    for p in Project.where(Project.tasks.name % 'finish').find():
        print(p.dumps(pretty_print=True))

Know

.. note::
    All the examples are uin

Queries
-------

Query operators
'''''''''''''''

Native Queries
''''''''''''''

llll

Index management
----------------

Schema Installation
-------------------

MongoDB Aggregation Pipeline
----------------------------

Auditable Repository
--------------------

Generates the following output: ::

    {
        "created": "2018-06-03T19:54:06.830000",
        "id": "OBJ_5b142be00df7a9647023f0b1",
        "inserted": "2018-06-03T19:56:48.794000",
        "name": "some test project",
        "tasks": [
            {
                "completed": false,
                "created": "2018-06-03T19:53:38.149000",
                "name": "finish the documentation",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041000",
                "name": "finish all todos",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-03T19:53:51.041000",
                "name": "complete the unit tests",
                "priority": "MEDIUM"
            }
        ],
        "updated": "2018-06-03T19:56:48.794000",
        "version": 1
    }

You might have observed that there are a few extra fields, which we didn't defined on the model. This happens due to the **AuditableRepository** class we
extended in the very beginning. This will bring a few additionalf features to the mix:

- *inserted*:
- *updated*:
- *version*:
