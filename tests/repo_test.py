import json

from pymongo.errors import WriteError

from test_util import *
from appkernel.configuration import config
from pymongo import MongoClient
import pytest
from datetime import timedelta


def setup_module(module):
    config.mongo_database=MongoClient(host='localhost')['appkernel']


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')
    Project.delete_all()
    User.delete_all()


def teardown_function(function):
    """ teardown any state that was previously setup with a setup_method
    call.
    """
    print("\nTEAR DOWN <==")


def test_empty_collection():
    Project.delete_all()
    projects = Project.find_by_query()
    assert len(projects) == 0


def test_delete():
    p = Project().update(name='some project'). \
        append_to(tasks=Task(name='some_task', description='some description'))
    obj_id = p.save()
    p2 = Project.find_by_id(obj_id)
    assert p2 is not None
    p2.delete()
    p3 = Project.find_by_id(obj_id)
    assert p3 is None


def test_basic_model():
    p = Project()
    p.name = 'somename'
    p.undefined_parameter = 'something else'
    p.tasks = [Task(name='some_task', description='some description')]
    print '\n\n==== saving user ===='
    obj_id = p.save()
    print 'Upserted ID: {}'.format(obj_id)

    print '\n\n==== reloading ===='
    p2 = Project.find_by_id(obj_id)
    print('> dict of p2: {}'.format(Model.to_dict(p2, convert_id=False)))
    print('\n{}'.format(p2.get_parameter_spec()))
    print('> str reloaded object :: {}'.format(p2))
    assert p2.undefined_parameter == 'something else'
    assert p2.id is not None
    assert p2.name == 'somename'
    assert isinstance(p2.tasks, list), '> p2.tasks is supposed to be a list instead of {}'.format(type(p2.tasks))
    converted_id_model = Model.to_dict(p2, convert_id=True)
    print('> converted id model: {}'.format(converted_id_model))
    assert '_id' in converted_id_model
    assert 'id' not in converted_id_model
    non_converted_id_model = Model.to_dict(p2, convert_id=False)
    print('> NON converted id model: {}'.format(non_converted_id_model))
    assert 'id' in non_converted_id_model
    assert '_id' not in non_converted_id_model


def test_complex_model():
    p = Project().update(name='some_name').update(undefined_parameter='something undefined'). \
        append_to(groups='some group name').append_to(groups='some other group name')
    obj_id = p.save()
    u2 = Project.find_by_id(obj_id)
    print '\n{}'.format(u2.get_parameter_spec())
    print 'reloaded user -> {}'.format(u2)
    print '\n\n'
    assert len(u2.groups) == 2


def test_update():
    print '\n\n'
    u = Project().update(name='some_name').update(undefined_parameter='something undefined'). \
        append_to(tasks=[Task(name='task1', description='task one'), Task(name='task2', description='task two')])
    obj_id = u.save()
    p2 = Project.find_by_id(obj_id)
    print('after first load: {}'.format(Model.to_dict(p2)))
    p2.name = 'some_other_name'
    p2.append_to(tasks=Task(name='task3', description='task three'))
    obj_id = p2.save()
    assertable_project = Project.find_by_id(obj_id)
    print('after first load: {}'.format(Model.to_dict(p2)))
    assert assertable_project is not None
    assert assertable_project.name == 'some_other_name'
    assert len(assertable_project.tasks) == 3
    assert assertable_project.version == 2
    assert assertable_project.inserted < assertable_project.updated

# todo: update previously deleted object


def test_find_all():
    project_count=10
    for i in xrange(project_count):
        u = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        u.save()
    assert Project.count() == project_count
    counter = 0
    for u in Project.find():
        print(u)
        counter += 1
    assert counter == project_count


def test_find_all_by_query():
    for i in xrange(50):
        u = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        u.save()
    assert Project.count() == 50
    counter = 0
    for _, u in zip(range(10), Project.find_by_query()):
        print 'User name: {}'.format(u.name)
        counter += 1
    assert counter == 10


def test_find_some_by_query():
    for i in xrange(50):
        p = Project().update(name='multi_user_%s' % i).update(undefined_parameter='something undefined'). \
            append_to(groups='some group name').append_to(groups='some other group name')
        p.counter = i
        p.save()
    assert Project.count() == 50, '>> should be 50, but was %s' % Project.count()
    counter = 0
    for p in Project.find_by_query({'counter': {'$gte': 0, '$lt': 10}}):
        print 'User name: {} and counter: {}'.format(p.name, p.counter)
        counter += 1
    assert counter == 10, "counter should be 10, was: {}".format(counter)


def test_unique_index_creation():
    User.get_collection().drop()
    User.init_indexes()
    user = create_and_save_a_user('some user', 'some pass', 'some description')
    idx_info = User.get_collection().index_information()
    #idx_info = config.mongo_database['Users'].index_information()
    print('\n{}'.format(idx_info))
    assert 'name_idx' in idx_info
    assert 'sequence_idx' in idx_info
    assert 'description_idx' in idx_info
    assert idx_info.get('name_idx').get('key')[0][0] == 'name'


def test_schema_validation_success():
    print('\n{}\n'.format(json.dumps(Project.get_json_schema(mongo_compatibility=True)), indent=2, sort_keys=True))
    Project.add_schema_validation(validation_action='error')
    project = create_rich_project()
    print Model.dumps(project, pretty_print=True)
    project.save()

# todo: user schema validation
# OperationFailure: $jsonSchema keyword 'format' is not currently supported


def test_schema_validation_rejected():
    Project.add_schema_validation(validation_action='error')
    with pytest.raises(WriteError):
        project = create_rich_project()
        project.tasks[0].priority = 'TRICKY'
        project.save()


def test_basic_query():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.name == 'John')
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'

# todo: test non existing property
# Project.find_one(Project.version == '2')


def test_basic_negative_query():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.name == 'Milord')
    results = [user for user in user_iterator]
    for user in results:
        print(user)
    assert len(results) == 0


def test_multiple_or_requests():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find((User.name == 'John') | (User.name == 'Jane'))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    for user in results:
        print(user.dumps(pretty_print=True))

    assert len(results) == 2
    assert isinstance(results[0], User)
    for result in results:
        assert result.name in ['John', 'Jane']


def test_multiple_and_requests():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find((User.name == 'John') & (User.description == 'John is a random guy'))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'


def test_negative_multiple_and_requests():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find((User.name == 'John') & (User.description == 'Jane is a random girl'))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_contains():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.description % 'John')
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    for user in results:
        print(user.dumps(pretty_print=True))
    assert len(results) == 1
    assert isinstance(results[0], User)
    assert results[0].name == 'John'


def test_contains_array():
    john, jane, max = create_and_save_john_jane_and_max()
    no_role_user = create_and_save_a_user_with_no_roles('no role', 'some pass')
    user_iterator = User.find(User.roles % ['Admin', 'Operator'])
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.name in ['John', 'Jane', 'Max']


def test_empty_array():
    john, jane, max = create_and_save_john_jane_and_max()
    no_role_user = create_and_save_a_user_with_no_roles('no role', 'some pass')
    user_iterator = User.find(User.roles == None)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 1


# todo: test starts with ends with


def test_not_equal():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.name != 'Max')
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 2
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.name in ['John', 'Jane']


def test_is_none():
    john, jane, max = create_and_save_john_jane_and_max()
    no_desc_user = create_and_save_a_user('Erika', 'a password')
    user_iterator = User.find(User.description == None)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 1
    assert results[0].name == 'Erika'
    for user in results:
        print(user.dumps(pretty_print=True))


def test_is_not_none():
    john, jane, max = create_and_save_john_jane_and_max()
    no_desc_user = create_and_save_a_user('Erika', 'a password')
    user_iterator = User.find(User.description != None)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 3


def test_smaller_than_date():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.created < datetime.now())
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 3


def test_smaller_than_date_negative():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.created < (datetime.now() - timedelta(days=1)))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_bigger_than_date():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.created > (datetime.now() - timedelta(days=1)))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 3


def test_bigger_than_date_negative():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(User.created > datetime.now())
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_between_date():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(
        (User.created > (datetime.now() - timedelta(days=1))) & (User.created < (datetime.now() + timedelta(days=1))))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 3


# todo: test this | Project.find_one((Project.created > date(2018, 6, 10)) & (Project.created < date(2018,6,12)))

def test_between_date_negative():
    john, jane, max = create_and_save_john_jane_and_max()
    user_iterator = User.find(
        (User.created > (datetime.now() - timedelta(days=2))) & (User.created < (datetime.now() - timedelta(days=1))))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_smaller_than_int():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence < 25)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 24


def test_smaller_or_equal_than_int():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence <= 25)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 25


def test_smaller_than_int_negative():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence < 1)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_bigger_than_int():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence > 25)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 25


def test_bigger_or_equal_than_int():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence >= 25)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 26


def test_bigger_than_int_negative():
    create_and_save_some_users()
    user_iterator = User.find(User.sequence > 50)
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_between_int():
    create_and_save_some_users()
    user_iterator = User.find((User.sequence > 25) & (User.sequence < 27))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 1


def test_between_int_negative():
    create_and_save_some_users()
    user_iterator = User.find((User.sequence > 25) & (User.sequence < 26))
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 0


def test_sort_by():
    create_and_save_some_users()
    user_iterator = User.where((User.sequence > 0) & (User.sequence <= 5)).sort_by(User.sequence.desc()).find()
    results = [user for user in user_iterator]
    print '\n>fetched: {}'.format(len(results))
    assert len(results) == 5
    this_seq = 6
    for user in results:
        print(user.dumps(pretty_print=True))
        assert user.sequence < this_seq
        this_seq = user.sequence


def test_pagination():
    create_and_save_some_users()
    this_seq = 1
    for page in range(0, 5):
        user_iterator = User.where(User.sequence < 51).sort_by(User.sequence.asc()).find(page, 10)
        results = [user for user in user_iterator]
        print '\n>fetched: {}'.format(len(results))
        assert len(results) == 10
        for user in results:
            print(user.dumps(pretty_print=True))
            assert user.sequence == this_seq
            this_seq += 1


def test_count():
    create_and_save_some_users()
    assert User.where(User.sequence < 51).count() == 50


def test_delete_many():
    create_and_save_some_users()
    assert User.count() == 50
    print('\n\n deleted count: {}'.format(User.where((User.sequence > 0) & (User.sequence <= 5)).delete()))
    assert User.count() == 45


# def test_empty_collection():
#     create_and_save_some_users()
#     user_iterator = User.find(User.roles.empty())
#     results = [user for user in user_iterator]
#     print '\n>fetched: {}'.format(len(results))


def test_find_one():
    john, jane, max = create_and_save_john_jane_and_max()
    assert User.find_one(User.name == 'John').name == 'John'


def test_find_one_negative():
    john, jane, max = create_and_save_john_jane_and_max()
    assert User.find_one(User.name == 'Kylie') is None


def test_bulk_insert():
    ids = User.bulk_insert(create_user_batch())
    print ids
    assert User.count() == 50


def test_nested_queries():
    create_and_save_portfolio_with_owner()
    portfolio = Portfolio.where(Portfolio.owner.name == 'Owner User').find_one()
    assert isinstance(portfolio.stocks[0], Stock)
    assert isinstance(portfolio.owner, User)
    assert portfolio.name == 'Portfolio with owner'
    print(portfolio.dumps(pretty_print=True))
    check_portfolio(portfolio)


def test_nested_query_negative():
    create_and_save_portfolio_with_owner()
    portfolio = Portfolio.where(Portfolio.owner.name == 'Some other user').find_one()
    assert portfolio is None


def test_query_in_array_simple():
    create_and_save_some_projects()
    project = Project.where(Project.tasks.name == 'sequential tasks 6-1').find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


def test_query_in_array_simple_negative():
    create_and_save_some_projects()
    project = Project.where(Project.tasks.name == 'some text').find_one()
    assert project is None


def test_query_in_empty_array():
    project = Project.where(Project.tasks.name == 'sequential tasks 6-1').find_one()
    assert project is None


def test_query_in_array_does_not_contain():
    create_and_save_some_projects()
    project_generator = Project.where(Project.tasks.name != 'sequential tasks 6-1').find()
    proj_counter = 0
    for project in project_generator:
        print('======={}======='.format(project.name))
        print(project.dumps(pretty_print=True))
        assert project.name != 'Project 6'
        proj_counter += 1
    assert proj_counter == 49


# def test_query_in_array_lte():
#     assert True is False
#
#
# def test_query_in_array_gte():
#     assert True is False


def test_query_in_array():
    create_and_save_some_projects()
    project = Project.where(Project.tasks[Task.name == 'sequential tasks 6-1']).find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


def test_negative_query_in_an_array():
    create_and_save_some_projects()
    project_generator = Project.where(Project.tasks[Task.name != 'sequential tasks 6-1']).find()
    proj_counter = 0
    for project in project_generator:
        print('======={}======='.format(project.name))
        print(project.dumps(pretty_print=True))
        assert project.name != 'Project 6'
        proj_counter += 1
    assert proj_counter == 49


def test_query_simple_array_in_simple_way():
    # when the array contains a string
    create_and_save_some_users()
    special_user = User(name='Special User', password='some pass', roles=['Special', 'SuperAdmin'])
    special_user.save()
    user = User.where(User.roles % 'Special').find_one()
    assert user.name == 'Special User'


def test_query_simple_array_in_simple_way_negative():
    # when the array contains a string
    create_and_save_some_users()
    special_user = User(name='Special User', password='some pass', roles=['Special', 'SuperAdmin'])
    special_user.save()
    user = User.where(User.roles % 'NonExisting').find_one()
    assert user is None


def test_query_simple_array_contains():
    create_and_save_some_projects()
    project = Project.where(Project.tasks.name % 'sequential tasks 6-1').find_one()
    print(project.dumps(pretty_print=True))
    assert project.name == 'Project 6'
    assert len(project.tasks) == 5


# def test_array_size():
#     create_and_save_some_projects()
#     projects = Project.where(Project.tasks.length() >= 5).get()
#     assert len(projects) == 50
#
#
# def test_array_size_negative():
#     create_and_save_some_projects()
#     projects = Project.where(Project.tasks.length() > 5).get()
#     assert len(projects) == 0

# todo: test multiple sort criteria
# todo: find distinct
#     # u2 = User.find(User.name == 'some_unique_name', u2.undefined_parameter == 'something else')  # {name:'some_unique_name'}#
#     # { $ and: [{price: { $ne: 1.99}}, {price: { $exists: true}}]}
#     # { price: { $ne: 1.99, $exists: true } }
#
# todo: test missing fields / test fields which do exist
# todo: test relationships.