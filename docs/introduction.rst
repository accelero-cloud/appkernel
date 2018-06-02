How does it works?
------------------
AppKernel is built around the concepts of Domain Driven Design. You can start the project by laying out the model (the Enitity).

The Model class represents the data in our application and stands at the heart of the architecture. As a first step we define
the *Properties* (fields) of our new domain model object as static class variable. ::

    class User(Model):
        id = Property(str)
        name = Property(str)
        email = Property(str)
        password = Property(str)
        roles = Property(list, sub_type=str)


By this time we've got for free a keyword argument constructor (__init__ methof), a  json and dict representation of the class: ::

    u = User(name='some name', email='some name')
    u.password='some pass'

    str(u)
    '<User> {"email": "some name", "name": "some name", "password": "some pass"}'

    u.dumps()
    '{"email": "some name", "name": "some name", "password": "some pass"}'

Or in case we want a pretty printed Json we can do: ::

    u.dumps(pretty_print=True)
    {
        "email": "some name",
        "name": "some name",
        "password": "some pass"
    }'


As a next step we can add some validation rules and a few default values, just to make life a bit easier: ::

    class User(Model):
        id = Property(str)
        name = Property(str, required=True)
        email = Property(str, validators=[Email])
        password = Property(str, required=True)
        roles = Property(list, sub_type=str, default_value=['Login'])

And let's try to list the properties again: ::

    u = User(name='some name', email='some name')
    str(u)
    '<User> {"email": "some name", "name": "some name"}'
    u.dumps()
    ValidationException: REGEXP on type str - The property email cannot be validated against (?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[-!#-[]-]|\[-	-])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[-!-ZS-]|\[-	-])+)\])

Whoops... but wait a minute, that's desired behaviour since we didn't provided a proper e-mail address. Let's try again: ::

    u.email='user@acme.com'
    u.dumps()
    PropertyRequiredException: The property [password] on class [User] is required.

Yeah, that's expected too. Final round: ::

    u.password='some pass'
    u.dumps()
    '{"email": "user@acme.com", "name": "some name", "password": "some pass", "roles": ["Login"]}'

Observe how the default value on the *roles* property is automagically added :)

But what if I just want to validate the class in my business logic, without generating json? Despair not my friend, there's a handy method for it: ::

    u.finalise_and_validate()

Ohh, that's good... but why it is called finalise and validate, why not just validate?

Well, because we have thought that there are few use-cases beyond validation and default value generation. Imagine that:

- we want to automatically hash password values
- or we want to add a custom ID generator to our model which has some alpha characters for the id

Now we add a pinch of augmentation by extending a few more utility classes:

* extend the Repository class (or its descendants) to add ORM functionality to the model (CRUD, Schema Generation, Indexing, etc.);
* extend the Service class (or its descendants) to expose the model as a REST services (create new instances with POST, retrieve existing ones with GET or DELETE them);

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