"""
Unit tests for Model — all pure-Python, no MongoDB required.

Covers: update, append_to, remove_from, finalise_and_validate (generator /
default / converter / validator / required / nested recursion), to_dict,
from_dict, from_list, dumps/loads, get_parameter_spec, get_json_schema,
init_model, custom_property, __str__.
"""
import pytest
from enum import Enum
from typing import Annotated

from appkernel import Model
from appkernel.dsl import CustomProperty
from appkernel.fields import (
    Required, Generator, Converter, Default, Validators, Marshal,
    MongoIndex, MongoUniqueIndex,
)
from appkernel.generators import create_uuid_generator, TimestampMarshaller
from appkernel.model import PropertyRequiredException
from appkernel.validators import Min, Max, Email, NotEmpty, Regexp


# ---------------------------------------------------------------------------
# Minimal model fixtures
# ---------------------------------------------------------------------------

class SimpleModel(Model):
    name: str | None = None
    age: int | None = None


class Color(Enum):
    RED = 1
    BLUE = 2


class EnumModel(Model):
    color: Color | None = None
    label: str | None = None


class Address(Model):
    city: str | None = None
    zip: str | None = None


class PersonModel(Model):
    name: str | None = None
    address: Address | None = None
    tags: list | None = None


class ValidationModel(Model):
    id: Annotated[str | None, Generator(create_uuid_generator('U'))] = None
    name: Annotated[str | None, Required()] = None
    score: Annotated[int | None, Validators(Min(0), Max(100))] = None
    tag: Annotated[str | None, Default('default_tag')] = None
    secret: Annotated[str | None, Converter(str.upper)] = None


class NestedParent(Model):
    child: Address | None = None
    items: list | None = None


class SchemaModel(Model):
    name: Annotated[str | None, Required()] = None
    age: Annotated[int | None, Validators(Min(0), Max(150))] = None
    email: Annotated[str | None, Validators(Email())] = None
    count: Annotated[int | None, Validators(Max(999))] = None


# ---------------------------------------------------------------------------
# __init__ — deferred validation pattern
# ---------------------------------------------------------------------------

def test_model_init_all_fields_default_to_none():
    m = SimpleModel()
    assert m.name is None
    assert m.age is None


def test_model_init_with_kwargs():
    m = SimpleModel(name='Alice', age=30)
    assert m.name == 'Alice'
    assert m.age == 30


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------

def test_update_sets_single_field():
    m = SimpleModel()
    m.update(name='Bob')
    assert m.name == 'Bob'


def test_update_sets_multiple_fields():
    m = SimpleModel()
    m.update(name='Carol', age=25)
    assert m.name == 'Carol'
    assert m.age == 25


def test_update_is_chainable():
    m = SimpleModel()
    result = m.update(name='Dan').update(age=40)
    assert result is m
    assert m.name == 'Dan'
    assert m.age == 40


def test_update_overwrites_existing_value():
    m = SimpleModel(name='Old')
    m.update(name='New')
    assert m.name == 'New'


# ---------------------------------------------------------------------------
# append_to()
# ---------------------------------------------------------------------------

def test_append_to_initialises_list_when_none():
    m = PersonModel()
    m.append_to(tags='python')
    assert m.tags == ['python']


def test_append_to_appends_single_item():
    m = PersonModel(tags=['a'])
    m.append_to(tags='b')
    assert m.tags == ['a', 'b']


def test_append_to_extends_with_list():
    m = PersonModel(tags=['a'])
    m.append_to(tags=['b', 'c'])
    assert m.tags == ['a', 'b', 'c']


def test_append_to_is_chainable():
    m = PersonModel()
    result = m.append_to(tags='x')
    assert result is m


# ---------------------------------------------------------------------------
# remove_from()
# ---------------------------------------------------------------------------

def test_remove_from_removes_item():
    m = PersonModel(tags=['a', 'b', 'c'])
    m.remove_from(tags='b')
    assert m.tags == ['a', 'c']


def test_remove_from_non_list_raises_attribute_error():
    m = SimpleModel(name='Alice')
    with pytest.raises(AttributeError, match='not a list'):
        m.remove_from(name='Alice')


def test_remove_from_absent_field_raises_attribute_error():
    m = SimpleModel()
    with pytest.raises(AttributeError, match='missing'):
        m.remove_from(name='anything')


def test_remove_from_is_chainable():
    m = PersonModel(tags=['x', 'y'])
    result = m.remove_from(tags='x')
    assert result is m


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------

def test_str_contains_class_name():
    m = SimpleModel(name='Eve')
    assert 'SimpleModel' in str(m)


def test_str_contains_field_value():
    m = SimpleModel(name='Eve')
    assert 'Eve' in str(m)


# ---------------------------------------------------------------------------
# init_model() / custom_property()
# ---------------------------------------------------------------------------

def test_init_model_updates_instance():
    m = SimpleModel()
    Model.init_model(m, name='Frank', age=50)
    assert m.name == 'Frank'
    assert m.age == 50


def test_init_model_non_model_raises_type_error():
    with pytest.raises(TypeError):
        Model.init_model({'not': 'a model'}, name='x')


def test_custom_property_returns_custom_property():
    cp = SimpleModel.custom_property('name')
    assert isinstance(cp, CustomProperty)
    assert cp.backreference.parameter_name == 'name'


# ---------------------------------------------------------------------------
# finalise_and_validate() — generator
# ---------------------------------------------------------------------------

def test_finalise_generator_auto_populates_none_field():
    m = ValidationModel(name='Alice')
    m.finalise_and_validate()
    assert m.id is not None
    assert m.id.startswith('U')


def test_finalise_generator_does_not_overwrite_existing_value():
    m = ValidationModel(id='my-custom-id', name='Alice')
    m.finalise_and_validate()
    assert m.id == 'my-custom-id'


# ---------------------------------------------------------------------------
# finalise_and_validate() — default
# ---------------------------------------------------------------------------

def test_finalise_default_applied_when_none():
    m = ValidationModel(name='Alice')
    m.finalise_and_validate()
    assert m.tag == 'default_tag'


def test_finalise_default_not_applied_when_value_set():
    m = ValidationModel(name='Alice', tag='custom')
    m.finalise_and_validate()
    assert m.tag == 'custom'


# ---------------------------------------------------------------------------
# finalise_and_validate() — converter
# ---------------------------------------------------------------------------

def test_finalise_converter_transforms_value():
    m = ValidationModel(name='Alice', secret='hello')
    m.finalise_and_validate()
    assert m.secret == 'HELLO'


def test_finalise_converter_skipped_when_field_none():
    m = ValidationModel(name='Alice')
    m.finalise_and_validate()
    assert m.secret is None


# ---------------------------------------------------------------------------
# finalise_and_validate() — required
# ---------------------------------------------------------------------------

def test_finalise_required_field_missing_raises():
    m = ValidationModel()
    with pytest.raises(PropertyRequiredException):
        m.finalise_and_validate()


def test_finalise_required_field_present_does_not_raise():
    m = ValidationModel(name='Alice')
    m.finalise_and_validate()  # should not raise


# ---------------------------------------------------------------------------
# finalise_and_validate() — validators
# ---------------------------------------------------------------------------

def test_finalise_validator_passes_when_valid():
    m = ValidationModel(name='Alice', score=50)
    m.finalise_and_validate()  # no exception


def test_finalise_validator_raises_when_invalid():
    from appkernel.validators import ValidationException
    m = ValidationModel(name='Alice', score=-1)
    with pytest.raises(ValidationException):
        m.finalise_and_validate()


# ---------------------------------------------------------------------------
# finalise_and_validate() — nested recursion
# ---------------------------------------------------------------------------

def test_finalise_recurses_into_nested_model():
    """Nested Model with a Required field raises if that field is None."""
    class Inner(Model):
        value: Annotated[str | None, Required()] = None

    class Outer(Model):
        inner: Inner | None = None

    o = Outer(inner=Inner())
    with pytest.raises(PropertyRequiredException):
        o.finalise_and_validate()


def test_finalise_recurses_into_list_of_models():
    """Models inside a list field are also validated."""
    class Item(Model):
        value: Annotated[str | None, Required()] = None

    class Container(Model):
        items: list | None = None

    c = Container(items=[Item()])
    with pytest.raises(PropertyRequiredException):
        c.finalise_and_validate()


# ---------------------------------------------------------------------------
# to_dict()
# ---------------------------------------------------------------------------

def test_to_dict_basic_fields():
    m = SimpleModel(name='Grace', age=28)
    d = Model.to_dict(m, validate=False)
    assert d['name'] == 'Grace'
    assert d['age'] == 28


def test_to_dict_omits_none_values():
    m = SimpleModel(name='Henry')
    d = Model.to_dict(m, validate=False)
    assert 'age' not in d


def test_to_dict_serialises_enum_as_name():
    m = EnumModel(color=Color.BLUE)
    d = Model.to_dict(m, validate=False)
    assert d['color'] == 'BLUE'


def test_to_dict_recurses_into_nested_model():
    m = PersonModel(name='Iris', address=Address(city='Budapest', zip='1052'))
    d = Model.to_dict(m, validate=False)
    assert d['address']['city'] == 'Budapest'


def test_to_dict_serialises_list():
    m = PersonModel(tags=['a', 'b'])
    d = Model.to_dict(m, validate=False)
    assert d['tags'] == ['a', 'b']


def test_to_dict_includes_type_key():
    m = SimpleModel(name='Jack')
    d = Model.to_dict(m, validate=False)
    assert '_type' in d


def test_to_dict_convert_id_renames_to_underscore_id():
    class IdModel(Model):
        id: str | None = None

    m = IdModel(id='abc123')
    d = Model.to_dict(m, validate=False, convert_id=True)
    assert '_id' in d
    assert 'id' not in d


def test_to_dict_skip_omitted_fields():
    from pydantic import Field

    class OmitModel(Model):
        visible: str | None = None
        hidden: str | None = Field(default=None, exclude=True)

    m = OmitModel(visible='yes', hidden='secret')
    d = Model.to_dict(m, validate=False, skip_omitted_fields=True)
    assert 'visible' in d
    assert 'hidden' not in d


def test_to_dict_applies_marshaller():
    import datetime
    from appkernel.fields import Marshal
    from appkernel.generators import TimestampMarshaller

    class TsModel(Model):
        created: Annotated[float | None, Marshal(TimestampMarshaller)] = None

    m = TsModel(created=1000.0)
    d = Model.to_dict(m, validate=False, marshal_values=True)
    # TimestampMarshaller.to_wireformat converts float → datetime string
    assert 'created' in d


# ---------------------------------------------------------------------------
# from_dict()
# ---------------------------------------------------------------------------

def test_from_dict_basic_fields():
    m = Model.from_dict({'name': 'Kate', 'age': 33}, SimpleModel)
    assert m.name == 'Kate'
    assert m.age == 33


def test_from_dict_enum_field():
    m = Model.from_dict({'color': 'RED'}, EnumModel)
    assert m.color == Color.RED


def test_from_dict_nested_model_field():
    m = Model.from_dict({'name': 'Leo', 'address': {'city': 'Vienna', 'zip': '1010'}}, PersonModel)
    assert isinstance(m.address, Address)
    assert m.address.city == 'Vienna'


def test_from_dict_unmanaged_params_set_by_default():
    m = Model.from_dict({'name': 'Mia', 'extra_field': 'bonus'}, SimpleModel)
    assert m.name == 'Mia'
    assert getattr(m, 'extra_field', None) == 'bonus'


def test_from_dict_convert_ids_renames_underscore_id():
    class IdModel(Model):
        id: str | None = None

    m = Model.from_dict({'_id': 'abc123'}, IdModel, convert_ids=True)
    assert m.id == 'abc123'


def test_from_dict_empty_dict_returns_empty_instance():
    m = Model.from_dict({}, SimpleModel)
    assert isinstance(m, SimpleModel)
    assert m.name is None


# ---------------------------------------------------------------------------
# from_list()
# ---------------------------------------------------------------------------

def test_from_list_empty_returns_empty_list():
    result = Model.from_list([], SimpleModel)
    assert result == []


def test_from_list_with_model_items():
    result = Model.from_list([{'name': 'Nina'}, {'name': 'Owen'}], SimpleModel)
    assert len(result) == 2
    assert all(isinstance(r, SimpleModel) for r in result)
    assert result[0].name == 'Nina'


def test_from_list_with_primitive_items():
    result = Model.from_list([1, 2, 3], None)
    assert result == [1, 2, 3]


def test_from_list_non_list_input_wrapped():
    result = Model.from_list('single', None)
    assert result == ['single']


# ---------------------------------------------------------------------------
# dumps() / loads()
# ---------------------------------------------------------------------------

def test_dumps_returns_json_string():
    m = SimpleModel(name='Pete')
    json_str = Model.to_dict(m, validate=False)
    assert isinstance(json_str, dict)


def test_dumps_loads_roundtrip():
    m = SimpleModel(name='Quinn', age=22)
    json_str = m.dumps(validate=False)
    restored = SimpleModel.loads(json_str)
    assert restored.name == 'Quinn'
    assert restored.age == 22


def test_dumps_pretty_print_produces_indented_output():
    m = SimpleModel(name='Rose')
    pretty = m.dumps(validate=False, pretty_print=True)
    assert '\n' in pretty


# ---------------------------------------------------------------------------
# get_parameter_spec()
# ---------------------------------------------------------------------------

def test_get_parameter_spec_includes_all_fields():
    spec = SchemaModel.get_parameter_spec()
    assert 'name' in spec
    assert 'age' in spec
    assert 'email' in spec


def test_get_parameter_spec_marks_required_field():
    spec = SchemaModel.get_parameter_spec()
    assert spec['name']['required'] is True
    assert spec['age']['required'] is False


def test_get_parameter_spec_includes_validators():
    spec = SchemaModel.get_parameter_spec()
    assert 'validators' in spec['age']
    validator_types = [v['type'] for v in spec['age']['validators']]
    assert 'Min' in validator_types


def test_get_parameter_spec_as_json_returns_string():
    result = SchemaModel.get_paramater_spec_as_json()
    assert isinstance(result, str)
    assert 'name' in result


# ---------------------------------------------------------------------------
# get_json_schema()
# ---------------------------------------------------------------------------

def test_get_json_schema_returns_valid_structure():
    schema = SchemaModel.get_json_schema()
    assert schema['type'] == 'object'
    assert 'properties' in schema
    assert 'required' in schema


def test_get_json_schema_required_array_contains_required_field():
    schema = SchemaModel.get_json_schema()
    assert 'name' in schema['required']
    assert 'age' not in schema['required']


def test_get_json_schema_min_validator_sets_minimum():
    schema = SchemaModel.get_json_schema()
    assert schema['properties']['age'].get('minimum') == 0


def test_get_json_schema_max_validator_sets_maximum():
    schema = SchemaModel.get_json_schema()
    assert schema['properties']['age'].get('maximum') == 150


def test_get_json_schema_email_validator_sets_format():
    schema = SchemaModel.get_json_schema()
    assert schema['properties']['email'].get('format') == 'email'


def test_get_json_schema_mongo_compatibility():
    schema = SchemaModel.get_json_schema(mongo_compatibility=True)
    assert 'bsonType' in schema
    assert '$schema' not in schema


def test_get_json_schema_no_additional_properties():
    schema = SchemaModel.get_json_schema(additional_properties=False)
    assert 'additionalProperties' not in schema


# ---------------------------------------------------------------------------
# from_dict — datetime string conversion (covers convert_date_time)
# ---------------------------------------------------------------------------

def test_from_dict_converts_datetime_string():
    from datetime import datetime

    class EventModel(Model):
        started: datetime | None = None

    m = Model.from_dict({'started': '2024-03-15T10:30:00.123456'}, EventModel)
    assert isinstance(m.started, datetime)
    assert m.started.year == 2024


# ---------------------------------------------------------------------------
# to_dict — list containing Enum items (covers lines 463-467)
# ---------------------------------------------------------------------------

def test_to_dict_list_of_enum_values_serialised_as_names():
    from enum import Enum

    class Status(Enum):
        ACTIVE = 1
        INACTIVE = 2

    class ListEnumModel(Model):
        statuses: list | None = None

    m = ListEnumModel(statuses=[Status.ACTIVE, Status.INACTIVE])
    d = Model.to_dict(m, validate=False)
    assert d['statuses'] == ['ACTIVE', 'INACTIVE']


# ---------------------------------------------------------------------------
# finalise_and_validate — validator passed as class (not instance)
# ---------------------------------------------------------------------------

def test_finalise_validator_as_class_is_instantiated():
    """Passing the validator *class* (not an instance) in Validators() still works."""
    from appkernel.validators import ValidationException

    class MinModel(Model):
        value: Annotated[int | None, Validators(Min)] = None  # class, not instance

    m = MinModel(value=5)
    # Min() with no args raises TypeError during instantiation, which propagates
    with pytest.raises(TypeError):
        m.finalise_and_validate()


# ---------------------------------------------------------------------------
# dump_spec (covers line 683)
# ---------------------------------------------------------------------------

def test_dump_spec_prints_without_error(capsys):
    m = SimpleModel(name='Test')
    m.dump_spec()
    captured = capsys.readouterr()
    assert 'name' in captured.out


# ---------------------------------------------------------------------------
# get_json_schema — null type appended for optional fields
# ---------------------------------------------------------------------------

def test_get_json_schema_optional_field_includes_null_type():
    schema = SchemaModel.get_json_schema()
    # 'age' is not required, so its type list should include 'null'
    age_types = schema['properties']['age'].get('type', [])
    assert 'null' in age_types
