Features
------------------------------------------------
The vision of the project is to provide you with a full-fledged microservice chassis, as defined by Chris Richardson.

* :ref:`Extensible Data Validation`
* :ref:`Default Values and Generators`
* :ref:`Value Converters`
* :ref:`Dict and Json Converters`
* :ref:`JSON Schema Generator`

* Full range of CRUD operations

* :ref:`REST endpoints over HTTP`
* Customizable resource endpoints
* Filtering and Sorting
* Pagination
* Projections
* Embedded Resource Serialization
* MongoDB Aggregation Framework
* :ref:`Powered by Flask`

.. note::
    hehehe

.. warning::
    hahaha

Extensible Data Validation
``````````````````````````
USE CASE / MOTIVATION
Take the following example and observe the different validators: ::

    class User(Model, AuditableRepository, Service):
        id = Parameter(str, required=True, generator=uuid_generator('U'))
        ident_code = Parameter(str, required=True, validators=[Regexp('^[0-9]+$')])
        name = Parameter(str, required=True, validators=[Unique])
        email = Parameter(str, required=True, validators=[Email, NotEmpty])
        password = Parameter(str, required=True, validators=[NotEmpty],
                             to_value_converter=password_hasher(rounds=10), omit=True)
        roles = Parameter(list, sub_type=str, default_value=['Login'])
        registration = Parameter(datetime, validators=[Past])

All parameters have a builtin `required` field which - if set to True - will check the existence of a property.
The list of validators provides a higher sophistication for backend and database validation.
For example you might want to make sure that a property contains a valid e-mail address (by using the Email validator),
or any other one (one can add new validators by extending the :class:`Validator` base class;

:class:`NotEmpty` - checks that the property value is defined and not empty;
:class:`Regexp` - checks if the property value matches a regular expression;
:class:`Email` - a specialisation of the Regexp validator, providing a basic e-mail regexp pattern;
:class:`Min` - the field should be numeric one and the value should be higher than the one defined;
:class:`Max` -the field should be a numeric one and the value should not be higher than the defined one;
:class:`Past` - the field should be a temporal one and the value should be in the past;
:class:`Future` - the field should be a temporal one and the value should be in the future;
:class:`Unique` - the field value should be unique in the collection of this Model object (it will install a unique
index in the Mongo database and will cause cause a special unique property in the Json schema;

In case you would like to create a new validator, you just need to extend the appropiate base class. ::

    class CustomValidator(Validator):
        def __init__(self, value):
            super(CustomValidator, self).__init__('CustomValidator', value)

        def validate(self, parameter_name, validable_object):
            # implement your custom validationn logic
            # here's the logic of the regexp validator as an example
            if isinstance(validable_object, basestring):
                if not re.match(self.value, validable_object):
                    raise ValidationException(self.type, validable_object,
                                              'The parameter *{}* cannot be validated against {}'.format(parameter_name,
                                                                                                         self.value))



Default Values and Generators
`````````````````````````````
USE CASE / MOTIVATION
Sometimes required field values can be automatically generated upon persisting the model object (eg. a database ID)
or sensible defaults can be provided in design time (eg. the role 'Login' might be safely added to all users); ::

    id = Parameter(str, required=True, generator=uuid_generator('U'))

In this case the id field will get a generated value upon saving (or running the `finalise_and_validate()` method on the model)
if one was not provided already;
Writing customer generators is easy: any method with a return value would suffice.
In case the generator requires an input parameter (like the uuid_generator in our case), one would create a method which returns
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


REST endpoints over HTTP
````````````````````````]
USE CASE / MOTIVATION
bla bla

Powered by Flask
`````````````````

Let's assume that we have created a User class extending the :class:`Model` and the :class:`Service`. Now we'd like to expose it as a REST endpoint ::

    if __name__ == '__main__':
        app = Flask(__name__)
        kernel = AppKernelEngine('demo app', app=app)
        kernel.register(User)
        kernel.run()


Why did we built this?
----------------------
* We had the need to build a myriad of small services in our daily business, ranging from data-aggregation pipelines, to housekeeping services and other process automation services. These do share similar requirements and the underlying infrastructure needed to be rebuilt and tested over and over again. The question arose: what if we avoid spending valuable time on the boilerplate and focus only on the fun part?

* Often time takes a substantial effort to make a valuable internal hack or proof of concept presentable to customers, until it reaches the maturity in terms reliability, fault tolerance and security. What if all these non-functional requirements would be taken care by an underlying platform?

* There are several initiatives out there (Flask Admin, Flask Rest Extension and so), which do target parts of the problem, but they either need substantial effort to make them play nice together, either they feel complicated and uneasy to use. We wanted something simple and beautiful, which we love working with.

* These were the major driving question, which lead to the development of App Kernel.

How does it works?
------------------
AppKernel is built around the concepts of Domain Driven Design. You can start the project by laying out the model. The first step is to define the validation and data generations rules. For making life easier, one can also set default values. Than one can extend several built-in classes in order to augment the model with extended functionality:

* extending the Repository class (or its descendants) adds and ORM persistency capability to the model;
* extending the Service class (or its descendants) add the capability to expose the model over REST services;