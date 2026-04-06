"""
AppKernel field metadata types for Pydantic Annotated[] fields.

These dataclass markers are attached to fields via typing.Annotated and read at runtime
by finalise_and_validate(), init_indexes(), to_dict(), from_dict(), and get_parameter_spec().
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from pydantic._internal._model_construction import ModelMetaclass

from .dsl import (
    DslBase, BackReference, OPS, Marshaller, SortOrder,
    tag_class_items,
)


# ---------------------------------------------------------------------------
# Field metadata markers (used inside Annotated[])
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Required:
    """Marks a field as required. Checked by finalise_and_validate()."""
    pass


@dataclass(frozen=True)
class Generator:
    """Auto-generate field value when None at validation time."""
    func: Callable


@dataclass(frozen=True)
class Converter:
    """Convert field value during finalise_and_validate()."""
    func: Callable


@dataclass(frozen=True)
class Default:
    """Default value applied when field is None at validation time."""
    value: Any


class Validators:
    """List of AppKernel Validator instances for validation and parameter spec."""
    __slots__ = ('items',)

    def __init__(self, *validators):
        object.__setattr__(self, 'items', list(validators))

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other


@dataclass(frozen=True)
class Marshal:
    """Bidirectional wire-format converter (Marshaller class or instance)."""
    marshaller: Any


# ---------------------------------------------------------------------------
# MongoDB index metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MongoIndex:
    """Regular MongoDB index on a field."""
    sort_order: SortOrder = SortOrder.ASC


@dataclass(frozen=True)
class MongoTextIndex(MongoIndex):
    """Full-text search index."""
    pass


@dataclass(frozen=True)
class MongoUniqueIndex(MongoIndex):
    """Unique constraint index."""
    pass


# ---------------------------------------------------------------------------
# Helpers to extract metadata from Pydantic FieldInfo
# ---------------------------------------------------------------------------

def get_field_meta(field_info, meta_type):
    """Extract the first metadata marker of the given type from a FieldInfo's metadata list."""
    for m in field_info.metadata:
        if isinstance(m, meta_type):
            return m
    return None


def get_all_field_meta(field_info, meta_type):
    """Extract all metadata markers of the given type."""
    return [m for m in field_info.metadata if isinstance(m, meta_type)]


def get_field_index(field_info):
    """Extract index metadata (MongoIndex or subclass) from a field."""
    return get_field_meta(field_info, MongoIndex)


def get_field_validators_meta(field_info):
    """Extract the Validators metadata from a field, returns list of validator instances."""
    v = get_field_meta(field_info, Validators)
    return v.items if v else []


def get_field_marshaller(field_info):
    """Extract and instantiate the marshaller from a field."""
    m = get_field_meta(field_info, Marshal)
    if m is None:
        return None
    marshaller = m.marshaller
    if isinstance(marshaller, type) and issubclass(marshaller, Marshaller):
        return marshaller()
    if isinstance(marshaller, Marshaller):
        return marshaller
    return None


def is_field_required(field_info):
    """Check if a field has the Req() marker."""
    return get_field_meta(field_info, Required) is not None


def is_field_omitted(field_info):
    """Check if a field is excluded from serialization."""
    return getattr(field_info, 'exclude', False) is True


def get_field_generator(field_info):
    """Extract the Gen metadata (generator function)."""
    g = get_field_meta(field_info, Generator)
    return g.func if g else None


def get_field_converter(field_info):
    """Extract the Conv metadata (converter function)."""
    c = get_field_meta(field_info, Converter)
    return c.func if c else None


def get_field_default(field_info):
    """Extract the Default metadata value."""
    d = get_field_meta(field_info, Default)
    return d.value if d else None


def has_field_default(field_info):
    """Check if a field has a Default metadata."""
    return get_field_meta(field_info, Default) is not None


def extract_base_type(annotation):
    """Extract the base Python type and sub_type from a type annotation.

    Examples:
        str | None          -> (str, None)
        list[Stock] | None  -> (list, Stock)
        datetime | None     -> (datetime, None)
        Annotated[str|None, ...] -> (str, None)
    """
    import types as builtin_types
    import typing

    # Unwrap Annotated
    origin = get_origin(annotation)
    if hasattr(typing, 'Annotated') and origin is getattr(typing, 'Annotated', None):
        args = get_args(annotation)
        if args:
            return extract_base_type(args[0])

    # Plain type
    if isinstance(annotation, type):
        if annotation is list:
            return (list, None)
        return (annotation, None)

    origin = get_origin(annotation)

    # Union type (str | None, Optional[str], etc.)
    if origin is Union or isinstance(annotation, builtin_types.UnionType):
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            base = non_none[0]
            base_origin = get_origin(base)
            if base_origin is list:
                list_args = get_args(base)
                sub = list_args[0] if list_args else None
                return (list, sub)
            return (base, None)
        return (type(None), None)

    # list[X]
    if origin is list:
        args = get_args(annotation)
        sub = args[0] if args else None
        return (list, sub)

    return (annotation, None)


# ---------------------------------------------------------------------------
# FieldProxy — query DSL proxy for Pydantic model fields
# ---------------------------------------------------------------------------

class FieldProxy(DslBase):
    """
    Proxy object returned when accessing model fields at the class level
    (e.g. User.name). Supports the query DSL via operator overloading.
    """

    def __init__(self, cls, field_name, field_info=None, python_type=None, sub_type=None):
        self._cls = cls
        self._field_info = field_info
        self.backreference = BackReference(class_name=cls.__name__, parameter_name=field_name)
        self._python_type = python_type
        self._sub_type = sub_type

        # Resolve types from annotation if not provided
        if (python_type is None or sub_type is None) and cls is not None:
            ann = cls.__annotations__.get(field_name)
            if ann is not None:
                pt, st = extract_base_type(ann)
                if python_type is None:
                    self._python_type = pt
                if sub_type is None:
                    self._sub_type = st

    def __getattr__(self, attribute):
        """Support nested property access via dot notation.

        For a Model-typed field, returns a new FieldProxy with a dot-path
        parameter name (e.g. ``User.address.city`` → ``address.city``).
        For a ``list[Model]`` field, marks the returned proxy as within an
        array so operators produce ``$elemMatch`` queries.
        """
        from pydantic import BaseModel

        if self._python_type == list and self._sub_type and inspect.isclass(self._sub_type):
            if issubclass(self._sub_type, BaseModel) and hasattr(self._sub_type, 'model_fields'):
                if attribute in self._sub_type.model_fields:
                    nested_fi = self._sub_type.model_fields[attribute]
                    proxy = FieldProxy(self._sub_type, attribute, nested_fi)
                    proxy.backreference.array_parameter_name = self.backreference.parameter_name
                    proxy.backreference.within_an_array = True
                    return proxy
        elif self._python_type and inspect.isclass(self._python_type) and issubclass(self._python_type, BaseModel):
            if hasattr(self._python_type, 'model_fields') and attribute in self._python_type.model_fields:
                nested_fi = self._python_type.model_fields[attribute]
                proxy = FieldProxy(self._python_type, attribute, nested_fi)
                proxy.backreference.parameter_name = f'{self.backreference.parameter_name}.{attribute}'
                return proxy
        raise AttributeError(f'{self._cls.__name__}.{self.backreference.parameter_name} has no attribute {attribute}')

    def __getitem__(self, item_expression):
        """Enable array element matching via bracket notation.

        Example: ``Portfolio.stocks[Stock.code == 'AAA']`` produces an
        ``$elemMatch`` query on the ``stocks`` array.
        """
        from pydantic import BaseModel
        if (self._python_type == list
                and self._sub_type
                and inspect.isclass(self._sub_type)
                and issubclass(self._sub_type, BaseModel)
                and self._sub_type.__name__ == item_expression.lhs.backreference.class_name):
            item_expression.lhs.backreference.within_an_array = True
            item_expression.lhs.backreference.array_parameter_name = self.backreference.parameter_name
            if item_expression.ops == OPS.EQ:
                item_expression.ops = OPS.ELEM_MATCH
            elif item_expression.ops == OPS.NE:
                item_expression.ops = OPS.ELEM_DOES_NOT_MATCH
        else:
            raise TypeError(
                f'The subtype {self._sub_type} of the parameter is not '
                f'{item_expression.lhs.backreference.class_name}')
        return item_expression

    def asc(self):
        """Return an ascending sort tuple for use with ``query.sort_by()``."""
        return (self.backreference.parameter_name, 1)

    def desc(self):
        """Return a descending sort tuple for use with ``query.sort_by()``."""
        return (self.backreference.parameter_name, -1)


# ---------------------------------------------------------------------------
# AppKernelMeta — Pydantic metaclass with tagging + query DSL
# ---------------------------------------------------------------------------

class AppKernelMeta(ModelMetaclass):
    """
    Custom metaclass that extends Pydantic's ModelMetaclass to:
    1. Process @action/@resource tagged methods (like _TaggingMetaClass)
    2. Return FieldProxy objects for class-level field access (query DSL)
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        from typing import ClassVar

        # Process tagged functions (action/resource decorators)
        tags = tag_class_items(name, namespace)
        namespace.update(tags)

        # Annotate tag lists as ClassVar so Pydantic ignores them
        annotations = namespace.get('__annotations__', {})
        for tag_key in ('actions', 'resources'):
            if tag_key in tags:
                annotations[tag_key] = ClassVar[list]
        namespace['__annotations__'] = annotations

        # Let Pydantic build the class
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        return cls

    def __getattr__(cls, name):
        """Return FieldProxy for query DSL when accessing model fields at class level."""
        # Guard against recursion during class construction
        # Pydantic stores fields in __pydantic_fields__, not model_fields (which is a property)
        fields = cls.__dict__.get('__pydantic_fields__')
        if fields is not None and name in fields:
            # Get the FieldInfo from the public model_fields property
            field_info = cls.model_fields.get(name)
            return FieldProxy(cls, name, field_info)
        # Fall through to parent
        try:
            return super().__getattr__(name)
        except AttributeError:
            raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")
