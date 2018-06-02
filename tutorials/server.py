#!/usr/bin/python
import uuid
from flask import Flask
from appkernel import AppKernelEngine, Model, Repository, Service, Property, NotEmpty, Regexp, Past
from datetime import datetime
from appkernel.repository import MongoRepository

print('Initialising under {}'.format(__name__))

application_id = 'test_app'
app = Flask(__name__)
app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
kernel = AppKernelEngine(application_id, app=app)


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id


def date_now_generator():
    return datetime.now()


class User(Model, MongoRepository, Service):
    id = Property(str, required=True, generator=uuid_generator('U'))
    name = Property(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')])
    password = Property(str, required=True, validators=[NotEmpty])
    description = Property(str)
    roles = Property(list, sub_type=str)
    created = Property(datetime, required=True, validators=[Past], generator=date_now_generator)


@kernel.app.route('/cfg')
def extract_config():
    return '{}'.format(kernel.cfg_engine.cfg)


def init_app():
    kernel.register(User)
    u = User().update(name='some_user', password='some_pass')
    u.save()
    kernel.run()


if __name__ == '__main__':
    init_app()
