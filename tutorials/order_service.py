from datetime import datetime
from money import Money
from appkernel import MongoRepository, Model, Property, create_uuid_generator, date_now_generator, NotEmpty
from appkernel.http_client import HttpClientServiceProxy
from tutorials.inventory_service import Reservation

from tutorials.models import Product, PaymentMethod


class AuthorisationRequest(Model):
    payment_method = Property(PaymentMethod, required=True)
    amount = Property(Money, required=True)
    external_reference = Property(str, required=True, validators=NotEmpty)


class Order(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('O'))
    payment_method = Property(PaymentMethod, required=True)
    products = Property(list, sub_type=Product, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    client = HttpClientServiceProxy('http://127.0.0.1:5000/')

    @classmethod
    def before_post(cls, *args, **kwargs):
        order = kwargs.get('model')
        status_code, rsp_dict = Order.client.reservations.post(Reservation(order_id=order.id, products=order.products))
        order.update(reservation_id=rsp_dict.get('result'))

    @classmethod
    def after_post(cls, *args, **kwargs):
        order: Order = kwargs.get('model')
        amount = sum([p.price.amount for p in order.products])
        ar = AuthorisationRequest(payment_method=order.payment_method, amount=amount)
        ar.external_reference = order.id
        status_code, rsp_dict = Order.client.wrap('/paymentservice/authorize').post(ar)
