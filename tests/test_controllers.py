import os
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient
from appkernel import AppKernelEngine
from appkernel.service import _prepare_resources
from tests.utils import PaymentService

try:
    import simplejson as json
except ImportError:
    import json

kernel = None
payment_service = PaymentService()


@pytest.fixture
def client():
    return TestClient(kernel.app)


def setup_module(module):
    global kernel
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print(f'\nModule: >> {module} at {current_file_path}')
    kernel = AppKernelEngine('test_app', cfg_dir=f'{current_file_path}/../', development=True)
    kernel.register(payment_service)
    payment_service.sink = MagicMock(name='sink')


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')


def test_post(client):
    payload = 'something'
    rsp = client.post('/payments/authorise', content='{"payload":"' + payload + '"}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with(payload)
    payment_service.sink.reset_mock()
    assert rsp.status_code == 200
    assert rsp.json().get('result') == payload


## todo: test post form (positive / negative)
def test_post_form(client):
    rsp = client.post('/authorise/form', data=dict(
        product_id="12345",
        card_number="0123456789",
        amount="10.8"
    ), follow_redirects=True)
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with('12345', '0123456789', '10.8')
    payment_service.sink.reset_mock()
    assert rsp.status_code == 200
    assert rsp.json().get('authorisation_id') == 'xxx-yyy-zzz'


def test_get(client):
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with(str(auth_id))
    assert rsp.status_code == 200
    assert rsp.json().get('id') == '12345'
    payment_service.sink.reset_mock()


def test_get_with_query_params(client):
    rsp = client.get(f'/payments/list_payments?start=1&&stop=5')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with('1', '5')
    assert rsp.status_code == 200
    assert rsp.json().get('start') == '1'
    assert rsp.json().get('stop') == '5'
    payment_service.sink.reset_mock()


def test_get_with_path_param_and_query_params(client):
    rsp = client.get(f'/payments/multiple/12345?start=1&&stop=5')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with('12345', '1', '5')
    assert rsp.status_code == 200
    assert rsp.json().get('start') == '1'
    assert rsp.json().get('stop') == '5'
    assert rsp.json().get('id') == '12345'
    payment_service.sink.reset_mock()


# @pytest.mark.skip(reason="not yet implemented")
def test_delete_simple(client):
    rsp = client.delete(f'/payments/12345')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with('12345')
    assert rsp.status_code == 200
    assert rsp.json().get('status') == 'OK'
    assert rsp.json().get('id') == '12345'
    payment_service.sink.reset_mock()


def test_delete_with_absolute_path(client):
    rsp = client.delete(f'/cancel/12345')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    payment_service.sink.assert_called_once_with('12345')
    assert rsp.status_code == 200
    assert rsp.json().get('deleted') == ["12345"]
    payment_service.sink.reset_mock()


def test_exception(client):
    rsp = client.put(f'/payments/12345')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    assert rsp.status_code == 500
    assert rsp.json().get('_type') == "ErrorMessage"


def test_resource_instance_created_at_registration_not_on_first_request():
    """Prove that _prepare_resources constructs the instance eagerly at registration
    time, so no lazy write-race is possible during request handling."""

    class _InitTracker:
        init_count = 0

        @staticmethod
        def reset():
            _InitTracker.init_count = 0

    class TrackedService:
        def __init__(self):
            _InitTracker.init_count += 1

        def get_item(self):
            return {'ok': True}

    _InitTracker.reset()
    assert _InitTracker.init_count == 0

    # Simulate what kernel.register() does: call _prepare_resources with the class
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    eng = AppKernelEngine('test_eager', cfg_dir=f'{current_file_path}/../', development=True)
    from appkernel.dsl import tag_class_items
    cls_items = tag_class_items(TrackedService.__name__, TrackedService.__dict__)
    _prepare_resources(TrackedService, '/test/', class_items=cls_items)

    # Instance must have been constructed during registration, before any request
    assert _InitTracker.init_count == 1
