from datetime import datetime
from flask import request
from appkernel import MongoRepository, Model, Property, create_uuid_generator, date_now_generator, Service
from appkernel.http_client import HttpClientServiceProxy
from tutorials.inventory_service import Reservation

from tutorials.models import Product


class Order(Model, MongoRepository, Service):
    id = Property(str, generator=create_uuid_generator('O'))
    products = Property(list, sub_type=Product, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)

    @classmethod
    def after_post(cls, *args, **kwargs):
        print(request.args)
        print(request.headers)
        client = HttpClientServiceProxy('http://127.0.0.1:5000/')
        order = kwargs['model']
        status_code, rsp_dict = client.reservation.post(Reservation(order_id=order.id, products=order.products))
        print(f'status: {status_code} -> {rsp_dict}')