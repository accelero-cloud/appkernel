from flask import Flask
from appkernel import AppKernelEngine
import pytest
from test_util import User, create_and_save_some_users, create_and_save_a_user, create_and_save_john_jane_and_max
import os

try:
    import simplejson as json
except ImportError:
    import json

flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
flask_app.testing = True


@pytest.fixture
def app():
    return flask_app


def setup_module(module):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print '\nModule: >> {} at {}'.format(module, current_file_path)
    kernel = AppKernelEngine('test_app', app=flask_app, cfg_dir='{}/../'.format(current_file_path), development=True)
    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')
    User.delete_all()


def test_action_registration(client):
    print '\n>>>>>>>>>>>>> {}'.format(User.links)
    user = create_and_save_a_user('test user', 'test password', 'test description')
    rsp = client.get('/users/{}'.format(user.id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
