"""Tests for rate_limit.py: RateLimitConfig, RateLimiter, RateLimitMiddleware."""
import os
import time

import pytest
from starlette.testclient import TestClient

from appkernel import AppKernelEngine, RateLimitConfig
from appkernel.rate_limit import RateLimiter
from tests.utils import PaymentService, run_async, User

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
    print('\n\nSETUP ==> ')
    global kernel, payment_service
    payment_service = PaymentService()
    kernel = AppKernelEngine('test_app', cfg_dir=f'{current_file_path()}/../', development=True)
    kernel.register(payment_service)


def teardown_function(function):
    print('\nTEAR DOWN <==')


# ---------------------------------------------------------------------------
# RateLimiter unit tests (no HTTP stack)
# ---------------------------------------------------------------------------

class _FakeRequest:
    """Minimal stand-in for Starlette Request used by RateLimiter.check()."""
    def __init__(self, path: str, ip: str = '10.0.0.1', forwarded_for: str | None = None):
        self.url = type('URL', (), {'path': path})()
        self.client = type('Client', (), {'host': ip})()
        self.headers = {}
        if forwarded_for:
            self.headers['X-Forwarded-For'] = forwarded_for


def test_limiter_allows_requests_within_limit():
    limiter = RateLimiter(RateLimitConfig(requests_per_window=3, window_seconds=60))
    for _ in range(3):
        allowed, retry_after = limiter.check(_FakeRequest('/items/'))
        assert allowed
        assert retry_after == 0


def test_limiter_blocks_request_over_limit():
    limiter = RateLimiter(RateLimitConfig(requests_per_window=3, window_seconds=60))
    for _ in range(3):
        limiter.check(_FakeRequest('/items/'))
    allowed, retry_after = limiter.check(_FakeRequest('/items/'))
    assert not allowed
    assert retry_after > 0


def test_limiter_retry_after_is_positive_integer():
    limiter = RateLimiter(RateLimitConfig(requests_per_window=1, window_seconds=60))
    limiter.check(_FakeRequest('/items/'))
    allowed, retry_after = limiter.check(_FakeRequest('/items/'))
    assert not allowed
    assert isinstance(retry_after, int)
    assert 1 <= retry_after <= 61


def test_limiter_window_reset_allows_new_requests():
    limiter = RateLimiter(RateLimitConfig(requests_per_window=2, window_seconds=1))
    for _ in range(2):
        limiter.check(_FakeRequest('/items/'))
    allowed, _ = limiter.check(_FakeRequest('/items/'))
    assert not allowed
    time.sleep(1.1)
    allowed, retry_after = limiter.check(_FakeRequest('/items/'))
    assert allowed
    assert retry_after == 0


def test_limiter_different_ips_have_independent_counters():
    limiter = RateLimiter(RateLimitConfig(requests_per_window=2, window_seconds=60))
    for _ in range(2):
        limiter.check(_FakeRequest('/items/', ip='10.0.0.1'))
    # ip1 is now at limit
    allowed_1, _ = limiter.check(_FakeRequest('/items/', ip='10.0.0.1'))
    assert not allowed_1
    # ip2 starts fresh
    allowed_2, _ = limiter.check(_FakeRequest('/items/', ip='10.0.0.2'))
    assert allowed_2


def test_limiter_excluded_path_always_allowed():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=1, window_seconds=60, exclude_paths=['/health']
    ))
    for _ in range(10):
        allowed, _ = limiter.check(_FakeRequest('/health'))
        assert allowed


def test_limiter_excluded_path_prefix_match():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=1, window_seconds=60, exclude_paths=['/health']
    ))
    allowed, _ = limiter.check(_FakeRequest('/health/live'))
    assert allowed


def test_limiter_endpoint_limit_overrides_global():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=100,
        window_seconds=60,
        endpoint_limits={'/auth': 2},
    ))
    for _ in range(2):
        limiter.check(_FakeRequest('/auth/login'))
    allowed, _ = limiter.check(_FakeRequest('/auth/login'))
    assert not allowed


def test_limiter_endpoint_limit_does_not_affect_other_paths():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=100,
        window_seconds=60,
        endpoint_limits={'/auth': 2},
    ))
    for _ in range(2):
        limiter.check(_FakeRequest('/auth/login'))
    # /auth is exhausted, but /users should still use the global 100 limit
    allowed, _ = limiter.check(_FakeRequest('/users/'))
    assert allowed


def test_limiter_trust_proxy_header():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=1, window_seconds=60, trust_proxy_headers=True
    ))
    # Two requests from the same forwarded IP — second must be blocked
    limiter.check(_FakeRequest('/items/', forwarded_for='203.0.113.5, 10.0.0.1'))
    allowed, _ = limiter.check(_FakeRequest('/items/', forwarded_for='203.0.113.5, 10.0.0.1'))
    assert not allowed


def test_limiter_proxy_different_forwarded_ips_independent():
    limiter = RateLimiter(RateLimitConfig(
        requests_per_window=1, window_seconds=60, trust_proxy_headers=True
    ))
    limiter.check(_FakeRequest('/items/', forwarded_for='203.0.113.5'))
    # Different forwarded IP — should still be allowed
    allowed, _ = limiter.check(_FakeRequest('/items/', forwarded_for='203.0.113.6'))
    assert allowed


# ---------------------------------------------------------------------------
# Integration tests — full HTTP stack via TestClient
# ---------------------------------------------------------------------------

def test_http_requests_within_limit_succeed(client):
    kernel.enable_rate_limiting(RateLimitConfig(requests_per_window=3, window_seconds=60))
    for _ in range(3):
        rsp = client.get('/payments/123')
        assert rsp.status_code != 429


def test_http_request_over_limit_returns_429(client):
    kernel.enable_rate_limiting(RateLimitConfig(requests_per_window=3, window_seconds=60))
    for _ in range(3):
        client.get('/payments/123')
    rsp = client.get('/payments/123')
    assert rsp.status_code == 429


def test_http_429_response_has_retry_after_header(client):
    kernel.enable_rate_limiting(RateLimitConfig(requests_per_window=1, window_seconds=60))
    client.get('/payments/123')
    rsp = client.get('/payments/123')
    assert rsp.status_code == 429
    assert 'retry-after' in rsp.headers
    assert int(rsp.headers['retry-after']) > 0


def test_http_429_response_body_format(client):
    kernel.enable_rate_limiting(RateLimitConfig(requests_per_window=1, window_seconds=60))
    client.get('/payments/123')
    rsp = client.get('/payments/123')
    assert rsp.status_code == 429
    body = rsp.json()
    assert body.get('code') == 429
    assert 'message' in body


def test_http_excluded_path_not_rate_limited(client):
    kernel.enable_rate_limiting(RateLimitConfig(
        requests_per_window=1,
        window_seconds=60,
        exclude_paths=['/payments'],
    ))
    for _ in range(5):
        rsp = client.get('/payments/123')
        assert rsp.status_code != 429


def test_http_per_endpoint_limit_enforced(client):
    kernel.enable_rate_limiting(RateLimitConfig(
        requests_per_window=100,
        window_seconds=60,
        endpoint_limits={'/payments': 2},
    ))
    for _ in range(2):
        client.get('/payments/123')
    rsp = client.get('/payments/123')
    assert rsp.status_code == 429
