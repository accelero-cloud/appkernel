The Model Class
---------------

A child class extending the :class:`Model` becomes a data-holder object with some out-of the box features (json schema, validation, factory methods).
A Model corresponds to the *Entity* from the domain driven design concept. A Model is persisted in the database and/or sent through the wire between two or more services.
A Model is also similar to the Python Data Class (will appear in 3.6) but way more powerful.

.. warning::
    This section discusses the Model and its features in great detail. For a quick overview on the most notable features visit the :ref:`How does it works?` section if you
    didn't read that yet.

Features of a Model
'''''''''''''''''''

* :ref:`Introduction to the Model Class`
* :ref:`Extensible Data Validation`
* :ref:`Default Values and Generators`
* :ref:`Value Converters`
* :ref:`Dict and Json Converters`
* :ref:`JSON Schema`
* :ref:`Meta-data generator`

Introduction to the Model Class
'''''''''''''''''''''''''''''''

.. note::
    All the examples below were tested with Python's interactive console using the set of imports from below; ::

    from datetime import datetime
    from appkernel import Model, MongoRepository, Property, Email, UniqueIndex, NotEmpty, Past, create_uuid_generator, date_now_generator, password_hasher

The following example showcases the most notable features of a **Model** class: ::

    class User(Model, MongoRepository):
        id = Property(str, required=True, generator=create_uuid_generator('U'))
        name = Property(str, required=True, index=UniqueIndex)
        email = Property(str, validators=[Email], index=UniqueIndex)
        password = Property(str, validators=[NotEmpty],
                             value_converter=password_hasher(), omit=True)
        roles = Property(list, sub_type=str, default_value=['Login'])
        registration = Property(datetime, validators=[Past], generator=date_now_generator)


    user = User(name='some user', email='some@acme.com', password='some pass')
    user.save()
    print(user.dumps(pretty_print=True))

It will generate the following output: ::

    {
        "email": "some@acme.com",
        "id": "U943a5699-fa7c-4431-949d-3763ce92b847",
        "name": "some user",
        "registration": "2018-06-03T13:32:51.636770",
        "roles": [
            "Login"
        ]
    }

Let's have a look on what just have happened. The defined user class can be persisted in MongoDB with the following properties:

- database ID which gets auto-generated upon saving the instance (the UUID generator support a prefix, which later can be used to identify the model type in the support phase);
- **name**: which is validated upon saving (*required=True*) and a unique index will be added to the Users collection (duplicate names won't be allowed);
- **email**: also a unique value, additionally will be validated against a regular expression pattern which makes sure that the value follows the format of an e-mail address (must contain '@' and '.' characters);
- **password**: will be converted to a hashed value upon saving, so we maintain proper security practices; Observe the *omit=True* parameter which will cause
  the exclusion of this property from the JSON (and other wire-format) representation of the Model;
- **role**: will have a default value *['Login']* upon save (or by calling the builtin method `finalise_and_validate()`) even though we have omitted to specify any role upon instance creation;
- **registration**: will take the value of the date time of the moment of persistence;

.. note::
    Observe that the User class has now a keyword based constructor even-though we didn't defined one before.

Adding more roles to the User is also pretty straightforward: ::

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

Or let's say we've changed our mind and we would like to remove one element from the role list: ::

    user.remove_from(roles='Admin')

You also got a nice representation function for free: ::

    print(user)
    <User> {"email": "some@acme.com", "enabled": true, "id": "U943a5699-fa7c-4431-949d-3763ce92b847", "name": "some user", "registration": "2018-06-03T13:32:51.636770", "roles": ["Login", "Support"]}

New properties can also be added to the class (as expected in python): ::

    user.enabled=True
    print(user.dumps(pretty_print=True))
    {
        "email": "some@acme.com",
        "enabled": true,
        "id": "U943a5699-fa7c-4431-949d-3763ce92b847",
        "name": "some user",
        "registration": "2018-06-03T13:32:51.636770",
        "roles": [
            "Login",
            "Admin",
            "Support"
        ]
    }


But what if we would create a User object which is not valid? ::

    incomplete_user = User()
    incomplete_user.finalise_and_validate()

Of course, it will raise the following Exception: ::

    PropertyRequiredException: The property [name] on class [User] is required.

Do we have your attention? let's explore the details :)

Extensible Data Validation
``````````````````````````
We tried to make the boring task of validation a simple and fun experience. Therefore all properties have a builtin
**required** field which - if set to True - will check the existence of a property.
But in some cases this is far from enough, this is why we introduced the validator lists, which provides a higher sophistication
for backend and database validation.

For example you might want to make sure that a property value is a valid e-mail address (by using the Email validator),
or make sure that the value is lower than 10 (using the Max validator). You can use none, one or more validators for one single property,
or you can add your very own custom validator by extending the :class:`Validator` base class;

Built-in validators
...................

:class:`NotEmpty` - checks that the property value is defined and not empty; ::

    name = Property(str, validators=[NotEmpty]

:class:`Regexp` - checks if the property value matches a regular expression; ::

    just_numbers = Property(str, required=True, validators=[Regexp('^[0-9]+$')])

:class:`Email` - a specialisation of the Regexp validator, providing a basic e-mail regexp pattern; ::

    email = Property(str, validators=[Email])

:class:`Min` and :class:`Max` - the field should be numeric one and the value should be between the specified Min and Max values; ::

    sequence = Property(int, validators=[Min(1), Max(100)])

:class:`Past` and :class:`Future` - the field should be a temporal one and the value should be in the past or in the future; ::

    updated = Property(datetime, validators=[Past])

:class:`Unique` - the field value should be unique in the collection of this Model object (it will install a unique
index in the Mongo database and will cause cause a special unique property in the Json schema;

In case you would like to create a new type of validator, you just need to extend the :class:`Validator` base class and implement the **validate** method: ::

    class CustomValidator(Validator):
        def __init__(self, value):
            # initialise the extended class
            super(CustomValidator, self).__init__('CustomValidator', value)

        def validate(self, param_name, param_value):
            # implement your custom validation logic
            # here's the logic of the regexp validator as an example
            if self.value != param_value:
                raise ValidationException(self.type, param_value,
                                              _('The Property %(pname)s cannot be validated against %(value)s', pname=param_name,
                                                                                                         value=self.value))

.. note::
    The validate function should not return any value but raise a :class:`ValidationException` when the value is does not met the predefined conditions.

.. note::
    In the example above we used the **_()** function from *Babel* in order to provide translation support for to the validation error message;

Default Values and Generators
`````````````````````````````
Sometimes field values can be automatically generated upon persisting the model object (eg. a database ID or date values related to the creation or current used id
in case of need for auditing function) or sensible defaults can be provided in design time (eg. the role 'Login' might be safely added to all users);
Take the following example: ::

    id = Property(str, required=True, generator=create_uuid_generator('U'))

In this case the id property will take a generated value upon saving (or running the `finalise_and_validate()` method on the model) if another value is not provided already;
Writing custom generators is easy: any global function with a return value would suffice.
In case the generator requires an input argument (like the create_uuid_generator in our case), one would create a method which returns
another method: ::

    def uuid_generator(prefix=None):
        def generate_id():
            return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id

This type of ID generator enables you to prefix the IDs of your different Models, making easier the job of the support teams:
one will know immediately know in which collection to sarch for even if he only has an ID (given that the User model ID is prefixed
with 'U' and the Customer Model ID is prefixed with 'CT';

Built-in generators
...................

*UUID Generator*: generates a globally unique id. In case a prefix parameter is provided it will be added in-front of the result ::

    id = Property(str, generator=create_uuid_generator('U'))


*Date generator*: generate the date-time value of the finalisation moment: ::

    registration = Property(datetime, generator=date_now_generator)

*Current user generator*: used to add the authenticated user, useful to automatically register ownership on data object or audit activities. ::

    owner = Property(datetime, generator=current_user_generator)

Value Converters
````````````````
It is also needed to change already existing field values in way or another. Think about the following use-cases:

- passwords need to be hashed before saving it into the database;
- dates could be converted to and from UNIX time before saving or sending it over the wire so one needs to deal less with the data format;
- some sensitive data fragments (such as GDPR controlled private data) might be encrypted upon saving as well;

Therefore any function which returns a tuple of 2 other methods with the property value as input parameter can be used as a value converter.
In case the converter works only in one direction (like the password hasher), None can be returned as the second method.
Here's the code of the password hasher as an example: ::

    def password_hasher(rounds=20000, salt_size=16):
    def to_value_converter(password):
        # type: (str) -> str
        if password.startswith('$pbkdf2-sha256'):
            return password
        else:
            return pbkdf2_sha256.encrypt(password, rounds=rounds, salt_size=salt_size)

    return to_value_converter, None

Dict and Json Converters
''''''''''''''''''''''''

All Models can be easily converted back and forth to and from dict or json representation.
Writing JSON is as simple as: ::

    user.dumps()

The dumps method takes 2 optional parameter:

- *validate* is set to True by default (it will check the class parameters against the validators and the required parameter;
- *pretty_print* is set to False by default (one would need to set it explicitly to True one nice indented JSON output is favoured;

Let's try it out: ::

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

Observe that the password property is missing from the JSON output however the the instance contains a hashed password.
That is happening due to the fact that we set the password field to *omit=True*, which means that it will be excluded from all string representations. ::

    password = Property(str, value_converter=password_hasher(), omit=True)

What if we want to use a *dict* or any different format as output. In such cases comes handy the static method: ::

    def to_dict(instance, convert_id=False, validate=True, skip_omitted_fields=False)

And can be used in the following way: ::

    User.to_dict(user)

In case one wants to prepare some low level MongoDB persistence and we want to convert any property name **id** to **_id** as Mongo expects it. Im such cases
the *convert_id=True* parameter come handy.

Of course the opposite would work by using: ::

    User.from_dict(some_dict_object)

One can use the **set_unmanaged_parameters=False** if values from the dict which do not belong to the Model should be ignored.

JSON Schema
'''''''''''

So now we would want to validate objects when they are received on the wire or we would like to use it for validation in Mongo. Simple as that: ::

    User.get_json_schema()

In case you would like not to allow more properties on the wire than the ones already defined on the class you can set the **additional_properties=False**
which will remove the **'additionalProperties':True,** from the schema, does not allow any json document which contains more properties than the saved ones

In case you would like to use the schema as source of document validation in MongoDB, you would need to use **mongo_compatibility=True**, because the way
Mongo handles dates and several other objects on the scope.

Meta-data generator
'''''''''''''''''''
The JSON schema is a great standard format, however sometimes is harder to parse and it is fairly limited in features when it comes to generate user interfaces
from the schema definition on the fly. Therefore we've built a proprietary format which is thought to be easy to be parsed by Javascript. ::

    print(json.dumps(User.get_parameter_spec(), indent=4))
    {
            "name": {
            "required": true,
            "type": "str",
            "label": "User.name"
        },
        "roles": {
            "default_value": [
                "Login"
            ],
            "required": false,
            "type": "list",
            "sub_type": "str",
            "label": "User.roles"
        },
        "email": {
            "validators": [
                {
                    "type": "Email"
                }
            ],
            "required": false,
            "type": "str",
            "label": "User.email"
        },
        "registration": {
            "validators": [
                {
                    "type": "Past"
                }
            ],
            "required": false,
            "type": "datetime",
            "label": "User.registration"
        },
        "password": {
            "validators": [
                {
                    "type": "NotEmpty"
                }
            ],
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

