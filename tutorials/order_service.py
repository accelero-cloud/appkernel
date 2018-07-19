from datetime import datetime
from flask import request, Flask
from appkernel import MongoRepository, Model, Property, create_uuid_generator, date_now_generator, Service, \
    AppKernelEngine

from tutorials.models import Product


class Reservation(Model):
    pass


class Order(Model, MongoRepository, Service):
    id = Property(str, generator=create_uuid_generator('O'))
    products = Property(list, sub_type=Product, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)


    @classmethod
    def before_post(cls, *args, **kwargs):
        print(request.args)
        print(request.headers)


if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id))
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    kernel.run()
