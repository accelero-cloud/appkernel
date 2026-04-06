from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from appkernel.configuration import config
from tests.utils import User, create_and_save_a_user, Task, run_async


def setup_module(module):
    config.mongo_database = AsyncIOMotorClient(host='localhost')['appkernel']


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')
    run_async(User.delete_all())
    run_async(Task.delete_all())


def test_generator():
    task = Task()
    task.name = 'some task name'
    task.description = 'some task description'
    task.finalise_and_validate()
    print(f'\nTask:\n {task}')
    assert task.id is not None and task.id.startswith('U')


def test_converter():
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    print(f'\n{user.dumps(pretty_print=True)}')
    assert user.password.startswith('$2b$')
    hash1 = user.password
    run_async(user.save())
    assert user.password.startswith('$2b$')
    assert hash1 == user.password


def test_unix_time_marshaller():
    user = run_async(create_and_save_a_user('test user', 'test password', 'test description'))
    user.last_login = datetime.now()
    user.finalise_and_validate()
    print('\n\n')
    user_json = user.dumps(pretty_print=True)
    print(user_json)
    assert isinstance(User.to_dict(user).get('last_login'), float)
    reloaded_user = User.loads(user_json)
    print(str(reloaded_user))
    assert isinstance(reloaded_user.last_login, datetime)

# todo: test encryption of a value object or other aggregate
