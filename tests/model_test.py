import json
from decimal import Decimal

from pymongo import MongoClient
from appkernel import PropertyRequiredException
from appkernel import ValidationException
from appkernel.configuration import config
from .test_util import *
import pytest
from datetime import timedelta
from jsonschema import validate


def setup_module(module):
    config.mongo_database = MongoClient(host='localhost')['appkernel']


def setup_function(function):
    """ executed before each method call
    """
    print('\n\nSETUP ==> ')
    Project.delete_all()
    User.delete_all()


def test_regexp_validation():
    test_model_correct_format = ExampleClass()
    test_model_correct_format.just_numbers = '123456'
    test_model_correct_format.finalise_and_validate()

    with pytest.raises(ValidationException):
        test_model_correct_format = ExampleClass()
        test_model_correct_format.just_numbers = 'pppppp1234566p3455pppp'
        test_model_correct_format.finalise_and_validate()

    with pytest.raises(ValidationException):
        test_model_correct_format = ExampleClass()
        test_model_correct_format.just_numbers = '1234566p3455pppp'
        test_model_correct_format.finalise_and_validate()


def test_required_field():
    project = Project()
    with pytest.raises(PropertyRequiredException):
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
    project = Project().update(name='some project').append_to(
        tasks=Task().update(name='some task', description='some description'))
    project.tasks[0].complete()
    project.finalise_and_validate()
    print(('{}'.format(project)))
    project.tasks[0].update(closed_date=(datetime.now() - timedelta(days=1)))
    print(('\n\n> one day in the past \n{}'.format(project)))
    project.finalise_and_validate()
    with pytest.raises(ValidationException):
        project.tasks[0].update(closed_date=(datetime.now() + timedelta(days=1)))
        print(('\n\n> one day in the in the future \n{}'.format(project)))
        project.finalise_and_validate()


def test_future_validation():
    test_model = ExampleClass()
    test_model.just_numbers = 123
    test_model.finalise_and_validate()
    test_model.future_field = (datetime.now() + timedelta(days=1))
    test_model.finalise_and_validate()
    with pytest.raises(ValidationException):
        test_model.future_field = (datetime.now() - timedelta(days=1))
        print(('\n\n> one day in the in the future \n{}'.format(test_model)))
        test_model.finalise_and_validate()


def test_append_to_non_existing_non_defined_element():
    project = Project().update(name='strange project')
    project.append_to(users=Task().update(name='some_task', description='some description'))
    project.finalise_and_validate()
    assert 'users' in project.__dict__
    assert len(project.users) == 1
    assert isinstance(project.users[0], Task)
    print(('{}'.format(project)))


def test_append_to_non_existing_element():
    project = Project().update(name='strange project')
    project.append_to(tasks=Task().update(name='some_task', description='some description'))
    project.finalise_and_validate()
    assert 'tasks' in project.__dict__
    assert len(project.tasks) == 1
    assert isinstance(project.tasks[0], Task)
    print(('{}'.format(project)))


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
    print(('{}'.format(project)))
    project.remove_from(tasks=task1)
    assert len(project.tasks) == 2
    print(('{}'.format(project)))


def test_generator():
    task = Task()
    task.name = 'some task name'
    task.description = 'some task description'
    task.finalise_and_validate()
    print(('\nTask:\n {}'.format(task)))
    assert task.id is not None and task.id.startswith('U')


def test_converter():
    user = create_and_save_a_user('test user', 'test password', 'test description')
    print(('\n{}'.format(user.dumps(pretty_print=True))))
    assert user.password.startswith('$pbkdf2-sha256')
    hash1 = user.password
    user.save()
    assert user.password.startswith('$pbkdf2-sha256')
    assert hash1 == user.password


def test_nested_object_serialisation():
    portfolio = create_a_portfolion_with_owner()
    print((portfolio.dumps(pretty_print=True)))
    check_portfolio(portfolio)


def test_describe_model():
    user_spec = User.get_parameter_spec()
    print(User.get_paramater_spec_as_json())
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
    print(Project.get_paramater_spec_as_json())
    assert project_spec.get('created').get('required')
    assert project_spec.get('created').get('type') == 'datetime'

    assert project_spec.get('name').get('required')
    assert project_spec.get('name').get('type') == 'str'
    name_validators = project_spec.get('name').get('validators')
    assert len(name_validators) == 1
    assert name_validators[0].get('type') == 'NotEmpty'
    assert name_validators[0].get('value') is None or 'null'

    tasks = project_spec.get('tasks')
    assert not tasks.get('required')
    assert 'sub_type' in tasks
    assert tasks.get('type') == 'list'

    task = tasks.get('sub_type')
    assert task.get('type') == 'Task'
    assert 'props' in task

    props = task.get('props')
    assert not props.get('closed_date').get('required')
    assert props.get('closed_date').get('type') == 'datetime'
    assert props.get('closed_date').get('validators')[0].get('type') == 'Past'


def test_json_schema():
    json_schema = Project.get_json_schema()
    print('\n{}'.format(json.dumps(json_schema, indent=2)))
    print('===========')
    project = create_rich_project()
    print(project.dumps(pretty_print=True))
    assert json_schema.get('title') == 'Project Schema'
    assert 'title' in json_schema
    assert json_schema.get('type') == 'object'
    assert 'name' in json_schema.get('required')
    assert 'created' in json_schema.get('required')
    assert 'definitions' in json_schema
    assert json_schema.get('additionalProperties')
    definitions = json_schema.get('definitions')
    assert 'Task' in definitions
    assert len(definitions.get('Task').get('required')) == 6
    assert 'id' in definitions.get('Task').get('properties')
    closed_date = definitions.get('Task').get('properties').get('closed_date')
    assert 'string' in closed_date.get('type')
    assert len(closed_date.get('type')) == 2
    assert closed_date.get('format') == 'date-time'
    completed = definitions.get('Task').get('properties').get('completed')
    assert 'boolean' in completed.get('type')
    assert len(completed.get('type')) == 1

    validate(json.loads(project.dumps()), json_schema)
    # todo: check the enum / make a negative test
    # validator = Draft4Validator(json_schema)
    # errors = sorted(validator.iter_errors(project.dumps()), key=lambda e: e.path)
    # for error in errors:
    #     print('{}'.format(error.message, list(error.path)))


def test_json_schema_primitives_types():
    json_schema = Stock.get_json_schema()
    print(json.dumps(json_schema, indent=2))
    props = json_schema.get('properties')
    opentypes = props.get('open').get('type')
    assert 'number' in opentypes
    assert len(opentypes) == 1
    item_types = props.get('history').get('items').get('type')
    assert 'number' in item_types
    len(item_types) == 1
    stock = create_a_stock()
    validate(json.loads(stock.dumps()), json_schema)


def test_json_schema_complex():
    # print json.dumps(Portfolio.get_parameter_spec(True), indent=2)
    json_schema = Portfolio.get_json_schema()
    print(json.dumps(json_schema, indent=2))
    stock_definition = json_schema.get('definitions').get('Stock')
    assert stock_definition.get('properties').get('updated').get('format') == 'date-time'
    assert stock_definition.get('properties').get('code').get('pattern') == '[A-Za-z0-9-_]'
    assert stock_definition.get('properties').get('code').get('maxLength') == 4
    assert stock_definition.get('properties').get('open').get('minimum') == 0
    open_types = stock_definition.get('properties').get('open').get('type')
    assert 'number' in open_types
    assert len(open_types) == 1
    sequence_types = stock_definition.get('properties').get('sequence').get('type')
    assert 'number' in sequence_types
    assert len(sequence_types) == 2
    assert stock_definition.get('properties').get('sequence').get('minimum') == 1
    assert stock_definition.get('properties').get('sequence').get('maximum') == 100
    assert stock_definition.get('properties').get('sequence').get('multipleOf') == 1.0
    history_types = stock_definition.get('properties').get('history').get('type')
    assert 'array' in history_types
    assert len(history_types) == 2
    portfolio = create_portfolio('My Portfolio')
    validate(json.loads(portfolio.dumps()), json_schema)


def test_json_schema_in_mongo_compat_mode():
    json_schema = Project.get_json_schema(mongo_compatibility=True)
    print('\n\n{}'.format(json.dumps(json_schema, indent=2)))
    print('===========')
    task_spec = json_schema.get('properties').get('tasks')
    assert len(task_spec.get('items').get('required')) == 5
    priority_spec = task_spec.get('items').get('properties').get('priority')
    assert len(priority_spec.get('enum')) == 3
    closed_date_spec = task_spec.get('items').get('properties').get('closed_date')
    assert len(closed_date_spec.get('bsonType')) == 2
    assert 'bsonType' in json_schema
    assert 'id' not in json_schema
    assert '$schema' not in json_schema
    assert 'definitions' not in json_schema
    for prop in json_schema.get('properties').items():
        assert 'format' not in prop[1]
        assert 'bsonType' in prop[1]
    for prop in task_spec.get('items').get('properties').items():
        assert 'format' not in prop[1]
        assert 'bsonType' or 'enum' in prop[1]
    project = create_rich_project()
    print(project.dumps(pretty_print=True))
    validate(json.loads(project.dumps()), json_schema)


def __assert_product_dict(product_dict: dict):
    assert 'id' in product_dict
    assert 'name' in product_dict
    assert 'description' in product_dict
    assert 'size' in product_dict
    assert product_dict.get('size') == 'M'
    assert 'price' in product_dict
    assert isinstance(product_dict.get('price'), dict)
    price_dict = product_dict.get('price')
    assert '_type' in price_dict
    assert price_dict.get('_type') == 'money.money.Money'
    amount = price_dict.get('amount')
    assert isinstance(amount, Decimal)
    assert amount == 10.5
    assert price_dict.get('currency') == 'EUR'


def test_custom_object_marshalling():
    product = Product(name='White T-Shirt', description='a stylish white shirt', size=ProductSize.M,
                      price=Money(10.50, 'EUR'))
    product_dict = Model.to_dict(product)
    __assert_product_dict(product_dict)
    product_json = product.dumps(pretty_print=True)
    print('JSON: \n{}'.format(product_json))
    reloaded_product = Product.loads(product_json)
    assert reloaded_product is not None and isinstance(reloaded_product, Product)
    assert reloaded_product.id == product.id
    assert reloaded_product.name == product.name
    assert reloaded_product.description == product.description
    assert reloaded_product.size == product.size
    assert isinstance(reloaded_product.price, Money)
    assert reloaded_product.price == product.price


def test_custom_converter_function():
    pass
