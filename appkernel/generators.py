import uuid
from datetime import datetime
from passlib.hash import pbkdf2_sha256


def uuid_generator(prefix=None):
    def generate_id():
        return '{}{}'.format(prefix, str(uuid.uuid4()))

    return generate_id


def date_now_generator():
    return datetime.now()


def password_hash_generator(password):
    # type: (str) -> (str)

    if password.startswith('$pbkdf2-sha256'):
        return password
    else:
        return pbkdf2_sha256.encrypt(password, rounds=200000, salt_size=16)
