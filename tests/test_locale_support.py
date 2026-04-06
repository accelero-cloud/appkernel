import os

import pytest
from starlette.testclient import TestClient
from appkernel import extract_model_messages, AppKernelEngine
from tests.utils import User, run_async

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
    print('\nModule: >> {} at {}'.format(module, current_file_path))
    kernel = AppKernelEngine('test_app', cfg_dir='{}/../'.format(current_file_path), development=True)
    kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')
    run_async(User.delete_all())


def test_custom_message_xtractor():
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print('reading test_util py from {}'.format(current_file_path))
    with open('{}/utils.py'.format(current_file_path), 'rb') as file:
        print('------------------------------ \n')
        for tple in extract_model_messages(file, ['_l'], [], {}):
            print(tple)


def validate_result(result):
    assert 'label' in result.get('description')
    assert result.get('description').get('label') == 'Beschreibung'
    assert 'label' in result.get('roles')
    assert result.get('roles').get('label') == 'Rollen'
    assert 'label' in result.get('created')
    assert result.get('created').get('label') == 'User.created'
    assert 'label' in result.get('password')
    assert result.get('password').get('label') == 'Kennwort'
    assert 'label' in result.get('name')
    assert result.get('name').get('label') == 'Benutzername'


def test_basic_translation(client):
    """

    :param client:
    :type client: TestClient
    :return:
    """
    header_types = ['de, de-de;q=0.8, en;q=0.7', 'de-de, de;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5', 'de', 'de-de']
    for header in header_types:
        print(('\n==== current header [{}] ===='.format(header)))
        rsp = client.get('/users/meta', headers={'Accept-Language': header})
        result = rsp.json()
        print('\n{}'.format(json.dumps(result, indent=2)))
        assert 200 <= rsp.status_code < 300
        validate_result(result)

# todo: test translation of the validation exceptions
# todo: test translated field metadata
