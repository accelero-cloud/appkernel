"""
Unit tests for appkernel/fields.py — field metadata introspection helpers,
extract_base_type, FieldProxy DSL methods, and AppKernelMeta.__getattr__.

No MongoDB required. All tests operate on pure Python type annotations and
Model subclasses defined inline.
"""
import pytest
from typing import Annotated, Optional

from appkernel import Model
from appkernel.dsl import OPS, Expression
from appkernel.fields import (
    AppKernelMeta,
    Converter,
    Default,
    FieldProxy,
    Generator,
    Marshal,
    MongoIndex,
    MongoTextIndex,
    MongoUniqueIndex,
    Required,
    Validators,
    extract_base_type,
    get_all_field_meta,
    get_field_converter,
    get_field_default,
    get_field_generator,
    get_field_index,
    get_field_marshaller,
    get_field_meta,
    get_field_validators_meta,
    has_field_default,
    is_field_omitted,
    is_field_required,
)
from appkernel.generators import TimestampMarshaller
from appkernel.validators import Min, Max


# ---------------------------------------------------------------------------
# Fixture model with one field per metadata type
# ---------------------------------------------------------------------------

class _AllMarkersModel(Model):
    required_field: Annotated[str | None, Required()] = None
    generated_field: Annotated[str | None, Generator(lambda: 'gen')] = None
    converted_field: Annotated[str | None, Converter(str.upper)] = None
    defaulted_field: Annotated[str | None, Default('def_value')] = None
    validated_field: Annotated[int | None, Validators(Min(0), Max(100))] = None
    marshalled_field: Annotated[float | None, Marshal(TimestampMarshaller)] = None
    indexed_field: Annotated[str | None, MongoIndex()] = None
    unique_field: Annotated[str | None, MongoUniqueIndex()] = None
    text_field: Annotated[str | None, MongoTextIndex()] = None
    plain_field: str | None = None


def _fi(name: str):
    """Shorthand to retrieve a FieldInfo from _AllMarkersModel."""
    return _AllMarkersModel.model_fields[name]


# ---------------------------------------------------------------------------
# get_field_meta / get_all_field_meta
# ---------------------------------------------------------------------------

def test_get_field_meta_returns_first_matching_marker():
    m = get_field_meta(_fi('required_field'), Required)
    assert isinstance(m, Required)


def test_get_field_meta_returns_none_when_absent():
    m = get_field_meta(_fi('plain_field'), Required)
    assert m is None


def test_get_all_field_meta_returns_all_matching():
    all_m = get_all_field_meta(_fi('validated_field'), Validators)
    assert len(all_m) == 1
    assert isinstance(all_m[0], Validators)


def test_get_all_field_meta_empty_when_absent():
    all_m = get_all_field_meta(_fi('plain_field'), Required)
    assert all_m == []


# ---------------------------------------------------------------------------
# get_field_index
# ---------------------------------------------------------------------------

def test_get_field_index_returns_mongo_index():
    idx = get_field_index(_fi('indexed_field'))
    assert isinstance(idx, MongoIndex)


def test_get_field_index_returns_unique_index_subclass():
    idx = get_field_index(_fi('unique_field'))
    assert isinstance(idx, MongoUniqueIndex)


def test_get_field_index_returns_text_index_subclass():
    idx = get_field_index(_fi('text_field'))
    assert isinstance(idx, MongoTextIndex)


def test_get_field_index_returns_none_when_absent():
    assert get_field_index(_fi('plain_field')) is None


# ---------------------------------------------------------------------------
# is_field_required / is_field_omitted
# ---------------------------------------------------------------------------

def test_is_field_required_true_for_required_marker():
    assert is_field_required(_fi('required_field')) is True


def test_is_field_required_false_when_absent():
    assert is_field_required(_fi('plain_field')) is False


def test_is_field_omitted_false_by_default():
    assert is_field_omitted(_fi('plain_field')) is False


def test_is_field_omitted_true_when_excluded():
    from pydantic import Field

    class OmitModel(Model):
        hidden: str | None = Field(default=None, exclude=True)

    assert is_field_omitted(OmitModel.model_fields['hidden']) is True


# ---------------------------------------------------------------------------
# get_field_generator / get_field_converter / get_field_default / has_field_default
# ---------------------------------------------------------------------------

def test_get_field_generator_returns_callable():
    gen = get_field_generator(_fi('generated_field'))
    assert callable(gen)
    assert gen() == 'gen'


def test_get_field_generator_returns_none_when_absent():
    assert get_field_generator(_fi('plain_field')) is None


def test_get_field_converter_returns_callable():
    conv = get_field_converter(_fi('converted_field'))
    assert callable(conv)
    assert conv('hello') == 'HELLO'


def test_get_field_converter_returns_none_when_absent():
    assert get_field_converter(_fi('plain_field')) is None


def test_get_field_default_returns_default_value():
    default = get_field_default(_fi('defaulted_field'))
    assert default == 'def_value'


def test_get_field_default_returns_none_when_absent():
    assert get_field_default(_fi('plain_field')) is None


def test_has_field_default_true_when_present():
    assert has_field_default(_fi('defaulted_field')) is True


def test_has_field_default_false_when_absent():
    assert has_field_default(_fi('plain_field')) is False


# ---------------------------------------------------------------------------
# get_field_validators_meta
# ---------------------------------------------------------------------------

def test_get_field_validators_meta_returns_validator_list():
    validators = get_field_validators_meta(_fi('validated_field'))
    assert len(validators) == 2
    assert any(isinstance(v, Min) for v in validators)
    assert any(isinstance(v, Max) for v in validators)


def test_get_field_validators_meta_returns_empty_when_absent():
    assert get_field_validators_meta(_fi('plain_field')) == []


# ---------------------------------------------------------------------------
# get_field_marshaller
# ---------------------------------------------------------------------------

def test_get_field_marshaller_instantiates_from_class():
    m = get_field_marshaller(_fi('marshalled_field'))
    assert isinstance(m, TimestampMarshaller)


def test_get_field_marshaller_returns_same_instance_when_given_instance():
    instance = TimestampMarshaller()

    class InstanceMarshalModel(Model):
        ts: Annotated[float | None, Marshal(instance)] = None

    m = get_field_marshaller(InstanceMarshalModel.model_fields['ts'])
    assert m is instance


def test_get_field_marshaller_returns_none_when_absent():
    assert get_field_marshaller(_fi('plain_field')) is None


def test_get_field_marshaller_returns_none_for_non_marshaller_value():
    """Marshal with a non-Marshaller value returns None gracefully."""

    class BadMarshalModel(Model):
        field: Annotated[str | None, Marshal('not-a-marshaller')] = None

    result = get_field_marshaller(BadMarshalModel.model_fields['field'])
    assert result is None


# ---------------------------------------------------------------------------
# extract_base_type
# ---------------------------------------------------------------------------

def test_extract_base_type_plain_str():
    assert extract_base_type(str) == (str, None)


def test_extract_base_type_plain_list():
    assert extract_base_type(list) == (list, None)


def test_extract_base_type_optional_str():
    assert extract_base_type(str | None) == (str, None)


def test_extract_base_type_optional_int():
    assert extract_base_type(int | None) == (int, None)


def test_extract_base_type_list_with_subtype():
    base, sub = extract_base_type(list[str] | None)
    assert base is list
    assert sub is str


def test_extract_base_type_list_with_model_subtype():
    class Inner(Model):
        pass

    base, sub = extract_base_type(list[Inner] | None)
    assert base is list
    assert sub is Inner


def test_extract_base_type_bare_list_no_subtype():
    base, sub = extract_base_type(list[str])
    assert base is list
    assert sub is str


def test_extract_base_type_all_none_union():
    base, sub = extract_base_type(type(None))
    assert base is type(None)


def test_extract_base_type_annotated_unwraps():
    from typing import Annotated

    base, sub = extract_base_type(Annotated[str | None, Required()])
    assert base is str
    assert sub is None


# ---------------------------------------------------------------------------
# FieldProxy — asc / desc
# ---------------------------------------------------------------------------

class _SortModel(Model):
    name: str | None = None
    score: int | None = None


def test_field_proxy_asc_returns_ascending_tuple():
    assert _SortModel.name.asc() == ('name', 1)


def test_field_proxy_desc_returns_descending_tuple():
    assert _SortModel.score.desc() == ('score', -1)


# ---------------------------------------------------------------------------
# FieldProxy.__getattr__ — nested Model field (dot-path)
# ---------------------------------------------------------------------------

class _City(Model):
    name: str | None = None
    zip: str | None = None


class _PersonWithAddress(Model):
    address: _City | None = None


def test_field_proxy_nested_model_field_returns_proxy():
    proxy = _PersonWithAddress.address.name
    assert isinstance(proxy, FieldProxy)


def test_field_proxy_nested_model_builds_dot_path():
    proxy = _PersonWithAddress.address.name
    assert proxy.backreference.parameter_name == 'address.name'


def test_field_proxy_nested_model_nonexistent_attribute_raises():
    with pytest.raises(AttributeError):
        _ = _PersonWithAddress.address.nonexistent


# ---------------------------------------------------------------------------
# FieldProxy.__getattr__ — list[Model] field (within_an_array)
# ---------------------------------------------------------------------------

class _Item(Model):
    value: str | None = None


class _Container(Model):
    items: list[_Item] | None = None


def test_field_proxy_list_model_returns_proxy_with_array_flag():
    proxy = _Container.items.value
    assert proxy.backreference.within_an_array is True


def test_field_proxy_list_model_records_array_parameter_name():
    proxy = _Container.items.value
    assert proxy.backreference.array_parameter_name == 'items'


# ---------------------------------------------------------------------------
# FieldProxy.__getitem__ — elem-match
# ---------------------------------------------------------------------------

def test_field_proxy_getitem_changes_eq_to_elem_match():
    expr = _Container.items[_Item.value == 'x']
    assert isinstance(expr, Expression)
    assert expr.ops == OPS.ELEM_MATCH


def test_field_proxy_getitem_wrong_subtype_raises_type_error():
    class _Other(Model):
        x: str | None = None

    with pytest.raises(TypeError):
        _ = _Container.items[_Other.x == 'y']


# ---------------------------------------------------------------------------
# AppKernelMeta.__getattr__ — non-existent field raises AttributeError
# ---------------------------------------------------------------------------

def test_appkernelmeta_getattr_nonexistent_raises():
    with pytest.raises(AttributeError):
        _ = _SortModel.nonexistent_field


# ---------------------------------------------------------------------------
# Validators — hash and equality (used as metadata markers)
# ---------------------------------------------------------------------------

def test_validators_hash_is_id():
    v = Validators(Min(0))
    assert hash(v) == id(v)


def test_validators_equality_is_identity():
    v1 = Validators(Min(0))
    v2 = Validators(Min(0))
    assert v1 != v2
    assert v1 == v1
