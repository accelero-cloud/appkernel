#!/usr/bin/python
import uuid
from flask import Flask
from appkernel import AppKernelEngine, Model, Repository, Service, Parameter, NotEmpty, Regexp, Past
from datetime import datetime

print('Initialising under {}'.format(__name__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
kernel = AppKernelEngine('test_app', app=app)


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


def date_now_generator():
    return datetime.now()


def date_now_generator():
    return datetime.now()


class User(Model, Repository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')])
    created = Parameter(datetime, required=True, validators=[Past], generator=date_now_generator)

@kernel.app.route('/cfg')
def extract_config():
    return '{}'.format(kernel.cfg_engine.cfg)

def init_app():
    kernel.register(User)
    kernel.run()


if __name__ == '__main__':
    init_app()
