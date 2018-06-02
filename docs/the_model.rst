.. note::
    hehehe

.. warning::
    hahaha

The Model Class
---------------

A child class extending the :class:`Model` becomes a data-holder object packed with features. A Model corresponds to the *Entity* from
the domain driven design concept. A Model is persisted in the database and/or sent through the wire between two or more services.
A Model is also similar to the Python Data Class (will appear in 3.6) but way more powerful ::

Features of a Model
'''''''''''''''''''

* :ref:`Extensible Data Validation`
* :ref:`Default Values and Generators`
* :ref:`Value Converters`
* :ref:`Dict and Json Converters`
* :ref:`JSON Schema Generator`
* :ref:`Meta-data generator`

Example of a Model Class
''''''''''''''''''''''''
The following example showcases the most notable features of a **Model** class: ::

    class User(Model, MongoRepository):
        id = Property(str, required=True, generator=uuid_generator('U'))
        name = Property(str, required=True, index=UniqueIndex)
        email = Property(str, validators=[Email], index=UniqueIndex)
        password = Property(str, validators=[NotEmpty],
                             to_value_converter=password_hasher(rounds=10), omit=True)
        roles = Property(list, sub_type=str, default_value=['Login'])
        registration = Property(datetime, validators=[Past], generator=date_now_generator)


    user = User(name='some user', email='some@acme.com', password='some pass')
    user.save()
    print('User with ID {} was persisted in the database at {}.'.format(user.id, user.registration))

Let's have a look on wha we have just did. We have defined a User class which is also persisted in MongoDB under the name Users. It has:

- a database ID which gets auto-generated upon saving the instance;
- a Property called '**name**', which is validated upon saving (*required=True*) and a unique index will be added to the Users collection (duplicate names won't be allowed);
- a Property called '**email**'. Also a unique value, additionally will be validated against an e-mail address regular expression pattern (must contain '@' and '.' characters);
- a Property called '**password**', where the password value will be converted to a hashed value upon saving, so we maintain proper security practices; Please observe the *omit=True* Property which will cause
  the exclusion of this Property from the JSON (and other wire-format) representation of the Model;
- the '**role**' Property which will have a default value *['Login']* upon save even though we have omitted to specify any role upon instance creation;
- and finally the '**registration**' Property which will take the value of the date of the actual date of persistence;

Interested? let's explore more details :)

Extensible Data Validation
``````````````````````````
We tried to make the boring task of validation a simple and fun experience for you. Therefore all Propertys have a builtin
**required** field which - if set to True - will check the existence of a property.
But in some cases this is far from enough, this is why we introduced the validator lists, which provides a higher sophistication
for backend and database validation.

For example you might want to make sure that a Property value is a valid e-mail address (by using the Email validator),
or make sure that the value is lower than 10 (using the Max validator). You can use none, one or more validators for one single Property,
or you can add you very own custom validator by extending the :class:`Validator` base class;

Built-in validators
...................

:class:`NotEmpty` - checks that the property value is defined and not empty; ::

    name = Property(str, validators=[NotEmpty]

:class:`Regexp` - checks if the property value matches a regular expression; ::

        just_numbers = Property(str, required=True, validators=[Regexp('^[0-9]+$')])


:class:`Email` - a specialisation of the Regexp validator, providing a basic e-mail regexp pattern; ::

    email = Property(str, validators=[Email])

:class:`Min` and :class:`Max` - the field should be numeric one and the value should be higher or lowe than the specified one; ::

    sequence = Property(int, validators=[Min(1), Max(100)])

:class:`Past` and :class:`Future` - the field should be a temporal one and the value should be in the past or in the future; ::

    updated = Property(datetime, validators=[Past])

:class:`Unique` - the field value should be unique in the collection of this Model object (it will install a unique
index in the Mongo database and will cause cause a special unique property in the Json schema;

In case you would like to create a new validator, you just need to extend the :class:`Validator` base class and implement the **validate** method: ::

    class CustomValidator(Validator):
        def __init__(self, value):
            # initialise the extended class
            super(CustomValidator, self).__init__('CustomValidator', value)

        def validate(self, Property_name, Property_value):
            # implement your custom validation logic
            # here's the logic of the regexp validator as an example
            if self.value != Property_value:
                raise ValidationException(self.type, Property_value,
                                              _('The Property %(pname) cannot be validated against %(value)', pname=Property_name,
                                                                                                         value=self.value))

In the example above we used the **_()** function from *Babel* in order to provide translation support for to the validation error message;

Default Values and Generators
`````````````````````````````
USE CASE / MOTIVATION
Sometimes required field values can be automatically generated upon persisting the model object (eg. a database ID)
or sensible defaults can be provided in design time (eg. the role 'Login' might be safely added to all users); ::

    id = Property(str, required=True, generator=uuid_generator('U'))

In this case the id field will get a generated value upon saving (or running the `finalise_and_validate()` method on the model)
if one was not provided already;
Writing customer generators is easy: any method with a return value would suffice.
In case the generator requires an input Property (like the uuid_generator in our case), one would create a method which returns
another method: ::

    def uuid_generator(prefix=None):
        def generate_id():
            return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id

This type of ID generator enables you to prefix the IDs of your different Models, making easier the job of the support teams:
one will know immediately know in which collection to sarch for even if he only has an ID (given that the User model ID is prefixed
with 'U' and the Customer Model ID is prefixed with 'CT';

Value Converters
````````````````
USE CASE / MOTIVATION


