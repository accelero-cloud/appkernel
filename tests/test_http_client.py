import os

import pytest
import requests
import requests_mock
from money import Money
from requests import Request

from appkernel import Model
from appkernel.http_client import HttpClientServiceProxy, RequestHandlingException
from tests.test_util import Order, Product, ProductSize, Address, Payment, PaymentMethod

try:
    import simplejson as json
except ImportError:
    import json

client = HttpClientServiceProxy('mock://test.com/')
adapter = None


# todo: test circuit breaker
# todo: test retry, and timing


def custom_matcher(request: Request, context):
    if request.path_url == '/test':
        resp = requests.Response()
        resp.status_code = 200
        return resp
    return None


def setup_module(module):
    current_file_path = os.path.dirname(os.path.realpath(__file__))
    print('\nModule: >> {} at {}'.format(module, current_file_path))
    global adapter
    adapter = requests_mock.Adapter()
    # adapter.add_matcher(custom_matcher)
    client.session.mount('mock', adapter)
    # adapter.register_uri('POST', 'mock://test.com/additional', additional_matcher=match_request_text, text='resp')


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')


def create_order() -> Order:
    order = Order(products=[Product(code='BTX', name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    order.delivery_address = Address(first_name='John', last_name='Doe', city='Big City', street='some address 8',
                                     country='Country', postal_code='1234')
    order.payment_method = Payment(method=PaymentMethod.PAYPAL, customer_id='1234567890123456789012', customer_secret='120')
    return order


def test_simple_get():
    adapter.register_uri('GET', 'mock://test.com/test', text='data')
    code, response = client.wrap('/test').get(payload='payload')
    print(f'-> {code}/{response}')
    assert code == 200
    assert response.get('result') == 'data'


def test_simple_get_timeout():
    adapter.register_uri('GET', 'mock://test.com/timeout', exc=requests.exceptions.ConnectTimeout)
    with pytest.raises(RequestHandlingException) as rhe:
        code, response = client.wrap('/timeout').get(payload='payload')
        print(f'-> {code}/{response}')


def test_simple_post():
    adapter.register_uri('POST', 'mock://test.com/payments/authorise', status_code=201)
    code, response = client.wrap('/payments/authorise').post(payload='payload')
    print(f'-> {code}/{response}')
    assert code == 201


def test_simple_patch():
    adapter.register_uri('PATCH', 'mock://test.com/payments/authorise', status_code=200)
    code, response = client.wrap('/payments/authorise').patch(payload={'id': 'xxxyyy'})
    print(f'-> {code}/{response}')
    assert code == 200


def test_simple_delete():
    adapter.register_uri('DELETE', 'mock://test.com/payments/authorise/12345', status_code=200)
    code, response = client.wrap('/payments/authorise/12345').delete()
    print(f'-> {code}/{response}')
    assert code == 200


def test_service_get():
    adapter.register_uri('GET', 'mock://test.com/orders/12345', status_code=200, text=create_order().dumps())
    rsp_code, rcvd_order = client.orders.get(path_extension='12345')
    print(f' received order {rsp_code} >>> {rcvd_order}')
