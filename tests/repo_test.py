from test_util import *
from appkernel import *
from pymongo import MongoClient


def setup_module(module):
    AppKernelEngine.database = MongoClient(host='localhost')['appkernel']


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
    print '> dict of p2: {}'.format(Model.to_dict(p2, convert_id=False))
    p2.describe()
    print '> str reloaded object :: %s' % p2
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
    u2.describe
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


def test_find_all():
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


def test_find_some():
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
    user = create_and_save_a_user('some user', 'some pass', 'some description')
    idx_info = AppKernelEngine.database['Users'].index_information()
    assert 'name_idx' in idx_info

def test_find_one():
    pass

# def test_basic_query():
#     print_banner('>>', 'basic query')
#     User.delete_all()
#     obj_id = User().update(name='some_unique_name').update(undefined_parameter='something undefined'). \
#         append_to(groups='some group name').append_to(groups='some other group name').save()
#     assert obj_id is not None, 'at this stahe an object must be available in the database'
#     print '-> saved object id: {}'.format(obj_id)
#
#     # select queries
#     # user_iterator = User.select().where(User.name == 'some_unique_name').execute()
#     # user_iterator = User.select().where(User.name == 'some_unique_name').sort_by(User.created).execute()
#     # user_iterator = User.select().where(User.name == 'some_unique_name').sort_by(User.created).execute(limit=5)
#     # user_count = User.select().where(User.name == 'some_unique_name').count()
#     # user_count = User.select().where((User.name == 'some_unique_name') | (User.name == 'some_other_name'))
#     # today = date.today()
#     #Project.update('ssss'=True).where(Task.creation_date < today).execute()
#
#     # u2 = User.find(User.name == 'some_unique_name') # {name:'some_unique_name'}
#     # u2 = User.find(User.name == 'some_unique_name', u2.undefined_parameter == 'something else')  # {name:'some_unique_name'}
#     # u2 = User.find(User.name.contains('some'))
#
#     # { $ and: [{price: { $ne: 1.99}}, {price: { $exists: true}}]}
#     # { price: { $ne: 1.99, $exists: true } }
#     print_banner('<<', 'basic query', '\n')
#


# todo:
# better json serialisation (eg object id)
# escape parameters
# create index
# sort query result
# db validation and unique index
