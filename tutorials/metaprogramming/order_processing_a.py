import time
import random

service_performance = 1


class Order(object):
    def __init__(self, id, total, products, card_number):
        self.id = id
        self.total = total
        self.products = products
        self.card_number = card_number

    def validate(self):
        required_fields = set(['id', 'total', 'products', 'card_number'])
        fields = [f for f in self.__dict__ if not f.startswith('_')]
        assert len(required_fields.intersection(fields)) >= len(required_fields), '!!! validation failed, some fields are missing'


class PaymentService(object):

    @staticmethod
    def authorise_payment(order):
        # simulate magic
        time.sleep(service_performance)
        authorised = random.choice([True, False])
        if authorised:
            print('... authorised payment for card number: {}'.format(order.card_number))
        else:
            print('!!! payment for card {} is declined.'.format(order.card_number))
        return authorised

    @staticmethod
    def reverse_payment(order):
        # simulate magic
        time.sleep(service_performance)
        print('... reversed payment for card number: {}'.format(order.card_number))
        return True


class WarehouseService(object):

    @staticmethod
    def reserve(order):
        # simulate magic
        time.sleep(service_performance)
        shipped = random.choice([True, False])
        if shipped:
            print('... the following products are reserved and shipped: {}'.format(order.products))
        else:
            print('!!! some of the following products is not available anymore: {}.'.format(order.products))
        return shipped


payment_service = PaymentService()
warehouse_service = WarehouseService()


class OrderProcessingService(object):

    @staticmethod
    def process_order(order):
        # the orchestration
        try:
            print('Processing order with id: {}'.format(order.id))
            order.validate()
            if payment_service.authorise_payment(order):
                if not warehouse_service.reserve(order):
                    payment_service.reverse_payment(order)
        except Exception as exc:
            print(str(exc))
            payment_service.reverse_payment(order)


if __name__ == '__main__':
    print('\n\n')
    order_processing_service = OrderProcessingService()
    order_processing_service.process_order(Order('123', '10', ['umbrella', 'socks'], '01234567890'))
