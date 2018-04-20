import uuid
from datetime import datetime


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id


def date_now_generator():
    return datetime.now()
