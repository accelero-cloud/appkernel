import datetime
import re
from enum import Enum

from flask_babel import _

from .model import AppKernelException


class ValidatorType(Enum):
    REGEXP = 1
    NOT_EMPTY = 2
    PAST = 3
    FUTURE = 4
    EXACT = 5
    UNIQUE = 6
    MIN = 7
    MAX = 8
    RANGE = 9
    EMAIL = 10


class ValidationException(AppKernelException):
    def __init__(self, message, validable_object=None, validator_type=None):
        self.validable_object_name = validable_object.__class__.__name__ if validable_object else 'unspec'
        validator_name = str(validator_type) if validator_type else 'unspec'
        super().__init__(f'{validator_name} on type {self.validable_object_name} - {message}')


class Validator(object):
    """
    a root object for different type of validators
    """

    def __init__(self, validator_type, value=None, message=None):
        # type: (str, str) -> ()
        self.type = validator_type.name if isinstance(validator_type, ValidatorType) else validator_type
        self.value = value
        self.message = message

    def validate_objects(self, parameter_name: str, instance_parameters: list):
        self.validate(parameter_name, instance_parameters.get(parameter_name))

    def validate(self, parameter_name: str, validable_object: any):
        """
        Validates and object against the validation parameters.

        :param parameter_name:
        :param validable_object:
        :raise ValidationException:
        """
        pass

    def _is_date(self, validable_object):
        return isinstance(validable_object, (datetime.datetime, datetime.date))


class Regexp(Validator):
    def __init__(self, value):
        super(Regexp, self).__init__(ValidatorType.REGEXP, value)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, str):
            if not re.match(self.value, validable_object):
                raise ValidationException(_('The property %(prop_name)s cannot be validated against %(value)s.',
                                            prop_name=parameter_name, value=self.value), self.type, validable_object)


class Email(Regexp):
    """
    It is a convenience validator extending the Regexp validator and initialising it with an e-mail regular expression.
    """

    def __init__(self):
        super(Email, self).__init__(
            '(?:[a-z0-9!#$%&\'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&\'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])')


class Min(Validator):
    def __init__(self, minimum):
        super(Min, self).__init__(ValidatorType.MIN, minimum)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, (int, float)) and validable_object < self.value:
            raise ValidationException(f'The parameter {parameter_name} should hava a min. value of {self.value}',
                                      validable_object, self.type)


class Max(Validator):
    def __init__(self, maximum):
        super(Max, self).__init__(ValidatorType.MAX, maximum)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, (int, float)) and validable_object > self.value:
            raise ValidationException(f'The parameter {parameter_name} should have a max. value of {self.value}',
                                      validable_object, self.type)


# class Range(Validator):
#     def __init__(self, minimum, maximum):
#         super(Range, self).__init__(ValidatorType.RANGE, minimum)
#         self.maximum = maximum
#
#     def validate(self, parameter_name, validable_object):
#         if isinstance(validable_object, (int, float, long)) and self.value <= validable_object <= self.maximum:
#             raise ValidationException(
#                 f'The parameter {parameter_name} value should be in the range of {self.value}-{self.maximum}',
#                 validable_object, self.type)


class Unique(Validator):
    def __init__(self):
        super(Unique, self).__init__(ValidatorType.UNIQUE)

    def validate(self, parameter_name, validable_object):
        if validable_object and isinstance(validable_object, list):
            if len(set(validable_object)) != len(validable_object):
                raise ValidationException(f'The parameter {parameter_name} must not contain duplicated elements',
                                          validable_object, self.type)


class NotEmpty(Validator):
    """
    Used for string types to make sure that there's a string with length longer than 0. Also checks lists for a size.
    """

    def __init__(self):
        super(NotEmpty, self).__init__(ValidatorType.NOT_EMPTY)

    def validate(self, parameter_name, validable_object):
        if not validable_object or not isinstance(validable_object,
                                                  (str, list, set, dict, tuple)) or len(validable_object) == 0:
            raise ValidationException(f'The parameter {parameter_name} is None or empty.', validable_object, self.type)


class Past(Validator):
    def __init__(self):
        super(Past, self).__init__(ValidatorType.PAST)

    def validate(self, parameter_name, validable_object):
        if validable_object is None:
            return
        elif not self._is_date(validable_object):
            raise ValidationException(f'The parameter {parameter_name} is none or not date type.', validable_object,
                                      self.type)
        elif validable_object >= datetime.datetime.now():
            raise ValidationException(f'The parameter {parameter_name} must define the past.', validable_object,
                                      self.type)


class Future(Validator):
    def __init__(self):
        super(Future, self).__init__(ValidatorType.FUTURE)

    def validate(self, parameter_name, validable_object):
        if validable_object is None or not self._is_date(validable_object):
            raise ValidationException(f'The parameter {parameter_name} is none or not date type.', validable_object,
                                      self.type)
        elif validable_object <= datetime.datetime.now():
            raise ValidationException(f'The parameter {parameter_name} must define the future.', validable_object,
                                      self.type)
