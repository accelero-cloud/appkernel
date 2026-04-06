import uuid

import httpx
import pytest
import respx
from moneyed import Money

from appkernel import Model
from appkernel.http_client import HttpClientServiceProxy, RequestHandlingException
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
