from appkernel import Service
from appkernel.model import *
from datetime import datetime
from appkernel.repository import AuditableRepository, Repository, MongoRepository
from appkernel.service import link
from appkernel import NotEmpty, Regexp, Past, Future, uuid_generator, date_now_generator, password_hash_generator


class User(Model, MongoRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    password = Parameter(str, required=True, validators=[NotEmpty], to_value_converter=password_hash_generator)
    description = Parameter(str)
    roles = Parameter(list, sub_type=str)
    created = Parameter(datetime, required=True, validators=[Past], generator=date_now_generator)

    @link(rel='change_password', http_method='POST')
    def change_p(self, current_password, new_password):
        if self.password != current_password:
            raise ServiceException(403, 'Current password is not correct')
        else:
            self.password = new_password
            self.save()

    @link()
    def get_description(self):
        return self.description


class TestClass(Model):
    just_numbers = Parameter(str, required=True, validators=[Regexp('^[0-9]+$')])
    future_field = Parameter(datetime, validators=[Future])


class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str, required=True, validators=[NotEmpty])
    completed = Parameter(bool, required=True, default_value=False)
    created = Parameter(datetime, required=True, generator=date_now_generator)
    closed_date = Parameter(datetime, validators=[Past])

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()


class Project(Model, AuditableRepository):
    name = Parameter(str, required=True, validators=[NotEmpty()])
    tasks = Parameter(list, sub_type=Task)
    created = Parameter(datetime, required=True, generator=date_now_generator)

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)


def create_simple_project():
    p = Project(name='some_project_name').append_to(tasks=Task(name='some task'))
    return p


def create_rich_project():
    p = Project().update(name='some project'). \
        append_to(tasks=[Task(name='some_task', description='some description'),
                         Task(name='some_other_task', description='some other description')])
    p.undefined_parameter = 'some undefined parameter'
    return p


def create_and_save_a_user(name, password, description):
    u = User().update(name=name).update(password=password). \
        append_to(roles=['Admin', 'User', 'Operator']).update(description=description)
    u.save()
    return u


def create_and_save_some_users(range=51):
    for i in xrange(1, range):
        u = User().update(name='multi_user_{}'.format(i)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(sequence=i)
        u.save()
    assert User.count() == range - 1


def create_and_save_john_jane_and_max():
    john = create_and_save_a_user('John', 'a password', 'John is a random guy')
    jane = create_and_save_a_user('Jane', 'a password', 'Jane is a random girl')
    maxx = create_and_save_a_user('Max', 'a password', 'Jane is a random girl')
    return john, jane, maxx
