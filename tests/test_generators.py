from datetime import date

from appkernel.generators import MongoDateTimeMarshaller


def test_mongo_date_time_marshaller():
    marshaler = MongoDateTimeMarshaller()
    result = marshaler.to_wireformat(date.today())
    print(f'result: {type(result)}/{result}')
    assert isinstance(result, date)
    result = marshaler.to_wireformat('raw text')
    print(f'result: {type(result)}/{result}')
    assert isinstance(result, str)
