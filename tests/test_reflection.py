"""
Tests for appkernel/reflection.py — pure utility predicates.
All functions are stateless, so each test is a simple assertion.
"""
import os
import time
import types

import pytest

from appkernel.reflection import (
    has_method,
    importable_name,
    is_bytes,
    is_dictionary,
    is_dictionary_subclass,
    is_function,
    is_list,
    is_list_like,
    is_module,
    is_module_function,
    is_noncomplex,
    is_object,
    is_primitive,
    is_sequence,
    is_sequence_subclass,
    is_set,
    is_tuple,
    is_type,
    is_unicode,
    itemgetter,
    translate_module_name,
    untranslate_module_name,
)


# ---------------------------------------------------------------------------
# is_type
# ---------------------------------------------------------------------------

def test_is_type_with_class():
    assert is_type(int)
    assert is_type(str)
    assert is_type(list)


def test_is_type_with_instance():
    assert not is_type(42)
    assert not is_type('hello')
    assert not is_type([])


# ---------------------------------------------------------------------------
# is_object
# ---------------------------------------------------------------------------

def test_is_object_with_primitives():
    assert is_object(1)
    assert is_object('hello')
    assert is_object(object())


def test_is_object_with_function():
    assert not is_object(lambda x: x)


def test_is_object_with_type():
    assert not is_object(int)


# ---------------------------------------------------------------------------
# is_primitive
# ---------------------------------------------------------------------------

def test_is_primitive_with_none():
    assert is_primitive(None)


def test_is_primitive_with_scalars():
    assert is_primitive(3)
    assert is_primitive(3.14)
    assert is_primitive(True)
    assert is_primitive('hello')


def test_is_primitive_with_collections():
    assert not is_primitive([4, 4])
    assert not is_primitive({'key': 'value'})


# ---------------------------------------------------------------------------
# is_dictionary
# ---------------------------------------------------------------------------

def test_is_dictionary_with_dict():
    assert is_dictionary({'key': 'value'})
    assert is_dictionary({})


def test_is_dictionary_with_non_dict():
    assert not is_dictionary([])
    assert not is_dictionary('hello')


# ---------------------------------------------------------------------------
# is_sequence
# ---------------------------------------------------------------------------

def test_is_sequence_with_list():
    assert is_sequence([4])
    assert is_sequence([])


def test_is_sequence_with_set():
    assert is_sequence({1, 2})


def test_is_sequence_with_tuple():
    assert is_sequence((1, 2))


def test_is_sequence_with_non_sequence():
    assert not is_sequence({})
    assert not is_sequence('hello')


# ---------------------------------------------------------------------------
# is_list / is_set / is_bytes / is_unicode / is_tuple
# ---------------------------------------------------------------------------

def test_is_list():
    assert is_list([])
    assert not is_list(())
    assert not is_list({1})


def test_is_set():
    assert is_set(set())
    assert is_set({1, 2})
    assert not is_set([])


def test_is_bytes():
    assert is_bytes(b'foo')
    assert not is_bytes('foo')


def test_is_unicode():
    assert is_unicode('hello')
    assert not is_unicode(b'hello')


def test_is_tuple():
    assert is_tuple((1,))
    assert is_tuple(())
    assert not is_tuple([1])


# ---------------------------------------------------------------------------
# is_dictionary_subclass
# ---------------------------------------------------------------------------

def test_is_dictionary_subclass_with_subclass():
    class Temp(dict):
        pass
    assert is_dictionary_subclass(Temp())


def test_is_dictionary_subclass_with_plain_dict():
    assert not is_dictionary_subclass({})


def test_is_dictionary_subclass_with_non_dict():
    assert not is_dictionary_subclass([])


# ---------------------------------------------------------------------------
# is_sequence_subclass
# ---------------------------------------------------------------------------

def test_is_sequence_subclass_with_list_subclass():
    class Temp(list):
        pass
    assert is_sequence_subclass(Temp())


def test_is_sequence_subclass_with_plain_list():
    assert not is_sequence_subclass([])


# ---------------------------------------------------------------------------
# is_list_like
# ---------------------------------------------------------------------------

def test_is_list_like_with_list():
    assert is_list_like([])


def test_is_list_like_with_int():
    assert not is_list_like(42)


def test_is_list_like_with_string():
    # strings have __getitem__ but not append
    assert not is_list_like('hello')


# ---------------------------------------------------------------------------
# is_noncomplex
# ---------------------------------------------------------------------------

def test_is_noncomplex_with_struct_time():
    assert is_noncomplex(time.localtime())


def test_is_noncomplex_with_int():
    assert not is_noncomplex(42)


# ---------------------------------------------------------------------------
# is_function
# ---------------------------------------------------------------------------

def test_is_function_with_lambda():
    assert is_function(lambda x: x)


def test_is_function_with_builtin():
    assert is_function(len)


def test_is_function_with_int():
    assert not is_function(1)


def test_is_function_with_named_function():
    def my_func():
        pass
    assert is_function(my_func)


# ---------------------------------------------------------------------------
# is_module_function
# ---------------------------------------------------------------------------

def test_is_module_function_with_module_function():
    assert is_module_function(os.path.exists)


def test_is_module_function_with_lambda():
    assert not is_module_function(lambda: None)


# ---------------------------------------------------------------------------
# is_module
# ---------------------------------------------------------------------------

def test_is_module_with_module():
    import os as os_mod
    assert is_module(os_mod)


def test_is_module_with_non_module():
    assert not is_module(42)
    assert not is_module('os')


# ---------------------------------------------------------------------------
# translate_module_name / untranslate_module_name
# ---------------------------------------------------------------------------

def test_translate_module_name_builtins():
    assert translate_module_name('builtins') == '__builtin__'


def test_translate_module_name_exceptions():
    assert translate_module_name('exceptions') == '__builtin__'


def test_translate_module_name_other():
    assert translate_module_name('mymodule') == 'mymodule'


def test_untranslate_module_name_builtin():
    assert untranslate_module_name('__builtin__') == 'builtins'


def test_untranslate_module_name_exceptions():
    assert untranslate_module_name('exceptions') == 'builtins'


def test_untranslate_module_name_other():
    assert untranslate_module_name('mymodule') == 'mymodule'


# ---------------------------------------------------------------------------
# importable_name
# ---------------------------------------------------------------------------

def test_importable_name_builtin_int():
    assert importable_name(int) == '__builtin__.int'


def test_importable_name_builtin_none():
    assert importable_name(type(None)) == '__builtin__.NoneType'


def test_importable_name_builtin_bool():
    assert importable_name(bool) == '__builtin__.bool'


def test_importable_name_builtin_error():
    assert importable_name(AttributeError) == '__builtin__.AttributeError'


# ---------------------------------------------------------------------------
# has_method
# ---------------------------------------------------------------------------

def test_has_method_existing_method():
    assert has_method([], 'append')
    assert has_method([], 'pop')


def test_has_method_missing_method():
    assert not has_method([], 'nonexistent_method')


def test_has_method_wrapper_method():
    # __getitem__ is a slot wrapper detected as a FunctionType in some versions
    # but __len__ is a builtin_function_or_method and is not detected by has_method.
    # has_method correctly returns True for wrapped descriptor methods like __getitem__.
    assert has_method([], '__getitem__')


def test_has_method_on_class():
    class MyClass:
        def my_method(self):
            pass
    assert has_method(MyClass(), 'my_method')


# ---------------------------------------------------------------------------
# itemgetter
# ---------------------------------------------------------------------------

def test_itemgetter_returns_first_element():
    assert itemgetter(('alpha', 'beta')) == 'alpha'


def test_itemgetter_with_single_element_tuple():
    assert itemgetter(('only',)) == 'only'
