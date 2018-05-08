.. appkernel documentation master file, created by
   sphinx-quickstart on Mon May  7 23:04:10 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Appkernel- microservices made easy!
=====================================

What is Appkernel?
------------------
A beautiful python framework "for humans", enabling you to deliver a REST enabled micro-services from zero to production within minutes (no kidding: literally within minutes).
It is powered by Flask and it offers native support for MongoDB data stores.

The codebase is thoroughly tested under Python 2.7 (3.4+ and PyPy are planned for the release 1.0).

What's in it for you?
---------------------
We've spent the time on analysing the stack, made the hard choices for you in terms of Database/ORM/Security/Rate Limiting and so on, so you don't have to.
You can focus entirely on delivering business value on day one and being the rockstar of your project.

Quick overview
==============

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. include:: contents.rst.inc

Crash Course
-----------
Let's build a mini identity service: ::

    class User(Model, AuditedMongoRepository, Service):
        id = Parameter(str, required=True, generator=uuid_generator('U'))
        name = Parameter(str, required=True, validators=[NotEmpty], index=UniqueIndex)
        email = Parameter(str, required=True, validators=[Email, NotEmpty], index=UniqueIndex)
        password = Parameter(str, required=True, validators=[NotEmpty],
                             to_value_converter=create_password_hasher(rounds=10), omit=True)
        roles = Parameter(list, sub_type=str, default_value=['Login'])

    app = Flask(__name__)
    kernel = AppKernelEngine('demo app', app=app)

    if __name__ == '__main__':
        kernel.register(User)

        # let's create a sample user
        user = User(name='Test User', email='test@accelero.cloud', password='some pass')
        user.save()

        kernel.run()

That's all folks, our user service is ready to roll, the entity is saved, we can re-load the object from the database, or we can request its json
schema for validation, or metadata to generate an SPA (Single Page Application). Of course validation and some more goodies are built-in as well :)

Now we can test it by using curl: ::

   curl -i -X GET 'http://127.0.0.1:5000/users/'
**And check out the result** ::

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
