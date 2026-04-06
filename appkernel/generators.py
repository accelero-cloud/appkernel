from __future__ import annotations

import uuid
from datetime import datetime, date, time as dtime
import time
import bcrypt
from typing import Any
from collections.abc import Callable

from appkernel.dsl import Marshaller


class TimestampMarshaller(Marshaller):
    def to_wireformat(self, instance_value: date | datetime | Any) -> float | Any:
        if isinstance(instance_value, (date, datetime)):
            return time.mktime(instance_value.timetuple())
        else:
            return instance_value

    def from_wire_format(self, wire_value: str | float | int | Any) -> datetime | Any:
        if isinstance(wire_value, str):
            wire_value = float(wire_value)
        if isinstance(wire_value, (float, int)):
            return datetime.fromtimestamp(wire_value)
        else:
            return wire_value


class MongoDateTimeMarshaller(Marshaller):

    def to_wireformat(self, instance_value: date) -> datetime:
        if isinstance(instance_value, date):
            return datetime.combine(instance_value, dtime.min)
        else:
            return instance_value

    def from_wire_format(self, wire_value: datetime) -> date | datetime:
        if isinstance(wire_value, datetime):
            return wire_value.date()
        else:
            return wire_value


class CypherMarshaller(Marshaller):

    def to_wireformat(self, instance_value: Any) -> Any:
        pass

    def from_wire_format(self, wire_value: Any) -> Any:
        pass


def create_uuid_generator(prefix: str | None = None) -> Callable[[], str]:
    def generate_id() -> str:
        return f'{prefix or ""}{uuid.uuid4()!s}'

    return generate_id


def date_now_generator() -> datetime:
    return datetime.now()


def content_hasher(rounds: int = 12) -> Callable[[str], str]:
    def hash_content(password: str) -> str:
        if password.startswith('$2b$'):
            return password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=rounds))
        return hashed.decode('utf-8')

    return hash_content
