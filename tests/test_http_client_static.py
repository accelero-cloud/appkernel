"""
Unit tests for the pure-Python / static parts of appkernel/http_client.py.

No network calls, no httpx mocking. Covers:
  - RequestHandlingException construction
  - RequestWrapper.get_headers()
  - RequestWrapper._serialize()
  - HttpClientServiceProxy URL building (wrap / __getattr__)
  - HttpClientFactory.get()
"""
import json
import pytest

from appkernel import Model
from appkernel.http_client import (
    HttpClientFactory,
    HttpClientServiceProxy,
    RequestHandlingException,
    RequestWrapper,
)


# ---------------------------------------------------------------------------
# RequestHandlingException
# ---------------------------------------------------------------------------

def test_request_handling_exception_stores_status_code():
    exc = RequestHandlingException(502, 'upstream error')
    assert exc.status_code == 502


def test_request_handling_exception_message_accessible():
    exc = RequestHandlingException(404, 'not found')
    assert 'not found' in str(exc)


def test_request_handling_exception_upstream_service_defaults_to_none():
    exc = RequestHandlingException(500, 'oops')
    assert exc.upstream_service is None


def test_request_handling_exception_upstream_service_settable():
    exc = RequestHandlingException(503, 'unavailable')
    exc.upstream_service = 'payments'
    assert exc.upstream_service == 'payments'


# ---------------------------------------------------------------------------
# RequestWrapper.get_headers()
# ---------------------------------------------------------------------------

def test_get_headers_without_auth_returns_accept_language_only():
    headers = RequestWrapper.get_headers()
    assert 'Authorization' not in headers
    assert headers['Accept-Language'] == 'en'


def test_get_headers_with_auth_header_includes_authorization():
    headers = RequestWrapper.get_headers(auth_header='Bearer mytoken')
    assert headers['Authorization'] == 'Bearer mytoken'


def test_get_headers_explicit_language():
    headers = RequestWrapper.get_headers(accept_language='fr')
    assert headers['Accept-Language'] == 'fr'


def test_get_headers_none_language_defaults_to_en():
    headers = RequestWrapper.get_headers(accept_language=None)
    assert headers['Accept-Language'] == 'en'


def test_get_headers_returns_dict():
    assert isinstance(RequestWrapper.get_headers(), dict)


# ---------------------------------------------------------------------------
# RequestWrapper._serialize()
# ---------------------------------------------------------------------------

def test_serialize_none_returns_none():
    assert RequestWrapper._serialize(None) is None


def test_serialize_dict_returns_json_string():
    result = RequestWrapper._serialize({'key': 'value'})
    parsed = json.loads(result)
    assert parsed['key'] == 'value'


def test_serialize_model_calls_dumps():
    class Payload(Model):
        x: str | None = None

    m = Payload(x='hello')
    result = RequestWrapper._serialize(m)
    assert isinstance(result, str)
    assert 'hello' in result


def test_serialize_string_passthrough():
    assert RequestWrapper._serialize('raw-body') == 'raw-body'


def test_serialize_bytes_passthrough():
    assert RequestWrapper._serialize(b'bytes') == b'bytes'


# ---------------------------------------------------------------------------
# HttpClientServiceProxy
# ---------------------------------------------------------------------------

def test_proxy_wrap_builds_correct_url():
    proxy = HttpClientServiceProxy('http://localhost:5000')
    wrapper = proxy.wrap('/users')
    assert wrapper.url == 'http://localhost:5000/users'


def test_proxy_wrap_strips_trailing_slash_from_root():
    proxy = HttpClientServiceProxy('http://api.example.com/')
    wrapper = proxy.wrap('/items')
    assert wrapper.url == 'http://api.example.com/items'


def test_proxy_wrap_strips_leading_slash_from_path():
    proxy = HttpClientServiceProxy('http://localhost:5000')
    wrapper = proxy.wrap('orders')
    assert wrapper.url == 'http://localhost:5000/orders'


def test_proxy_getattr_builds_url_from_attribute_name():
    proxy = HttpClientServiceProxy('http://localhost:5000')
    wrapper = proxy.users
    assert wrapper.url == 'http://localhost:5000/users/'


def test_proxy_getattr_appends_trailing_slash():
    proxy = HttpClientServiceProxy('http://localhost:5000')
    wrapper = proxy.payments
    assert wrapper.url.endswith('/')


def test_proxy_root_url_strips_trailing_slash():
    proxy = HttpClientServiceProxy('http://api.example.com/')
    assert proxy.root_url == 'http://api.example.com'


# ---------------------------------------------------------------------------
# HttpClientFactory
# ---------------------------------------------------------------------------

def test_factory_get_returns_service_proxy():
    proxy = HttpClientFactory.get('http://localhost:5000')
    assert isinstance(proxy, HttpClientServiceProxy)


def test_factory_get_sets_root_url():
    proxy = HttpClientFactory.get('http://example.com')
    assert proxy.root_url == 'http://example.com'


def test_factory_get_strips_trailing_slash():
    proxy = HttpClientFactory.get('http://example.com/')
    assert proxy.root_url == 'http://example.com'


# ---------------------------------------------------------------------------
# RequestWrapper instantiation
# ---------------------------------------------------------------------------

def test_request_wrapper_stores_url():
    wrapper = RequestWrapper('http://localhost:5000/users')
    assert wrapper.url == 'http://localhost:5000/users'
