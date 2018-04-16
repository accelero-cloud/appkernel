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


def test_working_action(client):
    print '\n> links >{}'.format(User.links)
    user = create_and_save_a_user('test user', 'test password', 'test description')
    rsp = client.get('/users/{}'.format(user.id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json
    assert result.get('_links') is not None
    assert 'change_password' in result.get('_links')
    assert 'get_description' in result.get('_links')
    assert 'self' in result.get('_links')
    assert 'collection' in result.get('_links')
    change_pass_included = False
    for link_name, link_value in result.get('_links').iteritems():
        if link_name == 'change_password':
            change_pass_included = True
            post_data = json.dumps({'current_password': 'test password', 'new_password': 'new pass'})
            assert link_value.get('href') is not None
            rsp = client.post(link_value.get('href'), data=post_data)
            print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
            assert rsp.status_code == 200, 'the status code is expected to be 200'
            break
    assert change_pass_included, 'Should contain change_password link'
    rsp = client.get('/users/{}'.format(user.id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json
    assert result.get('password') == 'new pass'


def test_failing_action(client):
    user = create_and_save_a_user('test user', 'test password', 'test description')
    rsp = client.get('/users/{}'.format(user.id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json
    assert result.get('_links') is not None
    change_pass_included = False
    for link_name, link_value in result.get('_links').iteritems():
        if link_name == 'change_password':
            change_pass_included = True
            post_data = json.dumps({'current_password': 'test wrong password', 'new_password': 'new pass'})
            rsp = client.post(link_value.get('href'), data=post_data)
            print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
            assert rsp.status_code == 403
            break
    assert change_pass_included, 'Should contain change_password link'


def test_getter_action(client):
    user = create_and_save_a_user('test user', 'test password', 'test description')
    rsp = client.get('/users/{}'.format(user.id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json
    assert result.get('_links') is not None
    get_description_included = False
    for link_name, link_value in result.get('_links').iteritems():
        if link_name == 'get_description':
            get_description_included = True
            rsp = client.get(link_value.get('href'))
            print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
            assert rsp.status_code == 200
            assert rsp.json.get('result') == 'test description'
            break
    assert get_description_included, 'Should contain get_description link'