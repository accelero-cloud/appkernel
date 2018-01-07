from appkernel.model import *
from datetime import datetime

def uui_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


def date_now_generator():
    return datetime.now()


class TestClass(Model):
    just_numbers = Parameter(str, required=True, validators=[Regexp('^[0-9]+$')])


class Task(Model):
    id = Parameter(str, required=True, generator=uui_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str, required=True, validators=[NotEmpty])
    completed = Parameter(bool, required=True, default_value=False)
    created = Parameter(datetime, required=True, generator=date_now_generator)
    closed_date = Parameter(datetime, validators=[Past])

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()


class Project(Model):
    name = Parameter(str, required=True, validators=[NotEmpty()])
    tasks = Parameter(list, sub_type=Task)


def create_project():
    p = Project(name='some_project_name').append_to(tasks=Task(name='some task'))