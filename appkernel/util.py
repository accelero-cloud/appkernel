import datetime, sys, os, tarfile, yaml

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


class Configurator(object):
    """
    Encapsulates application configuration. One can use it for retrieving various section form the configuration.
    Attributes:
        cwd     current working directory.
        cfg     the parsed configuration dictionary.
        config_file_name  global variable defining the config file.
    """
    config_file_name = 'cfg.yml'

    def __init__(self, logger, current_working_directory):
        """
        :param logger:
        :type logger: logging.Logger
        :param current_working_directory:
        """
        cwd = current_working_directory.rstrip('/')
        config_file = '%s/%s' % (cwd, Configurator.config_file_name)
        if not os.access(config_file, os.R_OK):
            logger.error('the config file [%s] is missing or not readable. Exiting...' % config_file)
            sys.exit(1)

        self.logger = logger

        # reading configuration
        with open(config_file, 'r') as ymlfile:
            try:
                self.cfg = yaml.load(ymlfile)
            except yaml.scanner.ScannerError as se:
                logger.exception('cannot read configuration file due to: %s' % str(se), se)
                sys.exit(1)

    def get_section(self, section_name):
        """
        :param section_name: the name of the configuration section, one needs to parse
        :return: a section identified by section name or None
        """
        return self.cfg.get(section_name)

    def get_value_for_section(self, section_name, config_key):
        """
        :param section_name: the name of the configuration section
        :param config_key: a key from the configuration section
        :return: the value identified by the section_name and config_key
        """
        section = self.get_section(section_name)
        return section.get(config_key) if section else None
