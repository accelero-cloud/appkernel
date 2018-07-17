import time

from werkzeug.datastructures import Headers

from appkernel import AppKernelEngine, Role, Anonymous
from appkernel.authorisation import check_token
import os
import pytest
from flask import Flask
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
    print(('\nModule: >> {} at {}'.format(module, current_file_path())))


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')

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
    print(('\n{}'.format(user.dumps(pretty_print=True))))
    token = user.auth_token
    print(('token: {}'.format(token)))
    decoded_token = check_token(token)
    print(('decoded with public key (internal): {}'.format(decoded_token)))


def create_basic_user():
    u = User().update(name='some_user', password='some_pass')
    u.save()
    return u


def default_config():
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])
    return create_basic_user()


def test_auth_basic_deny_without_token(client):
    user = default_config()
    headers = Headers()
    headers.add('X-Tenant', 'rockee')
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 401, 'should be unauthorized'
    assert rsp.json.get('message') == 'The authorisation header is missing.'


def test_auth_basic_garbage_token(client):
    user = default_config()
    headers = Headers()
    user.update(roles=['user', 'admin'])
    headers.add('Authorization', 'Bearer {}'.format('eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.'))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json.get('message') == 'Not enough segments'


def test_auth_basic_missing_signature(client):
    user = default_config()
    headers = Headers()
    user.update(roles=['user', 'admin'])
    headers.add('Authorization', 'Bearer {}'.format(
        'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE1Mjc0Mjc3NDcsInJvbGVzIjpbIkFkbWluIiwiVXNlciIsIk9wZXJhdG9yIl0sInN1YiI6IlVjNzZkMjEyNy1iM2Y2LTQ1ZGUtYmU4YS0xMjg5MWMwMzM4YmYiLCJleHAiOjE1Mjc0MzEzNDd9.'))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json.get('message') == 'Signature verification failed'


def test_auth_basic_deny_with_token_without_roles(client):
    user = default_config()
    headers = Headers()
    headers.add('X-Custom', 'rookie')
    headers.add('Authorization', 'Bearer {}'.format(user.auth_token))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json.get('message') == 'The required permission is missing.'


def test_auth_basic_with_token_and_roles(client):
    user = default_config()
    headers = Headers()
    headers.add('X-Tenant', 'rockee')
    user.update(roles=['user', 'admin'])
    headers.set('Authorization', 'Bearer {}'.format(user.auth_token))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 200, 'should be accepted'


def test_auth_basic_with_expired_token(client):
    user = default_config()
    headers = Headers()
    User.set_validity(1)
    user.update(roles=['user', 'admin'])
    headers.add('Authorization', 'Bearer {}'.format(user.auth_token))
    time.sleep(2)
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json.get('message') == 'Signature has expired'


def test_auth_decorated_link_missing_token(client):
    user = default_config()
    headers = Headers()
    headers.add('X-Tenant', 'rockee')
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post('/users/{}/change_password'.format(user.id), data=post_data, headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 401, 'should be unauthorized'


def test_auth_decorated_link_good_token_correct_authority(client):
    user = default_config()
    headers = Headers()
    headers.add('X-Tenant', 'rockee')
    headers.set('Authorization', 'Bearer {}'.format(user.auth_token))
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post('/users/{}/change_password'.format(user.id), data=post_data, headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 200, 'should be ok'


def test_auth_decorated_link_good_token_wrong_authority(client):
    user1 = default_config()
    user2 = User(name='second user', password='second-pass', roles=['user'])
    user2.save()
    headers = Headers()
    headers.set('Authorization', 'Bearer {}'.format(user2.auth_token))
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post('/users/{}/change_password'.format(user1.id), data=post_data, headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be ok'


def test_auth_decorated_link_good_token_admin_role(client):
    user1 = default_config()
    user2 = User(name='second user', password='second-pass', roles=['user', 'admin'])
    user2.save()
    headers = Headers()
    headers.set('Authorization', 'Bearer {}'.format(user2.auth_token))
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post('/users/{}/change_password'.format(user1.id), data=post_data, headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 200, 'should be ok'
    assert rsp.json.get('result') == 'Password changed'

    # for h in rsp.headers:
    #     print h
    # self.assertTrue('WWW-Authenticate' in rv.headers)
    # self.assertTrue('Basic' in rv.headers['WWW-Authenticate'])


def test_auth_explicit_anonymous(client):
    user = default_config()
    user.description = 'A dummy user'
    user.save()
    headers = Headers()
    rsp = client.get('/users/{}/get_description'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 200, 'should be ok'
    assert rsp.json.get('result') == 'A dummy user'


def test_deny_all(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all()
    user = create_basic_user()
    user.update(roles=['user', 'admin'])
    headers = Headers()
    headers.set('Authorization', 'Bearer {}'.format(user.auth_token))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json.get('message') == 'Not allowed to access method.'

    rsp = client.delete('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json.get('message') == 'Not allowed to access method.'


def test_default_state_with_enabled_security(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all()
    user = create_basic_user()
    user.update(roles=['user', 'admin'])
    headers = Headers()
    headers.set('Authorization', 'Bearer {}'.format(user.auth_token))
    rsp = client.get('/users/{}'.format(user.id), headers=headers)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json.get('message') == 'Not allowed to access method.'


def test_enable_all(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.allow_all()
    user = create_basic_user()
    rsp = client.get('/users/{}'.format(user.id))
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data.decode()))
    assert rsp.status_code == 200, 'should be enabled'

# def test_exempt(client, current_file_path):
#     user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
#     user_service.deny_all().exempt(Anonymous(), methods=['GET'])
