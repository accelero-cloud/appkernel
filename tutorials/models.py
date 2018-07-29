from enum import Enum

from appkernel import Model, Property, create_uuid_generator, MongoRepository, date_now_generator, UniqueIndex, NotEmpty
from money import Money


class ProductSize(Enum):
    S = 1,
    M = 2,
    L = 3,
    XXL = 4


class Product(Model):
    code = Property(str, required=True, validators=[NotEmpty])
    name = Property(str, required=True)
    description = Property(str)
    size = Property(ProductSize, required=True)
    price = Property(Money, required=True)
