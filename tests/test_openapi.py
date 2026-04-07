"""
Tests for OpenAPI schema generation (appkernel/openapi.py).

The setup registers a User CRUD model and a PaymentService controller, then
calls enable_openapi() so the /openapi.json endpoint is available.  Most
assertions operate on the spec dict returned by the generator directly to
keep the tests fast and independent of a running MongoDB instance.
"""
import os
import pytest
from typing import Annotated
from starlette.testclient import TestClient

from appkernel import (
    AppKernelEngine, Model, resource, action,
    Required, Validators, Generator,
    Min, Max, Regexp, Email,
    create_uuid_generator,
)
from appkernel.openapi import OpenAPISchemaGenerator
from tests.utils import PaymentService, User, Stock

try:
    import simplejson as json
except ImportError:
    import json

kernel = None
payment_service = PaymentService()
_spec: dict = {}   # cached spec dict, populated in setup_module


@pytest.fixture
def client():
    return TestClient(kernel.app)


def setup_module(module):
    global kernel, _spec
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    kernel = AppKernelEngine(
        'openapi_test_app',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    kernel.register(User, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    kernel.register(payment_service)
    kernel.enable_openapi(title='Test API', version='0.0.1', description='Test description')
    # Cache the spec so individual tests do not re-generate it each time
    generator = OpenAPISchemaGenerator(title='Test API', version='0.0.1')
    _spec = generator.generate()


# ---------------------------------------------------------------------------
# /openapi.json HTTP endpoint
# ---------------------------------------------------------------------------

def test_openapi_json_endpoint_returns_200(client):
    rsp = client.get('/openapi.json')
    assert rsp.status_code == 200
    body = rsp.json()
    assert body['openapi'] == '3.1.0'


def test_openapi_spec_has_info_block(client):
    rsp = client.get('/openapi.json')
    info = rsp.json()['info']
    assert info['title'] == 'Test API'
    assert info['version'] == '0.0.1'
    assert info['description'] == 'Test description'


def test_docs_endpoint_returns_html(client):
    rsp = client.get('/docs')
    assert rsp.status_code == 200
    assert b'swagger' in rsp.content.lower() or b'openapi' in rsp.content.lower()


def test_redoc_endpoint_returns_html(client):
    rsp = client.get('/redoc')
    assert rsp.status_code == 200
    assert b'redoc' in rsp.content.lower() or b'openapi' in rsp.content.lower()


# ---------------------------------------------------------------------------
# CRUD paths
# ---------------------------------------------------------------------------

def test_crud_get_collection_in_paths():
    assert '/users/' in _spec['paths']
    assert 'get' in _spec['paths']['/users/']


def test_crud_get_by_id_in_paths():
    assert '/users/{object_id}' in _spec['paths']
    assert 'get' in _spec['paths']['/users/{object_id}']


def test_crud_post_in_paths():
    assert 'post' in _spec['paths']['/users/']


def test_crud_put_in_paths():
    assert 'put' in _spec['paths']['/users/']


def test_crud_patch_in_paths():
    assert 'patch' in _spec['paths']['/users/{object_id}']


def test_crud_delete_in_paths():
    assert 'delete' in _spec['paths']['/users/{object_id}']


# ---------------------------------------------------------------------------
# Component schemas / model field introspection
# ---------------------------------------------------------------------------

def test_model_in_components():
    assert 'User' in _spec['components']['schemas']


def test_model_fields_in_schema():
    schema = _spec['components']['schemas']['User']
    props = schema['properties']
    assert 'name' in props
    assert 'created' in props


def test_model_required_field_in_required_list():
    schema = _spec['components']['schemas']['User']
    assert 'name' in schema['required']


def test_error_message_schema_in_components():
    assert 'ErrorMessage' in _spec['components']['schemas']
    assert _spec['components']['schemas']['ErrorMessage']['type'] == 'object'


def test_envelope_schema_in_components():
    assert 'Envelope' in _spec['components']['schemas']


def test_stock_validator_max_on_code_field():
    gen = OpenAPISchemaGenerator(title='Test API', version='0.0.1')
    schema = Stock.get_json_schema(additional_properties=False)
    # code field has Max(4) validator and str type → maxLength
    assert schema['properties']['code'].get('maxLength') == 4


def test_stock_validator_min_on_open_field():
    schema = Stock.get_json_schema(additional_properties=False)
    # open field has Min(0) validator and float type → minimum
    assert schema['properties']['open'].get('minimum') == 0


def test_user_regexp_on_name_field():
    schema = User.get_json_schema(additional_properties=False)
    assert 'pattern' in schema['properties']['name']


def test_stock_int_validators():
    schema = Stock.get_json_schema(additional_properties=False)
    seq = schema['properties']['sequence']
    assert seq.get('minimum') == 1
    assert seq.get('maximum') == 100


# ---------------------------------------------------------------------------
# Path parameters
# ---------------------------------------------------------------------------

def test_path_param_documented_on_get_by_id():
    op = _spec['paths']['/users/{object_id}']['get']
    param_names = [p['name'] for p in op.get('parameters', [])]
    assert 'object_id' in param_names
    path_param = next(p for p in op['parameters'] if p['name'] == 'object_id')
    assert path_param['in'] == 'path'
    assert path_param['required'] is True


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------

def test_query_params_from_decorator_on_list_payments():
    # PaymentService.list_payments has query_params=['start', 'stop']
    ops = _spec['paths']
    # Find the operation whose operationId ends with list_payments
    op = None
    for path, path_item in ops.items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('list_payments_get'):
                op = operation
                break
    assert op is not None, 'list_payments_get operation not found in spec'
    param_names = [p['name'] for p in op.get('parameters', [])]
    assert 'start' in param_names
    assert 'stop' in param_names
    for p in op['parameters']:
        if p['name'] in ('start', 'stop'):
            assert p['in'] == 'query'


def test_pagination_params_on_collection_route():
    op = _spec['paths']['/users/']['get']
    param_names = [p['name'] for p in op.get('parameters', [])]
    for std in ('page', 'page_size', 'sort_by', 'sort_order'):
        assert std in param_names


# ---------------------------------------------------------------------------
# Standard error responses
# ---------------------------------------------------------------------------

def test_standard_error_responses_on_get():
    op = _spec['paths']['/users/']['get']
    for code in ('400', '401', '403', '404', '500'):
        assert code in op['responses']


def test_standard_error_responses_on_post():
    op = _spec['paths']['/users/']['post']
    for code in ('400', '401', '403', '404', '500'):
        assert code in op['responses']


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------

def test_crud_post_has_request_body():
    op = _spec['paths']['/users/']['post']
    assert 'requestBody' in op
    schema = op['requestBody']['content']['application/json']['schema']
    assert schema == {'$ref': '#/components/schemas/User'}


def test_non_typed_method_falls_back_to_object_schema():
    # PaymentService.authorise has no type hints → fallback schema
    ops = _spec['paths']
    op = None
    for path, path_item in ops.items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('authorise_post'):
                op = operation
                break
    assert op is not None, 'authorise_post operation not found in spec'
    body_schema = op['requestBody']['content']['application/json']['schema']
    assert body_schema == {'type': 'object'}


# ---------------------------------------------------------------------------
# Type-hint inference
# ---------------------------------------------------------------------------

def test_type_hinted_method_infers_request_schema():
    """A service method with a Model-typed parameter should produce a $ref schema."""
    from appkernel.openapi import OpenAPISchemaGenerator

    class _TypedService:
        @resource(method='POST', path='/typed')
        def create_thing(self, user: User) -> User:
            return user

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'typed_openapi_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_TypedService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='typed', version='0.0.1')
    local_spec = gen.generate()

    # Find the typed route
    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('create_thing_post'):
                op = operation
                break
    assert op is not None, 'create_thing_post not found'
    body_schema = op['requestBody']['content']['application/json']['schema']
    assert body_schema == {'$ref': '#/components/schemas/User'}


def test_type_hinted_return_infers_response_schema():
    """A method with a Model return type hint should produce a $ref response schema."""
    from appkernel.openapi import OpenAPISchemaGenerator

    class _ReturnTypedService:
        @resource(method='GET', path='/ret-typed')
        def get_thing(self) -> User:
            return User()

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'ret_typed_openapi_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_ReturnTypedService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='ret_typed', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('get_thing_get'):
                op = operation
                break
    assert op is not None, 'get_thing_get not found'
    response_schema = op['responses']['200']['content']['application/json']['schema']
    assert response_schema == {'$ref': '#/components/schemas/User'}


# ---------------------------------------------------------------------------
# Explicit request_model / response_model overrides
# ---------------------------------------------------------------------------

def test_request_model_override():
    class _OverrideService:
        @resource(method='POST', path='/override', request_model=User)
        def my_endpoint(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'override_req_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_OverrideService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='override', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('my_endpoint_post'):
                op = operation
                break
    assert op is not None
    body_schema = op['requestBody']['content']['application/json']['schema']
    assert body_schema == {'$ref': '#/components/schemas/User'}


def test_response_model_override():
    class _OverrideRespService:
        @resource(method='GET', path='/override-resp', response_model=User)
        def my_endpoint(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'override_resp_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_OverrideRespService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='override', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('my_endpoint_get'):
                op = operation
                break
    assert op is not None
    response_schema = op['responses']['200']['content']['application/json']['schema']
    assert response_schema == {'$ref': '#/components/schemas/User'}


# ---------------------------------------------------------------------------
# summary and tags
# ---------------------------------------------------------------------------

def test_summary_from_decorator():
    class _SummaryService:
        @resource(method='GET', path='/summarised', summary='My Custom Summary')
        def my_endpoint(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'summary_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_SummaryService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='summary', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('my_endpoint_get'):
                op = operation
                break
    assert op is not None
    assert op['summary'] == 'My Custom Summary'


def test_tags_from_decorator():
    class _TaggedService:
        @resource(method='GET', path='/tagged', tags=['payments', 'v2'])
        def my_endpoint(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'tags_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_TaggedService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='tags', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('my_endpoint_get'):
                op = operation
                break
    assert op is not None
    assert op['tags'] == ['payments', 'v2']


# ---------------------------------------------------------------------------
# Collection response envelope
# ---------------------------------------------------------------------------

def test_collection_response_is_envelope_with_items_array():
    op = _spec['paths']['/users/']['get']
    schema = op['responses']['200']['content']['application/json']['schema']
    assert '_items' in schema['properties']
    assert schema['properties']['_items']['type'] == 'array'
    assert schema['properties']['_items']['items'] == {'$ref': '#/components/schemas/User'}


def test_single_get_response_is_model_ref():
    op = _spec['paths']['/users/{object_id}']['get']
    schema = op['responses']['200']['content']['application/json']['schema']
    assert schema == {'$ref': '#/components/schemas/User'}


def test_delete_response_is_operation_result():
    op = _spec['paths']['/users/{object_id}']['delete']
    schema = op['responses']['200']['content']['application/json']['schema']
    assert 'result' in schema['properties']


# ---------------------------------------------------------------------------
# Internal utility routes (schema/meta) are excluded
# ---------------------------------------------------------------------------

def test_internal_schema_route_excluded():
    for path in _spec['paths']:
        assert not path.endswith('/schema'), f'internal /schema route leaked into spec: {path}'
        assert not path.endswith('/meta'), f'internal /meta route leaked into spec: {path}'


# ---------------------------------------------------------------------------
# deprecated decorator kwarg
# ---------------------------------------------------------------------------

def test_deprecated_flag_on_operation():
    class _DeprecatedService:
        @resource(method='GET', path='/old-endpoint', deprecated=True, summary='Use /new instead')
        def old_endpoint(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'deprecated_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_DeprecatedService())
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='deprecated', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('old_endpoint_get'):
                op = operation
                break
    assert op is not None
    assert op.get('deprecated') is True
    assert op['summary'] == 'Use /new instead'


def test_non_deprecated_operation_has_no_deprecated_key():
    # Operations without deprecated=True should NOT include the key at all
    op = _spec['paths']['/users/']['get']
    assert 'deprecated' not in op


# ---------------------------------------------------------------------------
# registration-level tags on kernel.register()
# ---------------------------------------------------------------------------

def test_registration_tags_applied_to_crud_endpoints():
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'reg_tags_crud_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(User, methods=['GET', 'POST'], tags=['v2'])
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='reg_tags', version='0.0.1')
    local_spec = gen.generate()

    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            assert 'v2' in operation.get('tags', []), \
                f'registration tag missing on {method.upper()} {path}'


def test_registration_tags_applied_to_service_endpoints():
    class _TaggedPaymentService:
        @resource(method='POST', path='/pay')
        def pay(self):
            pass

        @resource(method='GET', path='/status', tags=['status'])
        def status(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'reg_tags_service_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_TaggedPaymentService(), tags=['payments'])
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='reg_tags_svc', version='0.0.1')
    local_spec = gen.generate()

    pay_op = status_op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            op_id = operation.get('operationId', '')
            if op_id.endswith('pay_post'):
                pay_op = operation
            elif op_id.endswith('status_get'):
                status_op = operation

    assert pay_op is not None
    assert 'payments' in pay_op['tags']

    # decorator tag 'status' is appended after the registration tag 'payments'
    assert status_op is not None
    assert status_op['tags'] == ['payments', 'status']


def test_registration_tags_merge_order():
    """Registration tags come before decorator-level tags."""
    class _MergeService:
        @resource(method='GET', path='/merge', tags=['decorator-tag'])
        def merge(self):
            pass

    current_file_path = os.path.dirname(os.path.realpath(__file__))
    local_kernel = AppKernelEngine(
        'merge_tags_test',
        cfg_dir=f'{current_file_path}/../',
        development=True,
    )
    local_kernel.register(_MergeService(), tags=['reg-tag'])
    local_kernel.enable_openapi(include_docs=False)

    gen = OpenAPISchemaGenerator(title='merge', version='0.0.1')
    local_spec = gen.generate()

    op = None
    for path, path_item in local_spec['paths'].items():
        for method, operation in path_item.items():
            if operation.get('operationId', '').endswith('merge_get'):
                op = operation
                break
    assert op is not None
    assert op['tags'] == ['reg-tag', 'decorator-tag']
