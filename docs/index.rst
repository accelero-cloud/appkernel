Welcome to Appkernel- microservices made easy!
==============================================

What is Appkernel?
------------------
A beautiful python framework "safe for human consumption", enabling to deliver a REST based micro-services from zero to production within minutes (no kidding: literally within minutes).
It is powered by Flask and it offers native support for MongoDB repositories.

The codebase is thoroughly tested under Python 3.6 (Python 2.7 support was dropped somewhere on the road).


Read the docs :)
================
.. include:: contents.rst.inc

****

Crash Course (TL;DR)
--------------------
Let's build a mini identity service: ::

    class User(Model, MongoRepository, Service):
        id = Property(str)
        name = Property(str, required=True, index=UniqueIndex)
        email = Property(str, validators=[Email], index=UniqueIndex)
        password = Property(str, validators=[NotEmpty],
                             converter=content_hasher(), omit=True)
        roles = Property(list, sub_type=str, default_value=['Login'])

    app = Flask(__name__)
    kernel = AppKernelEngine('demo app', app=app, enable_defaults=True)

    if __name__ == '__main__':

        kernel.register(User)

        # let's create a sample user
        user = User(name='Test User', email='test@accelero.cloud', password='some pass')
        user.save()

        kernel.run()

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

That's all folks, our user service is ready to roll, the entity is saved, we can re-load the object from the database, or we can request its json
schema for validation, or metadata to generate an SPA (Single Page Application). Of course validation and some more goodies are built-in as well :)

Quick overview of some notable features
=======================================
Built-in ORM function
----------------------

Find one user matching the query parameter: ::

   user = User.where(name=='Some username').find_one()

Return the first 5 users which have the role "Admin": ::

   user_generator = User.where(User.roles % 'Admin').find(page=0, page_size=5)

Or use native Mongo Query: ::

   user_generator = Project.find_by_query({'name': 'user name'})

Some more extras baked into the Model
-------------------------------------
Generate the ID value automatically using a uuid generator and a prefix 'U': ::

   id = Property(..., generator=uuid_generator('U-'))

It will generate an ID which gives a hint about the object type (eg. *U-0590e790-46cf-42a0-bdca-07b0694d08e2*)

Add a Unique index to the User's name property: ::

   name = Property(..., index=UniqueIndex)

Validate the e-mail property, using the NotEmpty and Email validators ::

   email = Property(..., validators=[Email, NotEmpty])

Add schema validation to the database: ::

   User.add_schema_validation(validation_action='error')

Hash the password and omit this attribute from the json representation: ::

   password = Property(..., converter=content_hasher(rounds=10), omit=True)

Run the generators on the attributes and validate the resulting object (usually not needed, since it is implicitly called by save and dumps methods): ::

   user.finalise_and_validate()


Setup role based access control
-------------------------------

Right after exposing the service as a REST endpoint, security rules can be added to it: ::

    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').
    require(Role('admin'), methods=['PUT', 'POST', 'PATCH', 'DELETE'])
The configuration above will allow to GET `user` related endpoints by all users who has the **user** role. PUT, POST, PATCH and DELETE method are allowed
to be called by users with the **admin** role.

JWT Token
.........

Once the Model object extends the :class:`IdentityMixin`, it will feature a property called **auth_token** which will contain a valid JWT token.
All **roles** from the model are added to the token. Accessing the jqt token is simple: ::

    token = user.auth_token