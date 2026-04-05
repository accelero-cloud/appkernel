#!/usr/bin/python
import atexit
import getopt
import inspect
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Request
from pymongo import MongoClient
from starlette.middleware.base import BaseHTTPMiddleware

from .authorisation import authorize_request
from .infrastructure import CfgEngine
from .configuration import config
from .core import AppInitialisationError
from .iam import RbacMixin
from .model import Model
from .util import default_json_serializer, create_custom_error

try:
    import simplejson as json
except ImportError:
    import json


def get_option_value(option_dict, opts):
    for opt, arg in opts:
        if opt in option_dict:
            return arg or True
    return None


def get_cmdline_options():
    # working dir is also available on: self.app.root_path
    argv = sys.argv[1:]
    opts, args = getopt.getopt(argv, 'c:dw:h:', ['config-dir=', 'development', 'working-dir=', 'db-host='])
    cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
    # -- config directory
    config_dir_param = get_option_value(('-c', '--config-dir'), opts)

    if config_dir_param:
        cfg_dir = '{}/'.format(str(config_dir_param).rstrip('/'))
        cfg_dir = os.path.expanduser(cfg_dir)
        if not os.path.isdir(cfg_dir) or not os.access(cfg_dir, os.W_OK):
            raise AppInitialisationError('The config directory [{}] is not found/not writable.'.format(cfg_dir))
    else:
        cfg_dir = None

    # -- working directory
    working_dir_param = get_option_value(('-w', '--working-dir'), opts)
    if working_dir_param:
        cwd = os.path.expanduser('{}/'.format(str(config_dir_param).rstrip('/')))
        if not os.path.isdir(cwd) or not os.access(cwd, os.W_OK):
            raise AppInitialisationError('The working directory[{}] is not found/not writable.'.format(cwd))
    else:
        cwd = f'{cwd.rstrip("/")}'
    development = get_option_value(('-d', '--development'), opts)
    db_host = get_option_value(('-h', '--db-host'), opts)
    return {
        'cfg_dir': cfg_dir,
        'development': development,
        'cwd': cwd,
        'db': db_host
    }


class ResourceController(RbacMixin):
    def __init__(self, cls):
        super().__init__(cls)
        self.cls = cls


class AppKernelEngine(object):

    def __init__(self,
                 app_id: str,
                 app: FastAPI = None,
                 root_url: str = '/',
                 log_level=logging.DEBUG,
                 cfg_dir: str = None,
                 development: bool = False,
                 enable_defaults: bool = True):
        """
        Initialiser of AppKernel Engine.
        :param app: the FastAPI App
        :type app: FastAPI
        :param root_url: the url where the services are exposed to.
        :type root_url: str
        :param log_level: the level of log
        :param cfg_dir: the directory containing the cfg.yml file. If not provided it will be taken from the command line or from current working dir;
        :param development: the system will be initialised in development mode if True. If None, it will try to read the value as command line parameter or default to false;
        :type log_level: logging
        """
        assert app_id is not None, 'The app_id must be provided'
        assert re.match('[A-Za-z0-9-_]',
                        app_id), 'The app_id must be a single word, no space or special characters except - or _ .'
        self.app: FastAPI = app or FastAPI(title=app_id)
        assert self.app is not None, 'The FastAPI App must be provided as init parameter.'
        self.logger = logging.getLogger(app_id)
        try:
            config.service_registry = {}
            config.url_rules = {}
            config.url_to_endpoint = {}
            self.before_request_functions = []
            self.after_request_functions = []
            self.app_id = app_id
            self.root_url = root_url
            self.cmd_line_options = get_cmdline_options()
            self.cfg_dir = cfg_dir or self.cmd_line_options.get('cfg_dir')
            self.cfg_engine = CfgEngine(self.cfg_dir, optional=enable_defaults)
            config.cfg_engine = self.cfg_engine
            self.__init_locale()
            self.__init_error_handlers()
            self.development = development or self.cmd_line_options.get('development')
            cwd = self.cmd_line_options.get('cwd')
            self.init_logger(log_folder=cwd, level=log_level)
            atexit.register(self.shutdown_hook)
            # -- database host
            db_host = self.cmd_line_options.get('db') or self.cfg_engine.get('appkernel.mongo.host', 'localhost')
            db_name = self.cfg_engine.get('appkernel.mongo.db', 'app')
            self.mongo_client = MongoClient(host=db_host)
            config.mongo_database = self.mongo_client[db_name]
            config.app = self.app
            config.app_engine = self
        except (AppInitialisationError, AssertionError) as init_err:
            self.logger.error(str(init_err))
            sys.exit(-1)

    def enable_security(self, authorisation_method=None):
        self.enable_pki()
        if not authorisation_method:
            authorisation_method = authorize_request
        self._security_authorisation_method = authorisation_method
        self.__init_security_middleware()
        config.security_enabled = True
        return self

    def enable_pki(self):
        if not hasattr(config, 'public_key'):
            self.__init_crypto()

    def add_before_request_function(self, func):
        self.before_request_functions.append(func)

    def add_after_request_function(self, func):
        self.after_request_functions.append(func)

    def __init_security_middleware(self):
        authorisation_method = self._security_authorisation_method

        class SecurityMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                # Look up the endpoint from the URL path and method
                path = request.url.path
                method = request.method
                lookup_key = f'{method}:{path}'
                endpoint = config.url_to_endpoint.get(lookup_key)

                # Try pattern matching for parameterized routes
                view_args = {}
                if not endpoint:
                    endpoint, view_args = _resolve_endpoint(method, path)

                if endpoint and endpoint in config.service_registry:
                    result = authorisation_method(
                        method=method,
                        endpoint=endpoint,
                        headers=request.headers,
                        view_args=view_args
                    )
                    if result is not None:
                        return result
                response = await call_next(request)
                return response

        self.app.add_middleware(SecurityMiddleware)

    def __init_crypto(self):
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

    def __init_locale(self):
        supported_languages = []
        try:
            for supported_lang in self.cfg_engine.get('appkernel.i18n.languages', ['en-US']):
                supported_languages.append(supported_lang)
                if '-' in supported_lang:
                    supported_languages.append(supported_lang.split('-')[0])
        except Exception:
            supported_languages = ['en-US', 'en']

        the_supported_languages = supported_languages

        # Load translations if translations directory exists
        translations_dir = None
        if self.cfg_dir:
            for candidate_path in [
                os.path.join(self.cfg_dir, 'translations'),
                os.path.join(self.cfg_dir, 'tests', 'translations'),
                os.path.join(os.path.dirname(self.cfg_dir.rstrip('/')), 'translations'),
            ]:
                if os.path.isdir(candidate_path):
                    translations_dir = candidate_path
                    break

        # Try to load default (English) translations
        if translations_dir:
            try:
                from babel.support import Translations
                config.translations = Translations.load(translations_dir, ['en'])
                config.translations_dir = translations_dir
            except Exception:
                config.translations = None
                config.translations_dir = None
        else:
            config.translations = None
            config.translations_dir = None

        class LocaleMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                accept_language = request.headers.get('accept-language', 'en')
                # Simple best-match: parse Accept-Language and pick the first supported
                best = 'en'
                for lang in _parse_accept_language(accept_language):
                    if lang in the_supported_languages:
                        best = lang
                        break
                    short = lang.split('-')[0]
                    if short in the_supported_languages:
                        best = short
                        break
                locale = best.replace('-', '_')
                request.state.locale = locale
                # Update translations for this request's locale
                if translations_dir:
                    try:
                        from babel.support import Translations
                        config.translations = Translations.load(translations_dir, [locale])
                    except Exception:
                        pass
                response = await call_next(request)
                return response

        self.app.add_middleware(LocaleMiddleware)

    def __init_error_handlers(self):
        @self.app.exception_handler(Exception)
        async def generic_exception_handler(request: Request, exc: Exception):
            return self.generic_error_handler(exc)

        @self.app.exception_handler(404)
        async def not_found_handler(request: Request, exc):
            msg = f'Not Found: {request.method} {request.url}'
            return create_custom_error(404, msg)

    def run(self):
        self.logger.info('===== Starting {} ====='.format(self.app_id))
        try:
            import uvicorn
            port = self.cfg_engine.get('appkernel.server.port', 5000)
            binding_address = self.cfg_engine.get('appkernel.server.address', '0.0.0.0')
            self.logger.info(f'--> starting server |host: {binding_address}|port: {port}')
            uvicorn.run(self.app, host=binding_address, port=port,
                        log_level='debug' if self.development else 'info')
        except ImportError:
            self.logger.error('uvicorn is required to run the server. Install it with: pip install uvicorn')
            sys.exit(-1)

    def shutdown_hook(self):
        if config and hasattr(config, 'mongo_database') and config.mongo_database is not None:
            try:
                self.mongo_client.close()
            except Exception:
                pass

    def init_logger(self, log_folder, level=logging.DEBUG):
        assert log_folder is not None, 'The log folder must be provided.'
        if self.development:
            formatter = logging.Formatter("%(levelname)s - %(message)s")
            handler = logging.StreamHandler()
            handler.setLevel(level)
        else:
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s")
            max_bytes = self.cfg_engine.get('appkernel.logging.max_size', 10485760)
            backup_count = self.cfg_engine.get('appkernel.logging.backup_count', 3)
            file_name = self.cfg_engine.get(
                'appkernel.logging.file_name') or f"{self.app_id.replace(' ', '_').lower()}.log"
            handler = RotatingFileHandler('{}/{}'.format(log_folder, file_name), maxBytes=max_bytes,
                                          backupCount=backup_count)
            handler.setLevel(level)
        handler.setFormatter(formatter)
        self.logger.setLevel(level)
        self.logger.handlers = [handler]
        self.logger.info('Logger initialised')

    def generic_error_handler(self, ex: Exception = None, upstream_service: str = None):
        """
        Takes a generic exception and returns a json error message which will be returned to the client.
        :param ex: the exception which is reported by this method
        :param upstream_service: the service name which generated this error
        :return:
        """
        code = getattr(ex, 'status_code', getattr(ex, 'code', 500))
        if not isinstance(code, int):
            code = 500
        if ex and code != 404:
            msg = '{}/{}'.format(ex.__class__.__name__, str(ex))
            self.logger.exception('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        elif ex and code == 404:
            msg = '{}: {}'.format(ex.__class__.__name__, str(ex))
            self.logger.exception('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        else:
            msg = 'Generic server error.'
            self.logger.warning('generic error handler: {}/{}'.format(ex.__class__.__name__, str(ex)))
        return create_custom_error(code, msg, upstream_service=upstream_service)

    def teardown(self, exception):
        """
        context teardown based deallocation
        :param exception:
        :type exception: Exception
        :return:
        """
        if exception is not None:
            self.logger.warning(exception.message if hasattr(exception, 'message') else str(exception))

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


def _parse_accept_language(header_value):
    """Parse Accept-Language header and return list of languages sorted by quality."""
    if not header_value:
        return ['en']
    parts = []
    for part in header_value.split(','):
        part = part.strip()
        if ';' in part:
            lang, params = part.split(';', 1)
            q = 1.0
            for param in params.split(';'):
                param = param.strip()
                if param.startswith('q='):
                    try:
                        q = float(param[2:])
                    except ValueError:
                        q = 0.0
            parts.append((lang.strip(), q))
        else:
            parts.append((part, 1.0))
    parts.sort(key=lambda x: x[1], reverse=True)
    return [lang for lang, q in parts]


def _resolve_endpoint(method, path):
    """
    Try to match a request path against registered URL patterns to find the endpoint.
    This handles parameterized routes like /users/{object_id}.
    Returns (endpoint, view_args) tuple.
    """
    for pattern_key, endpoint in config.url_to_endpoint.items():
        stored_method, stored_path = pattern_key.split(':', 1)
        if stored_method != method:
            continue
        # Convert FastAPI path pattern to regex with named groups
        regex_pattern = re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', stored_path)
        regex_pattern = f'^{regex_pattern}$'
        match = re.match(regex_pattern, path)
        if match:
            return endpoint, match.groupdict()
    return None, {}
