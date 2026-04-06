from datetime import datetime, date
from enum import Enum
from typing import Annotated

from moneyed import Money
import bcrypt
from pydantic import Field

from appkernel import AuditableRepository, MongoRepository, AppKernelException, ValidationException, Email, Unique
from appkernel import IdentityMixin, Role, CurrentSubject, Anonymous, TextIndex, Index
from appkernel import Max, Min
from appkernel import Model, UniqueIndex
from appkernel import NotEmpty, Regexp, Past, Future, create_uuid_generator, date_now_generator, content_hasher
from appkernel import ServiceException
from appkernel.generators import TimestampMarshaller, MongoDateTimeMarshaller
from appkernel.dsl import action, resource
from appkernel.fields import Required, Generator, Converter, Default, Validators, Marshal, MongoIndex, MongoUniqueIndex, MongoTextIndex

_ = lambda x: x


class User(Model, MongoRepository, IdentityMixin):
    id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
    name: Annotated[str | None, Required(), Validators(NotEmpty, Regexp('[A-Za-z0-9-_]')),
                    MongoUniqueIndex()] = None
    password: Annotated[str | None, Required(), Validators(NotEmpty),
                        Converter(content_hasher(rounds=10)), Field(exclude=True)] = None
    description: Annotated[str | None, MongoTextIndex()] = None
    roles: list[str] | None = None
    created: Annotated[datetime | None, Required(), Validators(Past), Generator(date_now_generator)] = None
    last_login: Annotated[datetime | None, Marshal(TimestampMarshaller)] = None
    sequence: Annotated[int | None, MongoIndex()] = None

    @action(rel='change_password', method='POST', require=[CurrentSubject(), Role('admin')])
    async def change_p(self, current_password, new_password):
        if not bcrypt.checkpw(current_password.encode('utf-8'), self.password.encode('utf-8')):
            raise ServiceException(403, _('Current password is not correct'))
        else:
            self.password = new_password
            await self.save()
        return _('Password changed')

    @action(require=Anonymous())
    def get_description(self):
        return self.description


class Group(Model, MongoRepository):
    id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
    name: Annotated[str | None, Required(), Validators(NotEmpty, Regexp('[A-Za-z0-9-_]')),
                    MongoUniqueIndex()] = None
    users: list[User] | None = None


class Stock(Model):
    code: Annotated[str | None, Required(), Validators(NotEmpty, Regexp('[A-Za-z0-9-_]'), Max(4)),
                    MongoUniqueIndex()] = None
    open: Annotated[float | None, Required(), Validators(Min(0))] = None
    updated: Annotated[datetime | None, Required(), Validators(Past), Generator(date_now_generator)] = None
    history: list[float] | None = None
    sequence: Annotated[int | None, Validators(Min(1), Max(100))] = None


class Portfolio(Model, MongoRepository):
    id: Annotated[str | None, Required(), Generator(create_uuid_generator('P'))] = None
    name: Annotated[str | None, Required(), Validators(NotEmpty, Regexp('[A-Za-z0-9-_]')),
                    MongoUniqueIndex()] = None
    stocks: Annotated[list[Stock] | None, Validators(NotEmpty)] = None
    owner: User | None = None


class Application(Model, MongoRepository):
    id: Annotated[str | None, Generator(create_uuid_generator())] = None
    application_date: Annotated[date | None, Required(), Marshal(MongoDateTimeMarshaller)] = None


class ProductSize(Enum):
    S = 1,
    M = 2,
    L = 3,
    XXL = 4


class ReservationState(Enum):
    RESERVED = 1,
    COMMITTED = 2,
    EXECUTED = 3,
    CANCELLED = 4


class Product(Model):
    code: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    name: Annotated[str | None, Required()] = None
    description: str | None = None
    size: Annotated[ProductSize | None, Required()] = None
    price: Annotated[Money | None, Required()] = None


class StockInventory(Model, MongoRepository):
    id: Annotated[str | None, Generator(create_uuid_generator('S'))] = None
    product: Annotated[Product | None, Required()] = None
    available: Annotated[int | None, Required(), Default(0)] = None
    reserved: Annotated[int | None, Required(), Default(0)] = None


class PaymentMethod(Enum):
    MASTER = 1,
    VISA = 2,
    PAYPAL = 3,
    DIRECT_DEBIT = 4


class Address(Model):
    first_name: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    last_name: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    city: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    street: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    country: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    postal_code: Annotated[str | None, Required(), Validators(NotEmpty)] = None


class Payment(Model):
    method: Annotated[PaymentMethod | None, Required()] = None
    customer_id: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    customer_secret: Annotated[str | None, Required(), Validators(NotEmpty)] = None

    def validate(self):
        if self.method in (PaymentMethod.MASTER, PaymentMethod.VISA):
            if len(self.customer_id) < 16 or len(self.customer_secret) < 3:
                raise ValidationException('The card number must be 16 character long and the CVC 3.', self,
                                          'payment_method')
        elif self.method in (PaymentMethod.PAYPAL, PaymentMethod.DIRECT_DEBIT):
            if len(self.customer_id) < 22:
                raise ValidationException('The IBAN must be at least 22 character long.', self, 'payment_method')


class Order(Model):
    id: Annotated[str | None, Generator(create_uuid_generator('O'))] = None
    payment_method: Annotated[Payment | None, Required()] = None
    products: Annotated[list[Product] | None, Required()] = None
    order_date: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None
    delivery_address: Annotated[Address | None, Required()] = None


class Reservation(Model, MongoRepository):
    id: Annotated[str | None, Generator(create_uuid_generator('R'))] = None
    order_id: Annotated[str | None, Required()] = None
    order_date: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None
    products: Annotated[list[Product] | None, Required(), Validators(NotEmpty())] = None
    state: Annotated[ReservationState | None, Required(), Default(ReservationState.RESERVED)] = None


class PaymentService:

    @resource(method='POST', require=[Role('user')])
    def authorise(self, payload):
        print(f'\n--> received as payload: {payload}\n')
        self.sink(payload)
        return payload

    @resource(method='POST', path='/authorise/form', require=[Role('user')])
    def authorise_payment(self, product_id, card_number, amount):
        print(f'\n--> received as payload: {product_id} / {card_number} / {amount}\n')
        self.sink(product_id, card_number, amount)
        return {'authorisation_id': 'xxx-yyy-zzz'}

    @resource(method='GET', path='./<authorisation_id>', require=[Role('user')])
    def check_status(self, authorisation_id):
        if hasattr(self, 'sink'):
            self.sink(authorisation_id)
        return {'id': authorisation_id, 'status': 'OK'}

    @resource(method='GET', query_params=['start', 'stop'], require=[Role('user')])
    def list_payments(self, start=None, stop=None):
        self.sink(start, stop)
        return {'start': start, 'stop': stop}

    @resource(method='GET', path='./multiple/<authorisation_id>', query_params=['start', 'stop'],
              require=[Role('user')])
    def check_multiple_status(self, authorisation_id, start=None, stop=None):
        self.sink(authorisation_id, start, stop)
        return {'id': authorisation_id, 'start': start, 'stop': stop}

    @resource(method='DELETE', path='./<authorisation_id>', require=[Role('user')])
    def reverse(self, authorisation_id):
        self.sink(authorisation_id)
        return {'id': authorisation_id, 'status': 'OK'}

    @resource(method='DELETE', path='/cancel/<payment_ids>', require=[Role('user')])
    def delete_many(self, payment_ids):
        self.sink(payment_ids)
        return {'deleted': [pid for pid in payment_ids.split(',')]}

    @resource(method='PUT', path='./<payment_ids>', require=[Role('user')])
    def blow(self, payment_ids):
        raise AppKernelException('throwing some custom exception')


def create_portfolio(name):
    msft = Stock(code='MSFT', open=123.7, updated=date_now_generator(), history=[120, 120.5, 123.9])
    amz = Stock(code='AMZ', open=223.1, updated=date_now_generator(), history=[234, 220.5, 199.9])
    portfolio = Portfolio(name=name, stocks=[msft, amz])
    return portfolio


def create_a_stock():
    return Stock(code='MSFT', open=123.7, updated=date_now_generator(), history=[120, 120.5, 123.9])


def create_a_portfolion_with_owner():
    portfolio = create_portfolio('Portfolio with owner')
    portfolio.owner = User(name='Owner User', password='some password')
    return portfolio


async def create_and_save_portfolio_with_owner():
    portfolio = create_a_portfolion_with_owner()
    await portfolio.save()
    return portfolio


class ExampleClass(Model):
    just_numbers: Annotated[str | None, Required(), Validators(Regexp('^[0-9]+$'))] = None
    future_field: Annotated[datetime | None, Validators(Future)] = None
    email: Annotated[str | None, Validators(Email)] = None
    distance: Annotated[int | None, Validators(Min(10), Max(15))] = None
    numbers: Annotated[list | None, Validators(Unique)] = None


class Priority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class Task(Model, AuditableRepository):
    id: Annotated[str | None, Required(), Generator(create_uuid_generator('U'))] = None
    name: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    description: Annotated[str | None, Required(), Validators(NotEmpty)] = None
    completed: Annotated[bool | None, Required(), Default(False)] = None
    created: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None
    closed_date: Annotated[datetime | None, Validators(Past)] = None
    priority: Annotated[Priority | None, Required(), Default(Priority.MEDIUM)] = None

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()


class Project(Model, AuditableRepository):
    name: Annotated[str | None, Required(), Validators(NotEmpty())] = None
    tasks: list[Task] | None = None
    created: Annotated[datetime | None, Required(), Generator(date_now_generator)] = None


def create_simple_project():
    p = Project(name='some_project_name').append_to(tasks=Task(name='some task'))
    return p


def create_rich_project():
    p = Project().update(name='some project'). \
        append_to(tasks=[Task(name='some_task', description='some description', priority=Priority.HIGH),
                         Task(name='some_other_task', description='some other description')])
    p.undefined_parameter = 'some undefined parameter'
    return p


def create_five_tasks(seed='A'):
    tasks = []
    for i in range(0, 5):
        tasks.append(
            Task(name=f'sequential tasks {seed}-{i}', description=f'some tasks description {i}',
                 priority=Priority.MEDIUM))
    return tasks


async def create_and_save_a_project(project_name='Default project name', tasks=None):
    p = Project(name=project_name).append_to(tasks=tasks)
    await p.save()
    return p


async def create_and_save_some_projects():
    projects = []
    for i in range(0, 50):
        p = await create_and_save_a_project(f'Project {i}', tasks=create_five_tasks(seed=f'{i}'))
        await p.save()
        projects.append(p)
    return projects


async def create_and_save_a_user(name, password, description=None):
    u = User().update(name=name).update(password=password). \
        append_to(roles=['Admin', 'User', 'Operator']).update(description=description)
    await u.save()
    return u


async def create_and_save_a_user_with_no_roles(name, password, description=None):
    u = User(name=name, password=password, description=description)
    await u.save()
    return u


async def create_and_save_some_users(urange=51):
    for i in range(1, urange):
        u = User().update(name=f'multi_user_{i}').update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(sequence=i)
        await u.save()
    assert await User.count() == urange - 1


def create_user_batch(urange=51):
    users = []
    for i in range(1, urange):
        users.append(User().update(name=f'multi_user_{i}').update(password='some default password').
                     append_to(roles=['Admin', 'User', 'Operator']).
                     update(description='some description').
                     update(sequence=i))
    return users


async def create_and_save_john_jane_and_max():
    john = await create_and_save_a_user('John', 'a password', 'John is a random guy')
    jane = await create_and_save_a_user('Jane', 'a password', 'Jane is a random girl')
    maxx = await create_and_save_a_user('Max', 'a password', 'Jane is a random girl')
    return john, jane, maxx


def run_async(coro):
    """Run an async coroutine synchronously. Use in sync test contexts (setup_function, sync test bodies)."""
    import asyncio
    return asyncio.run(coro)


def check_portfolio(portfolio):
    portfolio_dict = Model.to_dict(portfolio, convert_id=True)
    stocks = portfolio_dict.get('stocks')
    assert len(stocks) == 2
    msft_stock = list([stock for stock in stocks if stock.get('code') == 'MSFT'])[0]
    msft_stock_history = msft_stock.get('history')
    assert len(msft_stock_history)
    assert 120 in msft_stock_history
    assert 120.5 in msft_stock_history
    assert 123.9 in msft_stock_history
    assert msft_stock.get('open') == 123.7
    assert '_id' in portfolio_dict
    assert 'id' not in portfolio_dict
    assert '_id' in portfolio_dict.get('owner')
    assert 'id' not in portfolio_dict.get('owner')
