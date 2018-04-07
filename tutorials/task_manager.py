#!/usr/bin/python
import uuid
from flask import Flask
from appkernel import AppKernelEngine, Model, AuditableRepository, Service, Parameter, NotEmpty, Regexp, Past
from datetime import datetime

application_id = 'task_management_app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


class Task(Model, AuditableRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str)
    tags = Parameter(list, sub_type=str)
    completed = Parameter(bool, required=True, default_value=False)
    closed_date = Parameter(datetime, validators=[Past])

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        """
        Mark the task complete and set the completion date to now;
        """
        self.completed = True
        self.closed_date = datetime.now()


def init_app():
    kernel.register(Task)
    task = Task().update(name='develop appkernel',
                         description='deliver the first version and spread the word.') \
        .append_to(tags=['fun', 'important'])
    task.save()
    kernel.run()


if __name__ == '__main__':
    init_app()
