# -*- coding: utf-8 -*-
# pylint: skip-file

import sys

"""
Copied from Json Pickle: https://github.com/jsonpickle/jsonpickle/blob/master/jsonpickle/util.py
"""

__all__ = ('bytes', 'set', 'unicode', 'long', 'unichr', 'queue')

PY_MAJOR = sys.version_info[0]
PY_MINOR = sys.version_info[1]
PY2 = PY_MAJOR == 2
PY3 = PY_MAJOR == 3
PY32 = PY3 and PY_MINOR == 2

try:
    bytes = bytes
except NameError:
    bytes = str

try:
    set = set
except NameError:
    from sets import Set as set
    set = set

try:
    str = str
except NameError:
    str = str

try:
    long = int
    numeric_types = (int, int)
except NameError:
    long = int
    numeric_types = (int,)

try:
    chr = chr
except NameError:
    chr = chr


try:
    # Python3
    import queue
except ImportError:
    # Python2
    import Queue as queue