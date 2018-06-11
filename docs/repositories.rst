Repositories
============

.. warning::
    Work in progress section of documentation

The repository API is influenced by **peewee**, a nice and small python API focusing on relational databases (sqlite, MySQL, PostgreSQL). The major
difference between **peewee** and the built-in **Appkernel** ORM is that the later is optimised (and till this time) implemented only for MongoDB.

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

The following example describe a way for database initialisation which is only recommended for the interactive interpreter or for unit tests. ::

    from appkernel import Model, MongoRepository, Property, password_hasher, create_uuid_generator, Email, AuditableRepository, NotEmpty, date_now_generator, Past
    from appkernel.configuration import config
    from pymongo import MongoClient
    from enum import Enum
    from datetime import datetime, date, timedelta

    config.mongo_database=MongoClient(host='localhost')['tutorial']

# todo: how to initialise it for production

We need some model classes which we will be using throughout this tutorial. Let's create a simple project management app with some tasks in it: ::

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
    # or if you like one-liners, you can add multiple tasks at once
    project.append_to(tasks=[Task(name='finish all todos'), Task(name='complete the unit tests')])

    project.save()
    print(project.dumps(pretty_print=True))

And the output looks sleek: ::

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

Let's search for the the project which has at least one task containing the word 'finish' in its name : ::

    reloaded_project = Project.find_one(Project.tasks.name % 'finish')
    print(reloaded_project.dumps(pretty_print=True))

It will generates the following output: ::

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

You might have observed that there are a few extra fields, which we didn't defined on the model explicitly.
This is happening due to the **AuditableRepository** class we've used in the very beginning. This will bring a few additional features to the mix:

- *inserted*: the date and time when the object was inserted to the database;
- *updated*: the date and time when the object was updated for the last time;
- *version*: the number of updates on this class;

We can check the number of projects quickly: ::

    Project.count()
    1

Let's complete the first task: ::

    project.tasks[0].complete()
    project.save()
    ObjectId('5b1ee7050df7a9087e0e8952')

Observe the property **completed** which now is set to True and the **closed_date** having the value of the invocation of the **complete()** method: ::

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
            {
                "completed": false,
                "created": "2018-06-11T23:17:57.050000",
                "name": "finish all todos",
                "priority": "MEDIUM"
            },
            {
                "completed": false,
                "created": "2018-06-11T23:17:57.050000",
                "name": "complete the unit tests",
                "priority": "MEDIUM"
            }
        ],
        "updated": "2018-06-11T23:19:46.428000",
        "version": 2
    }

Once we don't need the project anymore we can issue the **delete** command: ::

    project.delete()
    1

You can delete all Projects at once: ::

    Project.delete_all()

Queries
-------

Appkernel provides a simple abstraction over the native MongoDB queries, simplifying the job of the developer for most of the queries. The query expressions
can be provided as parameter to the:
* **find** method: returns a generator, which can be used to iterate over the result set;
* **find_one** method: returns the first hit or None, if nothing matches the query criteria;
* **where** method: returns the :class:`Query` object, which allows the chaining of further expressions, such as **sort**;

A simple example: ::

    prj = Project.find_one(Project.name == 'some test project')
    print(prj.dumps(pretty_print=True))

Or you can iterate through all occurrences... ::

    for prj in Project.find(Project.name == 'some test project'):
        print(prj.dumps(pretty_print=True))

... and sort the result in a particular order: ::

    for prj in Project.where(Project.name == 'some test project').sort_by(Project.created.asc()).find():
        print(prj.dumps(pretty_print=True))

Chaining multiple expressions is also possible: ::

    yesterday = datetime.combine(date(2018, 6, 10), datetime.min.time())
    today = datetime.combine(date(2018, 6, 11), datetime.min.time())
    prj = Project.find_one((Project.created > yesterday) & (Project.created < today))
    print(prj.dumps(pretty_print=True))

Pagination
..................

Sometimes it is a good approach to define a range (a page) which is gonna be queried, in this way you avoid filling up the memory with huge result sets.
The following query will return the first 10 Projects from the database: ::

    for prj in Project.find(page=0, page_size=10):
        print(prj)

Query expressions
'''''''''''''''''

Find by ID
..........
    ::

    Project.find_by_id('5b1ee9930df7a9087e0e8953')

Exact match
...........
Returns Project A: ::

    prj = Project.find_one((User.name == 'Project A'))

Not equal
.........
Return all projects **except** 'Project A': ::

    prj = Project.find_one((User.name != 'Project A'))

Or
..
Returns Project A or Project B: ::

    prj = Project.find_one((Project.name == 'Project A') | (Project.name == 'Project B'))


And
...
Returns every project named 'Project A' created after yesterday: ::

    yesterday = (datetime.now() - timedelta(days=1))
    prj = Project.find_one((Project.name == 'Project A') & (Project.created > yesterday))

Empty Array
...........
Find all Projects with no tasks: ::

    prj = Project.find_one(Project.tasks == None)

Contains
........
Find all projects which has at least one task containing the string 'finish': ::

    prj = Project.find_one(Project.tasks.name % 'finish')

Also you can query for values in an array. The following query will return all users, who are having the Role **Admin** and **Operator**: ::

    User.find(User.roles % ['Admin', 'Operator'])

Does not exists
...............

Return all users which have no defined **description** field: ::

    User.find(User.description == None)

Value exists
............
Return all users which has description field: ::

    User.find(User.description != None)

Smaller and bigger
..................

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
