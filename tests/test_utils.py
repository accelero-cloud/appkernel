import datetime
import os
import tarfile
import tempfile

from bson import ObjectId

from appkernel.util import (
    assure_folder,
    b64decode,
    b64encode,
    create_custom_error,
    default_json_serializer,
    make_tar_file,
    merge_dicts,
    sanitize,
    to_boolean,
)


def test_sanitise():
    test_text = "some,text:with'\n some chars"
    sanitised = sanitize(test_text)
    print(f'result >>> {sanitised}')
    assert sanitised == "some;text:with'  some chars"


def test_boolean():
    bval = to_boolean('true')
    assert bval
    bval = to_boolean('1')
    assert bval
    bval = to_boolean('y')
    assert bval
    bval = to_boolean('YES')
    assert bval
    bval = to_boolean('FALSE')
    assert not bval
    bval = to_boolean('0')
    assert not bval
    bval = to_boolean('n')
    assert not bval
    bval = to_boolean('No')
    assert not bval


def test_merge_dicts():
    result = merge_dicts({'a': 1}, {'b': 2})
    assert result.get('b') == 2


# ---------------------------------------------------------------------------
# b64encode / b64decode
# ---------------------------------------------------------------------------

def test_b64_roundtrip():
    assert b64decode(b64encode(b'hello world')) == b'hello world'


def test_b64encode_returns_str():
    assert isinstance(b64encode(b'test'), str)


def test_b64decode_from_str():
    encoded = b64encode(b'appkernel')
    assert b64decode(encoded) == b'appkernel'


# ---------------------------------------------------------------------------
# default_json_serializer
# ---------------------------------------------------------------------------

def test_default_json_serializer_datetime():
    dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
    assert default_json_serializer(dt) == '2024-01-15T10:30:00'


def test_default_json_serializer_date():
    d = datetime.date(2024, 6, 1)
    assert default_json_serializer(d) == '2024-06-01'


def test_default_json_serializer_timedelta():
    td = datetime.timedelta(hours=1, minutes=30, seconds=15)
    result = default_json_serializer(td)
    assert '01:30:15' in result


def test_default_json_serializer_objectid():
    oid = ObjectId()
    result = default_json_serializer(oid)
    assert result.startswith('OBJ_')
    assert len(result) > 4


def test_default_json_serializer_unknown_type():
    result = default_json_serializer(object())
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# create_custom_error
# ---------------------------------------------------------------------------

def test_create_custom_error_basic():
    response = create_custom_error(404, 'not found')
    assert response.status_code == 404
    assert b'not found' in response.body


def test_create_custom_error_with_upstream_service():
    response = create_custom_error(502, 'upstream failed', upstream_service='payments')
    assert response.status_code == 502
    assert b'payments' in response.body
    assert b'upstream failed' in response.body


# ---------------------------------------------------------------------------
# make_tar_file / assure_folder
# ---------------------------------------------------------------------------

def test_make_tar_file_creates_valid_archive():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'data.txt')
        out = os.path.join(tmpdir, 'archive.tar.gz')
        with open(src, 'w') as f:
            f.write('test content')
        make_tar_file(src, out)
        assert os.path.isfile(out)
        assert tarfile.is_tarfile(out)


def test_assure_folder_creates_nested_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, 'a', 'b', 'c')
        assure_folder(nested)
        assert os.path.isdir(nested)


def test_assure_folder_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, 'existing')
        assure_folder(path)
        assure_folder(path)  # second call should not raise
        assert os.path.isdir(path)


# ---------------------------------------------------------------------------
# to_boolean edge cases
# ---------------------------------------------------------------------------

def test_boolean_with_none():
    assert not to_boolean(None)


def test_boolean_with_bool():
    assert to_boolean(True)
    assert not to_boolean(False)


def test_boolean_with_int():
    assert to_boolean(1)
    assert not to_boolean(0)
