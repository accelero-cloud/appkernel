from money import Money

from appkernel import Service, IdentityMixin, Role, CurrentSubject, Anonymous, TextIndex, Index
from appkernel import Model, Property, UniqueIndex
from appkernel import ServiceException
from datetime import datetime, date
from appkernel import AuditableRepository, Repository, MongoRepository
from appkernel.generators import TimestampMarshaller, MongoDateTimeMarshaller
from appkernel.service import link
from appkernel import NotEmpty, Regexp, Past, Future, create_uuid_generator, date_now_generator, content_hasher
from passlib.hash import pbkdf2_sha256
from enum import Enum
from flask_babel import _, lazy_gettext as _l
from appkernel.validators import Max, Min, Email


class User(Model, MongoRepository, Service, IdentityMixin):
    id = Property(str, required=True, generator=create_uuid_generator('U'))
    name = Property(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    password = Property(str, required=True, validators=[NotEmpty],
                        converter=content_hasher(rounds=10), omit=True)
    description = Property(str, index=TextIndex)
    roles = Property(list, sub_type=str)
    created = Property(datetime, required=True, validators=[Past], generator=date_now_generator)
    last_login = Property(datetime, marshaller=TimestampMarshaller)
    sequence = Property(int, index=Index)

    @link(rel='change_password', http_method='POST', require=[CurrentSubject(), Role('admin')])
    def change_p(self, current_password, new_password):
        if not pbkdf2_sha256.verify(current_password, self.password):
            raise ServiceException(403, _('Current password is not correct'))
        else:
            self.password = new_password
            self.save()
        return _('Password changed')

    @link(require=Anonymous())
    def get_description(self):
        return self.description


class Group(Model, MongoRepository):
    id = Property(str, required=True, generator=create_uuid_generator('U'))
    name = Property(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    users = Property(list, sub_type=User)


class Stock(Model):
    code = Property(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]'), Max(4)], index=UniqueIndex)
    open = Property(float, required=True, validators=[Min(0)])
    updated = Property(datetime, required=True, validators=[Past], generator=date_now_generator)
    history = Property(list, sub_type=int)
    sequence = Property(int, validators=[Min(1), Max(100)])


class Portfolio(Model, MongoRepository):
    id = Property(str, required=True, generator=create_uuid_generator('P'))
    name = Property(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    stocks = Property(list, sub_type=Stock, validators=NotEmpty)
    owner = Property(User, required=False)


class Application(Model, MongoRepository):
    id = Property(str, required=True, generator=create_uuid_generator())
    application_date = Property(date, required=True, marshaller=MongoDateTimeMarshaller)


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


class Product(Model, MongoRepository):
    code = Property(str, required=True, validators=[NotEmpty])
    name = Property(str, required=True)
    description = Property(str)
    size = Property(ProductSize, required=True)
    price = Property(Money, required=True)


class StockInventory(Model, MongoRepository):
    id = Property(str, generator=create_uuid_generator('S'))
    product = Property(Product, required=True)
    available = Property(int, required=True, default_value=0)
    reserved = Property(int, required=True, default_value=0)


class Reservation(Model, MongoRepository, Service):
    id = Property(str, generator=create_uuid_generator('R'))
    order_id = Property(str, required=True)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    products = Property(list, sub_type=Product, required=True, validators=NotEmpty())
    state = Property(ReservationState, required=True, default_value=ReservationState.RESERVED)


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


def create_and_save_portfolio_with_owner():
    portfolio = create_a_portfolion_with_owner()
    portfolio.save()
    return portfolio


class ExampleClass(Model):
    just_numbers = Property(str, required=True, validators=[Regexp('^[0-9]+$')])
    future_field = Property(datetime, validators=[Future])


class Priority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class Task(Model, AuditableRepository):
    id = Property(str, required=True, generator=create_uuid_generator('U'))
    name = Property(str, required=True, validators=[NotEmpty])
    description = Property(str, required=True, validators=[NotEmpty])
    completed = Property(bool, required=True, default_value=False)
    created = Property(datetime, required=True, generator=date_now_generator)
    closed_date = Property(datetime, validators=[Past])
    priority = Property(Priority, required=True, default_value=Priority.MEDIUM)

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()


class Project(Model, AuditableRepository, Service):
    name = Property(str, required=True, validators=[NotEmpty()])
    tasks = Property(list, sub_type=Task)
    created = Property(datetime, required=True, generator=date_now_generator)

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)


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
            Task(name='sequential tasks {}-{}'.format(seed, i), description='some tasks description {}'.format(i),
                 priority=Priority.MEDIUM))
    return tasks


def create_and_save_a_project(project_name='Default project name', tasks=None):
    p = Project(name=project_name).append_to(tasks=tasks)
    p.save()
    return p


def create_and_save_some_projects():
    projects = []
    for i in range(0, 50):
        p = create_and_save_a_project('Project {}'.format(i), tasks=create_five_tasks(seed='{}'.format(i)))
        p.save()
        projects.append(p)
    return projects


def create_and_save_a_user(name, password, description=None):
    u = User().update(name=name).update(password=password). \
        append_to(roles=['Admin', 'User', 'Operator']).update(description=description)
    u.save()
    return u


def create_and_save_a_user_with_no_roles(name, password, description=None):
    u = User(name=name, password=password, description=description)
    u.save()
    return u


def create_and_save_some_users(urange=51):
    for i in range(1, urange):
        u = User().update(name='multi_user_{}'.format(i)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(sequence=i)
        u.save()
    assert User.count() == urange - 1


def create_user_batch(urange=51):
    users = []
    for i in range(1, urange):
        users.append(User().update(name='multi_user_{}'.format(i)).update(password='some default password').
            append_to(roles=['Admin', 'User', 'Operator']).
            update(description='some description').
            update(sequence=i))
    return users


def create_and_save_john_jane_and_max():
    # type: () -> (User, User, User)
    john = create_and_save_a_user('John', 'a password', 'John is a random guy')
    jane = create_and_save_a_user('Jane', 'a password', 'Jane is a random girl')
    maxx = create_and_save_a_user('Max', 'a password', 'Jane is a random girl')
    return john, jane, maxx


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
