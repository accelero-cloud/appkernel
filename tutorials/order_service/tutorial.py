from flask import Flask

from appkernel import AppKernelEngine
from tutorials.order_service import InventoryService, Order
from tutorials.order_service import PaymentService
from tutorials.order_service import ShippingService

if __name__ == '__main__':
    app_id = "{} Service".format(Order.__name__)
    kernel = AppKernelEngine(app_id, app=Flask(app_id), development=True, enable_defaults=True)
    kernel.register(Order, methods=['GET', 'POST', 'DELETE'])

    # o = Order(products=[Product(code='BTX', name='t-shirt', size=ProductSize.M, price=Money(10, 'EUR'))])
    # o.delivery_address = Address(first_name='John', last_name='Doe', city='Big City', street='some address 8',
    #                              country='Country', postal_code='1234')
    # o.payment_method = Payment(method=PaymentMethod.PAYPAL, customer_id='1234567', customer_secret='120')
    # print(o.dumps(pretty_print=True))
    inventory_service = InventoryService(kernel)
    kernel.register(PaymentService())
    kernel.register(ShippingService())
    kernel.run()
