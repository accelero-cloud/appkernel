Welcome to Appkernel- microservices made easy!
==============================================

What is Appkernel?
------------------
A beautiful python framework "for humans", enabling you to deliver a REST enabled micro-services from zero to production within minutes (no kidding: literally within minutes).
It is powered by Flask and it offers native support for MongoDB data stores.

The codebase is thoroughly tested under Python 2.7 (3.4+ and PyPy are planned for the release 1.0).

How does it helps you?
----------------------
**We did the heavy lifting so you can focus on the things that matter :)**

We've spent the time on analysing the stack, made the hard choices in terms of Database/ORM/Security/Rate Limiting and so on, so you don't have to.
You can focus entirely on delivering business value on day one and being the rockstar of your project.


Read the docs
=============
.. include:: contents.rst.inc

****

Crash Course (TL;DR)
--------------------
Let's build a mini identity service: ::

    class User(Model, MongoRepository, Service):
        id = Parameter(str)
        name = Parameter(str, required=True, index=UniqueIndex)
        email = Parameter(str, validators=[Email, NotEmpty], index=UniqueIndex)
        password = Parameter(str, validators=[NotEmpty],
                             value_converter=password_hasher(), omit=True)
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
         "id": "0590e790-46cf-42a0-bdca-07b0694d08e2",
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

Quick overview
==============
A few features of the built-in ORM function
-------------------------------------------

Find one single user matching the query parameter: ::

   user = User.where(name=='Some username').find_one()

Return the first 5 users which have the role "Admin": ::

   user_generator = User.where(User.roles % 'Admin').find(page=0, page_size=5)

Or use native Mongo Query: ::

   user_generator = Project.find_by_query({'name': 'user name'})

Some more extras baked into the Model
-------------------------------------
Generate the ID value automatically using a uuid generator and a prefix 'U': ::

   id = Parameter(..., generator=uuid_generator('U-'))

It will generate an ID which gives a hint about the object type: *U-0590e790-46cf-42a0-bdca-07b0694d08e2*

Add a Unique index to the User's name property: ::

   name = Parameter(..., index=UniqueIndex)

Validate the e-mail property, using the NotEmpty and Email validators ::

   email = Parameter(..., validators=[Email, NotEmpty])

Add schema validation to the database: ::

   User.add_schema_validation(validation_action='error')

Hash the password and omit this attribute from the json representation: ::

   password = Parameter(..., value_converter=password_hasher(rounds=10), omit=True)

Run the generators on the attributes and validate the resulting object (usually not needed, since it is implicitly called by save and dumps methods): ::

   user.finalise_and_validate()

