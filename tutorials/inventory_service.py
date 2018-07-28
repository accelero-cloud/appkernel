from datetime import datetime
from enum import Enum
from appkernel import Service, MongoRepository, Model, Property, date_now_generator, create_uuid_generator, NotEmpty
from tutorials.models import Product


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
        Stock.find()

    @classmethod
    def after_post(cls, *args, **kwargs):
        print('bbbb')
