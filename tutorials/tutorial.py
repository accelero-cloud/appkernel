from flask import Flask

from appkernel import AppKernelEngine
from tutorials.inventory_service import Reservation
from tutorials.order_service import Order

if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    kernel.register(Reservation, methods=['GET', 'POST', 'PUT'])
    kernel.run()
