from enum import Enum
from datetime import datetime, date
import re
from flask_babel import _


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


class AppKernelException(Exception):
    def __init__(self, message):
        """
        A base exception class for AppKernel
        :param message: the cause of the failure
        """
        super(AppKernelException, self).__init__(message)


class AppInitialisationError(AppKernelException):

    def __init__(self, message):
        super(AppInitialisationError, self).__init__(message)


class ValidationException(AppKernelException):
    def __init__(self, validator_type, validable_object, message):
        self.validable_object_name = validable_object.__class__.__name__
        super(ValidationException, self).__init__(
            '{} on type {} - {}'.format(validator_type, self.validable_object_name, message))


class Validator(object):
    """
    a root object for different type of validators
    """

    def __init__(self, validator_type, value=None, message=None):
        # type: (str, str) -> ()
        self.type = validator_type.name if isinstance(validator_type, ValidatorType) else validator_type
        self.value = value
        self.message = message

    def validate(self, parameter_name, validable_object):
        """
        Validates and object against the validation parameters.

        :param parameter_name:
        :param validable_object:
        :raise ValidationException:
        """
        pass

    def _is_date(self, validable_object):
        return isinstance(validable_object, (datetime, date))


class Regexp(Validator):
    def __init__(self, value):
        super(Regexp, self).__init__(ValidatorType.REGEXP, value)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, str):
            if not re.match(self.value, validable_object):
                raise ValidationException(self.type, validable_object,
                                          _('The property %(prop_name)s cannot be validated against %(value)s.',
                                            prop_name=parameter_name, value=self.value))


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
            raise ValidationException(self.type, validable_object,
                                      'The parameter {} should hava a min. value of {}'.format(parameter_name,
                                                                                               self.value))


class Max(Validator):
    def __init__(self, maximum):
        super(Max, self).__init__(ValidatorType.MAX, maximum)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, (int, float)) and validable_object > self.value:
            raise ValidationException(self.type, validable_object,
                                      'The parameter {} should have a max. value of {}'.format(parameter_name,
                                                                                               self.value))


# class Range(Validator):
#     def __init__(self, minimum, maximum):
#         super(Range, self).__init__(ValidatorType.RANGE, minimum)
#         self.maximum = maximum
#
#     def validate(self, parameter_name, validable_object):
#         if isinstance(validable_object, (int, float, long)) and self.value <= validable_object <= self.maximum:
#             raise ValidationException(self.type, validable_object,
#                                       'The parameter {} value should be in the range of {}-{}'.format(parameter_name,
#                                                                                                       self.value,
#                                                                                                       self.maximum))


class Unique(Validator):
    def __init__(self):
        super(Unique, self).__init__(ValidatorType.UNIQUE)

    def validate(self, parameter_name, validable_object):
        if validable_object and isinstance(validable_object, list):
            if len(set(validable_object)) != len(validable_object):
                raise ValidationException(self.type, validable_object,
                                          'The parameter {} must not contain duplicated elements'.format(
                                              parameter_name))


class NotEmpty(Validator):
    """
    Used for string types to make sure that there's a string with length longer than 0. Also checks lists for a size.
    """

    def __init__(self):
        super(NotEmpty, self).__init__(ValidatorType.NOT_EMPTY)

    def validate(self, parameter_name, validable_object):
        if not validable_object or not isinstance(validable_object,
                                                  (str, list, set, dict, tuple)) or len(
            validable_object) == 0:
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* is None or not String '.format(parameter_name))


class Past(Validator):
    def __init__(self):
        super(Past, self).__init__(ValidatorType.PAST)

    def validate(self, parameter_name, validable_object):
        if validable_object is None or not self._is_date(validable_object):
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* is none or not date type.'.format(parameter_name))
        elif validable_object >= datetime.now():
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* must define the past.'.format(parameter_name))


class Future(Validator):
    def __init__(self):
        super(Future, self).__init__(ValidatorType.FUTURE)

    def validate(self, parameter_name, validable_object):
        if validable_object is None or not self._is_date(validable_object):
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* is none or not date type.'.format(parameter_name))
        elif validable_object <= datetime.now():
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* must define the future.'.format(parameter_name))
