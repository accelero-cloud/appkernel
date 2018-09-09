from appkernel.util import sanitize, to_boolean, merge_dicts


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
