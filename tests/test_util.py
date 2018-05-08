from appkernel import Service
from appkernel.model import Model, Parameter, UniqueIndex
from datetime import datetime
from appkernel.repository import AuditableRepository, Repository, MongoRepository
from appkernel.service import link
from appkernel import NotEmpty, Regexp, Past, Future, create_uuid_generator, date_now_generator, create_password_hasher
from passlib.hash import pbkdf2_sha256
from enum import Enum


class User(Model, MongoRepository, Service):
    id = Parameter(str, required=True, generator=create_uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    password = Parameter(str, required=True, validators=[NotEmpty],
                         to_value_converter=create_password_hasher(rounds=10), omit=True)
    description = Parameter(str)
    roles = Parameter(list, sub_type=str)
    created = Parameter(datetime, required=True, validators=[Past], generator=date_now_generator)
    sequence = Parameter(int)

    @link(rel='change_password', http_method='POST')
    def change_p(self, current_password, new_password):
        if not pbkdf2_sha256.verify(current_password, self.password):
            raise ServiceException(403, 'Current password is not correct')
        else:
            self.password = new_password
            self.save()

    @link()
    def get_description(self):
        return self.description


class Stock(Model):
    code = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]'), Max(4)], index=UniqueIndex)
    open = Parameter(float, required=True, validators=[Min(0)])
    updated = Parameter(datetime, required=True, validators=[Past], generator=date_now_generator)
    history = Parameter(list, sub_type=long)
    sequence = Parameter(int, validators=[Min(1), Max(100)])


class Portfolio(Model, MongoRepository):
    id = Parameter(str, required=True, generator=create_uuid_generator('P'))
    name = Parameter(str, required=True, validators=[NotEmpty, Regexp('[A-Za-z0-9-_]')], index=UniqueIndex)
    stocks = Parameter(list, sub_type=Stock, validators=NotEmpty)
    owner = Parameter(User, required=False)


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
    just_numbers = Parameter(str, required=True, validators=[Regexp('^[0-9]+$')])
    future_field = Parameter(datetime, validators=[Future])


class Priority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class Task(Model, AuditableRepository):
    id = Parameter(str, required=True, generator=create_uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    description = Parameter(str, required=True, validators=[NotEmpty])
    completed = Parameter(bool, required=True, default_value=False)
    created = Parameter(datetime, required=True, generator=date_now_generator)
    closed_date = Parameter(datetime, validators=[Past])
    priority = Parameter(Priority, required=True, default_value=Priority.MEDIUM)

    def __init__(self, **kwargs):
        Model.init_model(self, **kwargs)

    def complete(self):
        self.completed = True
        self.closed_date = datetime.now()


class Project(Model, AuditableRepository):
    name = Parameter(str, required=True, validators=[NotEmpty()])
    tasks = Parameter(list, sub_type=Task)
    created = Parameter(datetime, required=True, generator=date_now_generator)

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
    for i in xrange(0, 5):
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
    for i in xrange(0, 50):
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


def create_and_save_some_users(range=51):
    for i in xrange(1, range):
        u = User().update(name='multi_user_{}'.format(i)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(sequence=i)
        u.save()
    assert User.count() == range - 1


def create_user_batch(range=51):
    users = []
    for i in xrange(1, range):
        users.append(User().update(name='multi_user_{}'.format(i)).update(password='some default password'). \
            append_to(roles=['Admin', 'User', 'Operator']).update(description='some description').update(
            sequence=i))
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
    msft_stock = list(filter(lambda stock: stock.get('code') == 'MSFT', stocks))[0]
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