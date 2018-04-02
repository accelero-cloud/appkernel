from appkernel import Service
from appkernel.model import *
from datetime import datetime
from appkernel.repository import AuditableRepository, Repository, MongoRepository


def uui_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


def date_now_generator():
    return datetime.now()


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


class User(Model, MongoRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')])
    password = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str)
    roles = Parameter(list, sub_type=str)
    created = Parameter(datetime, required=True, validators=[Past], generator=date_now_generator)

class TestClass(Model):
    just_numbers = Parameter(str, required=True, validators=[Regexp('^[0-9]+$')])
    future_field = Parameter(datetime, validators=[Future])


class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=uui_generator('U'))
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
        append_to(tasks=[Task(name='some_task', description='some description'), Task(name='some_other_task', description='some other description')])
    p.undefined_parameter = 'some undefined parameter'
    return p