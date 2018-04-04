from flask import Flask
from appkernel import AppKernelEngine, Model, Repository, Service, Parameter, NotEmpty, Regexp, Past
from datetime import datetime
from appkernel.repository import MongoRepository
from test_util import User
import uuid, os, sys
import pytest

try:
    import simplejson as json
except ImportError:
    import json

# crud
# not found
# method not allowed
# patch nonexitent/existent field
# test sort and sort by
# test some error
# more params on the query than supported by the method
# less params than supported on the query
# test between a range of sequences
# test not just date but time too

flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
flask_app.testing = True


@pytest.fixture
def app():
    return flask_app


@pytest.fixture
def user_dict():
    return {
        "birth_date": "1980-06-30T00:00:00",
        "description": "some description",
        "name": "some_user",
        "password": "some_pass",
        "roles": [
            "User",
            "Admin",
            "Operator"
        ]
    }


def setup_module(module):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print '\nModule: >> {} at {}'.format(module, current_file_path)
    kernel = AppKernelEngine('test_app', app=flask_app, cfg_dir='{}/../'.format(current_file_path), development=True)
    kernel.register(User)


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')
    User.delete_all()


def test_get_basic(client):
    u = User().update(name='some_user', password='some_pass')
    user_id = u.save()
    rsp = client.get('/users/{}'.format(user_id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result = rsp.json
    assert result.get('id') == user_id
    assert 'type' in result
    assert result.get('type') == 'User'


def test_get_not_found(client):
    rsp = client.get('/users/1234')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404, 'the status code is expected to be 404'
    assert rsp.json.get('type') == 'ErrorMessage'


def test_delete_basic(client):
    u = User().update(name='some_user', password='some_pass')
    user_id = u.save()
    rsp = client.delete('/users/{}'.format(user_id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    assert rsp.json.get('result') == 1


def test_get_query_between_dates(client):
    u = User().update(name='some_user', password='some_pass')
    u.birth_date = datetime.strptime('1980-06-30', '%Y-%m-%d')
    u.description = 'some description'
    u.roles = ['User', 'Admin', 'Operator']
    user_id = u.save()
    print('\nSaved user -> {}'.format(User.find_by_id(user_id)))
    rsp = client.get('/users/?birth_date=>1980-06-30&birth_date=<1985-08-01&logic=AND')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    assert rsp.json[0].get('id') == user_id


def test_get_query_between_not_found(client):
    rsp = client.get('/users/?birth_date=>1980&birth_date=<1985&logic=AND')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404, 'the status code is expected to be 404'
    assert rsp.json.get('type') == 'ErrorMessage'


def test_find_date_range(client):
    base_birth_date = datetime.strptime('1980-01-01', '%Y-%m-%d')
    for m in xrange(1, 13):
        u = User().update(name='multi_user_{}'.format(m)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(birth_date=base_birth_date.replace(month=m))
        u.save()
    assert User.count() == 12
    rsp = client.get('/users/?birth_date=>1980-03-01&birth_date=<1980-05-30&logic=AND')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_list = rsp.json
    assert len(response_list) == 3


def create_a_user(name, password, description):
    u = User().update(name=name).update(password=password). \
        append_to(roles=['Admin', 'User', 'Operator']).update(description=description)
    u.save()
    return u


def create_50_users():
    for i in xrange(50):
        u = User().update(name='multi_user_{}'.format(i)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(sequence=i)
        u.save()
    assert User.count() == 50


def test_find_range_in_user_sequence(client):
    create_50_users()
    rsp = client.get('/users/?sequence=>20&sequence=<25&logic=OR')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object) == 5


def test_find_less_than(client):
    create_50_users()
    rsp = client.get('/users/?sequence=<5')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object) == 5


def test_find_greater_than(client):
    create_50_users()
    rsp = client.get('/users/?sequence=>45')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object) == 5


def test_find_contains(client):
    john = create_a_user('John Doe', 'a password', 'John is a random guy')
    jane = create_a_user('Jane Doe', 'a password', 'Jane is a random girl')
    rsp = client.get('/users/?name=~Jane')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object) == 1
    assert rsp_object[0].get('name') == 'Jane Doe'

    rsp = client.get('/users/?name=~John')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object) == 1
    assert rsp_object[0].get('name') == 'John Doe'

    rsp = client.get('/users/?name=~Doe')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object) == 2


#todo: find contains string
#todo: find boolean

def test_post_user(client, user_dict):
    user_json = json.dumps(user_dict)
    print '\nSending: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201, 'the status code is expected to be 200'
    document_id = rsp.json.get('result')
    user = User.find_by_id(document_id)
    print '\nLoaded user: {}'.format(user)
    assert user is not None
    assert len(user.roles) == 3


def test_post_incomplete_user(client, user_dict):
    del user_dict['name']
    user_json = json.dumps(user_dict)
    print '\nSending request: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 400, 'the status code is expected to be 400'
    assert rsp.json.get('type') == 'ErrorMessage'


def test_post_update_with_id(client, user_dict):
    user_json = json.dumps(user_dict)
    print '\nSending: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201, 'the status code is expected to be 200'
    document_id = rsp.json.get('result')
    user_dict['id'] = document_id
    user_dict['name'] = 'changed name'
    user_json = json.dumps(user_dict)
    print '\nSending: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    user = User.find_by_id(rsp.json.get('result'))
    assert user.name == 'changed name'


def test_patch_user(client, user_dict):
    user_json = json.dumps(user_dict)
    print '\nSending: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201, 'the status code is expected to be 200'
    document_id = rsp.json.get('result')
    user_url = '/users/{}'.format(document_id)
    rsp = client.patch(user_url, data=json.dumps({'description': 'patched description'}))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp = client.get(user_url)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    result_user = rsp.json
    assert result_user.get('description') == 'patched description'


def test_put_user(client, user_dict):
    user_json = json.dumps(user_dict)
    print '\nSending: {}'.format(user_json)
    rsp = client.post('/users/', data=user_json)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201, 'the status code is expected to be 200'
    document_id = rsp.json.get('result')

    replacement_user = user_dict.copy()
    del replacement_user['birth_date']
    del replacement_user['description']
    replacement_user.update(id=document_id)
    replacement_user.update(name='changed user')
    replacement_user.update(locked=True)
    replacement_user.update(roles=[])
    replacement_user_json = json.dumps(replacement_user)
    print '\nSending: {}'.format(replacement_user_json)
    rsp = client.put('/users/', data=replacement_user_json)
    assert rsp.status_code >= 200
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp = client.get('/users/'.format(document_id))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    returned_user = rsp.json
    assert returned_user[0].get('locked') == True
    assert returned_user[0].get('name') == 'changed user'
    assert len(returned_user[0].get('roles')) == 0
