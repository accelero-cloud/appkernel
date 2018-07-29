from datetime import datetime
from enum import Enum

from money import Money

from appkernel import Service, MongoRepository, Model, Property, date_now_generator, create_uuid_generator, NotEmpty, \
    AppKernelEngine
from tutorials.models import Product, ProductSize


class ReservationException(Exception):
    def __init__(self, msg):
        super().__init__(msg)


class Stock(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('S'))
    product = Property(Product, required=True)
    available = Property(int, required=True, default_value=0)
    reserved = Property(int, required=True, default_value=0)


class ReservationState(Enum):
    RESERVED = 1,
    COMMITTED = 2,
    EXECUTED = 3,
    CANCELLED = 4


class Reservation(Model, MongoRepository, Service):
    id = Property(str, generator=create_uuid_generator('R'))
    order_id = Property(str, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    products = Property(list, sub_type=Product, required=True, validators=NotEmpty())
    state = Property(ReservationState, required=True, default_value=ReservationState.RESERVED)

    @classmethod
    def before_post(cls, *args, **kwargs):
        product_list = dict()
        for product in kwargs['model'].products:
            size_and_quantity = product_list.get(product.code, dict({product.size.name: 0}))
            size_and_quantity[product.size.name] = size_and_quantity[product.size.name] + 1
            product_list[product.code] = size_and_quantity

        for pcode, size_and_quantity in product_list.items():
            for psize, quantity in size_and_quantity.items():
                query = Stock.where((Stock.product.code == pcode) & (Stock.product.size == psize))
                res = query.update(available=Stock.available - quantity, reserved=Stock.reserved + quantity)
                if res == 0:
                    raise ReservationException(f"There's no stock available for code: {pcode} and size: {psize} / updated count: {res}.")
                elif res > 1:
                    raise ReservationException(f"Multiple product items were reserved ({res}).")


    @classmethod
    def after_post(cls, *args, **kwargs):
        print('bbbb')


class InventoryService(object):

    def __init__(self, appkernel: AppKernelEngine):
        self.appkernel = appkernel
        self.appkernel.register(Reservation, methods=['GET', 'POST', 'PUT'])
        InventoryService.__initialise_inventory()

    @staticmethod
    def __initialise_inventory():
        Stock.delete_all()
        for code, tple in {'BTX': ('Black T-Shirt', 12.30), 'TRS': ('Trousers', 20.00), 'SHRT': ('Shirt', 72.30),
                           'NBS': ('Nice Black Shoe', 90.50)}.items():
            for size in ProductSize:
                stock = Stock(available=100,
                              product=Product(code=code, name=tple[0], size=size, price=Money(tple[1], 'EUR')))
                stock.save()
