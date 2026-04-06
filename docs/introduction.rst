How does it work?
-----------------

Base Model
..........

AppKernel is built around Domain-Driven Design. You start a project by laying out the domain model (the Entity).

.. note::
    All example code below can be followed in Python's interactive console.
    Prerequisites: MongoDB 4.0+ running on localhost and AppKernel installed in a virtual environment
    (``pip install appkernel``).

The :class:`Model` class represents the data in your application. Fields are declared as class-level
type annotations. All fields default to ``None`` — validation runs later, explicitly via
``finalise_and_validate()`` or implicitly when calling ``save()`` or ``dumps()``::

    from typing import Annotated
    from appkernel import Model

    class User(Model):
        id: str | None = None
        name: str | None = None
        email: str | None = None
        password: str | None = None
        roles: list[str] | None = None

You get a keyword-argument constructor, JSON serialisation, and a readable string representation for free::

    u = User(name='some name', email='some name')
    u.password = 'some pass'

    str(u)
    '<User> {"email": "some name", "name": "some name", "password": "some pass"}'

    u.dumps()
    '{"email": "some name", "name": "some name", "password": "some pass"}'

Or with pretty-printing::

    print(u.dumps(pretty_print=True))
    {
        "email": "some name",
        "name": "some name",
        "password": "some pass"
    }

Now let's add validation rules and a default value::

    from appkernel import Required, Default, Validators, Email

    class User(Model):
        id: str | None = None
        name: Annotated[str | None, Required()] = None
        email: Annotated[str | None, Validators(Email)] = None
        password: Annotated[str | None, Required()] = None
        roles: Annotated[list[str] | None, Default(['Login'])] = None

Trying to serialise with an invalid e-mail::

    u = User(name='some name', email='not-an-email')
    u.dumps()
    ValidationException: REGEXP on type str - The property email cannot be validated ...

That's expected — 'not-an-email' is not a valid address. Let's fix it::

    u.email = 'user@acme.com'
    u.dumps()
    PropertyRequiredException: The property [password] on class [User] is required.

Also expected — the required password is missing. Final attempt::

    u.password = 'some pass'
    print(u.dumps(pretty_print=True))
    {
        "email": "user@acme.com",
        "name": "some name",
        "password": "some pass",
        "roles": [
            "Login"
        ]
    }

The ``Default(['Login'])`` marker on the ``roles`` field populated it automatically.

To validate a model without serialising it::

    u.finalise_and_validate()

``finalise_and_validate()`` does more than validate — it also runs *generators* and *converters*:

- a **generator** produces a value for a field when it is ``None`` (e.g. UUID, current timestamp);
- a **converter** transforms an existing value (e.g. hashing a password, normalising text);

Let's add both::

    from appkernel import Generator, Converter, create_uuid_generator, content_hasher

    class User(Model):
        id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required()] = None
        email: Annotated[str | None, Validators(Email)] = None
        password: Annotated[str | None, Required(), Converter(content_hasher())] = None
        roles: Annotated[list[str] | None, Default(['Login'])] = None

    u = User(name='some name', email='user@acme.com', password='some pass')
    print(u.dumps(pretty_print=True))

    {
        "email": "user@acme.com",
        "id": "U013333e7-9f23-4e9d-80de-480505535cad",
        "name": "some name",
        "password": "$pbkdf2-sha256$20000$C0GI8f4/B2AsRah1LiWE8A$2KBVlwBMtaoy1c2dhNORCETNEwssKMnYvB5NAPbkg1s",
        "roles": [
            "Login"
        ]
    }

Two things happened:

- the **id** was auto-generated and prefixed with 'U', making it immediately identifiable as a User;
- the **password** was hashed, so it is stored securely;


Service classes
...............

Once you have your model, you can persist it in MongoDB and expose it as a REST service by mixing in the appropriate classes.

Repository
``````````

Extend :class:`MongoRepository` to add CRUD, schema generation, indexing, and querying::

    from appkernel import Model, MongoRepository, AppKernelEngine
    from appkernel import Required, Generator, Converter, Validators, Email
    from appkernel import create_uuid_generator, content_hasher
    from typing import Annotated

    kernel = AppKernelEngine('tutorial', enable_defaults=True)

    class User(Model, MongoRepository):
        id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required()] = None
        email: Annotated[str | None, Validators(Email)] = None
        password: Annotated[str | None, Required(), Converter(content_hasher())] = None
        roles: Annotated[list[str] | None, Default(['Login'])] = None

    u = User(name='some name', email='user@acme.com', password='some pass')
    u.save()
    # Returns the saved document's ID
    'U7ebc9ae7-d33c-458e-af56-d08283dcabb7'

Retrieve it by ID::

    loaded_user = User.find_by_id(u.id)
    print(loaded_user)
    <User> {"email": "user@acme.com", "id": "Ua727d463-...", "name": "some name", "roles": ["Login"]}

Or with a query expression::

    user_at_acme = User.where(User.email == 'user@acme.com').find_one()
    print(user_at_acme.dumps(pretty_print=True))

    {
        "email": "user@acme.com",
        "id": "Ueeb4139a-1e35-43cd-ab69-7bc3b9104ae4",
        "name": "some name",
        "roles": ["Login"]
    }

More details are in the Repository section.

REST Service
````````````

Registering a model with the AppKernel engine exposes it as a REST API.
No separate `Service` class is needed — just register the model::

    from appkernel import AppKernelEngine, Model, MongoRepository
    from appkernel import Required, Generator, Converter, Validators, Email
    from appkernel import create_uuid_generator, content_hasher, Default
    from typing import Annotated

    kernel = AppKernelEngine('demo app')

    class User(Model, MongoRepository):
        id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required()] = None
        email: Annotated[str | None, Validators(Email)] = None
        password: Annotated[str | None, Required(), Converter(content_hasher())] = None
        roles: Annotated[list[str] | None, Default(['Login'])] = None

    kernel.register(User, methods=['GET', 'POST', 'PUT', 'DELETE'])

    if __name__ == '__main__':
        kernel.run()

Expected output::

    INFO:     Started server process
    INFO:     Uvicorn running on http://0.0.0.0:5000 (Press CTRL+C to quit)

The User model is now available at ``http://localhost:5000/users/``.

List all users::

    curl -X GET http://127.0.0.1:5000/users/

    {
      "_items": [
        {
          "_type": "User",
          "email": "user@acme.com",
          "id": "U9c6785f5-b8b1-4801-a09c-a45109af1222",
          "name": "some name",
          "roles": ["Login"]
        }
      ],
      "_links": {
        "self": {"href": "/users/"}
      }
    }

Search by a field value (the ``~`` prefix means "contains")::

    curl -X GET "http://127.0.0.1:5000/users/?name=~some"

Retrieve the JSON schema::

    curl -X GET http://127.0.0.1:5000/users/schema

Retrieve the UI metadata::

    curl -X GET http://127.0.0.1:5000/users/meta

Try to delete without enabling the DELETE method (the default only enables GET)::

    curl -X DELETE "http://127.0.0.1:5000/users/U9c6785f5-b8b1-4801-a09c-a45109af1222"
    {
      "_type": "ErrorMessage",
      "code": 405,
      "message": "MethodNotAllowed/The method is not allowed for the requested URL."
    }

Register with the full set of methods to enable all operations::

    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])

Now delete works::

    curl -X DELETE "http://127.0.0.1:5000/users/U9c6785f5-b8b1-4801-a09c-a45109af1222"
    {
      "_type": "OperationResult",
      "result": 1
    }

Service Hooks
=============

Register lifecycle hooks by implementing ``before_<method>`` or ``after_<method>`` class methods::

    from appkernel import Model, MongoRepository, AppKernelEngine, action
    from appkernel.http_client import HttpClientServiceProxy

    class Order(Model, MongoRepository):
        id: Annotated[str | None, Generator(create_uuid_generator('O'))] = None
        products: Annotated[list | None, Required()] = None
        order_date: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None

        @classmethod
        def before_post(cls, *args, **kwargs):
            order = kwargs['model']
            client = HttpClientServiceProxy('http://127.0.0.1:5000/')
            status_code, rsp_dict = client.reservation.post(
                Reservation(order_id=order.id, products=order.products))
            order.update(reservation_id=rsp_dict.get('result'))

    if __name__ == '__main__':
        kernel = AppKernelEngine('Order Service', development=True)
        kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
        kernel.run()


Now that you have a taste of **AppKernel**, explore the full feature set in the rest of this documentation.
