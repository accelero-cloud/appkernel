from flask import Flask
from appkernel import AppKernelEngine
from tutorials.inventory_service import Reservation, InventoryService
from tutorials.order_service import Order
from tutorials.payment_service import PaymentService

if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])
    # o = Order(products=[Product(name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    # print(o.dumps(pretty_print=True))
    inventory_service = InventoryService(kernel)
    kernel.register(PaymentService)
    kernel.run()
