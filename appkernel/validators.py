from enum import Enum
from appkernel.engine import AppKernelException
from datetime import datetime, date
import re

class ValidatorType(Enum):
    REGEXP = 1
    NOT_EMPTY = 2
    PAST = 3
    FUTURE = 4
    EXACT = 5


class ValidationException(AppKernelException):
    def __init__(self, validator_type, validable_object, message):
        self.validable_object_name = validable_object.__class__.__name__
        super(ValidationException, self).__init__(
            '{} on type {} - {}'.format(validator_type.name, self.validable_object_name, message))


class Validator(object):
    """
    a root object for different type of validators
    """

    def __init__(self, validator_type, value=None, message=None):
        # type: (str, ValidatorType) -> ()
        self.type = validator_type
        self.value = value
        self.message = message

    def validate(self, parameter_name, validable_object):
        """
        Validates and object against the validation pramaters.
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
        if isinstance(validable_object, basestring):
            if not re.match(self.value, validable_object):
                raise ValidationException(self.type, validable_object,
                                          'The parameter *{}* cannot be validated against {}'.format(parameter_name,
                                                                                                     self.value))


class NotEmpty(Validator):
    def __init__(self):
        super(NotEmpty, self).__init__(ValidatorType.NOT_EMPTY)

    def validate(self, parameter_name, validable_object):
        if not validable_object or not isinstance(validable_object, (basestring, str, unicode)) or len(
                validable_object) == 0:
            raise ValidationException(self.type, validable_object,
                                      'The parameter *{}* is None or not String.'.format(parameter_name))


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
