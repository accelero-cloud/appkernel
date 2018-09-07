#!/usr/bin/python
import atexit
import getopt
import inspect
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

import eventlet.debug
import yaml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from flask import Flask, current_app, request, g
from flask_babel import Babel, get_locale
from pymongo import MongoClient
from werkzeug.exceptions import default_exceptions, HTTPException

from .authorisation import authorize_request
from .configuration import config
from .core import AppKernelException
from .iam import RbacMixin
from .model import Model
from .util import default_json_serializer, create_custom_error

try:
    import simplejson as json
except ImportError:
    import json

try:
    from flask import _app_ctx_stack as stack
except ImportError:
    from flask import _request_ctx_stack as stack


class AppKernelJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            return default_json_serializer(obj)
        except TypeError:
            pass
        return json.JSONEncoder.default(self, obj)


def get_cmdline_options():
    # working dir is also available on: self.app.root_path
    argv = sys.argv[1:]
    opts, args = getopt.getopt(argv, 'c:dw:', ['config-dir=', 'development', 'working-dir='])
    # -- config directory
    config_dir_provided, config_dir_param = AppKernelEngine.is_option_provided(('-c', '--config-dir'), opts, args)
    cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
    if config_dir_provided:
        cfg_dir = '{}/'.format(str(config_dir_param).rstrip('/'))
        cfg_dir = os.path.expanduser(cfg_dir)
        if not os.path.isdir(cfg_dir) or not os.access(cfg_dir, os.W_OK):
            raise AppInitialisationError('The config directory [{}] is not found/not writable.'.format(cfg_dir))
    else:
        cfg_dir = '{}/../'.format(cwd.rstrip('/'))

    # -- working directory
    working_dir_provided, working_dir_param = AppKernelEngine.is_option_provided(('-w', '--working-dir'), opts,
                                                                                 args)
    if working_dir_provided:
        cwd = os.path.expanduser('{}/'.format(str(config_dir_param).rstrip('/')))
        if not os.path.isdir(cwd) or not os.access(cwd, os.W_OK):
            raise AppInitialisationError('The working directory[{}] is not found/not writable.'.format(cwd))
    else:
        cwd = '{}/../'.format(cwd.rstrip('/'))
    development, param = AppKernelEngine.is_option_provided(('-d', '--development'), opts, args)
    return {
        'cfg_dir': cfg_dir,
        'development': development,
        'cwd': cwd
    }


class ResourceController(RbacMixin):
    def __init__(self, cls):
        super().__init__(cls)
        self.cls = cls


class AppInitialisationError(AppKernelException):

    def __init__(self, message):
        super().__init__(message)


class AppKernelEngine(object):

    def __init__(self,
                 app_id: str,
                 app: Flask = None,
                 root_url: str = '/',
                 log_level=logging.DEBUG,
                 cfg_dir: str = None,
                 development: bool = None,
                 enable_defaults: bool = False):
        """
        Initialiser of Flask Engine.
        :param app: the Flask App
        :type app: Flask
        :param root_url: the url where the service are exposed to.
        :type root_url: str
        :param log_level: the level of log
        :param cfg_dir: the directory containing the cfg.yml file. If not provided it will be taken from the command line or from current working dir;
        :param development: the system will be initialised in development mode if True. If None, it will try to read the value as command line parameter or default to false;
        :type log_level: logging
        """
        assert app_id is not None, 'The app_id must be provided'
        assert re.match('[A-Za-z0-9-_]',
                        app_id), 'The app_id must be a single word, no space or special characters except - or _ .'
        self.app: Flask = app or current_app
        assert self.app is not None, 'The Flask App must be provided as init parameter.'
        try:
            config.service_registry = {}
            self.before_request_functions = []
            self.after_request_functions = []
            self.app_id = app_id
            self.root_url = root_url
            self.__configure_flask_app()
            self.__init_web_layer()
            self.cmd_line_options = get_cmdline_options()
            self.cfg_dir = cfg_dir or self.cmd_line_options.get('cfg_dir')
            self.cfg_engine = CfgEngine(self.cfg_dir, optional=enable_defaults)
            config.cfg_engine = self.cfg_engine
            self.__init_babel()
            self.__init_cross_cutting_concerns()
            self.__init_event_loop()
            self.development = development or self.cmd_line_options.get('development')
            cwd = self.cmd_line_options.get('cwd')
            self.init_logger(log_folder=cwd, level=log_level)
            # -- initialisation
            # this can raise false positives if a bit of code running
            # longer than 1 seconds.
            # the timeout can be increased by adding the parameter:
            # resolution=3, where the value 3 represents 3 seconds.
            eventlet.debug.hub_blocking_detection(True, resolution=3)
            atexit.register(self.shutdown_hook)
            if hasattr(app, 'teardown_appcontext'):
                app.teardown_appcontext(self.teardown)
            else:
                app.teardown_request(self.teardown)
            # -- database host
            db_host = self.cfg_engine.get('appkernel.mongo.host') or 'localhost'
            db_name = self.cfg_engine.get('appkernel.mongo.db') or 'app'
            self.mongo_client = MongoClient(host=db_host)
            config.mongo_database = self.mongo_client[db_name]
            config.flask_app: Flask = self.app
            config.app_engine = self
        except (AppInitialisationError, AssertionError) as init_err:
            # print >> sys.stderr,
            self.app.logger.error(init_err.message)
            sys.exit(-1)

    def enable_security(self, authorisation_method=None):
        self.enable_pki()
        if not authorisation_method:
            authorisation_method = authorize_request
        self.add_before_request_function(authorisation_method)
        config.security_enabled = True
        return self

    def enable_pki(self):
        if not hasattr(self.app, 'public_key'):
            self.__init_crypto()

    def add_before_request_function(self, func):
        self.before_request_functions.append(func)

    def add_after_request_function(self, func):
        self.after_request_functions.append(func)

    @staticmethod
    def __init_event_loop():
        # todo: implement event loop
        # config.event_loop = asyncio.get_event_loop()
        pass

        def shutdown_eventloop():
            if 'event_loop' in config.__dict__ and config.event_loop and config.event_loop.is_running():
                logging.info('shutting down the event loop.')
                config.event_loop.shutdown_asyncgens()
                config.event_loop.stop()

        atexit.register(shutdown_eventloop)

    def __init_cross_cutting_concerns(self):
        def create_function_chain_executor(chain):
            def function_chain_executor():
                for func in chain:
                    return func()

            return function_chain_executor

        # todo: journaling request responses
        # todo: rate limiting
        self.app.before_request(create_function_chain_executor(self.before_request_functions))
        # todo: add after request processor
        # self.app.after_request(create_function_chain_executor(self.after_request_functions))

    def __init_crypto(self):
        # https://stackoverflow.com/questions/29650495/how-to-verify-a-jwt-using-python-pyjwt-with-public-key
        with self.app.app_context():
            with open('{}/keys/appkernel.pem'.format(self.cfg_dir), "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                    backend=default_backend()
                )
                config.private_key = private_key
            with open('{}/keys/appkernel.pub'.format(self.cfg_dir), 'rb') as key_file:
                public_key = serialization.load_pem_public_key(
                    key_file.read(),
                    backend=default_backend()
                )
                config.public_key = public_key

    def __init_babel(self):
        self.babel = Babel(self.app)
        # translations = Translations.load('translations')
        # translations.merge(Translations.load())
        # todo: support for multiple plugins
        supported_languages = []
        for supported_lang in self.cfg_engine.get('appkernel.i18n.languages') or ['en-US']:
            supported_languages.append(supported_lang)
            if '-' in supported_lang:
                supported_languages.append(supported_lang.split('-')[0])

        def get_current_locale():
            with self.app.app_context():
                best_match = request.accept_languages.best_match(supported_languages, default='en')
                return best_match.replace('-', '_')

        self.babel.localeselector(get_current_locale)
        # catalogs = gettext.find('locale', 'locale', all=True)
        # self.logger.info('Using message catalogs: {}'.format(catalogs))

    @property
    def logger(self):
        return self.app.logger

    def run(self):
        self.app.logger.info('===== Starting {} ====='.format(self.app_id))
        self.app.logger.debug(f'--> registered routes:\n {self.app.url_map}')
        # todo: make the threading and deployment configurable
        self.app.run(debug=self.development, threaded=True)
        # self.app.run(debug=self.development, processes=8)

    def shutdown_hook(self):
        if config.mongo_database:
            self.mongo_client.close()
        if self.app and self.app.logger:
            self.app.logger.info('======= Shutting Down {} ======='.format(self.app_id))

    @staticmethod
    def get_cmdline_options():
        # working dir is also available on: self.app.root_path
        argv = sys.argv[1:]
        opts, args = getopt.getopt(argv, 'c:dw:', ['config-dir=', 'development', 'working-dir='])
        # -- config directory
        config_dir_provided, config_dir_param = AppKernelEngine.is_option_provided(('-c', '--config-dir'), opts, args)
        cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
        if config_dir_provided:
            cfg_dir = '{}/'.format(str(config_dir_param).rstrip('/'))
            cfg_dir = os.path.expanduser(cfg_dir)
            if not os.path.isdir(cfg_dir) or not os.access(cfg_dir, os.W_OK):
                raise AppInitialisationError('The config directory [{}] is not found/not writable.'.format(cfg_dir))
        else:
            cfg_dir = '{}/../'.format(cwd.rstrip('/'))

        # -- working directory
        working_dir_provided, working_dir_param = AppKernelEngine.is_option_provided(('-w', '--working-dir'), opts,
                                                                                     args)
        if working_dir_provided:
            cwd = os.path.expanduser('{}/'.format(str(config_dir_param).rstrip('/')))
            if not os.path.isdir(cwd) or not os.access(cwd, os.W_OK):
                raise AppInitialisationError('The working directory[{}] is not found/not writable.'.format(cwd))
        else:
            cwd = '{}/../'.format(cwd.rstrip('/'))
        development, param = AppKernelEngine.is_option_provided(('-d', '--development'), opts, args)
        return {
            'cfg_dir': cfg_dir,
            'development': development,
            'cwd': cwd
        }

    @staticmethod
    def is_option_provided(option_dict, opts, args):
        for opt, arg in opts:
            if opt in option_dict:
                return True, arg
        return False, ''

    def __configure_flask_app(self):
        if hasattr(self.app, 'teardown_appcontext'):
            self.app.teardown_appcontext(self.teardown)
        else:
            self.app.teardown_request(self.teardown)
        if not hasattr(self.app, 'extensions'):
            self.app.extensions = {}
        self.app.extensions['appkernel'] = self

    def __init_web_layer(self):
        self.app.json_encoder = AppKernelJSONEncoder
        self.app.register_error_handler(Exception, self.generic_error_handler)
        for code in default_exceptions.keys():
            # add a default error handler for everything is unhandled
            self.app.register_error_handler(code, self.generic_error_handler)

            def set_locale_on_request():
                g.locale = str(get_locale())

            self.app.before_request(set_locale_on_request)

    def init_logger(self, log_folder, level=logging.DEBUG):
        assert log_folder is not None, 'The log folder must be provided.'
        if self.development:
            formatter = logging.Formatter("%(levelname)s - %(message)s")
            handler = logging.StreamHandler()
            handler.setLevel(level)
            self._enable_werkzeug_logger(handler)
        else:
            # self.cfg_engine.get_value_for_section()
            # log_format = ' in %(module)s [%(pathname)s:%(lineno)d]:\n%(message)s'
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s")
            max_bytes = self.cfg_engine.get('appkernel.logging.max_size') or 10485760
            backup_count = self.cfg_engine.get('appkernel.logging.backup_count') or 3
            file_name = self.cfg_engine.get('appkernel.logging.file_name') or '{}.log'.format(self.app_id)
            handler = RotatingFileHandler('{}/{}.log'.format(log_folder, file_name), maxBytes=max_bytes,
                                          backupCount=backup_count)
            # handler = TimedRotatingFileHandler('logs/foo.log', when='midnight', interval=1)
            handler.setLevel(level)
        handler.setFormatter(formatter)
        self.app.logger.setLevel(level)
        self.app.logger.addHandler(handler)
        self.app.logger.info('Logger initialised')

    @staticmethod
    def _enable_werkzeug_logger(handler):
        logger = logging.getLogger('werkzeug')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

    def generic_error_handler(self, ex: Exception = None, upstream_service: str = None):
        """
        Takes a generic exception and returns a json error message which will be returned to the client
        :param ex: the exception which is reported by this method
        :param upstream_service: the servicr name which generated this error
        :return:
        """
        code = (ex.code if isinstance(ex, HTTPException) else 500)
        if ex and code != 404:
            msg = '{}/{}'.format(ex.__class__.__name__, ex.description if isinstance(ex, HTTPException) else str(ex))
            self.logger.exception('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        elif ex and code == 404:
            msg = '{} ({} {}): {}'.format(ex.__class__.__name__, request.method, request.url,
                                          ex.description if isinstance(ex, HTTPException) else str(ex))
            self.logger.exception('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        else:
            msg = 'Generic server error.'
            self.logger.warn('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        return create_custom_error(code, msg, upstream_service=upstream_service)

    def teardown(self, exception):
        """
        context teardown based deallocation
        :param exception:
        :type exception: Exception
        :return:
        """
        if exception is not None:
            self.app.logger.warn(exception.message if hasattr(exception, 'message') else str(exception))

    def register(self, service_class_or_instance, url_base=None, methods=['GET'],
                 enable_hateoas=True) -> ResourceController:
        """

        :param service_class_or_instance:
        :param url_base:
        :param methods:
        :param enable_hateoas:
        :return:
        :rtype: Service
        """
        if inspect.isclass(service_class_or_instance):
            assert issubclass(service_class_or_instance, (
                Model)), 'Only subclasses of Model can be registered as class. If you want to register a controller, please use its instance.'

        from appkernel.service import expose_service
        expose_service(service_class_or_instance, self, url_base or self.root_url, methods=methods,
                       enable_hateoas=enable_hateoas)
        return ResourceController(service_class_or_instance)


class CfgEngine(object):
    """
    Encapsulates application configuration. One can use it for retrieving various section form the configuration.
    """

    def __init__(self, cfg_dir, config_file_name='cfg.yml', optional=False):
        """
        :param cfg_dir: the directory which holds the configuration files;
        :param config_file_name: the file name which contains the configuration (cfg.yml by default);
        :param optional: if True it will initialise even if config resource is not found (defaults to False);
        """
        self.optional = optional
        self.initialised = False
        config_file = '{}/{}'.format(cfg_dir.rstrip('/'), config_file_name)
        if not os.access(config_file, os.R_OK):
            if not optional:
                raise AppInitialisationError('The config file {} is missing or not readable. '.format(config_file))
            else:
                return

        with open(config_file, 'r') as ymlfile:
            try:
                self.cfg = yaml.load(ymlfile)
                self.initialised = True
            except yaml.scanner.ScannerError as se:
                raise AppInitialisationError('cannot read configuration file due to: {}'.format(config_file))

    def get(self, path_expression):
        """
        :param path_expression: a . (dot) separated path to the configuration value: 'appkernel.backup_count'
        :type path_expression: str
        :return:
        """
        assert path_expression is not None, 'Path expression should be provided.'

        nodes = path_expression.split('.')
        return self.get_value_for_path_list(nodes)

    def get_value_for_path_list(self, config_nodes, section_dict=None):
        """
        :return: a section (or value) under the given array keys
        """
        if not self.initialised:
            return
        assert isinstance(config_nodes, list), 'config_nodes should be a string list'
        if section_dict is None:
            section_dict = self.cfg
        if len(config_nodes) == 0:
            return None
        elif len(config_nodes) == 1:
            # final element
            return section_dict.get(config_nodes[0])
        else:
            key = config_nodes.pop(0)
            return self.get_value_for_path_list(config_nodes, section_dict.get(key))
