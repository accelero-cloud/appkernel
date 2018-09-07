from datetime import datetime
from money import Money
from appkernel import MongoRepository, Model, Property, create_uuid_generator, date_now_generator, NotEmpty
from appkernel.http_client import HttpClientServiceProxy
from tutorials.inventory_service import Reservation

from tutorials.models import Product, PaymentMethod, Address, Payment
from tutorials.shipping_service import Shipping


class AuthorisationRequest(Model):
    payment_method = Property(PaymentMethod, required=True)
    amount = Property(Money, required=True)
    external_reference = Property(str, required=True, validators=NotEmpty)


class Order(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('O'))
    payment_method = Property(Payment, required=True)
    products = Property(list, sub_type=Product, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    delivery_address = Property(Address, required=True)
    client = HttpClientServiceProxy('http://127.0.0.1:5000/')

    @classmethod
    def before_post(cls, *args, **kwargs):
        order: Order = kwargs.get('model')
        order.finalise_and_validate()
        status_code, rsp_dict = Order.client.reservations.post(Reservation(order_id=order.id, products=order.products))
        order.update(reservation_id=rsp_dict.get('result'))

    @classmethod
    def after_post(cls, *args, **kwargs):
        order: Order = kwargs.get('model')
        amount = sum([p.price.amount for p in order.products])
        auth_req = AuthorisationRequest(payment_method=order.payment_method, amount=amount)
        auth_req.external_reference = order.id
        status_code, rsp_dict = Order.client.wrap('/payments/authorize').post(auth_req)
        print(f'<authorisation response> {rsp_dict}')
        if status_code not in [200, 201]:
            raise Exception('It is not aurhorised')
        else:
            Order.client.shippings.post(Shipping(reservation_id=order.reservation_id, delivery_address=order.delivery_address))
