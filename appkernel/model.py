from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import datetime, date
from enum import Enum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict

from .core import AppKernelException
from .validators import Validator, NotEmpty, Unique, Max, Min, Regexp, Email
from .util import default_json_serializer, OBJ_PREFIX

from .dsl import CustomProperty

# Import field metadata types and metaclass
from .fields import (
    AppKernelMeta,
    get_field_validators_meta, get_field_marshaller,
    is_field_required, is_field_omitted, get_field_generator, get_field_converter,
    get_field_default, extract_base_type,
)

try:
    from babel.support import LazyProxy
    lazy_gettext = lambda s: LazyProxy(lambda: _translate(s))
except ImportError:
    lazy_gettext = lambda s: s


try:
    import simplejson as json
except ImportError:
    import json


def _translate(s: str) -> str:
    """Translate a string using the configured translation catalog."""
    from .configuration import config
    translations = getattr(config, 'translations', None)
    if translations:
        result = translations.ugettext(s) if hasattr(translations, 'ugettext') else translations.gettext(s)
        return result if result != s else s
    return s


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

# MongoDB BSON types: https://docs.mongodb.com/manual/reference/bson-types/
bson_type_map = {
    'date': 'date',
    'datetime': 'date',
    'time': 'date',
    'int': 'int',
    'long': 'long',
    'float': 'double',
    'bool': 'bool',
    'list': 'array'
}


def _get_custom_class(fqdn: str) -> type | None:
    try:
        parts = fqdn.split('.')
        module_str = ".".join(parts[:-1])
        module = __import__(module_str)
        for comp in parts[1:]:
            module = getattr(module, comp)
        return module
    except Exception as ex:
        raise AppKernelException(
            f"Couldn't instantiate complex object due to {ex.__class__.__name__}: {str(ex)} -> {fqdn}")


def _instantiate_custom_class(clazz: type, param_dict: dict[str, Any], converter_func: Callable | None = None) -> Any:
    assert inspect.isclass(clazz)
    const_args = inspect.getfullargspec(clazz.__init__).args
    if len(const_args) > 1:
        constructor_dict = {}
        for c_arg in const_args:
            if c_arg != 'self' and c_arg in param_dict:
                val = param_dict.pop(c_arg)
                if isinstance(val, dict) and '_type' in val:
                    nested_class = _get_custom_class(val['_type'])
                    if nested_class:
                        val = _instantiate_custom_class(nested_class, val, converter_func=converter_func)
                if converter_func and isinstance(converter_func, Callable):
                    val = converter_func(val)
                constructor_dict[c_arg] = val
        custom_instance = clazz(**constructor_dict)
    else:
        custom_instance = clazz()
    for key, value in param_dict.items():
        if key != '_type':
            setattr(custom_instance, key, value)
    return custom_instance


def _xtract_custom_object_to_dict(custom_object: Any, converter_func: Callable | None = None) -> Any:
    if hasattr(custom_object, '__dict__'):
        instance_items = {(pn, pv) for pn, pv in custom_object.__dict__.items() if not pn.startswith('_')}
    else:
        if converter_func and isinstance(converter_func, Callable):
            return converter_func(custom_object)
        else:
            return custom_object
    result = {}
    result.update(_type=f'{custom_object.__module__}.{custom_object.__class__.__qualname__}')

    for prop_name, prop_value in instance_items:
        result[prop_name] = _xtract_custom_object_to_dict(prop_value, converter_func=converter_func)
    try:
        properties = set(inspect.getmembers(custom_object.__class__, lambda o: isinstance(o, property)))
    except Exception:
        properties = set()
    for prop_name, prop_value in properties:
        if converter_func and isinstance(converter_func, Callable):
            result[prop_name] = converter_func(getattr(custom_object, prop_name))
        else:
            result[prop_name] = getattr(custom_object, prop_name)
    return result


class PropertyRequiredException(AppKernelException):
    def __init__(self, value: str) -> None:
        super().__init__(f'The property {value} is required.')


def convert_date_time(string: str) -> datetime:
    return datetime.strptime(string, '%Y-%m-%dT%H:%M:%S.%f')


def default_convert(string: str) -> str:
    return string


string_to_type_converters: dict[type, Callable] = {
    date: convert_date_time,
    datetime: convert_date_time,
}


# ---------------------------------------------------------------------------
# Model — Pydantic BaseModel with AppKernel extensions
# ---------------------------------------------------------------------------

class Model(BaseModel, metaclass=AppKernelMeta):
    """
    The base class of all Model objects which are intended to be persisted
    in the database or served via REST. Built on Pydantic BaseModel.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow',
        populate_by_name=True,
    )

    def __init__(self, **kwargs: Any) -> None:
        # Initialize all declared fields to None if not provided,
        # to preserve AppKernel's deferred validation pattern.
        defaults = {}
        for field_name in self.__class__.model_fields:
            if field_name not in kwargs:
                defaults[field_name] = None
        defaults.update(kwargs)
        super().__init__(**defaults)

    def update(self, **kwargs: Any) -> Model:
        """Set one or more attributes and return ``self`` for method chaining.

        Args:
            **kwargs: attribute names and values to set on this instance.

        Returns:
            This Model instance, enabling fluent calls like
            ``user.update(name='John').update(password='secret')``.
        """
        for name, value in kwargs.items():
            setattr(self, name, value)
        return self

    def append_to(self, **kwargs: Any) -> Model:
        for name in kwargs:
            current = getattr(self, name, None)
            if current is None:
                setattr(self, name, [])
                current = getattr(self, name)
            if isinstance(current, list):
                if isinstance(kwargs[name], list):
                    current.extend(kwargs[name])
                else:
                    current.append(kwargs[name])
        return self

    def remove_from(self, **kwargs: Any) -> Model:
        for name in kwargs:
            current = getattr(self, name, None)
            if current is not None:
                if isinstance(current, list):
                    current.remove(kwargs[name])
                else:
                    raise AttributeError(
                        f'The attribute {name} is not a list on {self.__class__.__name__}.')
            else:
                raise AttributeError(
                    f'The attribute {name} is missing from the {self.__class__.__name__} class.')
        return self

    def __str__(self) -> str:
        return f"<{self.__class__.__name__}> {Model.to_dict(self, validate=False, marshal_values=False)}"

    @classmethod
    def custom_property(cls, custom_field_name: str) -> CustomProperty:
        return CustomProperty(cls, custom_field_name)

    @staticmethod
    def init_model(instance: Model, **kwargs: Any) -> None:
        if isinstance(instance, Model):
            instance.update(**kwargs)
        else:
            raise TypeError('The Model initialisation works only with instances which inherit from Model.')

    # -------------------------------------------------------------------
    # JSON Schema generation
    # -------------------------------------------------------------------

    @classmethod
    def get_json_schema(cls, additional_properties: bool = True, mongo_compatibility: bool = False) -> dict[str, Any]:
        specs = cls.get_parameter_spec(convert_types_to_string=False)
        properties, required_props, definitions = Model.__prepare_json_schema_properties(
            specs, mongo_compatibility=mongo_compatibility)

        type_label = 'type' if not mongo_compatibility else 'bsonType'

        schema = {
            'title': f'{cls.__name__} Schema',
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
    def __prepare_json_schema_properties(
        specs: dict[str, Any], mongo_compatibility: bool = False
    ) -> tuple[dict[str, Any], list[str], dict[str, Any]]:

        type_label = 'type' if not mongo_compatibility else 'bsonType'

        def describe_enum(enum_class: type) -> list[str]:
            return [e.name for e in enum_class]

        properties: dict[str, Any] = {}
        required_props: list[str] = []
        definitions: dict[str, Any] = {}

        for name, spec in specs.items():
            spec_type = spec.get('type')
            type_string = spec_type.__name__ if hasattr(spec_type, '__name__') else str(spec_type)
            if mongo_compatibility and (name == 'id' or name == '_id'):
                continue
            elif issubclass(spec.get('type'), Enum):
                properties[name] = {'enum': describe_enum(spec.get('type'))}
            else:
                if not mongo_compatibility:
                    properties[name] = {type_label: [type_map.get(type_string, 'string')]}
                    xtra_type = format_map.get(type_string)
                    if xtra_type:
                        properties[name].update(format=xtra_type)
                else:
                    properties[name] = {type_label: [bson_type_map.get(type_string, 'string')]}
                if type_string == 'int':
                    properties[name].update(multipleOf=1.0)

            if 'validators' in spec:
                for validator in spec.get('validators'):
                    if spec.get('type') == list and validator.get('type') == NotEmpty:
                        properties[name].update(minItems=1)
                    elif spec.get('type') == list and validator.get('type') == Unique:
                        properties[name].update(uniqueItems=True)
                    elif validator.get('type') == Min:
                        if spec.get('type') in [int, float]:
                            properties[name].update(minimum=validator.get('value'))
                        elif spec.get('type') in [str]:
                            properties[name].update(minLength=validator.get('value'))
                    elif validator.get('type') == Max:
                        if spec.get('type') in [int, float]:
                            properties[name].update(maximum=validator.get('value'))
                        elif spec.get('type') in [str]:
                            properties[name].update(maxLength=validator.get('value'))
                    elif validator.get('type') == Regexp:
                        properties[name].update(pattern=validator.get('value'))
                    elif validator.get('type') == Email and not mongo_compatibility:
                        properties[name].update(format='email')

            # Handle subtypes
            if spec.get('type') == list and spec.get('sub_type'):
                subtype = spec.get('sub_type')
                subtype_string = subtype.__name__ if hasattr(subtype, '__name__') else str(subtype)
                if not isinstance(subtype, dict):
                    if not mongo_compatibility:
                        properties[name].update(items={type_label: type_map.get(subtype_string, 'string')})
                    else:
                        properties[name].update(items={type_label: bson_type_map.get(subtype_string, 'string')})
                elif isinstance(spec.get('sub_type'), dict):
                    props, req_props, defs = Model.__prepare_json_schema_properties(
                        spec.get('sub_type').get('props'),
                        mongo_compatibility=mongo_compatibility)
                    def_name = spec.get('sub_type').get('type').__name__
                    definitions[def_name] = {}
                    if not mongo_compatibility:
                        definitions[def_name].update(required=req_props)
                        definitions[def_name].update(properties=props)
                        definitions.update(defs)
                        properties[name].update(type=['array'])
                        properties[name].update(items={'oneOf': [{"$ref": f"#/definitions/{def_name}"}]})
                    else:
                        properties[name].update(items={type_label: 'object'})
                        properties[name]['items'].update(required=req_props)
                        properties[name]['items'].update(properties=props)
            elif spec.get('type') == list and not spec.get('sub_type'):
                properties[name].update(items={type_label: 'string'})

            # Build required elements
            if spec.get('required', False):
                required_props.append(name)
            elif isinstance(properties[name].get(type_label), list):
                properties[name][type_label].append('null')

        return properties, required_props, definitions

    # -------------------------------------------------------------------
    # Parameter specification (UI metadata)
    # -------------------------------------------------------------------

    @classmethod
    def get_parameter_spec(cls, convert_types_to_string: bool = True) -> dict[str, Any]:
        result_dct: dict[str, Any] = {}
        for field_name, field_info in cls.model_fields.items():
            ann = cls.__annotations__.get(field_name)
            if ann is None:
                continue
            python_type, sub_type = extract_base_type(ann)
            if python_type is type(None):
                continue
            result_dct[field_name] = Model.__describe_field(
                cls, field_name, field_info, python_type, sub_type,
                convert_types_to_string=convert_types_to_string)
        return result_dct

    @classmethod
    def get_paramater_spec_as_json(cls) -> str:
        return json.dumps(cls.get_parameter_spec(), default=default_json_serializer, indent=4, sort_keys=True)

    @staticmethod
    def __describe_field(
        clazz: type, field_name: str, field_info: Any,
        python_type: type, sub_type: type | None,
        convert_types_to_string: bool = True
    ) -> dict[str, Any]:
        attr_desc: dict[str, Any] = {
            'type': python_type.__name__ if convert_types_to_string else python_type,
            'required': is_field_required(field_info),
        }
        label = lazy_gettext(f'{clazz.__name__}.{field_name}')
        if label:
            attr_desc.update(label=str(label))
        if python_type and inspect.isclass(python_type) and issubclass(python_type, Model):
            attr_desc.update(
                props=python_type.get_parameter_spec(convert_types_to_string=convert_types_to_string))
        default_meta = get_field_default(field_info)
        if default_meta is not None:
            attr_desc.update(default_value=default_meta)
        if sub_type:
            if inspect.isclass(sub_type) and issubclass(sub_type, Model):
                attr_desc.update(
                    sub_type={
                        'type': sub_type.__name__ if convert_types_to_string else sub_type,
                        'props': sub_type.get_parameter_spec(convert_types_to_string=convert_types_to_string)
                    })
            else:
                attr_desc.update(
                    sub_type=sub_type.__name__ if convert_types_to_string and hasattr(sub_type, '__name__') else sub_type)
        validators = get_field_validators_meta(field_info)
        if validators:
            attr_desc.update(
                validators=[Model.__describe_validator(val, convert_types_to_string=convert_types_to_string)
                            for val in validators])
        return attr_desc

    @staticmethod
    def __describe_validator(validator: Any, convert_types_to_string: bool = True) -> dict[str, Any]:
        def get_value(val: Any) -> Any:
            return val.__name__ if convert_types_to_string else val
        val_desc: dict[str, Any] = {
            'type': get_value(validator) if hasattr(validator, '__name__') else get_value(validator.__class__)
        }
        if hasattr(validator, 'value'):
            val_desc.update(value=validator.value)
        return val_desc

    # -------------------------------------------------------------------
    # Serialization: to_dict / from_dict / dumps / loads
    # -------------------------------------------------------------------

    @staticmethod
    def to_dict(
        instance: Model,
        convert_id: bool = False,
        validate: bool = True,
        skip_omitted_fields: bool = False,
        marshal_values: bool = True,
        converter_func: Callable | None = None,
    ) -> dict[str, Any]:
        if validate and isinstance(instance, Model):
            instance.finalise_and_validate()
        if not hasattr(instance, '__dict__') and not isinstance(instance, dict):
            return instance

        result: dict[str, Any] = {}

        # Get field metadata for this class
        cls_fields = instance.__class__.model_fields if hasattr(instance.__class__, 'model_fields') else {}

        # Collect instance data: Pydantic stores fields in __dict__ (or __pydantic_fields_set__)
        # We need both declared fields AND extra attributes
        instance_data = {}
        if isinstance(instance, BaseModel):
            # Get all set fields (declared + extra)
            for k, v in instance.__dict__.items():
                if not k.startswith('__') and not k.startswith('_'):
                    instance_data[k] = v
            # Also include extra fields from __pydantic_extra__
            extra = getattr(instance, '__pydantic_extra__', None)
            if extra:
                instance_data.update(extra)
        elif isinstance(instance, dict):
            instance_data = instance
        else:
            instance_data = {k: v for k, v in instance.__dict__.items()}

        for param, obj in instance_data.items():
            if skip_omitted_fields and param in cls_fields:
                field_info = cls_fields[param]
                if is_field_omitted(field_info):
                    continue

            if obj is None:
                continue

            if isinstance(obj, Model):
                result[param] = Model.to_dict(obj, convert_id, converter_func=converter_func)
            elif isinstance(obj, Enum):
                result[param] = obj.name
            elif isinstance(obj, list):
                result[param] = [Model.to_dict(item, convert_id, converter_func=converter_func)
                                 if isinstance(item, Model) else
                                 (item.name if isinstance(item, Enum) else item)
                                 for item in obj]
            else:
                # Apply marshaller if present
                marshaller = None
                if param in cls_fields:
                    marshaller = get_field_marshaller(cls_fields[param])
                if marshaller and marshal_values:
                    result_value = marshaller.to_wireformat(obj)
                else:
                    result_value = obj

                if convert_id and param == 'id':
                    result['_id'] = result_value
                else:
                    result_value = _xtract_custom_object_to_dict(result_value, converter_func=converter_func)
                    result[param] = result_value

        if hasattr(instance, '__module__'):
            result.update(_type=f'{instance.__module__}.{instance.__class__.__qualname__}')
        else:
            result.update(_type=f'{instance.__class__.__qualname__}')
        return result

    @staticmethod
    def from_dict(
        dict_obj: dict[str, Any],
        cls: type,
        convert_ids: bool = False,
        set_unmanaged_parameters: bool = True,
        converter_func: Callable | None = None,
    ) -> Model:
        instance = cls()
        cls_fields = cls.model_fields if hasattr(cls, 'model_fields') else {}
        processed_properties: set[str] = set()

        if dict_obj and isinstance(dict_obj, dict):
            for key, val in list(dict_obj.items()):
                if convert_ids and key == '_id':
                    key = 'id'
                processed_properties.add(key)

                if key in cls_fields:
                    field_info = cls_fields[key]
                    ann = cls.__annotations__.get(key)
                    python_type, sub_type = extract_base_type(ann) if ann else (None, None)

                    # Apply marshaller
                    marshaller = get_field_marshaller(field_info)
                    if marshaller:
                        val = marshaller.from_wire_format(val)

                    if python_type and inspect.isclass(python_type) and issubclass(python_type, Model):
                        setattr(instance, key, Model.from_dict(val, python_type, convert_ids=convert_ids,
                                                               converter_func=converter_func))
                    elif python_type == list:
                        setattr(instance, key, Model.from_list(val, sub_type, convert_ids=convert_ids,
                                                               converter_func=converter_func))
                    elif python_type and inspect.isclass(python_type) and issubclass(python_type, Enum):
                        setattr(instance, key, python_type[val])
                    elif isinstance(val, str) and python_type:
                        setattr(instance, key,
                                string_to_type_converters.get(python_type, default_convert)(val))
                    else:
                        setattr(instance, key,
                                Model.load_and_or_convert_object(val, converter_func=converter_func))

                elif (key == '_id' or key == 'id') and isinstance(val, (str, bytes)) and isinstance(val, str) and val.startswith(OBJ_PREFIX):
                    setattr(instance, key, ObjectId(val.split(OBJ_PREFIX)[1]))
                elif set_unmanaged_parameters:
                    setattr(instance, key, val)

            # Set unprocessed declared fields to None
            for field_name in cls_fields:
                if field_name not in processed_properties and getattr(instance, field_name, None) is None:
                    pass  # Already None from __init__

        return instance

    @staticmethod
    def load_and_or_convert_object(custom_value: Any, converter_func: Callable | None = None) -> Any:
        if custom_value and isinstance(custom_value, dict) and '_type' in custom_value:
            custom_class = _get_custom_class(custom_value.get('_type'))
            custom_value = _instantiate_custom_class(custom_class, custom_value, converter_func=converter_func)
        if converter_func and isinstance(converter_func, Callable):
            return converter_func(custom_value)
        else:
            return custom_value

    @staticmethod
    def from_list(
        list_obj: list[Any],
        item_cls: type | None,
        convert_ids: bool = False,
        converter_func: Callable | None = None,
    ) -> list[Any]:
        return_list: list[Any] = []
        if list_obj and not isinstance(list_obj, list):
            return_list.append(list_obj)
        elif list_obj:
            for item in list_obj:
                if item_cls and inspect.isclass(item_cls) and issubclass(item_cls, Model):
                    return_list.append(
                        Model.from_dict(item, item_cls, convert_ids=convert_ids, converter_func=converter_func))
                else:
                    return_list.append(item)
        return return_list

    def dumps(self, validate: bool = True, pretty_print: bool = False, json_serialiser_func: Callable | None = None) -> str:
        model_as_dict = Model.to_dict(self, validate=validate, skip_omitted_fields=True)
        default_serialiser_func = json_serialiser_func if json_serialiser_func and isinstance(json_serialiser_func,
                                                                                              Callable) else default_json_serializer
        return json.dumps(model_as_dict, default=default_serialiser_func, indent=4 if pretty_print else None,
                          sort_keys=True)

    @classmethod
    def loads(cls, json_string: str) -> Model:
        return Model.from_dict(json.loads(json_string), cls)

    # -------------------------------------------------------------------
    # Validation pipeline
    # -------------------------------------------------------------------

    def finalise_and_validate(self) -> None:
        """
        Runs generators, defaults, converters, and validators.
        Called before persistence (save/to_dict).
        """
        cls_fields = self.__class__.model_fields

        # Run custom validate() method if defined on the user's class (not BaseModel/Model)
        for klass in type(self).__mro__:
            if klass is Model or klass is BaseModel:
                break
            if 'validate' in klass.__dict__:
                klass.__dict__['validate'](self)
                break

        for field_name, field_info in cls_fields.items():
            current_value = getattr(self, field_name, None)

            # Apply defaults and generators for unset fields
            if current_value is None:
                default_val = get_field_default(field_info)
                if default_val is not None:
                    setattr(self, field_name, default_val)
                    current_value = default_val
                else:
                    generator = get_field_generator(field_info)
                    if generator:
                        generated = generator()
                        setattr(self, field_name, generated)
                        current_value = generated

            # Check required
            if is_field_required(field_info) and getattr(self, field_name, None) is None:
                raise PropertyRequiredException(
                    f'[{field_name}] on class [{self.__class__.__name__}]')

            # Apply converter
            converter = get_field_converter(field_info)
            if converter and getattr(self, field_name, None) is not None:
                setattr(self, field_name, converter(getattr(self, field_name)))

            # Run validators
            validators = get_field_validators_meta(field_info)
            for val in validators:
                self.__check_validity(val, field_name)

            # Recursively validate nested Models
            ann = self.__class__.__annotations__.get(field_name)
            if ann:
                python_type, sub_type = extract_base_type(ann)
                current_value = getattr(self, field_name, None)
                if python_type and inspect.isclass(python_type) and issubclass(python_type, Model) and current_value:
                    current_value.finalise_and_validate()
                elif python_type == list and current_value:
                    for item in current_value:
                        if isinstance(item, Model):
                            item.finalise_and_validate()

    def __check_validity(self, validator: Any, param_name: str) -> None:
        # Skip validation for fields that are None (not explicitly set)
        value = getattr(self, param_name, None)
        if value is None:
            return

        obj_items = self.__dict__
        extra = getattr(self, '__pydantic_extra__', None)
        if extra:
            obj_items = {**obj_items, **extra}

        if isinstance(validator, Validator):
            validator.validate_objects(param_name, obj_items)
        elif isinstance(validator, type) and issubclass(validator, Validator):
            validator().validate_objects(param_name, obj_items)

    def dump_spec(self) -> None:
        print(f"params: {list(self.__class__.model_fields.keys())}")
