from datetime import datetime
from enum import Enum

from appkernel import Model, Property, create_uuid_generator, MongoRepository, date_now_generator
from money import Money


class ProductSize(Enum):
    S = 1,
    M = 2,
    L = 3,
    XXL = 4


class Product(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('P'))
    name = Property(str, required=True)
    description = Property(str)
    size = Property(ProductSize, required=True)
    price = Property(Money, required=True)


class StockItem(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('S'))
    product = Property(Product, required=True)
    stock = Property(int, required=True, default_value=0)




class Reservation(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator())