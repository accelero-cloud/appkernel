from datetime import datetime
from enum import Enum

from money import Money

from appkernel import MongoRepository, Model, Property, date_now_generator, create_uuid_generator, NotEmpty, \
    AppKernelEngine, Role
from appkernel.configuration import config
from appkernel.model import action
from tutorials.order_service.models import Product, ProductSize


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


class Reservation(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('R'))
    order_id = Property(str, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    products = Property(list, sub_type=Product, required=True, validators=NotEmpty())
    state = Property(ReservationState, required=True, default_value=ReservationState.RESERVED)
    stocks = Property(dict, sub_type=dict)
    tracking_id = Property(str)

    def group_products_by_code(self):
        products_by_code = dict()
        for product in self.products:
            size_and_quantity = products_by_code.get(product.code, {product.size.name: 0})
            size_and_quantity[product.size.name] = size_and_quantity.get(product.size.name, 0) + 1
            products_by_code[product.code] = size_and_quantity
        return products_by_code

    @classmethod
    def before_post(cls, *args, **kwargs):
        # method called before the reservation id is sent
        for pcode, size_and_quantity in kwargs['model'].group_products_by_code().items():
            for psize, quantity in size_and_quantity.items():
                # todo: what if there are multiple stock items with the same product code
                query = Stock.where(
                    (Stock.product.code == pcode) & (Stock.product.size == psize) & (Stock.available >= quantity))
                reserved_stock = query.find_one_and_update(available=Stock.available - quantity,
                                                           reserved=Stock.reserved + quantity)
                if not reserved_stock:
                    raise ReservationException(f"There's no stock available for code: {pcode} and size: {psize}.")
                if hasattr(kwargs['model'], 'stocks') and kwargs['model'].stocks is not None:
                    size_and_qty = kwargs['model'].stocks.get(pcode, {psize: {'qty': quantity}})
                    if psize not in size_and_qty:
                        size_and_qty[psize] = {'qty': quantity}
                else:
                    size_and_qty = {psize: {'qty': quantity}}
                    kwargs['model'].stocks = {}
                size_and_qty[psize]['stock'] = reserved_stock.id
                kwargs['model'].stocks[pcode] = size_and_qty

    @classmethod
    def after_post(cls, *args, **kwargs):
        reservation: Reservation = kwargs.get('model')
        print(f'reservation id: {reservation.id}')

    @action(method='PATCH', require=[Role('user')])
    def commit(self):
        self.state = ReservationState.COMMITTED
        self.save()
        return self

    @action(method='PATCH', require=[Role('user')])
    def execute(self, tracking_id):
        self.state = ReservationState.EXECUTED
        self.tracking_id = tracking_id
        self.save()
        for pcode, sizes in self.stocks.items():
            for size, quantity_and_stock in sizes.items():
                stock_id = quantity_and_stock.get('stock')
                query = Stock.where(Stock.id == stock_id)
                modified_count = query.update_one(reserved=Stock.reserved - quantity_and_stock.get('qty'))
                if modified_count != 1:
                    config.app_engine.logger.warn(f'quantities were not reduced for stock: {stock_id}')
        return self

    @action(method='PATCH', require=[Role('user')])
    def cancel(self):
        error = False
        for pcode, sizes in self.stocks.items():
            for size, quantity_and_stock in sizes.items():
                stock_id = quantity_and_stock.get('stock')
                query = Stock.where(Stock.id == stock_id)
                qty = quantity_and_stock.get('qty')
                modified_count = query.update_one(reserved=Stock.reserved - qty, available=Stock.available + qty)
                if modified_count != 1:
                    error = True
                    config.app_engine.logger.warn(f'quantities were not reduced for stock: {stock_id}')
        if not error:
            self.state = ReservationState.CANCELLED
            self.save()
        return self


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
                stock = Stock(available=2,
                              product=Product(code=code, name=tple[0], size=size, price=Money(tple[1], 'EUR')))
                stock.save()
