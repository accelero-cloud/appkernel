from appkernel import Service
from werkzeug.datastructures import ImmutableMultiDict

# test query AND and OR and NOT
# test between
# test contains
# test date pattern recognition and conversion


def test_simple_query_processing():
    query_expression = ImmutableMultiDict([('first_name', u'first Name')])
    res = Service.convert_to_query(['first_name'], query_expression)
    print('\n{}'.format(res))
    assert isinstance(res, dict), 'it should be type of dict'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    assert 'first_name' in res, 'it should contain a key named: first_name'
    assert res.get('first_name') == 'first Name', 'the value of the key should be: first Name'


def test_simple_query_with_contains_expression():
    query_expression = ImmutableMultiDict([('first_name', u'~first Name')])
    res = Service.convert_to_query(['first_name'], query_expression)
    print('\n{}'.format(res))
    assert isinstance(res, dict), 'it should be type of dict'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    assert '$regex' in res.get('first_name')


def test_simple_query_with_less_then():
    query_expression = ImmutableMultiDict([('birth_date', u'<1980-07-31')])
    res = Service.convert_to_query(['birth_date'], query_expression)
    print('\n{}'.format(res))
    assert isinstance(res, dict), 'it should be type of dict'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    assert isinstance(res.get('birth_date'), dict), 'it should be type of dict'


def test_simple_query_with_between_query():
    query_expression=ImmutableMultiDict([('birth_date', u'>1980-07-01'), ('birth_date', u'<1980-07-31'), ('logic', u'AND')])
    res = Service.convert_to_query(['birth_date'], query_expression)
    print('\n{}'.format(res))
    assert isinstance(res, dict), 'it should be type of dict'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    assert isinstance(res.get('birth_date'), dict), 'it should be type of dict'
    assert len(res.get('birth_date')) == 2, 'the date parameter should contain 2 elements'


def test_or_logic():
    query_expression = ImmutableMultiDict(
        [('first_name', u'first Name'), ('last_name', u'last Name'), ('logic', u'OR')])
    res = Service.convert_to_query(['first_name', 'last_name'], query_expression)
    print('\n{}'.format(res))
    assert '$or' in res, 'it should contain a key $or'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    query_items = res.get('$or')
    assert len(query_items) == 2, 'the query should have 2 query params'


# def test_in_query():
#     query_expression = "state:[NEW,CLOSED]"
#     service = Service()
#     res = service._Service__convert_to_query(query_expression)
#     print('\n{}'.format(res))

def test_complex_query_processing():
    query_expression = ImmutableMultiDict(
        [('first_name', u'first Name'), ('last_name', u'last Name'), ('birth_date', u'>1980-07-01'), ('birth_date', u'<1980-07-31'), ('logic', u'AND')])
    res = Service.convert_to_query(['last_name', 'first_name', 'birth_date'], query_expression)
    print('\n{}'.format(res))
    assert '$and' in res, 'it should contain a key $and'
    assert len(list(res.keys())) == 1, 'it should have only one key'
    query_items = res.get('$and')
    assert isinstance(query_items, list), 'the logical groups should be included in a list'
    assert len(query_items) == 3, 'the query should have 3 query params'
    for query_item in query_items:
        if 'birth_date' in query_item:
            bd_item = query_item.get('birth_date')
            assert '$gte' in bd_item, '$gte expression should be in the birthday item'
            assert '$lt' in bd_item, '$lt expression should be in the birthday item'
        if 'first_name' in query_item:
            assert query_item.get('first_name') == 'first Name'
        if 'last_name' in query_item:
            assert query_item.get('last_name') == 'last Name'