import inspect

from bson import ObjectId
from enum import Enum
import re, uuid
from datetime import datetime, date

try:
    import simplejson as json
except ImportError:
    import json
from util import default_json_serializer, OBJ_PREFIX


def create_uui_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id


class AppKernelException(Exception):
    def __init__(self, message):
        super(AppKernelException, self).__init__(message)


class ParameterRequiredException(AppKernelException):
    def __init__(self, value):
        super(AppKernelException, self).__init__('The parameter {} is required.'.format(value))


class ValidationException(AppKernelException):
    def __init__(self, validator_type, validable_object, message):
        self.validable_object_name = validable_object.__class__.__name__
        super(AppKernelException, self).__init__(
            '{} on type {} - {}'.format(validator_type.name, self.validable_object_name, message))


class ServiceException(AppKernelException):
    def __init__(self, http_error_code, message):
        super(AppKernelException, self).__init__(message)
        self.http_error_code = http_error_code


class ValidatorType(Enum):
    REGEXP = 1
    NOT_EMPTY = 2
    PAST = 3
    FUTURE = 4
    EXACT = 5


class Validator(object):
    """
    a root object for different type of validators
    """

    def __init__(self, validator_type, value=None):
        # type: (str, ValidatorType) -> ()
        self.value = value
        self.type = validator_type

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


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


class Expression(object):
    """
    a binary expression, eg. foo < bar, foo == bar, foo.contains(bar)
    """
    OPS = AttrDict(
        AND='$and',
        EQ='$eq',
        OR='$or',
        IS='@'
    )

    def __init__(self, lhs, ops, rhs):
        self.lhs = lhs
        self.ops = ops
        self.rhs = rhs


def get_argument_spec(provisioner_method):
    """
    Provides the argument list and types of methods which have a default value;
    :param provisioner_method: the method of an instance
    :return: the method arguments and default values as a dictionary, with method parameters as key and default values as dictionary value
    """
    assert inspect.ismethod(provisioner_method) or inspect.isfunction(
        provisioner_method), 'The provisioner method must be a method'
    args = [name for name in getattr(inspect.getargspec(provisioner_method), 'args') if name not in ['cls', 'self']]
    defaults = getattr(inspect.getargspec(provisioner_method), 'defaults')
    return dict(zip(args, defaults or [None for arg in args]))


def create_tagging_decorator(tag_name):
    def tagging_decorator(*args, **kwargs):
        # here we can receive the parameters handed over on the decorator (@decorator(a=b))
        def wrapper(method):
            method.member_tag = (tag_name, {'args': args, 'kwargs': kwargs})
            return method

        return wrapper

    return tagging_decorator


class TaggingMetaClass(type):
    def __new__(cls, name, bases, dct):
        tags = {}
        for member in dct.itervalues():
            if hasattr(member, 'member_tag') and (inspect.isfunction(member) or inspect.ismethod(member)):
                if member.member_tag[0] not in tags:
                    tags[member.member_tag[0]] = []
                tags[member.member_tag[0]].append({'function_name': member.__name__,
                                                   'argspec': get_argument_spec(member),
                                                   'decorator_args': list(member.member_tag[1].get('args')),
                                                   'decorator_kwargs': member.member_tag[1].get('kwargs'),
                                                   })
                # One example of a tag:
                # {
                #   'function_name': 'change_password',
                #   'argspec': {'password': 'default pass'},
                #   'decorator_args': [],
                #   'decorator_kwargs': {'http_method': ['POST']},
                # }
        dct.update(tags)
        return type.__new__(cls, name, bases, dct)


class Parameter(object):
    def __init__(self, python_type,
                 required=False,
                 sub_type=None,
                 validators=None,
                 to_value_converter=None,
                 from_value_converter=None,
                 default_value=None,
                 generator=None):
        # type: (type, bool, ParameterType, list, function, function, function) -> ()
        """

        :param python_type: the python type object (str, datetime or anything else)
        :param required: if True, the field must be specified before validation
        :param sub_type: in case the python type is dict or list (or any other collection type), you might want to specify the element type
        :param validators: a list of validator elements which are used to validate field content
        :param to_value_converter:
        :param from_value_converter:
        :param default_value:
        :param generator:
        """
        self.python_type = python_type
        self.required = required
        self.sub_type = sub_type
        self.validators = validators
        self.to_value_converter = to_value_converter
        self.from_value_converter = from_value_converter
        self.default_value = default_value
        self.generator = generator

    # def __eq__(self, right_hand_side):
    #     if right_hand_side is None:
    #         return Expression(self, Expression.OPS.IS, None)
    #     return Expression(self, Expression.OPS.EQ, right_hand_side)
    #
    # def __ne__(self, rhs):
    #     if rhs is None:
    #         return Expression(self, Expression.OPS.IS_NOT, None)
    #     return Expression(self, Expression.OPS.NE, rhs)

    # @staticmethod
    # def _e(ops, inv=False):
    #     """
    #     Returns a method that builds an Expression
    #     consisting of the left-hand and right-hand operands, using `OPS`.
    #     """
    #
    #     def inner(self, rhs):
    #         if inv:
    #             return Expression(rhs, ops, self)
    #         return Expression(self, ops, rhs)
    #
    #     return inner
    # __and__ = _e(Expression.OPS.AND)
    # __or__ = _e(Expression.OPS.OR)
    #
    # __add__ = _e(Expression.OPS.ADD)
    # __sub__ = _e(Expression.OPS.SUB)
    # __mul__ = _e(Expression.OPS.MUL)
    # __div__ = __truediv__ = _e(Expression.OPS.DIV)
    # __xor__ = _e(Expression.OPS.XOR)
    # __radd__ = _e(Expression.OPS.ADD, inv=True)
    # __rsub__ = _e(Expression.OPS.SUB, inv=True)
    # __rmul__ = _e(Expression.OPS.MUL, inv=True)
    # __rdiv__ = __rtruediv__ = _e(Expression.OPS.DIV, inv=True)
    # __rand__ = _e(Expression.OPS.AND, inv=True)
    # __ror__ = _e(Expression.OPS.OR, inv=True)
    # __rxor__ = _e(Expression.OPS.XOR, inv=True)
    # __lt__ = _e(Expression.OPS.LT)
    # __le__ = _e(Expression.OPS.LTE)
    # __gt__ = _e(Expression.OPS.GT)
    # __ge__ = _e(Expression.OPS.GTE)
    # __lshift__ = _e(Expression.OPS.IN)
    # __rshift__ = _e(Expression.OPS.IS)
    # __mod__ = _e(Expression.OPS.LIKE)
    # __pow__ = _e(Expression.OPS.ILIKE)
    #
    # bin_and = _e(Expression.OPS.BIN_AND)
    # bin_or = _e(Expression.OPS.BIN_OR)
    #
    # def contains(self, rhs):
    #     return Expression(self, Expression.OPS.ILIKE, '%%%s%%' % rhs)


def convert_date_time(string):
    return datetime.strptime(string, '%Y-%m-%dT%H:%M:%S.%f')


def default_convert(string):
    return string


class Model(object):
    type_converters = {
        date: convert_date_time,
        datetime: convert_date_time
    }

    def update(self, **kwargs):
        for name in kwargs:
            setattr(self, name, kwargs[name])
        return self

    def append_to(self, **kwargs):
        """
        appends one or more objects to a list
        :param kwargs:
        :return: the current object itself
        """
        for name in kwargs:
            if name not in self.__dict__:
                setattr(self, name, [])
            attr = self.__dict__.get(name)
            if isinstance(attr, list):
                if isinstance(kwargs[name], list):
                    attr.extend(kwargs[name])
                else:
                    attr.append(kwargs[name])

        return self

    def remove_from(self, **kwargs):
        """
        delete one or more elements from a list
        :param kwargs:
        :return:
        """
        for name in kwargs:
            if name in self.__dict__:
                attr = self.__dict__.get(name)
                if isinstance(attr, list):
                    attr.remove(kwargs[name])
                else:
                    raise AttributeError(
                        'The attribute {} is not a list on {}.'.format(name, self.__class__.__name__))
            else:
                raise AttributeError(
                    'The attribute {} is missing from the {} class.'.format(name, self.__class__.__name__))

    def __str__(self):
        return "<{}> {}".format(self.__class__.__name__, Model.dumps(self, validate=False))

    @staticmethod
    def init_model(instance, **kwargs):
        if isinstance(instance, Model):
            instance.update(**kwargs)
        else:
            raise TypeError('The Model initialisation works only with instances which inherit from Model.')

    @staticmethod
    def to_dict(instance, convert_id=False, validate=True):
        """
        Turns the python instance object into a dictionary
        :param validate: if false, the validation of the object will be skipped
        :param convert_id: it will convert id fields to _id for mongodb
        :param instance: the pythin instance object
        :return: a dictionary representing the python object
        """
        if validate and isinstance(instance, Model):
            instance.finalise_and_validate()
        if not hasattr(instance, '__dict__') and not isinstance(instance, dict):
            return instance
        result = {}
        instance_items = instance.__dict__.items() if not isinstance(instance, dict) else instance.items()
        for param, obj in instance_items:
            if isinstance(obj, Model):
                result[param] = Model.to_dict(obj, convert_id)
            elif isinstance(obj, Enum):
                result[param] = obj.name
            elif isinstance(obj, list):
                result[param] = [Model.to_dict(list_item, convert_id) for list_item in obj]
            else:
                if convert_id and param == 'id':
                    result['_id'] = obj
                else:
                    result[param] = obj
        return result

    @staticmethod
    def from_dict(dict_obj, cls, convert_ids=False, set_unmanaged_parameters=True):
        # type: (dict, cls) -> Model
        """
        :param set_unmanaged_parameters: if False, key-value pairs from the dict object which are not class variables on the Model (there is no Parameter object for them) will not be set
        :param convert_ids: strip the underscore prefix from object id parameter is exists ( _id -> id )
        :param dict_obj: the dictionary to be converted to object
        :param cls: the type of the object needs to be returned
        :return: returns an instantiated object from the dict
        """
        instance = cls()
        class_variables = [f for f in set(dir(instance)) if Model._include_param(f, cls)]
        if dict_obj and isinstance(dict_obj, dict):
            for key, val in dict_obj.items():
                if convert_ids and key == '_id':
                    key = 'id'
                if key in class_variables:
                    parameter = getattr(cls, key)
                    if isinstance(parameter, Parameter):
                        if issubclass(parameter.python_type, Model):
                            setattr(instance, key, Model.from_dict(val, parameter.python_type))
                        elif issubclass(parameter.python_type, list):
                            setattr(instance, key, Model.from_list(val, parameter.sub_type))
                        elif issubclass(parameter.python_type, Enum):
                            setattr(instance, key, parameter.python_type[val])
                        elif (key == '_id' or key == 'id') and isinstance(val, (str, basestring)) and val.startswith(
                                OBJ_PREFIX):
                            # check if the object id is a mongo object id
                            setattr(instance, key, ObjectId(val.split(OBJ_PREFIX)[0]))
                        elif isinstance(val, (basestring, str, unicode)):
                            # convert json string elements into target types based on the Parameter class
                            setattr(instance, key,
                                    Model.type_converters.get(parameter.python_type, default_convert)(val))
                        else:
                            # set object elements on the target instance
                            setattr(instance, key, val)
                elif set_unmanaged_parameters:
                    setattr(instance, key, val)
        return instance

    @staticmethod
    def from_list(list_obj, item_cls):
        return_list = []
        if list_obj and not isinstance(list_obj, list):
            return_list.append(list_obj)
        elif list_obj:
            for item in list_obj:
                if issubclass(item_cls, str):
                    return_list.append(item)
                else:
                    return_list.append(Model.from_dict(item, item_cls))
        return return_list

    def dumps(self, validate=True, pretty_print=False):
        model_as_dict = Model.to_dict(self, validate=validate)
        return json.dumps(model_as_dict, default=default_json_serializer, indent=4 if pretty_print else None,
                          sort_keys=True)

    @classmethod
    def loads(cls, json_string):
        # type: (basestring, cls) -> Model
        return Model.from_dict(json.loads(json_string), cls)

    def finalise_and_validate(self):
        obj_items = self.__dict__
        cls_items = {k: v for k, v in self.__class__.__dict__.iteritems() if isinstance(v, Parameter)}
        for param_name, param_object in cls_items.items():
            # initialise default values and generators for parameters which were not defined by the user
            if param_name not in obj_items:
                if param_object.default_value is not None:
                    setattr(self, param_name, param_object.default_value)
                elif param_object.generator:
                    setattr(self, param_name, param_object.generator())
            # validate fields
            if param_object.required and param_name not in obj_items:
                raise ParameterRequiredException(
                    '[{}] on class [{}]'.format(param_name, self.__class__.__name__))
            if param_object.validators is not None and isinstance(param_object.validators, list):
                for val in param_object.validators:
                    if isinstance(val, Validator) and param_name in self.__dict__:
                        val.validate(param_name, self.__dict__[param_name])
                    elif isinstance(val, type) and issubclass(val, Validator) and param_name in self.__dict__:
                        val().validate(param_name, self.__dict__.get(param_name))
            if issubclass(param_object.python_type, Model):
                self.__dict__[param_name].finalise_and_validate()

    def describe(self):
        props = set(dir(self))
        # print '(P): %s' % dir(self)
        # obj_dict = {k: v for k, v in self.__dict__.items()}
        print "params: %s" % [f for f in props if self._include_param(f, self.__class__)]
        # print "vars :: %s" % vars(list).keys()

    def _include_instance(self, field):
        return not field.startswith('__') and not callable(getattr(self, field)) and not isinstance(
            getattr(self, field), Parameter)

    @staticmethod
    def _include_param(field, cls):
        return field in cls.__dict__ and isinstance(getattr(cls, field), Parameter)
