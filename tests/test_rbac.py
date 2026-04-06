import os
import time
import pytest
from starlette.testclient import TestClient
from appkernel import AppKernelEngine, Role, Denied
from appkernel.authorisation import check_token
from tests.utils import User, create_and_save_a_user, PaymentService, run_async

try:
    import simplejson as json
except ImportError:
    import json

kernel = None
payment_service = PaymentService()


@pytest.fixture
def client():
    return TestClient(kernel.app)


def current_file_path():
    return os.path.dirname(os.path.realpath(__file__))


def setup_module(module):
    print(f'\nModule: >> {module} at {current_file_path()}')


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')

    global kernel
    kernel = AppKernelEngine('test_app', cfg_dir=f'{current_file_path()}/../', development=True)
    kernel.enable_security()
    kernel.register(payment_service).require(Role('admin'), methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    run_async(User.delete_all())


def teardown_function(function):
    """ teardown any state that was previously setup with a setup_method
    call.
    """
    print("\nTEAR DOWN <==")


def test_create_token():
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    print(f'\n{user.dumps(pretty_print=True)}')
    token = user.auth_token
    print(f'token: {token}')
    decoded_token = check_token(token)
    print(f'decoded with public key (internal): {decoded_token}')


def create_basic_user():
    u = User().update(name='some_user', password='some_pass')
    run_async(u.save())
    return u


def default_config():
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all().require(Role('user'), methods='GET').require(Role('admin'),
                                                                         methods=['PUT', 'POST', 'PATCH', 'DELETE'])
    return create_basic_user()


def test_auth_basic_deny_without_token(client):
    user = default_config()
    headers = {}
    headers['X-Tenant'] = 'rockee'
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    # assert rsp.status_code == 401, 'should be unauthorized'
    # assert rsp.json().get('message') == 'The authorisation header is missing.'


def test_auth_basic_garbage_token(client):
    user = default_config()
    headers = {}
    user.update(roles=['user', 'admin'])
    headers['Authorization'] = 'Bearer {}'.format('eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.')
    rsp = client.get('/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json().get('message') == 'Not enough segments'


def test_auth_basic_missing_signature(client):
    user = default_config()
    headers = {}
    user.update(roles=['user', 'admin'])
    headers['Authorization'] = 'Bearer {}'.format(
        'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE1Mjc0Mjc3NDcsInJvbGVzIjpbIkFkbWluIiwiVXNlciIsIk9wZXJhdG9yIl0sInN1YiI6IlVjNzZkMjEyNy1iM2Y2LTQ1ZGUtYmU4YS0xMjg5MWMwMzM4YmYiLCJleHAiOjE1Mjc0MzEzNDd9.')
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json().get('message') == 'Signature verification failed'


def test_auth_malformed_header_scheme_only(client):
    """Authorization: Bearer  (no token after the scheme) must return 401,
    not 403 with a raw Python IndexError message."""
    default_config()
    rsp = client.get('/users/', headers={'Authorization': 'Bearer'})
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 401, 'malformed header should be 401 Unauthorized'
    assert 'list index out of range' not in rsp.json().get('message', ''), \
        'implementation detail must not leak into the response'


def test_auth_malformed_header_token_only(client):
    """Authorization: <token_without_scheme>  must return 401."""
    default_config()
    rsp = client.get('/users/', headers={'Authorization': 'eyJhbGciOiJSUzI1NiJ9.payload.sig'})
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 401, 'malformed header should be 401 Unauthorized'
    assert 'list index out of range' not in rsp.json().get('message', ''), \
        'implementation detail must not leak into the response'


def test_auth_malformed_header_wrong_scheme(client):
    """Authorization: Basic <token>  (wrong scheme) must return 401."""
    default_config()
    rsp = client.get('/users/', headers={'Authorization': 'Basic eyJhbGciOiJSUzI1NiJ9.payload.sig'})
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 401, 'non-Bearer scheme should be 401 Unauthorized'


def test_auth_basic_deny_with_token_without_roles(client):
    user = default_config()
    headers = {}
    headers['X-Custom'] = 'rookie'
    headers['Authorization'] = f'Bearer {user.auth_token}'
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json().get('message') == 'The required permission is missing.'


def test_auth_basic_with_token_and_roles(client):
    user = default_config()
    headers = {}
    headers['X-Tenant'] = 'rockee'
    user.update(roles=['user', 'admin'])
    headers['Authorization'] = f'Bearer {user.auth_token}'
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'should be accepted'


def test_auth_basic_with_expired_token(client):
    user = default_config()
    headers = {}
    User.set_validity(1)
    user.update(roles=['user', 'admin'])
    headers['Authorization'] = f'Bearer {user.auth_token}'
    time.sleep(2)
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be forbidden'
    assert rsp.json().get('message') == 'Signature has expired'


def test_auth_decorated_link_missing_token(client):
    user = default_config()
    headers = {}
    headers['X-Tenant'] = 'rockee'
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post(f'/users/{user.id}/change_password', content=post_data, headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 401, 'should be unauthorized'


def test_auth_decorated_link_good_token_correct_authority(client):
    user = default_config()
    headers = {}
    headers['X-Tenant'] = 'rockee'
    headers['Authorization'] = f'Bearer {user.auth_token}'
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post(f'/users/{user.id}/change_password', content=post_data, headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'should be ok'


def test_auth_decorated_link_good_token_wrong_authority(client):
    user1 = default_config()
    user2 = User(name='second user', password='second-pass', roles=['user'])
    run_async(user2.save())
    headers = {}
    headers['Authorization'] = f'Bearer {user2.auth_token}'
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post(f'/users/{user1.id}/change_password', content=post_data, headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be ok'


def test_auth_decorated_link_good_token_admin_role(client):
    user1 = default_config()
    user2 = User(name='second user', password='second-pass', roles=['user', 'admin'])
    run_async(user2.save())
    headers = {}
    headers['Authorization'] = f'Bearer {user2.auth_token}'
    post_data = json.dumps({'current_password': 'some_pass', 'new_password': 'newpass'})
    rsp = client.post(f'/users/{user1.id}/change_password', content=post_data, headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'should be ok'
    assert rsp.json().get('result') == 'Password changed'

    # for h in rsp.headers:
    #     print h
    # self.assertTrue('WWW-Authenticate' in rv.headers)
    # self.assertTrue('Basic' in rv.headers['WWW-Authenticate'])


def test_auth_explicit_anonymous(client):
    user = default_config()
    user.description = 'A dummy user'
    run_async(user.save())
    headers = {}
    rsp = client.get(f'/users/{user.id}/get_description', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'should be ok'
    assert rsp.json().get('result') == 'A dummy user'


def test_deny_all(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all()
    user = create_basic_user()
    user.update(roles=['user', 'admin'])
    headers = {}
    headers['Authorization'] = f'Bearer {user.auth_token}'
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json().get('message') == 'Not allowed to access method.'

    rsp = client.delete(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json().get('message') == 'Not allowed to access method.'


def test_default_state_with_enabled_security(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.deny_all()
    user = create_basic_user()
    user.update(roles=['user', 'admin'])
    headers = {}
    headers['Authorization'] = f'Bearer {user.auth_token}'
    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'should be accepted'
    assert rsp.json().get('message') == 'Not allowed to access method.'


def test_enable_all(client):
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.allow_all()
    user = create_basic_user()
    rsp = client.get(f'/users/{user.id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'should be enabled'


# def test_exempt(client, current_file_path):
#     user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
#     user_service.deny_all().exempt(Anonymous(), methods=['GET'])

def test_deny_specific_method(client):
    """deny() must restrict a specific HTTP method while leaving others accessible."""
    user_service = kernel.register(User, methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
    user_service.allow_all().deny(Denied(), methods=['DELETE'])
    user = create_basic_user()
    headers = {'Authorization': f'Bearer {user.auth_token}'}

    rsp = client.get(f'/users/{user.id}', headers=headers)
    print(f'\nGET Response: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 200, 'GET should be allowed by allow_all()'

    rsp = client.delete(f'/users/{user.id}', headers=headers)
    print(f'\nDELETE Response: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403, 'DELETE should be denied by deny(Denied(), ["DELETE"])'
    assert rsp.json().get('message') == 'Not allowed to access method.'


def test_get_controller_with_security_missing_header(client):
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}')
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    assert rsp.status_code == 401
    assert rsp.json().get('message') == 'The authorisation header is missing.'


def test_get_controller_with_wrong_role(client):
    user = default_config()
    headers = {}
    headers['Authorization'] = f'Bearer {user.auth_token}'
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    assert rsp.status_code == 403
    assert rsp.json().get('message') == 'The required permission is missing.'


def test_get_controller_correct(client):
    user = default_config()
    user.update(roles=['user', 'admin'])
    headers = {}
    headers['Authorization'] = f'Bearer {user.auth_token}'
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.content}')
    assert rsp.status_code == 200
    assert rsp.json().get('id') == '12345'


def test_token_audience_matches_app_id(client):
    """A token issued by this engine must carry aud == app_id ('test_app')."""
    from appkernel.configuration import config
    import jwt as _jwt
    user = default_config()
    user.update(roles=['user', 'admin'])
    decoded = _jwt.decode(
        user.auth_token,
        config.public_key,
        algorithms=['RS256'],
        audience='test_app',
    )
    assert decoded['aud'] == 'test_app'


def test_token_wrong_audience_is_rejected(client):
    """A token with a different aud claim must be rejected with 403."""
    import datetime
    import jwt as _jwt
    from appkernel.configuration import config
    user = default_config()
    user.update(roles=['user', 'admin'])
    # Forge a valid-signature token addressed to a different service
    payload = {
        'exp': datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=3600),
        'iat': datetime.datetime.now(datetime.UTC),
        'sub': str(user.id),
        'aud': 'other_service',
        'roles': ['user', 'admin'],
    }
    wrong_aud_token = _jwt.encode(payload, key=config.private_key, algorithm='RS256')
    headers = {'Authorization': f'Bearer {wrong_aud_token}'}
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403


def test_token_missing_audience_is_rejected(client):
    """A token with no aud claim must be rejected once audience validation is enforced."""
    import datetime
    import jwt as _jwt
    from appkernel.configuration import config
    user = default_config()
    user.update(roles=['user', 'admin'])
    # Token without any aud claim
    payload = {
        'exp': datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=3600),
        'iat': datetime.datetime.now(datetime.UTC),
        'sub': str(user.id),
        'roles': ['user', 'admin'],
    }
    no_aud_token = _jwt.encode(payload, key=config.private_key, algorithm='RS256')
    headers = {'Authorization': f'Bearer {no_aud_token}'}
    auth_id = 12345
    rsp = client.get(f'/payments/{auth_id}', headers=headers)
    print(f'\nResponse: {rsp.status_code} -> {rsp.text}')
    assert rsp.status_code == 403
