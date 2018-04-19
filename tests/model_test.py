from appkernel.validators import ValidationException
from test_util import *
import pytest
import json
from datetime import timedelta


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

    #todo: test mappers
    #to_value_converter=to_unix_time, from_value_converter=to_time_unit
