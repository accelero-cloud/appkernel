import json

from pymongo.errors import WriteError
import time
from motor.motor_asyncio import AsyncIOMotorClient
from appkernel.configuration import config
from appkernel.model import CustomProperty
from .utils import *
import pytest
from datetime import timedelta, date


def setup_module(module):
    config.mongo_database = AsyncIOMotorClient(host='localhost')['appkernel']


def setup_function(function):
    print('\n\nSETUP ==> ')
    run_async(Project.delete_all())
    run_async(User.delete_all())
    run_async(StockInventory.delete_all())
    run_async(Application.delete_all())
    run_async(Reservation.delete_all())
    run_async(Portfolio.delete_all())


def teardown_function(function):
    print("\nTEAR DOWN <==")


@pytest.mark.anyio
async def test_empty_collection():
    await Project.delete_all()
    projects = await Project.find_by_query()
    assert len(projects) == 0


@pytest.mark.anyio
async def test_delete():
    p = Project().update(name='some project'). \
        append_to(tasks=Task(name='some_task', description='some description'))
    obj_id = await p.save()
    p2 = await Project.find_by_id(obj_id)
    assert p2 is not None
    await p2.delete()
    p3 = await Project.find_by_id(obj_id)
    assert p3 is None


@pytest.mark.anyio
async def test_basic_model():
    p = Project()
    p.name = 'somename'
    p.undefined_parameter = 'something else'
    p.tasks = [Task(name='some_task', description='some description')]
    print('\n\n==== saving user ====')
    obj_id = await p.save()
    print(f'Upserted ID: {obj_id}')

    print('\n\n==== reloading ====')
    p2 = await Project.find_by_id(obj_id)
    print(f'> dict of p2: {Model.to_dict(p2, convert_id=False)}')
    print(f'\n{p2.get_parameter_spec()}')
    print(f'> str reloaded object :: {p2}')
    assert p2.undefined_parameter == 'something else'
    assert p2.id is not None
    assert p2.name == 'somename'
    assert isinstance(p2.tasks, list), f'> p2.tasks is supposed to be a list instead of {type(p2.tasks)}'
    converted_id_model = Model.to_dict(p2, convert_id=True)
    print(f'> converted id model: {converted_id_model}')
    assert '_id' in converted_id_model
    assert 'id' not in converted_id_model
    non_converted_id_model = Model.to_dict(p2, convert_id=False)
    print(f'> NON converted id model: {non_converted_id_model}')
    assert 'id' in non_converted_id_model
    assert '_id' not in non_converted_id_model


@pytest.mark.anyio
async def test_complex_model():
    p = Project().update(name='some_name').update(undefined_parameter='something undefined'). \
        append_to(groups='some group name').append_to(groups='some other group name')
    obj_id = await p.save()
    u2 = await Project.find_by_id(obj_id)
    print(f'\n{u2.get_parameter_spec()}')
    print(f'reloaded user -> {u2}')
    print('\n\n')
    assert len(u2.groups) == 2


@pytest.mark.anyio
async def test_update():
    print('\n\n')
    u = Project().update(name='some_name').update(undefined_parameter='something undefined'). \
        append_to(tasks=[Task(name='task1', description='task one'), Task(name='task2', description='task two')])
    obj_id = await u.save()
    p2 = await Project.find_by_id(obj_id)
    print(f'after first load: {Model.to_dict(p2)}')
    p2.name = 'some_other_name'
    p2.append_to(tasks=Task(name='task3', description='task three'))
    obj_id = await p2.save()
    assertable_project = await Project.find_by_id(obj_id)
    print(f'after first load: {Model.to_dict(p2)}')
    assert assertable_project is not None
    assert assertable_project.name == 'some_other_name'
    assert len(assertable_project.tasks) == 3
    assert assertable_project.version == 2
    assert assertable_project.inserted < assertable_project.updated


@pytest.mark.anyio
async def test_find_all():
    project_count = 10
    for i in range(project_count):
        u = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        await u.save()
    assert await Project.count() == project_count
    counter = 0
    for u in await Project.find():
        print(u)
        counter += 1
    assert counter == project_count


@pytest.mark.anyio
async def test_find_all_by_query():
    for i in range(50):
        u = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        await u.save()
    assert await Project.count() == 50
    counter = 0
    for _, u in zip(list(range(10)), await Project.find_by_query()):
        print(f'Project name: {u.name}')
        counter += 1
    assert counter == 10


@pytest.mark.anyio
async def test_find_some_by_query():
    for i in range(50):
        p = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        p.counter = i
        await p.save()
    count = await Project.count()
    assert count == 50, '>> should be 50, but was %s' % count
    counter = 0
    for p in await Project.find_by_query({'counter': {'$gte': 0, '$lt': 10}}):
        print(f'Project name: {p.name} and counter: {p.counter}')
        counter += 1
    assert counter == 10, f"counter should be 10, was: {counter}"


@pytest.mark.anyio
async def test_unique_index_creation():
    await User.get_collection().drop()
    await User.init_indexes()
    user = await create_and_save_a_user('some user', 'some pass', 'some description')
    idx_info = await User.get_collection().index_information()
    print(f'\n{idx_info}')
    assert 'name_idx' in idx_info
    assert 'sequence_idx' in idx_info
    assert 'description_idx' in idx_info
    assert idx_info.get('name_idx').get('key')[0][0] == 'name'


@pytest.mark.anyio
async def test_schema_validation_success():
    print(f'\n{json.dumps(Project.get_json_schema(mongo_compatibility=True))}\n')
    await Project.add_schema_validation(validation_action='error')
    project = create_rich_project()
    project.append_to(tasks=[Task(name='some_task', description='some description', closed_date=None)])
    print(Model.dumps(project, pretty_print=True))
    await project.save()


@pytest.mark.anyio
async def test_schema_validation_rejected():
    await Project.add_schema_validation(validation_action='error')
    with pytest.raises(WriteError):
        project = create_rich_project()
        project.tasks[0].priority = 'TRICKY'
        await project.save()


@pytest.mark.anyio
async def test_basic_query():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.name == 'John')
    print(f'\n>fetched: {len(results)}')
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'


@pytest.mark.anyio
async def test_find_with_custom_property():
    projects = await create_and_save_some_projects()
    project = await Project.find_one(Project.custom_property('version') == 2)
    assert project is not None
    print(f'Found Project {project.dumps(pretty_print=True)}')
    none_project = await Project.find_one(CustomProperty(Project, 'version') == 0)
    assert none_project is None


@pytest.mark.anyio
async def test_basic_negative_query():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.name == 'Milord')
    for user in results:
        print(user)
    assert len(results) == 0


@pytest.mark.anyio
async def test_multiple_or_requests():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find((User.name == 'John') | (User.name == 'Jane'))
    print(f'\n>fetched: {len(results)}')
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 2
    assert isinstance(results[0], User)
    for result in results:
        assert result.name in ['John', 'Jane']


@pytest.mark.anyio
async def test_multiple_and_requests():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find((User.name == 'John') & (User.description == 'John is a random guy'))
    print(f'\n>fetched: {len(results)}')
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'


@pytest.mark.anyio
async def test_negative_multiple_and_requests():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find((User.name == 'John') & (User.description == 'Jane is a random girl'))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_contains():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.description % 'John')
    print(f'\n>fetched: {len(results)}')
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'


@pytest.mark.anyio
async def test_contains_array():
    john, jane, max = await create_and_save_john_jane_and_max()
    no_role_user = await create_and_save_a_user_with_no_roles('no role', 'some pass')
    results = await User.find(User.roles % ['Admin', 'Operator'])
    print(f'\n>fetched: {len(results)}')
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.name in ['John', 'Jane', 'Max']


@pytest.mark.anyio
async def test_empty_array():
    john, jane, max = await create_and_save_john_jane_and_max()
    no_role_user = await create_and_save_a_user_with_no_roles('no role', 'some pass')
    results = await User.find(User.roles == None)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 1


@pytest.mark.anyio
async def test_not_equal():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.name != 'Max')
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 2
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.name in ['John', 'Jane']


@pytest.mark.anyio
async def test_is_none():
    john, jane, max = await create_and_save_john_jane_and_max()
    no_desc_user = await create_and_save_a_user('Erika', 'a password')
    results = await User.find(User.description == None)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 1
    assert results[0].name == 'Erika'
    for user in results:
        print(user.dumps(pretty_print=True))


@pytest.mark.anyio
async def test_is_not_none():
    john, jane, max = await create_and_save_john_jane_and_max()
    no_desc_user = await create_and_save_a_user('Erika', 'a password')
    results = await User.find(User.description != None)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 3


@pytest.mark.anyio
async def test_smaller_than_date():
    john, jane, max = await create_and_save_john_jane_and_max()
    time.sleep(1)
    results = await User.find(User.created < datetime.now())
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 3


@pytest.mark.anyio
async def test_smaller_than_date_negative():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.created < (datetime.now() - timedelta(days=1)))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_bigger_than_date():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.created > (datetime.now() - timedelta(days=1)))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 3


@pytest.mark.anyio
async def test_bigger_than_date_negative():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(User.created > datetime.now())
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_between_date():
    john, jane, max = await create_and_save_john_jane_and_max()
    yesterday = (datetime.now() - timedelta(days=1))
    tomorrow = (datetime.now() + timedelta(days=1))
    results = await User.find((User.created > yesterday) & (User.created < tomorrow))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 3


@pytest.mark.anyio
async def test_between_date_negative():
    john, jane, max = await create_and_save_john_jane_and_max()
    results = await User.find(
        (User.created > (datetime.now() - timedelta(days=2))) & (User.created < (datetime.now() - timedelta(days=1))))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_smaller_than_int():
    await create_and_save_some_users()
    results = await User.find(User.sequence < 25)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 24


@pytest.mark.anyio
async def test_smaller_or_equal_than_int():
    await create_and_save_some_users()
    results = await User.find(User.sequence <= 25)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 25


@pytest.mark.anyio
async def test_smaller_than_int_negative():
    await create_and_save_some_users()
    results = await User.find(User.sequence < 1)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_bigger_than_int():
    await create_and_save_some_users()
    results = await User.find(User.sequence > 25)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 25


@pytest.mark.anyio
async def test_bigger_or_equal_than_int():
    await create_and_save_some_users()
    results = await User.find(User.sequence >= 25)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 26


@pytest.mark.anyio
async def test_bigger_than_int_negative():
    await create_and_save_some_users()
    results = await User.find(User.sequence > 50)
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_between_int():
    await create_and_save_some_users()
    results = await User.find((User.sequence > 25) & (User.sequence < 27))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 1


@pytest.mark.anyio
async def test_between_int_negative():
    await create_and_save_some_users()
    results = await User.find((User.sequence > 25) & (User.sequence < 26))
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 0


@pytest.mark.anyio
async def test_sort_by():
    await create_and_save_some_users()
    results = await User.where((User.sequence > 0) & (User.sequence <= 5)).sort_by(User.sequence.desc()).find()
    print(f'\n>fetched: {len(results)}')
    assert len(results) == 5
    this_seq = 6
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.sequence < this_seq
        this_seq = user.sequence


@pytest.mark.anyio
async def test_pagination():
    await create_and_save_some_users()
    this_seq = 1
    for page in range(0, 5):
        results = await User.where(User.sequence < 51).sort_by(User.sequence.asc()).find(page, 10)
        print(f'\n>fetched: {len(results)}')
        assert len(results) == 10
        for user in results:
            print(user.dumps(pretty_print=True))
            assert user.sequence == this_seq
            this_seq += 1


@pytest.mark.anyio
async def test_count():
    await create_and_save_some_users()
    assert await User.where(User.sequence < 51).count() == 50


@pytest.mark.anyio
async def test_delete_many():
    await create_and_save_some_users()
    assert await User.count() == 50
    deleted = await User.where((User.sequence > 0) & (User.sequence <= 5)).delete()
    print(f'\n\n deleted count: {deleted}')
    assert await User.count() == 45


@pytest.mark.anyio
async def test_find_one():
    john, jane, max = await create_and_save_john_jane_and_max()
    result = await User.find_one(User.name == 'John')
    assert result.name == 'John'


@pytest.mark.anyio
async def test_find_one_negative():
    john, jane, max = await create_and_save_john_jane_and_max()
    result = await User.find_one(User.name == 'Kylie')
    assert result is None


@pytest.mark.anyio
async def test_bulk_insert():
    ids = await User.bulk_insert(create_user_batch())
    print(ids)
    assert await User.count() == 50


@pytest.mark.anyio
async def test_nested_queries():
    await create_and_save_portfolio_with_owner()
    portfolio = await Portfolio.where(Portfolio.owner.name == 'Owner User').find_one()
    assert isinstance(portfolio.stocks[0], Stock)
    assert isinstance(portfolio.owner, User)
    assert portfolio.name == 'Portfolio with owner'
    print(portfolio.dumps(pretty_print=True))
    check_portfolio(portfolio)


@pytest.mark.anyio
async def test_nested_query_negative():
    await create_and_save_portfolio_with_owner()
    portfolio = await Portfolio.where(Portfolio.owner.name == 'Some other user').find_one()
    assert portfolio is None


@pytest.mark.anyio
async def test_query_in_array_simple():
    await create_and_save_some_projects()
    project = await Project.where(Project.tasks.name == 'sequential tasks 6-1').find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


@pytest.mark.anyio
async def test_query_in_array_simple_negative():
    await create_and_save_some_projects()
    project = await Project.where(Project.tasks.name == 'some text').find_one()
    assert project is None


@pytest.mark.anyio
async def test_query_in_empty_array():
    project = await Project.where(Project.tasks.name == 'sequential tasks 6-1').find_one()
    assert project is None


@pytest.mark.anyio
async def test_query_in_array_does_not_contain():
    await create_and_save_some_projects()
    results = await Project.where(Project.tasks.name != 'sequential tasks 6-1').find()
    proj_counter = 0
    for project in results:
        print(f'======={project.name}=======')
        print(project.dumps(pretty_print=True))
        assert project.name != 'Project 6'
        proj_counter += 1
    assert proj_counter == 49


@pytest.mark.anyio
async def test_query_in_array():
    await create_and_save_some_projects()
    project = await Project.where(Project.tasks[Task.name == 'sequential tasks 6-1']).find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


@pytest.mark.anyio
async def test_negative_query_in_an_array():
    await create_and_save_some_projects()
    results = await Project.where(Project.tasks[Task.name != 'sequential tasks 6-1']).find()
    proj_counter = 0
    for project in results:
        print(f'======={project.name}=======')
        print(project.dumps(pretty_print=True))
        assert project.name != 'Project 6'
        proj_counter += 1
    assert proj_counter == 49


@pytest.mark.anyio
async def test_query_simple_array_in_simple_way():
    await create_and_save_some_users()
    special_user = User(name='Special User', password='some pass', roles=['Special', 'SuperAdmin'])
    await special_user.save()
    user = await User.where(User.roles % 'Special').find_one()
    assert user.name == 'Special User'


@pytest.mark.anyio
async def test_query_simple_array_in_simple_way_negative():
    await create_and_save_some_users()
    special_user = User(name='Special User', password='some pass', roles=['Special', 'SuperAdmin'])
    await special_user.save()
    user = await User.where(User.roles % 'NonExisting').find_one()
    assert user is None


@pytest.mark.anyio
async def test_query_simple_array_contains():
    await create_and_save_some_projects()
    project = await Project.where(Project.tasks.name % 'sequential tasks 6-1').find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


@pytest.mark.anyio
async def test_mongo_persistence_with_date():
    await Application.delete_all()
    application = Application(application_date=date.today())
    await application.save()


async def __init_stock_inventory():
    for code, prod_tuple in {'BTX': ('Black T-Shirt', 12.30), 'TRS': ('Trousers', 20.00), 'SHRT': ('Shirt', 72.30),
                             'NBS': ('Nice Black Shoe', 90.50)}.items():
        for size in ProductSize:
            stock = StockInventory(available=100,
                                   product=Product(code=code, name=prod_tuple[0], size=size,
                                                   price=Money(prod_tuple[1], 'EUR')))
            await stock.save()


@pytest.mark.anyio
async def test_multiple_queries():
    await __init_stock_inventory()
    for _ in range(10):
        result_count = await StockInventory.where(
            (StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.L)).count()
        assert result_count == 1

    for _ in range(10):
        result_count = await StockInventory.where(
            StockInventory.product.code == 'TRS').count()
        assert result_count == 4


@pytest.mark.anyio
async def test_atomic_updates():
    await __init_stock_inventory()
    query = StockInventory.where(
        (StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.M))
    for _ in range(10):
        await query.update_many(available=StockInventory.available - 1, reserved=StockInventory.reserved + 1)
    stock = await StockInventory.where(
        (StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.M)).find_one()
    assert stock.reserved == 10
    assert stock.available == 90


@pytest.mark.anyio
async def test_multiple_query_params():
    await __init_stock_inventory()
    query = StockInventory.where(
        (StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.M) & (StockInventory.available > 1))
    await query.update_many(available=StockInventory.available - 10, reserved=StockInventory.reserved + 10)

    stock = await StockInventory.where(
        (StockInventory.product.code == 'TRS') & (StockInventory.product.size == ProductSize.M)).find_one()
    assert stock.reserved == 10
    assert stock.available == 90


@pytest.mark.skip(reason='not implemented yet')
def test_multiple_query_param_with_grouping_logic():
    pass
