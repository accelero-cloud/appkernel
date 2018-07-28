from flask import Flask
from money import Money
from appkernel import AppKernelEngine
from tutorials.inventory_service import Reservation, Stock
from tutorials.models import Product, ProductSize
from tutorials.order_service import Order


def initialise_tutorial():
    for name, price in {'Black T-Shirt': 12, 'Trousers': 20, 'Shirt': 70, 'Nice Black Shoe': 90}.items():
        for size in ProductSize:
            stock = Stock(product=Product(name=name, size=size, available=100, price=Money(price, 'EUR')))
            stock.save()


if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    kernel.register(Reservation, methods=['GET', 'POST', 'PUT'])
    # o = Order(products=[Product(name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    # print(o.dumps(pretty_print=True))
    initialise_tutorial()
    kernel.run()
