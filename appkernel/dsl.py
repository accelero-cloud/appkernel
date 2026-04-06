"""
Query DSL primitives: operator overloading for building MongoDB query expressions.

This module contains the foundation types used by the query DSL. It has NO dependencies
on other appkernel modules, breaking the circular dependency chain.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from enum import IntEnum
from typing import Any


class AttrDict(dict):
    """Dictionary subclass that exposes keys as attributes."""

    def __getattr__(self, attr: str) -> Any:
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)


class Opex:
    """Operator expression: pairs a MongoDB operator name with a lambda that
    produces the corresponding query fragment."""

    def __init__(self, name: str | None = None, lmbda: Callable | None = None) -> None:
        self.name = name
        self.lmbda = lmbda

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return self.__str__()


OPS = AttrDict(
    AND=Opex('$and', lambda exp: {'$and': exp}),
    EQ=Opex('$eq', lambda exp: {'$eq': exp}),
    OR=Opex('$or', lambda exp: {'$or': exp}),
    GT=Opex('$gt', lambda exp: {'$gt': exp}),
    GTE=Opex('$gte', lambda exp: {'$gte': exp}),
    LT=Opex('$lt', lambda exp: {'$lt': exp}),
    LTE=Opex('$lte', lambda exp: {'$lte': exp}),
    IS=Opex('$eq', lambda exp: {'$eq': exp}),
    IS_NOT=Opex('is_not', lambda exp: {'$ne': exp}),
    LIKE=Opex('like', lambda exp: {'$regex': f'.*{exp}.*', '$options': 'i'}),
    ELEM_MATCH=Opex('$elemMatch', lambda exp: {'$elemMatch': {exp[0]: exp[1]}}),
    ELEM_DOES_NOT_MATCH=Opex('$elemMatchNot', lambda exp: {'$not': {'$elemMatch': {exp[0]: exp[1]}}}),
    ELEM_LIKE=Opex('$elemMatch',
                   lambda exp: {'$elemMatch': {exp[0]: {'$regex': f'.*{exp[1]}.*', '$options': 'i'}}}),
    NE=Opex('$ne', lambda exp: {'$ne': exp}),
    MUL=Opex('$mul', lambda exp: exp),
    DIV=Opex('$mul', lambda exp: 1 / exp),
    ADD=Opex('$inc', lambda exp: exp),
    SUB=Opex('$inc', lambda exp: -exp),
)


class DslBase:
    """Base class providing operator overloading for the MongoDB query DSL.

    Subclasses (FieldProxy, CustomProperty, Expression) inherit these operators
    to build lazy expression trees that are translated to MongoDB syntax at
    query time. Supported operators: ``==``, ``!=``, ``<``, ``>``, ``<=``,
    ``>=``, ``%`` (regex/contains), ``&`` (AND), ``|`` (OR), ``+``, ``-``,
    ``*``, ``/`` (atomic updates).
    """

    def __eq__(self, right_hand_side: Any) -> Expression:
        if self.backreference.within_an_array:
            return Expression(self, OPS.ELEM_MATCH, right_hand_side)
        if right_hand_side is None:
            return Expression(self, OPS.IS, None)
        return Expression(self, OPS.EQ, right_hand_side)

    def __ne__(self, right_hand_side: Any) -> Expression:
        if self.backreference.within_an_array:
            return Expression(self, OPS.ELEM_DOES_NOT_MATCH, right_hand_side)
        if right_hand_side is None:
            return Expression(self, OPS.IS_NOT, None)
        return Expression(self, OPS.NE, right_hand_side)

    def __mod__(self, right_hand_side: Any) -> Expression:
        if self.backreference.within_an_array:
            return Expression(self, OPS.ELEM_LIKE, right_hand_side)
        return Expression(self, OPS.LIKE, right_hand_side)

    def __create_expression(ops: Any, inv: bool = False) -> Callable:
        """Return a method that builds an Expression from the left-hand and
        right-hand operands using the given ``OPS`` entry."""

        def inner(self: Any, rhs: Any) -> Expression:
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
    __mul__ = __create_expression(OPS.MUL)
    __div__ = __truediv__ = __create_expression(OPS.DIV)
    __add__ = __create_expression(OPS.ADD)
    __sub__ = __create_expression(OPS.SUB)

    def contains(self, rhs: Any) -> Expression:
        return Expression(self, Expression.OPS.ILIKE, '%%%s%%' % rhs)

    def __hash__(self):
        return id(self)


class BackReference:
    """Links a DSL node back to the class and field it originates from.

    Attributes:
        class_name: name of the Model class owning this field.
        parameter_name: field name (or dot-path for nested access).
        within_an_array: True when the field is accessed inside a list sub-type.
        array_parameter_name: name of the enclosing list field, if any.
    """

    def __init__(self, class_name: str, parameter_name: str) -> None:
        self.class_name = class_name
        self.parameter_name = parameter_name
        self.within_an_array = False
        self.array_parameter_name: str | None = None


class Expression(DslBase):
    """A binary expression node (e.g. ``User.age > 30``, ``expr1 & expr2``).

    Expressions compose into trees via ``&`` (AND) and ``|`` (OR). The tree
    is converted to a MongoDB query dict lazily in ``MongoQuery.__prep_expressions()``.
    """

    def __init__(self, lhs: Any, ops: Any, rhs: Any) -> None:
        self.lhs = lhs
        self.ops = ops
        self.rhs = rhs

    def get_lhs_param_name(self) -> str:
        """Walk the left spine of the expression tree and return the field name."""
        def get_field_proxy(plhs: Any) -> Any:
            if hasattr(plhs, 'backreference'):
                return plhs
            return get_field_proxy(plhs.lhs)
        return get_field_proxy(self.lhs).backreference.parameter_name


class CustomProperty(DslBase):
    """Query proxy for fields not declared on the Model.

    Use ``Model.custom_property('version')`` to query ad-hoc or unmanaged
    fields that are not part of the Pydantic schema.
    """

    def __init__(self, cls: type, property_name: str) -> None:
        self.backreference = BackReference(class_name=cls.__name__, parameter_name=property_name)


class SortOrder(IntEnum):
    ASC = 1
    DESC = -1


class Marshaller:
    """Abstract base for bidirectional wire-format converters.

    Subclasses implement ``to_wireformat()`` and ``from_wire_format()`` to
    translate between the in-memory representation and the serialised form
    (e.g. ``TimestampMarshaller`` converts datetime to/from Unix timestamps).
    Cannot be instantiated directly.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> Marshaller:
        if cls is Marshaller:
            raise TypeError("the base Marshaller class may not be instantiated")
        return object.__new__(cls, *args, **kwargs)

    def to_wireformat(self, instance_value: Any) -> Any:
        """Convert an in-memory value to its wire-format representation."""
        pass

    def from_wire_format(self, wire_value: Any) -> Any:
        """Convert a wire-format value back to its in-memory representation."""
        pass


class Index:
    """Legacy index descriptor. Prefer ``MongoIndex`` in ``Annotated[]`` metadata for new code."""

    def __init__(self, sort_order: SortOrder = SortOrder.ASC) -> None:
        self.sort_order = sort_order


class TextIndex(Index):
    """Legacy full-text search index. Prefer ``MongoTextIndex`` for new code."""

    def __init__(self) -> None:
        super().__init__(SortOrder.ASC)


class UniqueIndex(Index):
    """Legacy unique-constraint index. Prefer ``MongoUniqueIndex`` for new code."""

    def __init__(self) -> None:
        super().__init__(SortOrder.ASC)


def get_argument_spec(provisioner_method: Callable) -> dict[str, Any]:
    """Return a method's parameter names mapped to their default values.

    Args:
        provisioner_method: a method or function to inspect.

    Returns:
        Dictionary with parameter names as keys and default values (or None) as values.
        ``cls`` and ``self`` parameters are excluded.
    """
    assert inspect.ismethod(provisioner_method) or inspect.isfunction(
        provisioner_method), f'The provisioner {str(provisioner_method)} method must be a method or function'
    args = [name for name in getattr(inspect.getfullargspec(provisioner_method), 'args') if name not in ['cls', 'self']]
    defaults = getattr(inspect.getfullargspec(provisioner_method), 'defaults')
    return dict(list(zip(args, defaults or [None for arg in args])))


def create_tagging_decorator(tag_name: str) -> Callable:
    """Create a decorator that tags methods for automatic route registration.

    Tagged methods are discovered at class-definition time by ``tag_class_items()``
    and stored in a class-level list (e.g. ``cls.actions``, ``cls.resources``).

    Args:
        tag_name: registry key under which tagged methods are collected
            (``'actions'`` or ``'resources'``).
    """
    def tagging_decorator(*args: Any, **kwargs: Any) -> Callable:
        def wrapper(method: Callable) -> Callable:
            method.member_tag = (tag_name, {'args': args, 'kwargs': kwargs})
            return method
        return wrapper
    return tagging_decorator


action = create_tagging_decorator('actions')
resource = create_tagging_decorator('resources')


def tag_class_items(class_name: str, class_dictionary: dict[str, Any]) -> dict[str, Any]:
    """Scan class members for ``@action``/``@resource`` tagged methods.

    Returns a dict mapping tag names to lists of method descriptors::

        {
            'actions': [
                {'function_name': 'change_password',
                 'argspec': {'password': 'default pass'},
                 'decorator_args': [],
                 'decorator_kwargs': {'method': ['POST']}},
            ]
        }
    """
    tags: dict[str, Any] = {}
    for member_name, member in class_dictionary.items():
        if hasattr(member, 'member_tag') and (inspect.isfunction(member) or inspect.ismethod(member)):
            if member.member_tag[0] not in tags:
                tags[member.member_tag[0]] = []
            tags[member.member_tag[0]].append({
                'function_name': member.__name__,
                'argspec': get_argument_spec(member),
                'decorator_args': list(member.member_tag[1].get('args')),
                'decorator_kwargs': member.member_tag[1].get('kwargs'),
            })
    return tags
