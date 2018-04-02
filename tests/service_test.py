from flask import Flask
from appkernel import AppKernelEngine, Model, Repository, Service, Parameter, NotEmpty, Regexp, Past
from datetime import datetime
from appkernel.repository import MongoRepository
from test_util import User
import uuid, os, sys
import pytest

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
    assert rsp.json.get('type') == 'ERROR'


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
    assert rsp.json.get('type') == 'ERROR'
