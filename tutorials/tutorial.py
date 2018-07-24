from flask import Flask
from money import Money
from appkernel import AppKernelEngine
from tutorials.inventory_service import Reservation
from tutorials.models import Product, ProductSize
from tutorials.order_service import Order

if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    kernel.register(Reservation, methods=['GET', 'POST', 'PUT'])
    o = Order(products=[Product(name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    print(o.dumps(pretty_print=True))
    kernel.run()
