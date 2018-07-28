from flask import Flask
from money import Money
from appkernel import AppKernelEngine
from tutorials.inventory_service import Reservation, Stock
from tutorials.models import Product, ProductSize
from tutorials.order_service import Order


def initialise_inventory():
    Stock.delete_all()
    for name, price in {'Black T-Shirt': 12.30, 'Trousers': 20.00, 'Shirt': 72.30, 'Nice Black Shoe': 90.50}.items():
        for size in ProductSize:
            stock = Stock(available=100, product=Product(name=name, size=size, price=Money(price, 'EUR')))
            stock.save()


if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    kernel.register(Reservation, methods=['GET', 'POST', 'PUT'])
    # o = Order(products=[Product(name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    # print(o.dumps(pretty_print=True))
    initialise_inventory()
    kernel.run()
