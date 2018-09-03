import os
from unittest.mock import MagicMock

import pytest
from flask import Flask
from appkernel import AppKernelEngine
from tests.test_util import list_flask_routes, PaymentService

try:
    import simplejson as json
except ImportError:
    import json

flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'S0m3S3cr3tC0nt3nt!'
flask_app.testing = True
payment_service = PaymentService()
# todo: test only http method names as class methods and external security config
# todo: test resource decorator with and without security
# todo: test mixture of the above two
# todo: test class naming convention with Resource, Service, Controller ending
# todo: negative tests (eg. wrong instance generation)


@pytest.fixture
def app():
    return flask_app


def setup_module(module):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print('\nModule: >> {} at {}'.format(module, current_file_path))
    kernel = AppKernelEngine('test_app', app=flask_app, cfg_dir='{}/../'.format(current_file_path), development=True)
    kernel.register(payment_service)
    payment_service.sink = MagicMock(name='sink')
    list_flask_routes(flask_app)


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')


def test_post(client):
    payload = 'something'
    rsp = client.post('/payments/authorise', data='{"payload":"' + payload + '"}')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with(payload)
    payment_service.sink.reset_mock()
    assert rsp.status_code == 200
    assert rsp.json.get('result') == payload


## todo: test post form (positive / negative)
def test_post_form(client):
    rsp = client.post('/authorise/form', data=dict(
        product_id="12345",
        card_number="0123456789",
        amount="10.8"
    ), follow_redirects=True)
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with('12345', '0123456789', '10.8')
    payment_service.sink.reset_mock()
    assert rsp.status_code == 200
    assert rsp.json.get('authorisation_id') == 'xxx-yyy-zzz'


def test_get(client):
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with(str(auth_id))
    assert rsp.status_code == 200
    assert rsp.json.get('id') == '12345'
    payment_service.sink.reset_mock()


def test_get_with_query_params(client):
    rsp = client.get(f'/payments/list_payments?start=1&&stop=5')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with('1', '5')
    assert rsp.status_code == 200
    assert rsp.json.get('start') == '1'
    assert rsp.json.get('stop') == '5'
    payment_service.sink.reset_mock()


def test_get_with_path_param_and_query_params(client):
    rsp = client.get(f'/payments/multiple/12345?start=1&&stop=5')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with('12345', '1', '5')
    assert rsp.status_code == 200
    assert rsp.json.get('start') == '1'
    assert rsp.json.get('stop') == '5'
    assert rsp.json.get('id') == '12345'
    payment_service.sink.reset_mock()


# @pytest.mark.skip(reason="not yet implemented")
def test_delete_simple(client):
    rsp = client.delete(f'/payments/12345')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with('12345')
    assert rsp.status_code == 200
    assert rsp.json.get('status') == 'OK'
    assert rsp.json.get('id') == '12345'
    payment_service.sink.reset_mock()


def test_delete_with_absolute_path(client):
    rsp = client.delete(f'/cancel/12345')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    payment_service.sink.assert_called_once_with('12345')
    assert rsp.status_code == 200
    assert rsp.json.get('deleted') == ["12345"]
    payment_service.sink.reset_mock()


def test_exception(client):
    rsp = client.put(f'/payments/12345')
    print('\nResponse: {} -> {}'.format(rsp.status, rsp.data))
    assert rsp.status_code == 500
    assert rsp.json.get('_type') == "ErrorMessage"
