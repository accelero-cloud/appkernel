import datetime
from datetime import timedelta

import pytest

from appkernel import ValidationException
from tests.utils import ExampleClass, Project, Task, Payment, PaymentMethod


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


def test_email_validator():
    example = ExampleClass(just_numbers='1234')
    example.finalise_and_validate()

    with pytest.raises(ValidationException):
        example.email = 'some_mail'
        example.finalise_and_validate()

    example.email = 'acme@coppa.com'
    example.finalise_and_validate()


def test_min_max():
    example = ExampleClass(just_numbers='1234')
    example.finalise_and_validate()

    with pytest.raises(ValidationException):
        example.distance = 1
        example.finalise_and_validate()

    with pytest.raises(ValidationException):
        example.distance = 16
        example.finalise_and_validate()

    example.distance = 10
    example.finalise_and_validate()


def test_unique():
    example = ExampleClass(just_numbers='1234')
    example.finalise_and_validate()
    with pytest.raises(ValidationException):
        example.numbers = [1, 2, 1]
        example.finalise_and_validate()

    with pytest.raises(ValidationException):
        example.numbers = ['a', 'b', 'a']
        example.finalise_and_validate()

    example.numbers = ['a', 'b', 'c']
    example.finalise_and_validate()

    example.numbers = [1, 2, 3]
    example.finalise_and_validate()


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
    print(f'{project}')
    project.tasks[0].update(closed_date=(datetime.datetime.now() - timedelta(days=1)))
    print(f'\n\n> one day in the past \n{project}')
    project.finalise_and_validate()

    with pytest.raises(ValidationException):
        project.tasks[0].update(closed_date=(datetime.datetime.now() + timedelta(days=1)))
        project.finalise_and_validate()

    with pytest.raises(ValidationException):
        project.tasks[0].update(closed_date='past')
        project.finalise_and_validate()


def test_future_validation():
    test_model = ExampleClass()
    test_model.just_numbers = 123
    test_model.finalise_and_validate()
    test_model.future_field = (datetime.datetime.now() + timedelta(days=1))
    test_model.finalise_and_validate()
    with pytest.raises(ValidationException):
        test_model.future_field = (datetime.datetime.now() - timedelta(days=1))
        print(f'\n\n> one day in the in the future \n{test_model}')
        test_model.finalise_and_validate()

    with pytest.raises(ValidationException):
        test_model.future_field = 'future'
        test_model.finalise_and_validate()


def test_validate_method():
    payment = Payment(method=PaymentMethod.MASTER, customer_id='123456', customer_secret='123')
    with pytest.raises(ValidationException):
        payment.finalise_and_validate()
    payment.customer_id = '1234567890123456'
    payment.finalise_and_validate()


# ---------------------------------------------------------------------------
# Direct validator class tests — covers remaining uncovered lines
# ---------------------------------------------------------------------------

def test_i18n_passthrough_with_kwargs():
    """Covers the `return message % kwargs` branch in validators._()."""
    from appkernel.validators import _
    result = _('Value %(value)s is invalid', value='42')
    assert '42' in result


def test_validator_base_validate_is_noop():
    """Covers Validator.validate() body — it's a no-op in the base class."""
    from appkernel.validators import Validator, ValidatorType
    v = Validator(ValidatorType.NOT_EMPTY)
    v.validate('field', 'any value')  # should not raise


def test_past_none_value_returns_early():
    """Covers Past.validate() when value is None — the explicit `return` on line 150."""
    from appkernel.validators import Past
    v = Past()
    v.validate('created_at', None)  # must not raise
