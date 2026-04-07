import os
import tempfile
import uuid

import httpx
import pytest
import respx
from moneyed import Money

from appkernel import Model
from appkernel.http_client import (
    CircuitBreakerConfig,
    CircuitOpenError,
    HttpClientServiceProxy,
    RequestHandlingException,
)
from tests.utils import Order, Product, ProductSize, Address, Payment, PaymentMethod

try:
    import simplejson as json
except ImportError:
    import json

pytestmark = pytest.mark.anyio

BASE_URL = 'http://test.com'
client = HttpClientServiceProxy(f'{BASE_URL}/')


def create_order() -> Order:
    order = Order(products=[Product(code='BTX', name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    order.delivery_address = Address(first_name='John', last_name='Doe', city='Big City', street='some address 8',
                                     country='Country', postal_code='1234')
    order.payment_method = Payment(method=PaymentMethod.PAYPAL, customer_id='1234567890123456789012',
                                   customer_secret='120')
    return order


def create_operation_result() -> dict:
    return {'_type': 'OperationResult', 'result': str(uuid.uuid4())}


def create_delete_result() -> dict:
    return {'_type': 'OperationResult', 'result': 1}


def create_not_found_result() -> dict:
    return {
        '_type': 'ErrorMessage',
        'code': 404,
        'message': 'Document with id Oc2e5b438-8d12-4533-b085-c38add1e126d was not deleted.',
        'upstream_service': 'Order'
    }


@respx.mock
async def test_simple_get():
    respx.get(f'{BASE_URL}/test').mock(return_value=httpx.Response(200, text='data'))
    code, response = await client.wrap('/test').get(payload='payload')
    print(f'-> {code}/{response}')
    assert code == 200
    assert response.get('result') == 'data'


@respx.mock
async def test_simple_get_timeout():
    respx.get(f'{BASE_URL}/timeout').mock(side_effect=httpx.ConnectTimeout('timeout'))
    with pytest.raises(RequestHandlingException):
        await client.wrap('/timeout').get(payload='payload')


@respx.mock
async def test_simple_post():
    respx.post(f'{BASE_URL}/payments/authorise').mock(return_value=httpx.Response(201))
    code, response = await client.wrap('/payments/authorise').post(payload='payload')
    print(f'-> {code}/{response}')
    assert code == 201


@respx.mock
async def test_simple_patch():
    respx.patch(f'{BASE_URL}/payments/authorise').mock(return_value=httpx.Response(200))
    code, response = await client.wrap('/payments/authorise').patch(payload='{"id": "xxxyyy"}')
    print(f'-> {code}/{response}')
    assert code == 200


@respx.mock
async def test_simple_delete():
    respx.delete(f'{BASE_URL}/payments/authorise/12345').mock(return_value=httpx.Response(200))
    code, response = await client.wrap('/payments/authorise/12345').delete()
    print(f'-> {code}/{response}')
    assert code == 200


@respx.mock
async def test_service_get():
    respx.get(f'{BASE_URL}/orders/12345').mock(return_value=httpx.Response(200, text=create_order().dumps()))
    rsp_code, rcvd_order = await client.orders.get(path_extension='12345')
    print(f' received order {rsp_code} >>> {rcvd_order.dumps(pretty_print=True)}')
    assert hasattr(rcvd_order, 'delivery_address')
    assert hasattr(rcvd_order, 'payment_method')
    assert '_type' in Model.to_dict(rcvd_order)
    assert len(rcvd_order.products) > 0


@respx.mock
async def test_service_post():
    respx.post(f'{BASE_URL}/orders/').mock(return_value=httpx.Response(200, json=create_operation_result()))
    rsp_code, payload = await client.orders.post(create_order())
    print(f' received order {rsp_code} >>> {payload}')
    assert '_type' in payload
    assert payload.get('_type') == 'OperationResult'


@respx.mock
async def test_patch():
    respx.patch(f'{BASE_URL}/orders/12345').mock(return_value=httpx.Response(200, text=create_order().dumps()))
    rsp_code, order = await client.orders.patch(create_operation_result(), path_extension='12345')
    print(f' received order {rsp_code} >>> {order.dumps(pretty_print=True)}')
    assert hasattr(order, 'delivery_address')
    assert hasattr(order, 'payment_method')
    assert '_type' in Model.to_dict(order)


@respx.mock
async def test_put():
    respx.put(f'{BASE_URL}/orders/12345').mock(return_value=httpx.Response(200, text=create_order().dumps()))
    rsp_code, order = await client.orders.put(create_operation_result(), path_extension='12345')
    print(f' received order {rsp_code} >>> {order.dumps(pretty_print=True)}')
    assert hasattr(order, 'delivery_address')
    assert hasattr(order, 'payment_method')
    assert '_type' in Model.to_dict(order)


@respx.mock
async def test_delete():
    respx.delete(f'{BASE_URL}/orders/12345').mock(return_value=httpx.Response(200, json=create_delete_result()))
    rsp_code, payload = await client.orders.delete(path_extension='12345')
    assert '_type' in payload
    assert payload.get('_type') == 'OperationResult'
    assert payload.get('result') == 1


@respx.mock
async def test_delete_not_found():
    respx.delete(f'{BASE_URL}/orders/12345').mock(return_value=httpx.Response(404, json=create_not_found_result()))
    with pytest.raises(RequestHandlingException):
        await client.orders.delete(path_extension='12345')


# ---------------------------------------------------------------------------
# Circuit breaker integration tests
# ---------------------------------------------------------------------------

@respx.mock
async def test_circuit_opens_after_repeated_500_responses():
    """After failure_threshold consecutive 5xx responses the circuit opens and
    subsequent calls raise CircuitOpenError immediately (no network hit)."""
    cb_proxy = HttpClientServiceProxy(BASE_URL, circuit_breaker=CircuitBreakerConfig(failure_threshold=3))
    error_body = {'_type': 'ErrorMessage', 'code': 500, 'message': 'boom'}
    respx.get(f'{BASE_URL}/items/').mock(return_value=httpx.Response(500, json=error_body))

    for _ in range(3):
        with pytest.raises(RequestHandlingException):
            await cb_proxy.items.get()

    # Circuit is now OPEN — next call must raise CircuitOpenError without hitting the network
    with pytest.raises(CircuitOpenError) as exc_info:
        await cb_proxy.items.get()
    assert exc_info.value.status_code == 503


@respx.mock
async def test_circuit_does_not_open_on_4xx_errors():
    """4xx responses are client errors, not upstream failures — they must not trip the circuit."""
    from appkernel.http_client import CircuitState
    cb_proxy = HttpClientServiceProxy(BASE_URL, circuit_breaker=CircuitBreakerConfig(failure_threshold=2))
    not_found = {'_type': 'ErrorMessage', 'code': 404, 'message': 'not found'}
    respx.get(f'{BASE_URL}/items/').mock(return_value=httpx.Response(404, json=not_found))

    for _ in range(3):
        with pytest.raises(RequestHandlingException):
            await cb_proxy.items.get()

    # Circuit must still be closed after repeated 404s
    assert cb_proxy._circuit.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# File upload / download tests
# ---------------------------------------------------------------------------

@respx.mock
async def test_upload_returns_json_response():
    """upload() sends a multipart POST and deserialises the JSON response."""
    file_ref = {
        'id': 'F123',
        'original_filename': 'photo.jpg',
        'content_type': 'image/jpeg',
        'size': 8,
        'storage_backend': 'filesystem',
        'storage_ref': 'abc-uuid',
    }
    respx.post(f'{BASE_URL}/files/').mock(return_value=httpx.Response(201, json=file_ref))
    code, body = await client.wrap('/files/').upload(
        b'\xff\xd8\xff\xe0',
        filename='photo.jpg',
        content_type='image/jpeg',
    )
    assert code == 201
    assert body.get('id') == 'F123'
    assert body.get('original_filename') == 'photo.jpg'


@respx.mock
async def test_upload_error_raises_request_handling_exception():
    """upload() raises RequestHandlingException on a non-2xx response."""
    error_body = {'_type': 'ErrorMessage', 'code': 422, 'message': 'File too large'}
    respx.post(f'{BASE_URL}/files/').mock(return_value=httpx.Response(422, json=error_body))
    with pytest.raises(RequestHandlingException) as exc_info:
        await client.wrap('/files/').upload(b'x' * 1000, filename='big.bin')
    assert exc_info.value.status_code == 422


@respx.mock
async def test_download_returns_bytes():
    """download() fetches a file and returns raw bytes."""
    content = b'Hello, binary world!'
    respx.get(f'{BASE_URL}/files/F123/content').mock(
        return_value=httpx.Response(200, content=content)
    )
    code, body = await client.wrap('/files/F123/content').download()
    assert code == 200
    assert body == content


@respx.mock
async def test_download_with_path_extension():
    """download() appends path_extension to the wrapper URL."""
    content = b'file bytes'
    respx.get(f'{BASE_URL}/files/F456/content').mock(
        return_value=httpx.Response(200, content=content)
    )
    code, body = await client.wrap('/files').download(path_extension='F456/content')
    assert code == 200
    assert body == content


@respx.mock
async def test_download_error_raises_request_handling_exception():
    """download() raises RequestHandlingException on non-2xx responses."""
    error_body = {'_type': 'ErrorMessage', 'code': 404, 'message': 'Not found'}
    respx.get(f'{BASE_URL}/files/missing/content').mock(
        return_value=httpx.Response(404, json=error_body)
    )
    with pytest.raises(RequestHandlingException) as exc_info:
        await client.wrap('/files/missing/content').download()
    assert exc_info.value.status_code == 404


@respx.mock
async def test_stream_download_yields_chunks():
    """stream_download() yields file bytes as chunks."""
    content = b'chunk1' + b'chunk2'
    respx.get(f'{BASE_URL}/files/F789/content').mock(
        return_value=httpx.Response(200, content=content)
    )
    collected = b''
    async for chunk in client.wrap('/files/F789/content').stream_download():
        collected += chunk
    assert collected == content


@respx.mock
async def test_stream_download_error_raises_request_handling_exception():
    """stream_download() raises RequestHandlingException on non-2xx."""
    respx.get(f'{BASE_URL}/files/bad/content').mock(
        return_value=httpx.Response(404, content=b'not found')
    )
    with pytest.raises(RequestHandlingException) as exc_info:
        async for _ in client.wrap('/files/bad/content').stream_download():
            pass
    assert exc_info.value.status_code == 404


@respx.mock
async def test_download_to_explicit_path():
    """download_to() writes bytes to an explicit file path and returns it."""
    content = b'binary content here'
    respx.get(f'{BASE_URL}/files/F1/content').mock(
        return_value=httpx.Response(
            200,
            content=content,
            headers={'content-disposition': 'attachment; filename="report.pdf"'},
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        save_path = os.path.join(tmp, 'output.bin')
        result = await client.wrap('/files/F1/content').download_to(save_path)
        assert result == os.path.abspath(save_path)
        with open(result, 'rb') as fh:
            assert fh.read() == content


@respx.mock
async def test_download_to_directory_uses_content_disposition_filename():
    """When dest is a directory, the filename comes from Content-Disposition."""
    content = b'pdf bytes'
    respx.get(f'{BASE_URL}/files/F2/content').mock(
        return_value=httpx.Response(
            200,
            content=content,
            headers={'content-disposition': 'attachment; filename="document.pdf"'},
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        result = await client.wrap('/files/F2/content').download_to(tmp)
        assert os.path.basename(result) == 'document.pdf'
        with open(result, 'rb') as fh:
            assert fh.read() == content


@respx.mock
async def test_download_to_directory_falls_back_to_url_segment():
    """Without Content-Disposition, the last URL path segment is used as filename."""
    content = b'image bytes'
    respx.get(f'{BASE_URL}/files/photo.jpg/content').mock(
        return_value=httpx.Response(200, content=content)
    )
    with tempfile.TemporaryDirectory() as tmp:
        result = await client.wrap('/files/photo.jpg/content').download_to(tmp)
        assert os.path.basename(result) == 'content'
        with open(result, 'rb') as fh:
            assert fh.read() == content


@respx.mock
async def test_download_to_error_raises_request_handling_exception():
    """download_to() raises RequestHandlingException on non-2xx responses."""
    respx.get(f'{BASE_URL}/files/gone/content').mock(
        return_value=httpx.Response(404, content=b'not found')
    )
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(RequestHandlingException) as exc_info:
            await client.wrap('/files/gone/content').download_to(tmp)
        assert exc_info.value.status_code == 404


@respx.mock
async def test_upload_from_local_path_infers_filename_and_content_type():
    """upload_from() infers filename and MIME type from the local path."""
    respx.post(f'{BASE_URL}/files/').mock(
        return_value=httpx.Response(201, json={'id': 'F99', 'original_filename': 'data.csv'})
    )
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
        tmp.write(b'col1,col2\n1,2\n')
        tmp_path = tmp.name
    try:
        code, body = await client.wrap('/files/').upload_from(tmp_path)
        assert code == 201
        assert body.get('id') == 'F99'
        # Verify the request used multipart with correct filename
        last_req = respx.calls.last.request
        assert b'data.csv' in last_req.content or b'.csv' in last_req.content
    finally:
        os.unlink(tmp_path)


@respx.mock
async def test_upload_from_explicit_filename_and_content_type():
    """upload_from() respects explicit filename and content_type overrides."""
    respx.post(f'{BASE_URL}/files/').mock(
        return_value=httpx.Response(201, json={'id': 'F100'})
    )
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp:
        tmp.write(b'\x00\x01\x02\x03')
        tmp_path = tmp.name
    try:
        code, body = await client.wrap('/files/').upload_from(
            tmp_path,
            filename='firmware.bin',
            content_type='application/octet-stream',
        )
        assert code == 201
        last_req = respx.calls.last.request
        assert b'firmware.bin' in last_req.content
    finally:
        os.unlink(tmp_path)


@respx.mock
async def test_upload_from_error_raises_request_handling_exception():
    """upload_from() propagates non-2xx responses as RequestHandlingException."""
    error_body = {'_type': 'ErrorMessage', 'code': 422, 'message': 'Bad file'}
    respx.post(f'{BASE_URL}/files/').mock(return_value=httpx.Response(422, json=error_body))
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
        tmp.write(b'hello')
        tmp_path = tmp.name
    try:
        with pytest.raises(RequestHandlingException) as exc_info:
            await client.wrap('/files/').upload_from(tmp_path)
        assert exc_info.value.status_code == 422
    finally:
        os.unlink(tmp_path)


@respx.mock
async def test_stream_download_circuit_open_raises():
    """stream_download() raises CircuitOpenError immediately when circuit is OPEN."""
    from appkernel.http_client import CircuitBreakerConfig
    cb_proxy = HttpClientServiceProxy(BASE_URL, circuit_breaker=CircuitBreakerConfig(failure_threshold=2))
    error_body = {'_type': 'ErrorMessage', 'code': 500, 'message': 'boom'}
    respx.get(f'{BASE_URL}/files/').mock(return_value=httpx.Response(500, json=error_body))

    # Trip the circuit via regular get calls
    for _ in range(2):
        with pytest.raises(RequestHandlingException):
            await cb_proxy.wrap('/files/').get()

    # Now stream_download must raise CircuitOpenError without hitting the network
    with pytest.raises(CircuitOpenError):
        async for _ in cb_proxy.wrap('/files/').stream_download():
            pass


@respx.mock
async def test_circuit_recovers_after_recovery_timeout():
    """After recovery_timeout the circuit moves to HALF_OPEN and a successful
    probe closes it again."""
    import time as _time
    from appkernel.http_client import CircuitState
    cb_proxy = HttpClientServiceProxy(
        BASE_URL,
        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05),
    )
    error_body = {'_type': 'ErrorMessage', 'code': 500, 'message': 'boom'}
    success_body = {'result': 'ok'}

    # Trip the circuit
    respx.get(f'{BASE_URL}/items/').mock(return_value=httpx.Response(500, json=error_body))
    for _ in range(2):
        with pytest.raises(RequestHandlingException):
            await cb_proxy.items.get()
    assert cb_proxy._circuit.state == CircuitState.OPEN

    # Wait for recovery timeout then re-mock to return 200
    _time.sleep(0.06)
    respx.get(f'{BASE_URL}/items/').mock(return_value=httpx.Response(200, json=success_body))
    code, _ = await cb_proxy.items.get()
    assert code == 200
    assert cb_proxy._circuit.state == CircuitState.CLOSED
