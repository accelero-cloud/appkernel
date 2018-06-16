from flask import Flask
from appkernel import AppKernelEngine
from datetime import datetime

from appkernel.util import OBJ_PREFIX
from test_util import User, create_and_save_some_users, create_and_save_a_user, create_and_save_john_jane_and_max, \
    Project, Task
import os
import pytest

try:
    import simplejson as json
except ImportError:
    import json

# == supported features ===
# examples of supported queries:
# GET /users/12345
# GET /users/?name=Jane&name=John
# GET /users/?name=Jane&name=John&logic=OR
# GET /users/?sequence=>10&sequence=<20
# GET /users/?birth_date=>1980-06-10&birth_date=<1980-08-15
# GET /users/?name=~Doe
# GET /users/?name=!Max
# GET /users/?query={} - json body with query expression
# GET /users/aggregate/?pipe={} - json body with query expression
# /users/?roles=~Admin
# GET /users/?name=[Jane,John]
# post patch and put with a form data
# -- features needs to be implemented
# -- Not yet implemented
# sort after multiple fields and use '-' for signaling descending order
# GET /users/?roles=#0
# find value in array (simple and complex array)
# search in structures ?subelement.field = 3
# test not just date but time too
# --
# todo: try class based discovery before regular expression matching

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
    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    kernel.register(Project, methods=['GET', 'PUT'])


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
    assert '_type' in result
    assert result.get('_type') == 'User'


def test_get_not_found(client):
    rsp = client.get('/users/1234')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404, 'the status code is expected to be 404'
    assert rsp.json.get('_type') == 'ErrorMessage'


def test_get_invalid_url(client):
    rsp = client.get('/uzerz/1234')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404, 'the status code is expected to be 404'
    assert rsp.json.get('_type') == 'ErrorMessage'


def test_delete_basic(client):
    u = User().update(name='some_user', password='some_pass')
    user_id = u.save()
    rsp = client.delete('/users/{}'.format(user_id))
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    assert rsp.json.get('result') == 1


def test_find_by_object_id(client):
    Project.get_collection().delete_many({})
    p = Project()
    p.name = 'somename'
    p.undefined_parameter = 'something else'
    p.tasks = [Task(name='some_task', description='some description')]
    proj_id = p.save()
    rsp = client.get('/projects/{}{}'.format(OBJ_PREFIX, proj_id))
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 200


def test_delete_invalid_url(client):
    rsp = client.delete('/uzerz/1234')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404, 'the status code is expected to be 404'
    assert rsp.json.get('_type') == 'ErrorMessage'


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
    result = rsp.json
    assert result.get('_items')[0].get('id') == user_id
    assert '_links' in result
    assert '_type' in result


def test_get_query_between_not_found(client):
    rsp = client.get('/users/?birth_date=>1980&birth_date=<1985&logic=AND')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 204, 'the status code is expected to be 204'


def test_find_date_range(client):
    base_birth_date = datetime.strptime('1980-01-01', '%Y-%m-%d')
    for m in xrange(1, 13):
        u = User().update(name='multi_user_{}'.format(m)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(
            birth_date=base_birth_date.replace(month=m))
        u.save()
    assert User.count() == 12
    rsp = client.get('/users/?birth_date=>1980-03-01&birth_date=<1980-05-30&logic=AND')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_list = rsp.json
    assert len(response_list) == 3


def test_find_range_in_user_sequence(client):
    create_and_save_some_users()
    rsp = client.get('/users/?sequence=>20&sequence=<25&logic=OR')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object.get('_items')) == 6


def test_find_less_than(client):
    create_and_save_some_users()
    rsp = client.get('/users/?sequence=<5')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object.get('_items')) == 5


def test_find_greater_than(client):
    create_and_save_some_users()
    rsp = client.get('/users/?sequence=>45')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    response_object = rsp.json
    assert len(response_object.get('_items')) == 6


def test_sort_by(client):
    create_and_save_some_users()
    rsp = client.get('/users/?sequence=>45&sort_by=sequence')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    prev_user_seq = None
    for uzer in rsp.json.get('_items'):
        if prev_user_seq:
            assert uzer.get('sequence') == prev_user_seq + 1
        prev_user_seq = uzer.get('sequence')
        assert prev_user_seq is not None


def test_sort_by_and_sort_order_desc(client):
    create_and_save_some_users()
    rsp = client.get('/users/?sequence=>45&sort_by=sequence&sort_order=DESC')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    prev_user_seq = None
    for uzer in rsp.json.get('_items'):
        if prev_user_seq:
            assert uzer.get('sequence') == prev_user_seq - 1
        prev_user_seq = uzer.get('sequence')
        assert prev_user_seq is not None


def test_pagination(client):
    create_and_save_some_users()
    for page in range(1, 6):
        print('\n== Page: ({}) ===='.format(page))
        rsp = client.get('/users/?page={}&page_size=5'.format(page))
        print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
        assert rsp.status_code == 200
        result_set = rsp.json
        assert len(result_set.get('_items')) == 5
        assert result_set.get('_items')[4].get('sequence') == page * 5, 'the sequence number should be a multiple of 5'
        assert result_set.get('_type') == 'list', 'the type should be a list here'
        assert result_set.get('_items')[0].get('_type') == 'User', 'the item type should be User'


def test_pagination_with_sort(client):
    create_and_save_some_users()
    for page in range(1, 6):
        print('\n== Page: ({}) ===='.format(page))
        rsp = client.get('/users/?page={}&page_size=5&sort_by=sequence&sort_order=DESC'.format(page))
        print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
        assert rsp.status_code == 200
        result_set = rsp.json
        assert len(result_set.get('_items')) == 5
        assert result_set.get('_items')[0].get('sequence') == 55 - (page * 5)


def test_default_pagination(client):
    create_and_save_some_users(range=101)
    rsp = client.get('/users/')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 50


def test_find_contains(client):
    john = create_and_save_a_user('John Doe', 'a password', 'John is a random guy')
    jane = create_and_save_a_user('Jane Doe', 'a password', 'Jane is a random girl')
    rsp = client.get('/users/?name=~Jane')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object.get('_items')) == 1
    assert rsp_object.get('_items')[0].get('name') == 'Jane Doe'

    rsp = client.get('/users/?name=~John')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object.get('_items')) == 1
    assert rsp_object.get('_items')[0].get('name') == 'John Doe'

    rsp = client.get('/users/?name=~Doe')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp_object = rsp.json
    assert len(rsp_object.get('_items')) == 2


def test_find_in_array(client):
    john = create_and_save_a_user('John Doe', 'a password', 'John is a random guy')
    rsp = client.get('/users/?roles=~xxxx')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 204
    rsp = client.get('/users/?roles=~Admin')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200


def test_find_in_array(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?name=[Jane,John]')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 2


def test_find_exact_or(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?name=Jane&name=John&logic=OR')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 2


def test_find_contains_and(client):
    jane1 = create_and_save_a_user('Jane 1', 'some secret', 'some silly description')
    jane2 = create_and_save_a_user('Jane 2', 'some secret', 'some silly description')
    jane1.enabled = True
    jane2.enabled = False
    jane1.save()
    jane2.save()
    rsp = client.get('/users/?name=~Jane&&enabled=false')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 1


def test_more_params_than_supported(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?name=~Jane&jibberish=5')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 204


def test_find_contains_or(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?name=~Jane&name=~John&logic=OR')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 2


def test_search_for_nonexistent_field(client):
    john = create_and_save_a_user('John Doe', 'a password', 'John is a random guy')
    rsp = client.get('/users/?xxxx=Jane')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 204, 'the status code is expected to be 204'


def test_find_by_exact_match(client):
    john = create_and_save_a_user('John', 'a_password', 'John is a random guy')
    rsp = client.get('/users/?name=John')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert rsp.json.get('_items')[0].get('name') == 'John'


def test_find_by_exact_match_with_space(client):
    john_doe = create_and_save_a_user('John Doe', 'hihihih', 'John Doe is an unknown person')
    rsp = client.get('/users/?name=John Doe')
    print ('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 200
    assert len(rsp.json.get('_items')) == 1
    rsp = client.get('/users/?name=John Pullmannn')
    print ('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 204


def test_find_boolean(client):
    john = create_and_save_a_user('John Doe', 'a password', 'John is a random guy')
    john.locked = True
    john.save()

    jane = create_and_save_a_user('Jane Doe', 'a password', 'Jane is a random girl')
    jane.locked = False
    jane.save()

    max = create_and_save_a_user('Max Mustermann', 'a password', 'Max is yet another random guy')

    rsp = client.get('/users/?locked=false')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.json.get('_items')[0].get('name') == 'Jane Doe'

    rsp = client.get('/users/?locked=true')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.json.get('_items')[0].get('name') == 'John Doe'

    rsp = client.get('/users/?locked=true&locked=false&logic=OR')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert len(rsp.json.get('_items')) == 2


def test_find_not_equal(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?name=!Max')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    result_set = rsp.json
    assert len(result_set.get('_items')) == 2
    max_found = False
    for uzer in result_set.get('_items'):
        max_found = uzer.get('name') == 'Max'
    assert not max_found


def test_find_by_query_expression(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?query={"$or":[{"name":"John"}, {"name":"Jane"}]}')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    result_set = rsp.json
    assert len(result_set.get('_items')) == 2


def test_find_by_query_expression_not_found(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?query={"$or":[{"name":"Brigitte"}, {"name":"Jona"}]}')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 204


def test_find_by_query_expression_wrong_query_format(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/?query={"$or":[{"name":", {"name":"Jona"}]}')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 500
    assert rsp.json.get('_type') == "ErrorMessage"


def test_run_aggregation_pipeline(client):
    create_and_save_john_jane_and_max()
    rsp = client.get('/users/aggregate/?pipe=[{"$match":{"name": "Jane"}}]')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert rsp.json.get('_items')[0].get('name') == 'Jane'


def test_post_user_as_json_payload(client, user_dict):
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
    assert rsp.json.get('_type') == 'ErrorMessage'


def test_post_user_as_form(client):
    rsp = client.post('/users/', data=dict(
        name="some_user",
        description="soe",
        password="some pass",
        birth_date="1980-06-30T00:00:00",
        roles=["User", "Admin", "Operator"]
    ), follow_redirects=True)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201
    user = User.find_by_id(rsp.json.get('result'))
    assert user is not None
    assert user.name == "some_user"
    assert len(user.roles) == 3


def test_post_user_as_form_with_single_list_item(client):
    rsp = client.post('/users/', data=dict(
        name="some_user",
        description="some description",
        password="some pass",
        birth_date="1980-06-30T00:00:00",
        roles=["User"]
    ), follow_redirects=True)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 201
    user = User.find_by_id(rsp.json.get('result'))
    assert user is not None
    assert len(user.roles) == 1
    assert user.roles[0] == "User"


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


def test_patch_user_with_form_data(client):
    maxx = create_and_save_a_user('Maxx', 'some pass', 'user description')
    user_url = '/users/{}'.format(maxx.id)
    rsp = client.patch(user_url, data=dict({'description': 'patched description'}))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200
    assert rsp.json.get('result') == maxx.id
    patched_user = User.find_by_id(maxx.id)
    assert patched_user.description == 'patched description'


def test_patch_nonexistent_field(client):
    john = create_and_save_a_user('John Doe', 'some pass', 'a silly description')
    user_url = '/users/{}'.format(john.id)
    rsp = client.patch(user_url, data=json.dumps({'locked': True}))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp = client.get(user_url)
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 200, 'the status code is expected to be 200'
    assert rsp.json.get('locked')


def test_patch_non_existent_document(client):
    rsp = client.patch('/users/12234567890', data=json.dumps({'locked': True}))
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    assert rsp.status_code == 404
    assert rsp.json.get('code') == 404


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
    assert 200 <= rsp.status_code < 300
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    rsp = client.get('/users/')
    print '\nResponse: {} -> {}'.format(rsp.status, rsp.data)
    returned_user = rsp.json
    assert returned_user.get('_items')[0].get('locked') is True
    assert returned_user.get('_items')[0].get('name') == 'changed user'
    assert len(returned_user.get('_items')[0].get('roles')) == 0


def test_put_with_object_id(client):
    Project.get_collection().delete_many({})
    p = Project()
    p.name = 'somename'
    p.undefined_parameter = 'something else'
    p.tasks = [Task(name='some_task', description='some description')]
    proj_id = p.save()
    rsp = client.get('/projects/{}{}'.format(OBJ_PREFIX, proj_id))
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 200

    p2 = Project()
    p2.name = 'some other project name'
    p2.tasks = []
    p2.id = proj_id
    new_project = p2.dumps(pretty_print=True)
    print('sending new content: {}'.format(new_project))
    rsp = client.put('/projects/', data=new_project)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 201
    assert Project.count() == 1
    replaced_project = Project.find_by_query({'_id': proj_id})[0]
    assert replaced_project.name == 'some other project name'
    assert len(replaced_project.tasks) == 0


def test_put_not_found_object(client):
    Project.get_collection().delete_many({})
    p2 = Project()
    p2.name = 'some other project name'
    p2.tasks = []
    p2.id = 'OBJ_123456789012'
    new_project = p2.dumps(pretty_print=True)
    print('sending new content: {}'.format(new_project))
    rsp = client.put('/projects/', data=new_project)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 404
    assert Project.count() == 0
    assert rsp.json.get('_type') == 'ErrorMessage'


def test_metadata(client):
    rsp = client.get('/users/meta')
    assert 200 <= rsp.status_code < 300
    result = rsp.json
    print '\n{}'.format(json.dumps(result, indent=2))
    assert 'description' in result
    assert 'roles' in result
    assert 'created' in result
    assert 'password' in result

    assert 'label' in result.get('description')
    assert result.get('description').get('label') == 'Description'

    assert 'label' in result.get('roles')
    assert result.get('roles').get('label') == 'Roles'

    assert 'label' in result.get('created')
    assert result.get('created').get('label') == 'User.created'

    assert 'label' in result.get('sequence')
    assert result.get('sequence').get('label') == 'User.sequence'

    assert 'label' in result.get('password')
    assert result.get('password').get('label') == 'Password'


def test_schema(client):
    rsp = client.get('/users/schema')
    assert 200 <= rsp.status_code < 300
    result = rsp.json
    print '\n{}'.format(json.dumps(result, indent=2))
    assert '$schema' in result


def test_not_found_url(client):
    rsp = client.get('/users/bad_url')
    result = rsp.json
    print '\n{}'.format(json.dumps(result, indent=2))
    assert rsp.status_code == 404
    assert result.get('_type') == 'ErrorMessage'


def test_bad_parameters(client):
    rsp = client.get('/users/users?as')
    result = rsp.json
    print '\n{}'.format(json.dumps(result, indent=2))
    assert rsp.status_code == 500
    assert result.get('_type') == 'ErrorMessage'
