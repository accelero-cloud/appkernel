import uuid
from datetime import datetime
import time
from passlib.hash import pbkdf2_sha256
from appkernel.model import Marshaller


class TimestampMarshaller(Marshaller):
    def to_wireformat(self, class_value):
        if isinstance(class_value, datetime):
            return time.mktime(class_value.timetuple())
        else:
            return class_value

    def from_wire_format(self, wire_value):
        if isinstance(wire_value, (str, basestring, unicode)):
            wire_value = float(wire_value)
        if isinstance(wire_value, (float, int)):
            return datetime.fromtimestamp(wire_value)
        else:
            return wire_value


class CypherMarshaller(Marshaller):

    def to_wireformat(self, class_value):
        pass

    def from_wire_format(self, wire_value):
        pass


def create_uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))

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
