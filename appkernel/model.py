from enum import Enum
import re, json, uuid
from datetime import datetime, date
from appkernel.util import default_serializer


def create_uui_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))
    return generate_id


class OpsmasterException(Exception):
    def __init__(self, message):
        super(OpsmasterException, self).__init__(message)


class ParameterRequiredException(OpsmasterException):
    def __init__(self, value):
        super(OpsmasterException, self).__init__('The parameter {} is required.'.format(value))


class ValidationException(OpsmasterException):
    def __init__(self, validator_type, validable_object, message):
        self.validable_object_name = validable_object.__class__.__name__
        super(OpsmasterException, self).__init__('{} on type {} - {}'.format(validator_type.name, self.validable_object_name, message))


class ValidatorType(Enum):
    REGEXP = 1
    NOT_EMPTY = 2
    PAST = 3
    FUTURE = 4


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


class Regexp(Validator):
    def __init__(self, value):
        super(Regexp, self).__init__(ValidatorType.REGEXP, value)

    def validate(self, parameter_name, validable_object):
        if isinstance(validable_object, basestring):
            if not re.match(self.value, validable_object):
                raise ValidationException(self.type, validable_object, 'The parameter {} cannot be validated against {}'.format(parameter_name, self.value))


class NotEmpty(Validator):
    def __init__(self):
        super(NotEmpty, self).__init__(ValidatorType.NOT_EMPTY)

    def validate(self, parameter_name, validable_object):
        if validable_object is None or not isinstance(validable_object, basestring) or not validable_object:
            raise ValidationException(self.type, validable_object, 'The parameter {} is None or empty.'.format(parameter_name))


class Past(Validator):
    def __init__(self):
        super(Past, self).__init__(ValidatorType.PAST)

    def _is_date(self, validable_object):
        return isinstance(validable_object, (datetime, date))

    def validate(self, parameter_name, validable_object):
        if validable_object is None or not self._is_date(validable_object):
            raise ValidationException(self.type, validable_object, 'The parameter {} is none or not date type.'.format(parameter_name))
        elif validable_object >= datetime.now():
            raise ValidationException(self.type, validable_object, 'The parameter {} must define the past.'.format(parameter_name))


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


class Model(object):
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
                raise AttributeError('The attribute {} is missing from the {} class.'.format(name, self.__class__.__name__))

    def __str__(self):
        return "<%s> %r" % (self.__class__.__name__, Model.dumps(self))

    @staticmethod
    def to_dict(instance, convert_id=False):
        """
        Turns the python instance object into a dictionary
        :param convert_id: it will convert id fields to _id for mongodb
        :param instance: the pythin instance object
        :return: a dictionary representing the python object
        """
        if isinstance(instance, Model):
            instance.validate_and_finalise()
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
        :param convert_ids: strip the underscore prefix from objec id parameter is exists ( _id -> id )
        :param dict_obj: the dictionary to be converted to object
        :param cls: the type of the object needs to be returned
        :return: returns an instantiated object from the dict
        """
        instance = cls()
        class_variables = [f for f in set(dir(instance)) if Model._include_param(f, cls)]
        if dict_obj and isinstance(dict_obj, dict):
            for k, v in dict_obj.items():
                if convert_ids and k == '_id':
                    k = 'id'
                if k in class_variables:
                    parameter = getattr(cls, k)
                    if isinstance(parameter, Parameter):
                        if issubclass(parameter.python_type, Model):
                            setattr(instance, k, Model.from_dict(v, parameter.python_type))
                        elif issubclass(parameter.python_type, list):
                            setattr(instance, k, Model.from_list(v, parameter.sub_type))
                        elif issubclass(parameter.python_type, Enum):
                            setattr(instance, k, parameter.python_type[v])
                        else:
                            setattr(instance, k, v)
                elif set_unmanaged_parameters:
                    setattr(instance, k, v)
        return instance

    @staticmethod
    def from_list(list_obj, item_cls):
        return_list = []
        if not list_obj:
            return return_list
        for item in list_obj:
            if issubclass(item_cls, str):
                return_list.append(item)
            else:
                return_list.append(Model.from_dict(item, item_cls))
        return return_list

    def dumps(self):
        print '==> {}'.format(Model.to_dict(self))
        return json.dumps(Model.to_dict(self), default=default_serializer, sort_keys=True)

    @staticmethod
    def loads(json_string, cls):
        # type: (basestring, cls) -> Model
        return Model.from_dict(json.loads(json_string), cls) #use object_hook

    def validate_and_finalise(self):
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
                raise ParameterRequiredException('parameter [{}] on class [{}] is required but missing'.format(param_name, self.__class__.__name__))
            if param_object.validators is not None and isinstance(param_object.validators, list):
                for val in param_object.validators:
                    if isinstance(val, Validator) and param_name in self.__dict__:
                        val.validate(param_name, self.__dict__[param_name])
                    elif isinstance(val, type) and issubclass(val, Validator) and param_name in self.__dict__:
                        val().validate(param_name, self.__dict__.get(param_name))
            if issubclass(param_object.python_type, Model):
                self.__dict__[param_name].validate_and_finalise()

    def describe(self):
        props = set(dir(self))
        # print '(P): %s' % dir(self)
        obj_dict = {k: v for k, v in self.__dict__.items()}
        print "params: %s" % [f for f in props if self._include_param(f, self.__class__)]
        # print "vars :: %s" % vars(list).keys()

    def _include_instance(self, field):
        return not field.startswith('__') and not callable(getattr(self, field)) and not isinstance(
            getattr(self, field), Parameter)

    @staticmethod
    def _include_param(field, cls):
        return field in cls.__dict__ and isinstance(getattr(cls, field), Parameter)
