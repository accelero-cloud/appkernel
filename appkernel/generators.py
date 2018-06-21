import uuid
from datetime import datetime, date, time as dtime
import time
from passlib.hash import pbkdf2_sha256
from appkernel.model import Marshaller


class TimestampMarshaller(Marshaller):
    def to_wireformat(self, instance_value):
        if isinstance(instance_value, (date, datetime)):
            return time.mktime(instance_value.timetuple())
        else:
            return instance_value

    def from_wire_format(self, wire_value):
        if isinstance(wire_value, str):
            wire_value = float(wire_value)
        if isinstance(wire_value, (float, int)):
            return datetime.fromtimestamp(wire_value)
        else:
            return wire_value


class MongoDateTimeMarshaller(Marshaller):

    def to_wireformat(self, instance_value):
        if isinstance(instance_value, date):
            return datetime.combine(instance_value, dtime.min)
        else:
            return instance_value

    def from_wire_format(self, wire_value):
        if isinstance(wire_value, datetime):
            return wire_value.date()
        else:
            return wire_value



class CypherMarshaller(Marshaller):

    def to_wireformat(self, instance_value):
        pass

    def from_wire_format(self, wire_value):
        pass


def create_uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix or '', str(uuid.uuid4()))

    return generate_id


def date_now_generator():
    return datetime.now()


def current_user_generator():
    # todo: finalise this
    return ''


def content_hasher(rounds=20000, salt_size=16):
    def hash_content(password):
        # type: (str) -> str
        if password.startswith('$pbkdf2-sha256'):
            return password
        else:
            return pbkdf2_sha256.encrypt(password, rounds=rounds, salt_size=salt_size)

    return hash_content
