import datetime, os, tarfile

import base64
from bson import ObjectId

from compat import PY3

OBJ_PREFIX = 'OBJ_' # pylint: disable-msg=C0103


def default_json_serializer(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, datetime.timedelta):
        return (datetime.datetime.min + obj).time().isoformat()
    elif isinstance(obj, (str, basestring)):
        return obj.decode('utf-8')
    elif isinstance(obj, ObjectId):
        return '{}{}'.format(OBJ_PREFIX, str(obj))
    else:
        str(obj)
    # raise TypeError("%r is not JSON serializable" % obj)


def b64encode(data):
    payload = base64.b64encode(data)
    if PY3 and type(payload) is bytes:
        payload = payload.decode('ascii')
    return payload


def b64decode(payload):
    if PY3 and type(payload) is not bytes:
        payload = bytes(payload, 'ascii')
    return base64.b64decode(payload)


def sanitize(content):
    if content or content == 0:
        if content:
            try:
                return (u'%s' % content).replace(',', ';').replace('\n', ' ').replace('"', '').replace('\\', '')
            except:
                raise
        else:
            return u''
    else:
        return u''


def make_tar_file(source_file, output_name):
    """
    Tar/gzips a file or folder
    :param source_file: the source file of folder to zipped
    :param output_name: the output folder
    :return:
    """
    with tarfile.open(output_name, 'w:gz') as tar:
        tar.add(source_file, arcname=os.path.basename(source_file))


def to_boolean(string_expression):
    if not string_expression:
        return False
    if type(string_expression) == bool:
        return string_expression
    if type(string_expression) == int:
        return False if string_expression == 0 else True
    return True if string_expression in ['true', 'True', 'y', 'yes', '1'] else False


def assure_folder(folder_path):
    if not os.path.isdir(folder_path):
        os.makedirs(folder_path)


def merge_dicts(x_dict, y_dict):
    return x_dict.copy().update(y_dict)
