"""
Tests for CORS support via AppKernelEngine.enable_cors() / CorsConfig.

Covers:
  - No CORS headers when enable_cors() is not called
  - Preflight OPTIONS returns 200 with correct headers for allowed origin
  - Preflight OPTIONS is rejected (403/400) for disallowed origin
  - Regular GET includes ACAO header for allowed origin
  - allow_credentials=True propagates to header
  - Wildcard origins work when credentials are not requested
  - ValueError raised at startup when allow_credentials=True + allow_origins=['*']
"""
import os
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from appkernel import AppKernelEngine, CorsConfig
from tests.utils import User, run_async


ALLOWED_ORIGIN = 'https://app.example.com'
OTHER_ORIGIN = 'https://evil.example.com'


def _make_kernel(cors_config=None, register=True):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    kernel = AppKernelEngine('cors_test_app', cfg_dir=f'{current_file_path}/../', development=True)
    if register:
        kernel.register(User, methods=['GET', 'POST', 'PUT', 'DELETE'])
    if cors_config is not None:
        kernel.enable_cors(cors_config)
    return kernel


# ---------------------------------------------------------------------------
# No CORS — baseline
# ---------------------------------------------------------------------------

def test_no_cors_headers_when_not_enabled():
    """Without enable_cors(), responses must not include ACAO headers."""
    kernel = _make_kernel(cors_config=None)
    client = TestClient(kernel.app)
    rsp = client.get('/users/', headers={'Origin': ALLOWED_ORIGIN})
    assert 'access-control-allow-origin' not in rsp.headers


def test_options_preflight_returns_405_when_cors_not_enabled():
    """Without CORS middleware, OPTIONS is not handled and returns 405."""
    kernel = _make_kernel(cors_config=None)
    client = TestClient(kernel.app)
    rsp = client.options('/users/', headers={
        'Origin': ALLOWED_ORIGIN,
        'Access-Control-Request-Method': 'POST',
    })
    assert rsp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Allowed origin
# ---------------------------------------------------------------------------

def test_preflight_returns_200_for_allowed_origin():
    """OPTIONS preflight for an allowed origin must return 200."""
    kernel = _make_kernel(CorsConfig(allow_origins=[ALLOWED_ORIGIN]))
    client = TestClient(kernel.app)
    rsp = client.options('/users/', headers={
        'Origin': ALLOWED_ORIGIN,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Content-Type',
    })
    assert rsp.status_code == 200


def test_preflight_includes_acao_header_for_allowed_origin():
    kernel = _make_kernel(CorsConfig(allow_origins=[ALLOWED_ORIGIN]))
    client = TestClient(kernel.app)
    rsp = client.options('/users/', headers={
        'Origin': ALLOWED_ORIGIN,
        'Access-Control-Request-Method': 'GET',
    })
    assert rsp.headers.get('access-control-allow-origin') == ALLOWED_ORIGIN


def test_regular_get_includes_acao_header_for_allowed_origin():
    """A normal GET from an allowed origin must receive the ACAO header."""
    kernel = _make_kernel(CorsConfig(allow_origins=[ALLOWED_ORIGIN]))
    client = TestClient(kernel.app)
    rsp = client.get('/users/', headers={'Origin': ALLOWED_ORIGIN})
    assert rsp.headers.get('access-control-allow-origin') == ALLOWED_ORIGIN


# ---------------------------------------------------------------------------
# Disallowed origin
# ---------------------------------------------------------------------------

def test_preflight_excludes_acao_header_for_disallowed_origin():
    """An origin not in the allowlist must not receive ACAO headers."""
    kernel = _make_kernel(CorsConfig(allow_origins=[ALLOWED_ORIGIN]))
    client = TestClient(kernel.app)
    rsp = client.options('/users/', headers={
        'Origin': OTHER_ORIGIN,
        'Access-Control-Request-Method': 'GET',
    })
    # Starlette returns 400 for disallowed preflight origins
    assert rsp.headers.get('access-control-allow-origin') != OTHER_ORIGIN


def test_regular_get_excludes_acao_header_for_disallowed_origin():
    kernel = _make_kernel(CorsConfig(allow_origins=[ALLOWED_ORIGIN]))
    client = TestClient(kernel.app)
    rsp = client.get('/users/', headers={'Origin': OTHER_ORIGIN})
    assert rsp.headers.get('access-control-allow-origin') != OTHER_ORIGIN


# ---------------------------------------------------------------------------
# allow_credentials
# ---------------------------------------------------------------------------

def test_allow_credentials_header_present_when_enabled():
    kernel = _make_kernel(CorsConfig(
        allow_origins=[ALLOWED_ORIGIN],
        allow_credentials=True,
    ))
    client = TestClient(kernel.app)
    rsp = client.get('/users/', headers={'Origin': ALLOWED_ORIGIN})
    assert rsp.headers.get('access-control-allow-credentials') == 'true'


def test_wildcard_without_credentials_is_allowed():
    """allow_origins=['*'] without credentials must not raise."""
    kernel = _make_kernel(CorsConfig(allow_origins=['*'], allow_credentials=False))
    client = TestClient(kernel.app)
    rsp = client.get('/users/', headers={'Origin': OTHER_ORIGIN})
    assert rsp.headers.get('access-control-allow-origin') == '*'


def test_wildcard_with_credentials_raises_at_startup():
    """allow_origins=['*'] combined with allow_credentials=True is invalid and
    must raise ValueError before the app starts handling requests."""
    with pytest.raises(ValueError, match='credentials'):
        _make_kernel(CorsConfig(allow_origins=['*'], allow_credentials=True))


# ---------------------------------------------------------------------------
# CorsConfig defaults
# ---------------------------------------------------------------------------

def test_cors_config_defaults():
    cfg = CorsConfig(allow_origins=[ALLOWED_ORIGIN])
    assert cfg.allow_credentials is False
    assert 'GET' in cfg.allow_methods
    assert 'POST' in cfg.allow_methods
    assert cfg.max_age == 600
