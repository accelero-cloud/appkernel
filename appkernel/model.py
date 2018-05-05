import inspect
from bson import ObjectId
from enum import Enum
from datetime import datetime, date
from appkernel.validators import Validator, NotEmpty, Unique, Max, Min, Regexp, Email

try:
    import simplejson as json
except ImportError:
    import json
from util import default_json_serializer, OBJ_PREFIX


class AppKernelException(Exception):
    def __init__(self, message):
        super(AppKernelException, self).__init__(message)


class ParameterRequiredException(AppKernelException):
    def __init__(self, value):
        super(AppKernelException, self).__init__('The parameter {} is required.'.format(value))


class ServiceException(AppKernelException):
    def __init__(self, http_error_code, message):
        super(AppKernelException, self).__init__(message)
        self.http_error_code = http_error_code


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


class Opex(object):
    def __init__(self, name=None, lmbda=None):
        self.name = name
        self.lmbda = lmbda

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()


OPS = AttrDict( # pylint: disable=C0103
    AND=Opex('$and', lambda exp: {'$and': exp}),
    EQ=Opex('$eq', lambda exp: {'$eq': exp}),
    OR=Opex('$or', lambda exp: {'$or': exp}),
    GT=Opex('$gt', lambda exp: {'$gt': exp}),
    GTE=Opex('$gte', lambda exp: {'$gte': exp}),
    LT=Opex('$lt', lambda exp: {'$lt': exp}),
    LTE=Opex('$lte', lambda exp: {'$lte': exp}),
    IS=Opex('$eq', lambda exp: {'$eq': exp}),
    IS_NOT=Opex('is_not', lambda exp: {'$ne': exp}),
    LIKE=Opex('like', lambda exp: {'$regex': '.*{}.*'.format(exp), '$options': 'i'}),
    NE=Opex('$ne', lambda exp: {'$ne': exp}),
    #ARRAY_GTW=('array_gte', lambda  exp: { '$exists: true', "this.{}.length > {}".format(exp) }),
)


class DslBase(object):
    # https://rszalski.github.io/magicmethods/#comparisons
    def __eq__(self, right_hand_side):
        if right_hand_side is None:
            return Expression(self, OPS.IS, None)
        return Expression(self, OPS.EQ, right_hand_side)

    def __ne__(self, rhs):
        if rhs is None:
            return Expression(self, OPS.IS_NOT, None)
        return Expression(self, OPS.NE, rhs)

    def __create_expression(ops, inv=False):
        """
        Returns a method that builds an Expression
        consisting of the left-hand and right-hand operands, using `OPS`.
        """

        def inner(self, rhs):
            if inv:
                return Expression(rhs, ops, self)
            return Expression(self, ops, rhs)

        return inner

    __and__ = __create_expression(OPS.AND)
    __or__ = __create_expression(OPS.OR)
    __lt__ = __create_expression(OPS.LT)
    __le__ = __create_expression(OPS.LTE)
    __gt__ = __create_expression(OPS.GT)
    __ge__ = __create_expression(OPS.GTE)
    __mod__ = __create_expression(OPS.LIKE)

    # __div__ = __truediv__ = __create_expression(OPS.DIV)

    # __rshift__ = create_expression(Expression.OPS.IS)
    # __add__ = create_expression(Expression.OPS.ADD)
    # __sub__ = create_expression(Expression.OPS.SUB)
    # __mul__ = create_expression(Expression.OPS.MUL)
    # __xor__ = create_expression(Expression.OPS.XOR)
    # __radd__ = create_expression(Expression.OPS.ADD, inv=True)
    # __rsub__ = create_expression(Expression.OPS.SUB, inv=True)
    # __rmul__ = create_expression(Expression.OPS.MUL, inv=True)
    # __rdiv__ = __rtruediv__ = create_expression(Expression.OPS.DIV, inv=True)
    # __rand__ = create_expression(Expression.OPS.AND, inv=True)
    # __ror__ = create_expression(Expression.OPS.OR, inv=True)
    # __rxor__ = create_expression(Expression.OPS.XOR, inv=True)
    # __lshift__ = create_expression(Expression.OPS.IN)
    # __mod__ = create_expression(Expression.OPS.LIKE)
    # __pow__ = create_expression(Expression.OPS.ILIKE)
    # bin_and = create_expression(Expression.OPS.BIN_AND)
    # bin_or = create_expression(Expression.OPS.BIN_OR)

    def contains(self, rhs):
        return Expression(self, Expression.OPS.ILIKE, '%%%s%%' % rhs)


class Expression(DslBase):
    """
    a binary expression, eg. foo < bar, foo == bar, foo.contains(bar)
    """

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
    """
    Creates a new decorator which adds arbitrary tags to the decorated functions and methods, enabling these to be listed in a registry
    :param tag_name:
    :return:
    """

    def tagging_decorator(*args, **kwargs):
        # here we can receive the parameters handed over on the decorator (@decorator(a=b))
        def wrapper(method):
            method.member_tag = (tag_name, {'args': args, 'kwargs': kwargs})
            return method

        return wrapper

    return tagging_decorator


class BackReference(object):
    def __init__(self, class_name, parameter_name):
        self.class_name = class_name
        self.parameter_name = parameter_name


class _TaggingMetaClass(type):
    def __new__(mcs, class_name, bases, dct):
        tags = {}
        for member_name, member in dct.iteritems():
            if hasattr(member, 'member_tag') and (inspect.isfunction(member) or inspect.ismethod(member)):
                # if it is a tagged member
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
            if isinstance(member, Parameter):
                # adding the name of the implementing class and the parameter name
                member.backreference = BackReference(class_name=class_name, parameter_name=member_name)
        dct.update(tags)
        return type.__new__(mcs, class_name, bases, dct)


class SortOrder(Enum):
    ASC = 1
    DESC = -1


class Index(object):
    def __init__(self, sort_order):
        # type: (SortOrder) -> ()
        self.sort_order = sort_order


class TextIndex(Index):
    def __init__(self):
        super(TextIndex, self).__init__(SortOrder.ASC)


class UniqueIndex(Index):
    def __init__(self):
        super(UniqueIndex, self).__init__(SortOrder.ASC)


class Parameter(DslBase):
    def __init__(self, python_type,
                 required=False,
                 sub_type=None,
                 validators=None,
                 to_value_converter=None,
                 from_value_converter=None,
                 default_value=None,
                 generator=None,
                 index=None,
                 omit=False):
        # type: (type, bool, type, function, function, function, function, Index) -> ()
        """

        :param python_type: the python type object (str, datetime or anything else)
        :param required: if True, the field must be specified before validation
        :param sub_type: in case the python type is dict or list (or any other collection type), you might want to specify the element type
        :param validators: a list of validator elements which are used to validate field content
        :param to_value_converter: comverts the value of the fields in the finalisation phase (before generating json or saving in the database)
        :param from_value_converter:
        :param default_value: this value is set on the field in case there's no other value there yet
        :param generator: content generator, perfect for date.now() generation or for field values calculated from other fields (eg. signatures)
        :param index: the type of index (if any) which needs to be added to the database;
        :param omit: if True, the field won't be included in the json or other wire-format messages
        """
        self.omit = omit
        self.index = index
        self.python_type = python_type
        self.required = required
        self.sub_type = sub_type
        self.validators = validators
        self.to_value_converter = to_value_converter
        self.from_value_converter = from_value_converter
        self.default_value = default_value
        self.generator = generator

    def asc(self):
        return (self.backreference.parameter_name, 1)

    def desc(self):
        return (self.backreference.parameter_name, -1)


def convert_date_time(string):
    return datetime.strptime(string, '%Y-%m-%dT%H:%M:%S.%f')


def default_convert(string):
    return string


class Model(object):
    __metaclass__ = _TaggingMetaClass

    type_converters = {
        date: convert_date_time,
        datetime: convert_date_time
    }

    def __init__(self, **kwargs):
        self.update(**kwargs)

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

    @classmethod
    def get_json_schema(cls, additional_properties=True, mongo_compatibility=False):
        # type: (bool, bool) -> dict
        """
        Generates a JSON Schema document from the Model
        :param additional_properties: if True the schema will have an additional parameter called 'additionalProperties':true, which will allow extra elements
        :param mongo_compatibility: if true, the generated json schema will be compatible with mongo
        :return: the schema of the current object as a string
        """
        specs = cls.get_parameter_spec(convert_types_to_string=False)
        properties, required_props, definitions = Model.__prepare_json_schema_properties(specs,
                                                                                         mongo_compatibility=mongo_compatibility)
        type_label = 'type' if not mongo_compatibility else 'bsonType'

        schema = {
            'title': cls.__name__,
            type_label: 'object',
            'properties': properties,
            'required': required_props
        }
        if not mongo_compatibility:
            schema['$schema'] = 'http://json-schema.org/draft-04/schema#'
            if len(definitions) > 0:
                schema.update(definitions=definitions)
        if additional_properties:
            schema.update(additionalProperties=True)
        return schema

    @staticmethod
    def __prepare_json_schema_properties(specs, mongo_compatibility=False):

        type_label = 'type' if not mongo_compatibility else 'bsonType'

        type_map = {
            'str': 'string',
            'unicode': 'string',
            'basestring': 'string',
            'list': 'array',
            'int': 'number',
            'long': 'number',
            'float': 'number',
            'bool': 'boolean',
            'tuple': 'object',
            'dictionary': 'object',
            'date': 'string',
            'datetime': 'string'
        }

        format_map = {
            'datetime': 'date-time',
            'time': 'time'
        }

        # mongo bson types: https://docs.mongodb.com/manual/reference/bson-types/
        bson_type_map = {
            'date': 'date',
            # 'datetime': 'timestamp',
            # 'time': 'timestamp',
            'datetime': 'date',
            'time': 'date',
            'int': 'int',
            'long': 'long',
            'float': 'double',
            'bool': 'bool',
            'list': 'array'
        }

        def describe_enum(enum_class):
            return [e.name for e in enum_class]

        properties = {}
        required_props = []
        definitions = {}

        for name, spec in specs.iteritems():
            spec_type = spec.get('type')
            type_string = spec_type.__name__ if hasattr(spec_type, '__name__') else str(spec_type)
            if mongo_compatibility and (name == 'id' or name == '_id'):
                continue
            if issubclass(spec.get('type'), Enum):
                properties[name] = {'enum': describe_enum(spec.get('type'))}
                properties[name][type_label] = 'string'
                continue
            else:
                if not mongo_compatibility:
                    properties[name] = {type_label: type_map.get(type_string, 'string')}
                else:
                    properties[name] = {type_label: bson_type_map.get(type_string, 'string')}
                if type_string == 'int':
                    properties[name].update(multipleOf=1.0)
            # -- define formats --
            if not mongo_compatibility:
                xtra_type = format_map.get(type_string)
                if xtra_type:
                    properties[name].update(format=xtra_type)

            if 'validators' in spec:
                for validator in spec.get('validators'):
                    if spec.get('type') == list and validator.get('type') == NotEmpty:
                        # checking validators for a list
                        properties[name].update(minItems=1)
                    elif spec.get('type') == list and validator.get('type') == Unique:
                        properties[name].update(uniqueItems=True)
                    elif validator.get('type') == Min:
                        if spec.get('type') in [int, float, long]:
                            properties[name].update(minimum=validator.get('value'))
                        elif spec.get('type') in [str, basestring, unicode]:
                            properties[name].update(minLength=validator.get('value'))
                    elif validator.get('type') == Max:
                        if spec.get('type') in [int, float, long]:
                            properties[name].update(maximum=validator.get('value'))
                        elif spec.get('type') in [str, basestring, unicode]:
                            properties[name].update(maxLength=validator.get('value'))
                    elif validator.get('type') == Regexp:
                        properties[name].update(pattern=validator.get('value'))
                    elif validator.get('type') == Email:
                        properties[name].update(format='email')
                        # todo: add formats for: hostname, ipv4, ipv6, uri
                        # todo: build dependencies

            # -- handle subtypes --
            if spec.get('type') == list and spec.get('sub_type'):
                subtype = spec.get('sub_type')
                subtype_string = subtype.__name__ if hasattr(subtype, '__name__') else str(subtype)
                if not isinstance(subtype, dict):
                    # subtype is a primitive
                    if not mongo_compatibility:
                        properties[name].update(items={type_label: type_map.get(subtype_string, 'string')})
                    else:
                        properties[name].update(items={type_label: bson_type_map.get(subtype_string, 'string')})
                elif isinstance(spec.get('sub_type'), dict):
                    # subtype is a Model
                    props, req_props, defs = Model.__prepare_json_schema_properties(spec.get('sub_type').get('props'),
                                                                                    mongo_compatibility=mongo_compatibility)
                    def_name = spec.get('sub_type').get('type').__name__
                    definitions[def_name] = {}
                    if not mongo_compatibility:
                        definitions[def_name].update(required=req_props)
                        definitions[def_name].update(properties=props)
                        definitions.update(defs)
                        properties[name].update(type='array')
                        properties[name].update(items={'oneOf': [{"$ref": "#/definitions/{}".format(def_name)}]})
                    else:
                        # the schema needs to be generated in mongo compatible way
                        properties[name].update(items={type_label: 'object'})
                        properties[name]['items'].update(required=req_props)
                        properties[name]['items'].update(properties=props)
            elif spec.get('type') == list and not spec.sub_type:
                properties[name].update(items={type_label: 'string'})

            # -- build required elements --
            if spec.get('required'):
                required_props.append(name)

            # -- process the validators --
            # validators = spec.get('validators')
            # if validators:
            #     for validator in validators:
        return properties, required_props, definitions

    @classmethod
    def get_parameter_spec(cls, convert_types_to_string=True):
        props = cls.__dict__  # or: set(dir(cls))
        # print "params: %s" % [f for f in props if cls.__is_param_field(f, cls)]
        result_dct = {}
        for field_name in props:
            attribute = getattr(cls, field_name)
            if isinstance(attribute, Parameter):
                result_dct[field_name] = Model.__describe_attribute(cls, attribute,
                                                                    convert_types_to_string=convert_types_to_string)
        return result_dct

    @classmethod
    def get_paramater_spec_as_json(cls):
        return json.dumps(cls.get_parameter_spec(), default=default_json_serializer, indent=4, sort_keys=True)

    @staticmethod
    def __describe_attribute(clazz, attribute, convert_types_to_string=True):
        attr_desc = {
            'type': attribute.python_type.__name__ if convert_types_to_string else attribute.python_type,
            'required': attribute.required,
        }
        if issubclass(attribute.python_type, Model):
            attr_desc.update(
                props=attribute.python_type.get_parameter_spec(convert_types_to_string=convert_types_to_string))
        if attribute.default_value:
            attr_desc.update(default_value=attribute.default_value)
        if attribute.sub_type:
            if issubclass(attribute.sub_type, Model):
                attr_desc.update(
                    sub_type={
                        'type': attribute.sub_type.__name__ if convert_types_to_string else attribute.sub_type,
                        'props': attribute.sub_type.get_parameter_spec(convert_types_to_string=convert_types_to_string)
                    })
            else:
                attr_desc.update(
                    sub_type=attribute.sub_type.__name__ if convert_types_to_string else attribute.sub_type)
        if attribute.validators:
            if not isinstance(attribute.validators, list) and ((
                                                                       inspect.isclass(
                                                                           attribute.validators) and issubclass(
                                                                   attribute.validators, Validator))
                                                               or (isinstance(attribute.validators, Validator))):
                attribute.validators = [attribute.validators]
            attr_desc.update(
                validators=[clazz.__describe_validator(val, convert_types_to_string=convert_types_to_string) for val in
                            attribute.validators])
        return attr_desc

    @staticmethod
    def __describe_validator(validator, convert_types_to_string=True):
        def get_value(val):
            return val.__name__ if convert_types_to_string else val

        val_desc = {
            'type': get_value(validator) if hasattr(validator, '__name__') else get_value(validator.__class__)
        }

        if hasattr(validator, 'value'):
            val_desc.update(value=validator.value)

        # for key, value in [(key, value) for(key, value) in validator.__dict__.iteritems() if not key.startswith('__') and not callable(value)]:
        #     #set(dir(Cls)) - set(dir(object))
        #     val_desc[key] = value

        return val_desc

    @staticmethod
    def to_dict(instance, convert_id=False, validate=True, skip_omitted_fields=False):
        """
        Turns the python instance object into a dictionary after finalising and validating it.
        :param skip_omitted_fields: if True, the omitted fields will be exluded
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
            if skip_omitted_fields:
                # skip the omitted fields
                cls_items = {k: v for k, v in instance.__class__.__dict__.iteritems() if isinstance(v, Parameter)}
                parameter_def = cls_items.get(param)
                if parameter_def and parameter_def.omit:
                    continue
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
        Reads a dictionary representation of the model and turns it into a python object model.
        :param set_unmanaged_parameters: if False, key-value pairs from the dict object which are not class variables on the Model (there is no Parameter object for them) will not be set
        :param convert_ids: strip the underscore prefix from object id parameter is exists ( _id -> id )
        :param dict_obj: the dictionary to be converted to object
        :param cls: the type of the object needs to be returned
        :return: returns an instantiated object from the dict
        """
        instance = cls()
        class_variables = [f for f in set(dir(instance)) if Model.__is_param_field(f, cls)]
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
        """
        Returns the json representation of the object.
        :param validate: if True (default), will validate the object before converting it to Json;
        :param pretty_print:  if True (False by default) it will format the json object upon conversion;
        :return: the json object as a string
        """
        model_as_dict = Model.to_dict(self, validate=validate, skip_omitted_fields=True)
        return json.dumps(model_as_dict, default=default_json_serializer, indent=4 if pretty_print else None,
                          sort_keys=True)

    @classmethod
    def loads(cls, json_string):
        """
        Takes a json string and creates a python object from it.
        :param json_string: the Json string to be converted into an object
        :return: the generated object (it won't run validation on it)
        """
        # type: (basestring, cls) -> Model
        return Model.from_dict(json.loads(json_string), cls)

    def finalise_and_validate(self):
        """
        Calls the generator, default value calculator and converter methods first,
        than it will validate the object;
        :raises ParameterRequiredException: in case some value property is mandatory
        :raises ValidationException: in case one of the parameter validators do not validate
        """
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
            if param_object.to_value_converter:
                setattr(self, param_name, param_object.to_value_converter(getattr(self, param_name)))
            if param_object.validators is not None and isinstance(param_object.validators, list):
                for val in param_object.validators:
                    if isinstance(val, Validator) and param_name in self.__dict__:
                        val.validate(param_name, self.__dict__[param_name])
                    elif isinstance(val, type) and issubclass(val, Validator) and param_name in self.__dict__:
                        val().validate(param_name, self.__dict__.get(param_name))
            if issubclass(param_object.python_type, Model):
                self.__dict__[param_name].finalise_and_validate()

    def dump_spec(self):
        """
        prints the parameter specification of the model
        """
        props = set(dir(self))
        # print '(P): %s' % dir(self)
        # obj_dict = {k: v for k, v in self.__dict__.items()}
        print "params: %s" % [f for f in props if self.__is_param_field(f, self.__class__)]
        # print "vars :: %s" % vars(list).keys()

    def _include_instance(self, field):
        return not field.startswith('__') and not callable(getattr(self, field)) and not isinstance(
            getattr(self, field), Parameter)

    @staticmethod
    def __is_param_field(field, cls):
        return field in cls.__dict__ and isinstance(getattr(cls, field), Parameter)
