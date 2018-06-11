import wrapt
import timeit
import inspect
import time
import random
from timeit import default_timer as timer
from requests import ConnectionError


service_performance = 1


def summon_chaos_monkey():
    choice = random.choice([True, False, ConnectionError])
    if isinstance(choice, bool):
        return choice
    else:
        raise choice('Random error')


def retryable(retries=3, delay=1):
    @wrapt.decorator()
    def _decorator(wrapped_function, instance, args, kw):
        number_of_tries = 1
        while True:
            try:
                return wrapped_function(*args, **kw)
            except Exception as exc:
                number_of_tries += 1
                if number_of_tries > retries:
                    raise exc
                else:
                    print('{} caught / retrying...'.format(str(exc)))
                    time.sleep(delay)
    return _decorator

@wrapt.decorator()
def timeit(wrapped_function, instance, args, kw):
    ts = timer()
    result = wrapped_function(*args, **kw)
    te = timer()
    print '>> Audit time: %r  %2.2f ms' % (wrapped_function.__name__, (te - ts) * 1000)
    return result


class ServiceClientType(type):
    def __new__(mcs, class_name, bases, class_dict):
        for member_name, member in class_dict.iteritems():
            if inspect.isroutine(member):
                # class_dict[member_name] = timeit(retryable()(member))
                class_dict[member_name] = timeit(retryable()(member))
        return type.__new__(mcs, class_name, bases, class_dict)


class Order(object):
    def __init__(self, id, total, products, card_number):
        self.id = id
        self.total = total
        self.products = products
        self.card_number = card_number

    def validate(self):
        required_fields = set(['id', 'total', 'products', 'card_number'])
        fields = [f for f in self.__dict__ if not f.startswith('_')]
        assert len(required_fields.intersection(fields)) >= len(
            required_fields), '!!! validation failed, some fields are missing'


class PaymentService(object):
    __metaclass__ = ServiceClientType

    @staticmethod
    def authorise_payment(order):
        # simulate magic
        time.sleep(service_performance)
        authorised = summon_chaos_monkey()
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
    __metaclass__ = ServiceClientType

    @staticmethod
    def reserve_and_ship(order):
        # simulate magic
        time.sleep(service_performance)
        shipped = summon_chaos_monkey()
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
            print('Processing order with id: {} \n======================> \n\n'.format(order.id))
            order.validate()
            if payment_service.authorise_payment(order):
                if not warehouse_service.reserve_and_ship(order):
                    payment_service.reverse_payment(order)
        except Exception as exc:
            print('!!! system exception caught: {}'.format(str(exc)))
            payment_service.reverse_payment(order)


if __name__ == '__main__':
    print('\n\n')
    order_processing_service = OrderProcessingService()
    order_processing_service.process_order(Order('123', '10', ['umbrella', 'socks'], '01234567890'))
