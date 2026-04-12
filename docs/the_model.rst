The Model Class
---------------

A class extending :class:`Model` becomes a domain object with built-in serialization, validation, schema generation, and factory methods.
A Model corresponds to the *Entity* concept from Domain-Driven Design — it is persisted in the database and exchanged between services.
Unlike Python's standard dataclass, a Model supports deferred validation, query DSL integration, automatic field generation, and MongoDB persistence.

.. warning::
    This section covers the Model and its features in depth. For a quick overview, visit the :ref:`How does it work?` section first.

Features of a Model
'''''''''''''''''''

* :ref:`Introduction to the Model Class`
* :ref:`Extensible Data Validation`
* :ref:`Default Values and Generators`
* :ref:`Converters`
* :ref:`Dict and Json Converters`
* :ref:`Marshallers`
* :ref:`JSON Schema`
* :ref:`Meta-data generator`

Introduction to the Model Class
''''''''''''''''''''''''''''''''

.. note::
    All examples below can be followed in Python's interactive console using the imports shown here::

        from datetime import datetime
        from typing import Annotated
        from pydantic import Field
        from appkernel import (
            Model, MongoRepository,
            Required, Generator, Converter, Default, Validators, Marshal,
            MongoUniqueIndex, Email, NotEmpty, Past,
            create_uuid_generator, date_now_generator, content_hasher,
        )
        from appkernel.generators import TimestampMarshaller

The following example showcases the most notable features of a **Model** class::

    class User(Model, MongoRepository):
        id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
        name: Annotated[str | None, Required(), MongoUniqueIndex()] = None
        email: Annotated[str | None, Validators(Email), MongoUniqueIndex()] = None
        password: Annotated[str | None, Validators(NotEmpty), Converter(content_hasher()), Field(exclude=True)] = None
        roles: Annotated[list[str] | None, Default(['Login'])] = None
        registration: Annotated[datetime | None, Validators(Past), Generator(date_now_generator)] = None


    user = User(name='some user', email='some@acme.com', password='some pass')
    user.save()
    print(user.dumps(pretty_print=True))

This produces the following output::

    {
        "email": "some@acme.com",
        "id": "U943a5699-fa7c-4431-949d-3763ce92b847",
        "name": "some user",
        "registration": "2018-06-03T13:32:51.636770",
        "roles": [
            "Login"
        ]
    }

Here is what happened:

- **id**: auto-generated on save. The UUID prefix ('U') makes it immediately clear which collection the document belongs to, which simplifies debugging;
- **name**: required and indexed with a unique constraint — duplicate names will be rejected;
- **email**: validated against a regular expression (must contain '@' and '.') and also unique in the collection;
- **password**: converted to a hashed value on save. ``Field(exclude=True)`` excludes it from all JSON and wire-format output;
- **roles**: assigned the default value ``['Login']`` automatically on validation if not provided;
- **registration**: set to the current date and time on save;

.. note::
    Models use a *deferred validation* pattern: all fields default to ``None`` and validation runs explicitly when ``finalise_and_validate()`` is called, or implicitly when ``save()`` or ``dumps()`` is invoked.

Appending items to a list field is straightforward::

    user.append_to(roles=['Admin', 'Support'])
    print(user.dumps(pretty_print=True))

    {
        "email": "some@acme.com",
        "id": "U943a5699-fa7c-4431-949d-3763ce92b847",
        "name": "some user",
        "registration": "2018-06-03T13:32:51.636770",
        "roles": [
            "Login",
            "Admin",
            "Support"
        ]
    }

Removing an item from a list is equally simple::

    user.remove_from(roles='Admin')

And the built-in string representation gives you a compact view::

    print(user)
    <User> {"email": "some@acme.com", "id": "U943a5699-fa7c-4431-949d-3763ce92b847", "name": "some user", "registration": "2018-06-03T13:32:51.636770", "roles": ["Login", "Support"]}

Extra attributes can also be set dynamically::

    user.enabled = True
    print(user.dumps(pretty_print=True))
    {
        "email": "some@acme.com",
        "enabled": true,
        "id": "U943a5699-fa7c-4431-949d-3763ce92b847",
        "name": "some user",
        "registration": "2018-06-03T13:32:51.636770",
        "roles": [
            "Login",
            "Support"
        ]
    }


What happens when we create an invalid User?::

    incomplete_user = User()
    incomplete_user.finalise_and_validate()

This raises::

    PropertyRequiredException: The property [name] on class [User] is required.


Extensible Data Validation
``````````````````````````

Validation is controlled by markers placed in the ``Annotated[]`` metadata of each field. The ``Required()`` marker checks that a field is not ``None`` at validation time. The ``Validators()`` marker accepts one or more validator instances or classes.

Built-in validators
...................

:class:`NotEmpty` — checks that the value is defined and non-empty::

    name: Annotated[str | None, Validators(NotEmpty)] = None

:class:`Regexp` — checks that the value matches a regular expression::

    code: Annotated[str | None, Required(), Validators(Regexp('^[0-9]+$'))] = None

:class:`Email` — a Regexp specialisation with a built-in e-mail pattern::

    email: Annotated[str | None, Validators(Email)] = None

:class:`Min` and :class:`Max` — numeric range validation::

    sequence: Annotated[int | None, Validators(Min(1), Max(100))] = None

:class:`Past` and :class:`Future` — temporal validation::

    updated: Annotated[datetime | None, Validators(Past)] = None

:class:`Unique` — adds a unique constraint and marks the field in the JSON schema::

    username: Annotated[str | None, Validators(Unique)] = None

Model-level validation
......................

For validation logic that spans multiple fields, implement a ``validate()`` method::

    class Payment(Model):
        method: Annotated[PaymentMethod | None, Required()] = None
        customer_id: Annotated[str | None, Required(), Validators(NotEmpty)] = None
        customer_secret: Annotated[str | None, Required(), Validators(NotEmpty)] = None

        def validate(self):
            if self.method in (PaymentMethod.MASTER, PaymentMethod.VISA):
                if len(self.customer_id) < 16 or len(self.customer_secret) < 3:
                    raise ValidationException('Card number must be 16 characters and CVC 3.')
            elif self.method in (PaymentMethod.PAYPAL, PaymentMethod.DIRECT_DEBIT):
                if len(self.customer_id) < 22:
                    raise ValidationException('IBAN must be at least 22 characters.')

.. note::
    The ``validate()`` method should not return a value — it raises :class:`ValidationException` when conditions are not met.

.. note::
    Use the ``_()`` function for translatable validation error messages.
    Import it at the top of your module and wrap every user-facing string::

        from gettext import gettext as _

        class Payment(Model):
            method: Annotated[PaymentMethod | None, Required()] = None
            customer_id: Annotated[str | None, Required(), Validators(NotEmpty)] = None
            customer_secret: Annotated[str | None, Required(), Validators(NotEmpty)] = None

            def validate(self):
                if self.method in (PaymentMethod.MASTER, PaymentMethod.VISA):
                    if len(self.customer_id) < 16 or len(self.customer_secret) < 3:
                        raise ValidationException(
                            _('Card number must be 16 characters and CVC 3.')
                        )
                elif self.method in (PaymentMethod.PAYPAL, PaymentMethod.DIRECT_DEBIT):
                    if len(self.customer_id) < 22:
                        raise ValidationException(
                            _('IBAN must be at least 22 characters.')
                        )

    AppKernel's ``LocaleMiddleware`` sets the active locale from the ``Accept-Language`` request
    header before validation runs, so the translated string is automatically chosen for each caller.
    See :ref:`Translations` for the full ``pybabel extract`` / ``init`` / ``compile`` workflow.

Writing a custom validator
..........................

Extend :class:`Validator` and implement the ``validate`` method::

    class CustomValidator(Validator):
        def __init__(self, value):
            super().__init__('CustomValidator', value)

        def validate(self, param_name, param_value):
            if self.value != param_value:
                raise ValidationException(
                    self.type, param_value,
                    _('Property %(pname)s cannot be validated against %(value)s',
                      pname=param_name, value=self.value))

For validators that need access to the whole object, implement ``validate_objects``::

    class CreditCardValidator(Validator):
        def __init__(self):
            super().__init__('CreditCardValidator')

        def validate_objects(self, parameter_name: str, instance_parameters: dict):
            card_number = instance_parameters.get(parameter_name)
            if instance_parameters.get('payment_method') == 'VISA':
                self.__visa_luhn_check(card_number)
            else:
                self.__mastercard_luhn_check(card_number)


Default Values and Generators
`````````````````````````````

Fields can be automatically populated at validation time using the ``Generator()`` marker, or assigned a static default using the ``Default()`` marker.

The ``Generator()`` marker wraps any callable that returns the desired value::

    id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None

The field will receive a generated value when ``finalise_and_validate()`` or ``save()`` is called — but only if the field is currently ``None``. Providing a value explicitly always takes precedence.

Writing a custom generator is straightforward — any zero-argument callable works::

    def uuid_generator(prefix=None):
        def generate_id():
            return f'{prefix}{uuid.uuid4()}'
        return generate_id

Prefixed IDs make it easy to identify the owning collection from the ID alone (e.g. 'U' for User, 'CT' for Customer).

Built-in generators
...................

*UUID Generator* — generates a globally unique ID, optionally prefixed::

    id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None

*Date generator* — captures the date-time at the moment of finalisation::

    registration: Annotated[datetime | None, Generator(date_now_generator)] = None

*Current user generator* — records the authenticated user, useful for auditing::

    owner: Annotated[str | None, Generator(current_user_generator)] = None

Converters
``````````

Converters transform an existing field value at validation time. Common use-cases include:

- hashing passwords before saving;
- encrypting sensitive data;
- normalising text (e.g. lower-casing an e-mail address);

Use the ``Converter()`` marker with any function that accepts the current value and returns the transformed value.
For one-way converters (like password hashing), the function simply returns the hashed value and the original is discarded::

    password: Annotated[str | None, Required(), Validators(NotEmpty), Converter(content_hasher()), Field(exclude=True)] = None

The built-in hasher::

    def content_hasher(rounds=20000, salt_size=16):
        def hash_content(content):
            if content.startswith('$pbkdf2-sha256'):
                return content
            return pbkdf2_sha256.encrypt(content, rounds=rounds, salt_size=salt_size)
        return hash_content


Dict and Json Converters
''''''''''''''''''''''''

All Models can be serialised to and from dict or JSON (the wire format).

Writing JSON::

    user.dumps()

The ``dumps()`` method accepts two optional parameters:

- *validate* (default ``True``): runs field validation and generators before serialising;
- *pretty_print* (default ``False``): produces indented output;

Example::

    print(user.dumps(pretty_print=True))
    {
        "email": "some@acme.com",
        "id": "Uf112dc8a-d75e-405c-ba8f-c15d1bf438f9",
        "name": "some user",
        "registration": "2018-06-03T17:39:54.125991",
        "roles": [
            "Login"
        ]
    }

The password field is absent because ``Field(exclude=True)`` excludes it from all serialised representations.

To serialise to a Python dict::

    User.to_dict(user)

Pass ``convert_id=True`` to rename the ``id`` field to ``_id`` for low-level MongoDB persistence.

To deserialise from a dict::

    User.from_dict(some_dict_object)


Marshallers
```````````

A marshaller translates a field between its in-memory representation and its wire format. This is useful when you want to store or transmit a value in a different format than what your code works with.

Timestamp marshaller
....................

The ``TimestampMarshaller`` converts a :class:`datetime` to a Unix timestamp (float) on write, and back to :class:`datetime` on read::

    class User(Model, MongoRepository):
        last_login: Annotated[datetime | None, Marshal(TimestampMarshaller)] = None

Date-to-datetime marshaller
...........................

MongoDB does not support the bare :class:`date` type — only :class:`datetime`. Use ``MongoDateTimeMarshaller`` to convert automatically::

    class Application(Model, MongoRepository):
        id: Annotated[str | None, Required(), Generator(create_uuid_generator())] = None
        application_date: Annotated[date | None, Required(), Marshal(MongoDateTimeMarshaller)] = None

Writing a custom marshaller
...........................

Extend :class:`Marshaller` and implement both conversion directions::

    class MyMarshaller(Marshaller):
        def to_wireformat(self, instance_value):
            # Return the value to store/transmit
            ...

        def from_wire_format(self, wire_value):
            # Return the in-memory value
            ...


JSON Schema
'''''''''''

Generate a JSON Schema for validation or UI purposes::

    User.get_json_schema()

Pass ``additional_properties=False`` to disallow any properties not declared on the class.
Pass ``mongo_compatibility=True`` when using the schema as a MongoDB document validator, since Mongo handles dates and some other types differently.

Meta-data generator
'''''''''''''''''''

In addition to standard JSON Schema, AppKernel provides a proprietary metadata format optimised for frontend UI generation::

    print(json.dumps(User.get_parameter_spec(), indent=4))
    {
        "name": {
            "required": true,
            "type": "str",
            "label": "User.name"
        },
        "roles": {
            "default_value": ["Login"],
            "required": false,
            "type": "list",
            "sub_type": "str",
            "label": "User.roles"
        },
        "email": {
            "validators": [{"type": "Email"}],
            "required": false,
            "type": "str",
            "label": "User.email"
        },
        "registration": {
            "validators": [{"type": "Past"}],
            "required": false,
            "type": "datetime",
            "label": "User.registration"
        },
        "password": {
            "validators": [{"type": "NotEmpty"}],
            "required": false,
            "type": "str",
            "label": "User.password"
        },
        "id": {
            "required": true,
            "type": "str",
            "label": "User.id"
        }
    }
