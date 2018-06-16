from datetime import datetime

from pymongo import MongoClient

from appkernel.configuration import config
from tests.test_util import User, create_and_save_a_user, Task


def setup_module(module):
    config.mongo_database=MongoClient(host='localhost')['appkernel']


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')
    User.delete_all()
    Task.delete_all()


def test_generator():
    task = Task()
    task.name = 'some task name'
    task.description = 'some task description'
    task.finalise_and_validate()
    print('\nTask:\n {}'.format(task))
    assert task.id is not None and task.id.startswith('U')


def test_converter():
    user = create_and_save_a_user('test user', 'test password', 'test description')
    print '\n{}'.format(user.dumps(pretty_print=True))
    assert user.password.startswith('$pbkdf2-sha256')
    hash1 = user.password
    user.save()
    assert user.password.startswith('$pbkdf2-sha256')
    assert hash1 == user.password


def test_unix_time_marshaller():
    user = create_and_save_a_user('test user', 'test password', 'test description')
    user.last_login = datetime.now()
    user.finalise_and_validate()
    print('\n\n')
    user_json = user.dumps(pretty_print=True)
    print(user_json)
    assert isinstance(User.to_dict(user).get('last_login'), float)
    reloaded_user = User.loads(user_json)
    print(str(reloaded_user))
    assert isinstance(reloaded_user.last_login, datetime)
