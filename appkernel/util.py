from __future__ import annotations

import base64
import datetime
import itertools
import tarfile
from pathlib import Path
from typing import Any

from bson import ObjectId
from starlette.responses import JSONResponse as _StarletteJSONResponse

from appkernel.core import MessageType

try:
    import simplejson as json
except ImportError:
    import json


class AppJSONResponse(_StarletteJSONResponse):
    """JSONResponse that handles datetime, ObjectId, and other custom types."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            default=default_json_serializer,
        ).encode("utf-8")


OBJ_PREFIX = 'OBJ_'  # pylint: disable-msg=C0103


def create_custom_error(code: int, message: str, upstream_service: str | None = None) -> AppJSONResponse:
    rsp = {'_type': MessageType.ErrorMessage.name, 'code': code, 'message': message}
    if upstream_service:
        rsp.update(upstream_service=upstream_service)
    return AppJSONResponse(content=rsp, status_code=code)


def default_json_serializer(obj: Any) -> str | int | float | None:
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, datetime.timedelta):
        return (datetime.datetime.min + obj).time().isoformat()
    elif isinstance(obj, ObjectId):
        return f'{OBJ_PREFIX}{obj!s}'
    else:
        return str(obj)


def b64encode(data: bytes) -> str:
    payload = base64.b64encode(data)
    if isinstance(payload, bytes):
        payload = payload.decode('ascii')
    return payload


def b64decode(payload: str | bytes) -> bytes:
    if not isinstance(payload, bytes):
        payload = bytes(payload, 'ascii')
    return base64.b64decode(payload)


def sanitize(content: str | None) -> str:
    if content:
        if len(content) > 0:
            try:
                return (
                    f'{content}'
                    .replace(',', ';')
                    .replace('\n', ' ')
                    .replace('"', '')
                    .replace('\\', '')
                )
            except Exception as ex:
                raise ex
        else:
            return ''
    else:
        return ''


def make_tar_file(source_file: str, output_name: str) -> None:
    """
    Tar/gzips a file or folder.

    :param source_file: the source file or folder to be zipped
    :param output_name: the output file name
    """
    with tarfile.open(output_name, 'w:gz') as tar:
        tar.add(source_file, arcname=Path(source_file).name)


def to_boolean(string_expression: str | bool | int | None) -> bool:
    if not string_expression:
        return False
    if isinstance(string_expression, bool):
        return string_expression
    if isinstance(string_expression, int):
        return string_expression != 0
    return string_expression.lower() in ['true', 'y', 'yes', '1']


def assure_folder(folder_path: str) -> None:
    Path(folder_path).mkdir(parents=True, exist_ok=True)


def merge_dicts(x_dict: dict, y_dict: dict) -> dict:
    res = x_dict.copy()
    res.update(y_dict)
    return res


def extract_model_messages(fileobj, keywords, comment_tags, options):
    """Extract messages from python model container-files.

    :param fileobj: the file-like object the messages should be extracted from
    :param keywords: a list of keywords (i.e. function names) that should be
                     recognized as translation functions
    :param comment_tags: a list of translator tags to search for and include
                         in the results
    :param options: a dictionary of additional options (optional)
    :return: an iterator over ``(lineno, funcname, message, comments)`` tuples
    :rtype: ``iterator``
    """

    def extract_model():
        import ast
        fileobj.seek(0)
        node = ast.parse(fileobj.read())
        classes = [n for n in node.body if isinstance(n, ast.ClassDef)]

        def has_model(class_def):
            for base in class_def.bases:
                from appkernel import Model
                if base.id == Model.__name__:
                    return True
            return False

        def is_parameter(body_elem):
            if not hasattr(body_elem, 'value') or not hasattr(body_elem.value, 'func'):
                return False
            return body_elem.value.func.id == 'Parameter'

        for class_ in classes:
            if has_model(class_):
                for param in [p for p in class_.body if isinstance(p, ast.Assign) and is_parameter(p)]:
                    clazz_name = class_.name
                    parameter_name = param.targets[0].id
                    yield (param.lineno, '', f'{clazz_name}.{parameter_name}',
                           [f'Parameter "{parameter_name}" on "{clazz_name}"'])

    from babel.messages.extract import extract_python
    return itertools.chain(extract_python(fileobj, keywords, comment_tags, options), extract_model())
