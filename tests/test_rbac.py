from werkzeug.datastructures import Headers

from appkernel import AppKernelEngine, Role, Anonymous
from appkernel.authorisation import check_token
import os
import pytest
from flask import Flask
from werkzeug.test import Client
from tests.test_util import User, create_and_save_a_user

try:
    import simplejson as json
except ImportError:
    import json

flask_app = None
kernel = None


@pytest.fixture
def app():
    return flask_app


@pytest.fixture
def current_file_path():
    return os.path.dirname(os.path.realpath(__file__))


def setup_module(module):
    print('\nModule: >> {} at {}'.format(module, current_file_path()))


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')

    global flask_app
    global kernel
    flask_app = Flask(__name__)
    flask_app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
    flask_app.testing = True
    kernel = AppKernelEngine('test_app', app=flask_app, cfg_dir='{}/../'.format(current_file_path()), development=True)
    kernel.enable_security()
    User.delete_all()


def teardown_function(function):
    """ teardown any state that was previously setup with a setup_method
    call.
    """
    print("\nTEAR DOWN <==")
    global flask_app
    if flask_app:
        flask_app.teardown_appcontext
        flask_app.teardown_appcontext_funcs


def test_create_token():
    user = create_and_save_a_user('test user', 'test password', 'test description')
    print('\n{}'.format(user.dumps(pretty_print=True)))
    with flask_app.app_context():
        token = user.auth_token
        print('token: {}'.format(token))
        decoded_token = check_token(token)
        print('decoded with public key (internal): {}'.format(decoded_token))


def test_auth_basic(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])
    u = User().update(name='some_user', password='some_pass')
    user_id = u.save()
    headers = Headers()
    headers.add('X-Tenant', 'rockee')
    rsp = client.get('/users/{}'.format(user_id), headers=headers)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 401, 'should be unauthorized'

    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post('/users/{}/change_password'.format(user_id), data=post_data, headers=headers)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 401, 'should be unauthorized'

    headers.add('Authorization', 'Bearer {}'.format(u.auth_token))
    rsp = client.get('/users/{}'.format(user_id), headers=headers)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 403, 'should be forbidden'

    u.update(roles=['user', 'admin'])
    headers.set('Authorization', 'Bearer {}'.format(u.auth_token))
    rsp = client.get('/users/{}'.format(user_id), headers=headers)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'should be accepted'
    # for h in rsp.headers:
    #     print h
    # self.assertTrue('WWW-Authenticate' in rv.headers)
    # self.assertTrue('Basic' in rv.headers['WWW-Authenticate'])

    # post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    # rsp = client.post('/users/{}/change_password'.format(user_id), data=post_data, headers=headers)
    # print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    # assert rsp.status_code == 200, 'should be ok'
    # todo: other user


def test_deny_all(client, current_file_path):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all()


def test_deny_one(client, current_file_path):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny(Role('anonymous'), methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])


def test_exempt(client, current_file_path):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().exempt(Anonymous(), methods=['GET'])
