from enum import Enum

from money import Money

from appkernel import Model, Property, NotEmpty, ValidationException


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


class PaymentMethod(Enum):
    MASTER = 1,
    VISA = 2,
    PAYPAL = 3,
    DIRECT_DEBIT = 4


class Address(Model):
    first_name = Property(str, required=True, validators=[NotEmpty])
    last_name = Property(str, required=True, validators=[NotEmpty])
    city = Property(str, required=True, validators=[NotEmpty])
    street = Property(str, required=True, validators=[NotEmpty])
    country = Property(str, required=True, validators=[NotEmpty])
    postal_code = Property(str, required=True, validators=[NotEmpty])


class Payment(Model):
    method = Property(PaymentMethod, required=True)
    customer_id = Property(str, required=True, validators=[NotEmpty])
    customer_secret = Property(str, required=True, validators=[NotEmpty])

    def validate(self):
        if self.method in (PaymentMethod.MASTER, PaymentMethod.VISA):
            if len(self.customer_id) < 16 or len(self.customer_secret) < 3:
                raise ValidationException('The card number must be 16 character long and the CVC 3.', self, 'payment')
        elif self.method in (PaymentMethod.PAYPAL, PaymentMethod.DIRECT_DEBIT):
            if len(self.customer_id) < 22:
                raise ValidationException('The IBAN must be at least 22 character long.', self, 'payment')
