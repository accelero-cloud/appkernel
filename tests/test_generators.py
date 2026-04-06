from datetime import date, datetime

from appkernel.generators import CypherMarshaller, MongoDateTimeMarshaller, TimestampMarshaller


def test_mongo_date_time_marshaller():
    marshaler = MongoDateTimeMarshaller()
    result = marshaler.to_wireformat(date.today())
    print(f'result: {type(result)}/{result}')
    assert isinstance(result, date)
    result = marshaler.to_wireformat('raw text')
    print(f'result: {type(result)}/{result}')
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# MongoDateTimeMarshaller.from_wire_format
# ---------------------------------------------------------------------------

def test_mongo_datetime_marshaller_from_datetime_returns_date():
    m = MongoDateTimeMarshaller()
    result = m.from_wire_format(datetime(2024, 6, 15, 12, 0, 0))
    assert isinstance(result, date)
    assert result == date(2024, 6, 15)


def test_mongo_datetime_marshaller_from_non_datetime_passthrough():
    m = MongoDateTimeMarshaller()
    assert m.from_wire_format('2024-06-15') == '2024-06-15'
    assert m.from_wire_format(None) is None


# ---------------------------------------------------------------------------
# TimestampMarshaller
# ---------------------------------------------------------------------------

def test_timestamp_marshaller_to_wireformat_datetime():
    m = TimestampMarshaller()
    result = m.to_wireformat(datetime(2024, 1, 1, 0, 0, 0))
    assert isinstance(result, float)


def test_timestamp_marshaller_to_wireformat_date():
    m = TimestampMarshaller()
    result = m.to_wireformat(date(2024, 1, 1))
    assert isinstance(result, float)


def test_timestamp_marshaller_to_wireformat_non_date_passthrough():
    m = TimestampMarshaller()
    assert m.to_wireformat('not-a-date') == 'not-a-date'
    assert m.to_wireformat(42) == 42


def test_timestamp_marshaller_from_wire_format_float():
    m = TimestampMarshaller()
    result = m.from_wire_format(0.0)
    assert isinstance(result, datetime)


def test_timestamp_marshaller_from_wire_format_int():
    m = TimestampMarshaller()
    result = m.from_wire_format(0)
    assert isinstance(result, datetime)


def test_timestamp_marshaller_from_wire_format_numeric_string():
    m = TimestampMarshaller()
    result = m.from_wire_format('0.0')
    assert isinstance(result, datetime)


def test_timestamp_marshaller_from_wire_format_non_numeric_string_raises():
    # The implementation tries float(wire_value) for any string — non-numeric raises ValueError
    import pytest
    m = TimestampMarshaller()
    with pytest.raises(ValueError):
        m.from_wire_format('not-a-timestamp')


# ---------------------------------------------------------------------------
# CypherMarshaller (stub implementations)
# ---------------------------------------------------------------------------

def test_cypher_marshaller_to_wireformat_returns_none():
    m = CypherMarshaller()
    assert m.to_wireformat('secret') is None


def test_cypher_marshaller_from_wire_format_returns_none():
    m = CypherMarshaller()
    assert m.from_wire_format('encrypted') is None
