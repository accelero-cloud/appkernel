from pymongo import MongoClient

from appkernel import AppKernelEngine
from appkernel.validators import ValidationException
from test_util import *
import pytest
from datetime import timedelta
from jsonschema import validate

def setup_module(module):
    AppKernelEngine.database = MongoClient(host='localhost')['appkernel']


def setup_function(function):
    """ executed before each method call
    """
    print ('\n\nSETUP ==> ')
    Project.delete_all()
    User.delete_all()


def test_regexp_validation():
    test_model_correct_format = TestClass()
    test_model_correct_format.just_numbers = '123456'
    test_model_correct_format.finalise_and_validate()

    with pytest.raises(ValidationException):
        test_model_correct_format = TestClass()
        test_model_correct_format.just_numbers = 'pppppp1234566p3455pppp'
        test_model_correct_format.finalise_and_validate()

    with pytest.raises(ValidationException):
        test_model_correct_format = TestClass()
        test_model_correct_format.just_numbers = '1234566p3455pppp'
        test_model_correct_format.finalise_and_validate()


def test_required_field():
    project = Project()
    with pytest.raises(ParameterRequiredException):
        project.finalise_and_validate()
    project.update(name='some_name')
    project.finalise_and_validate()


def test_not_empty_validation():
    project = Project().update(name='')
    with pytest.raises(ValidationException):
        project.finalise_and_validate()
    project.update(name='some_name')
    project.finalise_and_validate()


def test_past_validation():
    project = Project().update(name='some project').append_to(tasks=Task().update(name='some task', description='some description'))
    project.tasks[0].complete()
    project.finalise_and_validate()
    print('{}'.format(project))
    project.tasks[0].update(closed_date=(datetime.now() - timedelta(days=1)))
    print('\n\n> one day in the past \n{}'.format(project))
    project.finalise_and_validate()
    with pytest.raises(ValidationException):
        project.tasks[0].update(closed_date=(datetime.now() + timedelta(days=1)))
        print('\n\n> one day in the in the future \n{}'.format(project))
        project.finalise_and_validate()


def test_future_validation():
    test_model = TestClass()
    test_model.just_numbers = 123
    test_model.finalise_and_validate()
    test_model.future_field = (datetime.now() + timedelta(days=1))
    test_model.finalise_and_validate()
    with pytest.raises(ValidationException):
        test_model.future_field = (datetime.now() - timedelta(days=1))
        print('\n\n> one day in the in the future \n{}'.format(test_model))
        test_model.finalise_and_validate()


def test_append_to_non_existing_non_defined_element():
    project = Project().update(name='strange project')
    project.append_to(users=Task().update(name='some_task', description='some description'))
    project.finalise_and_validate()
    assert 'users' in project.__dict__
    assert len(project.users) == 1
    assert isinstance(project.users[0], Task)
    print('{}'.format(project))


def test_append_to_non_existing_element():
    project = Project().update(name='strange project')
    project.append_to(tasks=Task().update(name='some_task', description='some description'))
    project.finalise_and_validate()
    assert 'tasks' in project.__dict__
    assert len(project.tasks) == 1
    assert isinstance(project.tasks[0], Task)
    print('{}'.format(project))


def test_remove_non_existing_element():
    with pytest.raises(AttributeError):
        project = Project().update(name='strange project')
        project.remove_from(tasks=Task())

    with pytest.raises(AttributeError):
        project = Project().update(name='strange project')
        project.remove_from(tasks=None)

    with pytest.raises(AttributeError):
        project = Project().update(name='strange project')
        project.remove_from(somehtings=Task())


def test_remove_existing_defined_element():
    task1 = Task().update(name='some_task', description='some description')
    task2 = Task().update(name='some_other_task', description='some other description')
    task3 = Task().update(name='a third task', description='some third description')
    project = Project().update(name='strange project')
    project.append_to(tasks=[task1, task2])
    project.finalise_and_validate()
    assert len(project.tasks) == 2
    project.append_to(tasks=task3)
    project.finalise_and_validate()
    assert len(project.tasks) == 3
    print('{}'.format(project))
    project.remove_from(tasks=task1)
    assert len(project.tasks) == 2
    print('{}'.format(project))


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


def test_describe_model():
    user_spec = User.get_parameter_spec()
    print User.get_paramater_spec_as_json()
    assert 'name' in user_spec
    assert user_spec.get('name').get('required')
    assert user_spec.get('name').get('type') == 'str'
    assert len(user_spec.get('name').get('validators')) == 2
    for validator in user_spec.get('name').get('validators'):
        if validator.get('type') == 'Regexp':
            assert validator.get('value') == '[A-Za-z0-9-_]'
    assert user_spec.get('roles').get('sub_type') == 'str'


def test_describe_rich_model():
    project_spec = Project.get_parameter_spec()
    print Project.get_paramater_spec_as_json()


def test_json_schema():
    json_schema = Project.get_json_schema()
    print json.dumps(json_schema, indent=2)
    print '==========='
    project = create_rich_project()
    print project.dumps(pretty_print=True)
    assert json_schema.get('title') == 'Project'
    assert 'name' in json_schema.get('required')
    assert 'created' in json_schema.get('required')
    assert 'definitions' in json_schema
    assert json_schema.get('additionalProperties')
    definitions = json_schema.get('definitions')
    assert 'Task' in definitions
    assert len(definitions.get('Task').get('required')) == 5
    closed_date = definitions.get('Task').get('properties').get('closed_date')
    assert closed_date.get('type') == 'string'
    assert closed_date.get('format') == 'date-time'
    completed = definitions.get('Task').get('properties').get('completed')
    assert completed.get('type') == 'boolean'

    validate(json.loads(project.dumps()), json_schema)
    # validator = Draft4Validator(json_schema)
    # errors = sorted(validator.iter_errors(project.dumps()), key=lambda e: e.path)
    # for error in errors:
    #     print('{}'.format(error.message, list(error.path)))


def test_json_schema_in_mongo_compat_mode():
    json_schema = Project.get_json_schema(mongo_compatibility=True)
    print '\n\n{}'.format(json.dumps(json_schema, indent=2))
    print '==========='
    project = create_rich_project()
    print project.dumps(pretty_print=True)
    validate(json.loads(project.dumps()), json_schema)
    #todo: continue with assertions and mongo compatibility


    #todo: test converters
    #todo: expose model description over rest
    #to_value_converter=to_unix_time, from_value_converter=to_time_unit
