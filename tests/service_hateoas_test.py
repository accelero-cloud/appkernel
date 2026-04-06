from starlette.testclient import TestClient
from appkernel import AppKernelEngine
import pytest
from .utils import User, create_and_save_some_users, create_and_save_a_user, create_and_save_john_jane_and_max, \
    run_async
import os
import bcrypt

try:
    import simplejson as json
except ImportError:
    import json

kernel = None


@pytest.fixture
def client():
    return TestClient(kernel.app)


def setup_module(module):
    global kernel
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print(f'\nModule: >> {module} at {current_file_path}')
    kernel = AppKernelEngine('test_app', cfg_dir=f'{current_file_path}/../', development=True)
    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')
    run_async(User.delete_all())


def test_working_action(client):
    print(f'\n> links >{User.actions}')
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    rsp = client.get(f'/users/{user.id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json()
    assert result.get('_links') is not None
    assert 'change_password' in result.get('_links')
    assert 'get_description' in result.get('_links')
    assert 'self' in result.get('_links')
    assert 'collection' in result.get('_links')
    change_pass_included = False
    newpass = 'new pass'
    for link_name, link_value in result.get('_links').items():
        if link_name == 'change_password':
            change_pass_included = True
            post_data = json.dumps({'current_password': 'test password', 'new_password': newpass})
            assert link_value.get('href') is not None
            rsp = client.post(link_value.get('href'), content=post_data)
            print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
            assert rsp.status_code == 200, 'the status code is expected to be 200'
            break
    assert change_pass_included, 'Should contain change_password link'
    rsp = client.get(f'/users/{user.id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json()
    assert 'password' not in result
    stored_hash = run_async(User.find_by_id(result.get('id'))).password
    assert bcrypt.checkpw(newpass.encode('utf-8'), stored_hash.encode('utf-8'))


def test_failing_action(client):
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    rsp = client.get(f'/users/{user.id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json()
    assert result.get('_links') is not None
    change_pass_included = False
    for link_name, link_value in result.get('_links').items():
        if link_name == 'change_password':
            change_pass_included = True
            post_data = json.dumps({'current_password': 'test wrong password', 'new_password': 'new pass'})
            rsp = client.post(link_value.get('href'), content=post_data)
            print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
            assert rsp.status_code == 403
            break
    assert change_pass_included, 'Should contain change_password link'


def test_getter_action(client):
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    rsp = client.get(f'/users/{user.id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json()
    assert result.get('_links') is not None
    get_description_included = False
    for link_name, link_value in result.get('_links').items():
        if link_name == 'get_description':
            get_description_included = True
            rsp = client.get(link_value.get('href'))
            print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
            assert rsp.status_code == 200
            assert rsp.json().get('result') == 'test description'
            break
    assert get_description_included, 'Should contain get_description link'
