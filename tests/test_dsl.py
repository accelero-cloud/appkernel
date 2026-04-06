"""Tests for DSL primitives: AttrDict, Opex, Expression, Marshaller, legacy Index types."""
import pytest
from typing import Annotated

from appkernel import Model
from appkernel.dsl import (
    AttrDict,
    CustomProperty,
    Expression,
    Index,
    Marshaller,
    OPS,
    Opex,
    SortOrder,
    TextIndex,
    UniqueIndex,
)
from appkernel.fields import FieldProxy


# ---------------------------------------------------------------------------
# AttrDict
# ---------------------------------------------------------------------------

def test_attrdict_attribute_access():
    d = AttrDict(name='alice', age=30)
    assert d.name == 'alice'
    assert d.age == 30


def test_attrdict_missing_key_raises_attribute_error():
    d = AttrDict(a=1)
    with pytest.raises(AttributeError):
        _ = d.nonexistent


# ---------------------------------------------------------------------------
# Opex
# ---------------------------------------------------------------------------

def test_opex_str():
    op = Opex('$eq', lambda x: {'$eq': x})
    assert str(op) == '$eq'


def test_opex_repr_matches_str():
    op = Opex('$gt', lambda x: {'$gt': x})
    assert repr(op) == str(op)


def test_opex_lambda():
    op = OPS.EQ
    result = op.lmbda(42)
    assert result == {'$eq': 42}


# ---------------------------------------------------------------------------
# Marshaller
# ---------------------------------------------------------------------------

def test_marshaller_direct_instantiation_raises():
    with pytest.raises(TypeError, match='base Marshaller class may not be instantiated'):
        Marshaller()


def test_marshaller_subclass_can_be_instantiated():
    class ConcreteMarshaller(Marshaller):
        def to_wireformat(self, value):
            return str(value)

        def from_wire_format(self, value):
            return int(value)

    m = ConcreteMarshaller()
    assert m.to_wireformat(42) == '42'
    assert m.from_wire_format('99') == 99


def test_marshaller_base_methods_return_none():
    class MinimalMarshaller(Marshaller):
        def to_wireformat(self, v):
            return super().to_wireformat(v)

        def from_wire_format(self, v):
            return super().from_wire_format(v)

    m = MinimalMarshaller()
    assert m.to_wireformat('x') is None
    assert m.from_wire_format('x') is None


# ---------------------------------------------------------------------------
# Legacy Index constructors
# ---------------------------------------------------------------------------

def test_index_default_sort_order():
    idx = Index()
    assert idx.sort_order == SortOrder.ASC


def test_index_custom_sort_order():
    idx = Index(SortOrder.DESC)
    assert idx.sort_order == SortOrder.DESC


def test_text_index_sort_order():
    idx = TextIndex()
    assert idx.sort_order == SortOrder.ASC


def test_unique_index_sort_order():
    idx = UniqueIndex()
    assert idx.sort_order == SortOrder.ASC


# ---------------------------------------------------------------------------
# Expression.get_lhs_param_name
# ---------------------------------------------------------------------------

class _AgeModel(Model):
    age: int | None = None
    name: str | None = None


def test_expression_get_lhs_param_name_simple():
    expr = _AgeModel.age > 5
    assert expr.get_lhs_param_name() == 'age'


def test_expression_get_lhs_param_name_nested():
    # compound expression: (age > 5) & (name == 'x') — lhs is another Expression
    compound = (_AgeModel.age > 5) & (_AgeModel.name == 'x')
    # get_lhs_param_name walks the left spine to find the field proxy
    assert compound.get_lhs_param_name() == 'age'


# ---------------------------------------------------------------------------
# CustomProperty
# ---------------------------------------------------------------------------

def test_custom_property_backreference():
    cp = CustomProperty(Model, 'version')
    assert cp.backreference.parameter_name == 'version'
    assert cp.backreference.class_name == 'Model'


def test_custom_property_equality_expression():
    cp = CustomProperty(Model, 'version')
    expr = cp == 2
    assert isinstance(expr, Expression)


# ---------------------------------------------------------------------------
# DslBase.contains (references Expression.OPS.ILIKE which is not defined —
# this method is a stub; the test documents its current broken state)
# ---------------------------------------------------------------------------

def test_dslbase_contains_raises_on_missing_ops():
    # contains() references Expression.OPS.ILIKE which does not exist.
    # This documents the current behaviour so any future fix is visible.
    with pytest.raises(AttributeError):
        _AgeModel.name.contains('test')


# ---------------------------------------------------------------------------
# DslBase.__hash__
# ---------------------------------------------------------------------------

def test_field_proxy_is_hashable():
    proxy = _AgeModel.name
    assert hash(proxy) == id(proxy)


def test_field_proxy_usable_as_dict_key():
    proxy = _AgeModel.age
    d = {proxy: 'value'}
    assert d[proxy] == 'value'


# ---------------------------------------------------------------------------
# ReDoS: regex special characters must be escaped in LIKE / ELEM_LIKE / ~
# ---------------------------------------------------------------------------

def test_like_escapes_regex_special_characters():
    """User input containing regex metacharacters must be escaped so it is
    treated as a literal string, not a regex pattern."""
    expr = _AgeModel.name % '(a+)+'
    fragment = expr.ops.lmbda(expr.rhs)
    # The pattern must NOT contain an unescaped (a+)+
    assert '(a+)+' not in fragment['$regex']
    # It must contain the escaped form
    import re
    assert re.escape('(a+)+') in fragment['$regex']


def test_like_escapes_dot_and_star():
    expr = _AgeModel.name % 'file.name*'
    fragment = expr.ops.lmbda(expr.rhs)
    import re
    assert re.escape('file.name*') in fragment['$regex']


def test_like_plain_string_still_matches_substring():
    """After escaping, a plain alphanumeric search string must still appear
    verbatim in the pattern (re.escape leaves it unchanged)."""
    expr = _AgeModel.name % 'John'
    fragment = expr.ops.lmbda(expr.rhs)
    assert 'John' in fragment['$regex']


def test_query_processor_tilde_escapes_regex_special_characters():
    """The ~ operator in the QueryProcessor expression_mapper must also escape."""
    from appkernel.query import QueryProcessor
    qp = QueryProcessor()
    mapper = qp.expression_mapper['~']
    fragment = mapper('(a+)+')
    import re
    assert '(a+)+' not in fragment['$regex']
    assert re.escape('(a+)+') in fragment['$regex']


def test_elem_like_escapes_regex_special_characters():
    """ELEM_LIKE (array element contains) must escape the search term."""
    from appkernel.dsl import OPS
    fragment = OPS.ELEM_LIKE.lmbda(('field', '(a+)+'))
    import re
    inner_regex = fragment['$elemMatch']['field']['$regex']
    assert '(a+)+' not in inner_regex
    assert re.escape('(a+)+') in inner_regex
