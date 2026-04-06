from __future__ import annotations

import getopt
import inspect
import logging
import os
import re
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TYPE_CHECKING

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from .authorisation import authorize_request
from .http_client import HttpClientConfig, configure_http_client, close_http_client
from .rate_limit import RateLimitConfig, RateLimiter, RateLimitMiddleware
from .infrastructure import CfgEngine
from .configuration import config
from .core import AppInitialisationError
from .iam import RbacMixin
from .model import Model
from .util import create_custom_error


@dataclass
class CorsConfig:
    """Configuration for Cross-Origin Resource Sharing (CORS).

    Pass to :meth:`AppKernelEngine.enable_cors` to allow browser-based
    clients on other origins to call the API.

    ``allow_origins`` must be set explicitly — there is no permissive default.
    Passing ``allow_origins=['*']`` with ``allow_credentials=True`` is invalid
    and raises ``ValueError`` at startup (browsers reject this combination).

    Call ``enable_cors()`` **last** in the middleware chain so that it wraps
    all other middleware and handles preflight OPTIONS requests before security
    or rate-limiting checks run.

    Args:
        allow_origins: Explicit list of permitted origins, e.g.
            ``['https://app.example.com']``. Use ``['*']`` to permit any
            origin (only valid when ``allow_credentials=False``).
        allow_methods: HTTP methods to permit in CORS requests.
        allow_headers: Request headers the browser is allowed to send.
        allow_credentials: Set ``True`` to include
            ``Access-Control-Allow-Credentials: true``. Requires an explicit
            origin list — incompatible with ``allow_origins=['*']``.
        expose_headers: Response headers the browser JS is allowed to read.
        max_age: Preflight response cache lifetime in seconds (default 600).
    """
    allow_origins: list[str] = field(default_factory=list)
    allow_methods: list[str] = field(default_factory=lambda: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    allow_headers: list[str] = field(default_factory=lambda: ['Authorization', 'Content-Type', 'Accept-Language'])
    allow_credentials: bool = False
    expose_headers: list[str] = field(default_factory=list)
    max_age: int = 600

if TYPE_CHECKING:
    from starlette.responses import Response


def get_option_value(option_dict: tuple[str, ...], opts: list[tuple[str, str]]) -> str | bool | None:
    for opt, arg in opts:
        if opt in option_dict:
            return arg or True
    return None


def get_cmdline_options() -> dict[str, Any]:
    argv = sys.argv[1:]
    opts, args = getopt.getopt(argv, 'c:dw:h:', ['config-dir=', 'development', 'working-dir=', 'db-host='])
    cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
    config_dir_param = get_option_value(('-c', '--config-dir'), opts)

    if config_dir_param:
        cfg_dir = f'{str(config_dir_param).rstrip("/")}/'
        cfg_dir = os.path.expanduser(cfg_dir)
        cfg_path = Path(cfg_dir)
        if not cfg_path.is_dir() or not os.access(cfg_dir, os.W_OK):
            raise AppInitialisationError(f'The config directory [{cfg_dir}] is not found/not writable.')
    else:
        cfg_dir = None

    working_dir_param = get_option_value(('-w', '--working-dir'), opts)
    if working_dir_param:
        cwd = os.path.expanduser(f'{str(config_dir_param).rstrip("/")}/')
        if not Path(cwd).is_dir() or not os.access(cwd, os.W_OK):
            raise AppInitialisationError(f'The working directory[{cwd}] is not found/not writable.')
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
    def __init__(self, cls: type) -> None:
        super().__init__(cls)
        self.cls = cls


class AppKernelEngine:

    def __init__(
        self,
        app_id: str,
        app: FastAPI | None = None,
        root_url: str = '/',
        log_level: int = logging.DEBUG,
        cfg_dir: str | None = None,
        development: bool = False,
        enable_defaults: bool = True,
        http_client_config: HttpClientConfig | None = None,
    ) -> None:
        assert app_id is not None, 'The app_id must be provided'
        assert re.match('[A-Za-z0-9-_]',
                        app_id), 'The app_id must be a single word, no space or special characters except - or _ .'
        self.logger = logging.getLogger(app_id)
        try:
            config.service_registry = {}
            config.url_rules = {}
            config.url_to_endpoint = {}
            self.before_request_functions: list[Callable] = []
            self.after_request_functions: list[Callable] = []
            self.app_id = app_id
            config.app_id = app_id
            self.root_url = root_url
            self.cmd_line_options = get_cmdline_options()
            self.cfg_dir = cfg_dir or self.cmd_line_options.get('cfg_dir')
            self.cfg_engine = CfgEngine(self.cfg_dir, optional=enable_defaults)
            config.cfg_engine = self.cfg_engine
            self.development = development or self.cmd_line_options.get('development')
            cwd = self.cmd_line_options.get('cwd')
            self.init_logger(log_folder=cwd, level=log_level)

            # MongoDB — AsyncIOMotorClient can be created without a running event loop
            db_host = self.cmd_line_options.get('db') or self.cfg_engine.get('appkernel.mongo.host', 'localhost')
            db_name = self.cfg_engine.get('appkernel.mongo.db', 'app')
            self.mongo_client = AsyncIOMotorClient(host=db_host)
            config.mongo_database = self.mongo_client[db_name]

            # Wire the FastAPI app with lifespan for clean startup/shutdown
            engine_ref = self
            _http_client_config = http_client_config

            @asynccontextmanager
            async def lifespan(fastapi_app: FastAPI):
                engine_ref.logger.info(f'===== Starting {engine_ref.app_id} =====')
                configure_http_client(_http_client_config)
                yield
                # Shutdown: close HTTP client, then Motor connection
                await close_http_client()
                if config and hasattr(config, 'mongo_database') and config.mongo_database is not None:
                    try:
                        engine_ref.mongo_client.close()
                        engine_ref.logger.info('MongoDB connection closed.')
                    except Exception:
                        pass

            self.app: FastAPI = app or FastAPI(title=app_id, lifespan=lifespan)
            assert self.app is not None, 'The FastAPI App must be provided as init parameter.'

            config.app = self.app
            config.app_engine = self
            self.__init_locale()
            self.__init_error_handlers()
        except (AppInitialisationError, AssertionError) as init_err:
            self.logger.error(str(init_err))
            sys.exit(-1)

    def enable_rate_limiting(self, cfg: RateLimitConfig | None = None) -> AppKernelEngine:
        """Enable in-process fixed-window rate limiting.

        Call this **after** ``enable_security()`` so that the rate-limit
        middleware is added last and therefore executes first — throttling
        requests before JWT validation is attempted.

        Args:
            cfg: Pool and window settings. Defaults to ``RateLimitConfig()``
                (medium-traffic profile: 100 req / 60 s per client IP).

        Returns:
            ``self`` for fluent chaining.

        Example::

            from appkernel import AppKernelEngine, RateLimitConfig

            kernel = AppKernelEngine('my-app', cfg_dir='./config')
            kernel.enable_security()
            kernel.enable_rate_limiting(
                RateLimitConfig(
                    requests_per_window=100,
                    window_seconds=60,
                    endpoint_limits={'/auth': 10},
                    exclude_paths=['/health'],
                )
            )
        """
        limiter = RateLimiter(cfg or RateLimitConfig())
        self.app.add_middleware(RateLimitMiddleware, limiter=limiter)
        return self

    def enable_cors(self, cfg: CorsConfig | None = None) -> AppKernelEngine:
        """Enable CORS support for browser-based cross-origin clients.

        Installs Starlette's ``CORSMiddleware`` with the provided configuration.
        Call this **last** in the middleware chain — middleware added last
        executes first, so CORS headers are set and preflight OPTIONS requests
        are resolved before security or rate-limiting checks run.

        Args:
            cfg: CORS configuration. Defaults to ``CorsConfig()`` (empty
                ``allow_origins`` list — same-origin only).

        Raises:
            ValueError: If ``allow_origins=['*']`` and
                ``allow_credentials=True`` are combined (rejected by browsers).

        Example::

            kernel = AppKernelEngine('my-app', cfg_dir='./config')
            kernel.enable_security()
            kernel.enable_rate_limiting()
            kernel.enable_cors(CorsConfig(
                allow_origins=['https://app.example.com'],
                allow_credentials=False,
            ))

        Returns:
            ``self`` for fluent chaining.
        """
        c = cfg or CorsConfig()
        if c.allow_credentials and c.allow_origins == ['*']:
            raise ValueError(
                "allow_credentials=True is incompatible with allow_origins=['*']. "
                "Browsers reject this combination. Specify explicit origins instead."
            )
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=c.allow_origins,
            allow_methods=c.allow_methods,
            allow_headers=c.allow_headers,
            allow_credentials=c.allow_credentials,
            expose_headers=c.expose_headers,
            max_age=c.max_age,
        )
        return self

    def enable_security(self, authorisation_method: Callable | None = None) -> AppKernelEngine:
        self.enable_pki()
        if not authorisation_method:
            authorisation_method = authorize_request
        self._security_authorisation_method = authorisation_method
        self.__init_security_middleware()
        config.security_enabled = True
        return self

    def enable_pki(self) -> None:
        if not hasattr(config, 'public_key'):
            self.__init_crypto()

    def add_before_request_function(self, func: Callable) -> None:
        self.before_request_functions.append(func)

    def add_after_request_function(self, func: Callable) -> None:
        self.after_request_functions.append(func)

    def __init_security_middleware(self) -> None:
        authorisation_method = self._security_authorisation_method

        class SecurityMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: Callable) -> Response:
                path = request.url.path
                method = request.method
                lookup_key = f'{method}:{path}'
                endpoint = config.url_to_endpoint.get(lookup_key)

                view_args: dict[str, str] = {}
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

    def __init_crypto(self) -> None:
        # Key path resolution order:
        #   1. APPKERNEL_PRIVATE_KEY_PATH / APPKERNEL_PUBLIC_KEY_PATH env vars
        #   2. appkernel.security.private_key_path / public_key_path in cfg.yml
        #   3. Default: {cfg_dir}/keys/appkernel.pem and appkernel.pub
        default_key_dir = Path(self.cfg_dir) / 'keys'
        private_key_path = (
            os.environ.get('APPKERNEL_PRIVATE_KEY_PATH')
            or self.cfg_engine.get('appkernel.security.private_key_path')
            or str(default_key_dir / 'appkernel.pem')
        )
        public_key_path = (
            os.environ.get('APPKERNEL_PUBLIC_KEY_PATH')
            or self.cfg_engine.get('appkernel.security.public_key_path')
            or str(default_key_dir / 'appkernel.pub')
        )
        with open(private_key_path, 'rb') as key_file:
            config.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
        with open(public_key_path, 'rb') as key_file:
            config.public_key = serialization.load_pem_public_key(
                key_file.read(),
                backend=default_backend()
            )

    def __init_locale(self) -> None:
        supported_languages: list[str] = []
        try:
            for supported_lang in self.cfg_engine.get('appkernel.i18n.languages', ['en-US']):
                supported_languages.append(supported_lang)
                if '-' in supported_lang:
                    supported_languages.append(supported_lang.split('-')[0])
        except Exception:
            supported_languages = ['en-US', 'en']

        the_supported_languages = supported_languages

        translations_dir: str | None = None
        if self.cfg_dir:
            for candidate_path in [
                os.path.join(self.cfg_dir, 'translations'),
                os.path.join(self.cfg_dir, 'tests', 'translations'),
                os.path.join(os.path.dirname(self.cfg_dir.rstrip('/')), 'translations'),
            ]:
                if Path(candidate_path).is_dir():
                    translations_dir = candidate_path
                    break

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
            async def dispatch(self, request: Request, call_next: Callable) -> Response:
                accept_language = request.headers.get('accept-language', 'en')
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
                if translations_dir:
                    try:
                        from babel.support import Translations
                        config.translations = Translations.load(translations_dir, [locale])
                    except Exception:
                        pass
                response = await call_next(request)
                return response

        self.app.add_middleware(LocaleMiddleware)

    def __init_error_handlers(self) -> None:
        @self.app.exception_handler(Exception)
        async def generic_exception_handler(request: Request, exc: Exception) -> Response:
            return self.generic_error_handler(exc)

        @self.app.exception_handler(404)
        async def not_found_handler(request: Request, exc: Exception) -> Response:
            msg = f'Not Found: {request.method} {request.url}'
            return create_custom_error(404, msg)

    def run(self) -> None:
        self.logger.info(f'===== Starting {self.app_id} =====')
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

    def init_logger(self, log_folder: str, level: int = logging.DEBUG) -> None:
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
            handler = RotatingFileHandler(f'{log_folder}/{file_name}', maxBytes=max_bytes,
                                          backupCount=backup_count)
            handler.setLevel(level)
        handler.setFormatter(formatter)
        self.logger.setLevel(level)
        self.logger.handlers = [handler]
        self.logger.info('Logger initialised')

    def generic_error_handler(self, ex: Exception | None = None, upstream_service: str | None = None) -> Response:
        code = getattr(ex, 'status_code', getattr(ex, 'code', 500))
        if not isinstance(code, int):
            code = 500
        if ex and code != 404:
            msg = f'{ex.__class__.__name__}/{str(ex)}'
            self.logger.exception(f'generic error handler: {ex.__class__.__name__}/{str(ex)}')
        elif ex and code == 404:
            msg = f'{ex.__class__.__name__}: {str(ex)}'
            self.logger.exception(f'generic error handler: {ex.__class__.__name__}/{str(ex)}')
        else:
            msg = 'Generic server error.'
            self.logger.warning(f'generic error handler: {ex.__class__.__name__}/{str(ex)}')
        return create_custom_error(code, msg, upstream_service=upstream_service)

    def teardown(self, exception: Exception | None) -> None:
        if exception is not None:
            self.logger.warning(exception.message if hasattr(exception, 'message') else str(exception))

    def register(
        self,
        service_class_or_instance: type | object,
        url_base: str | None = None,
        methods: list[str] | None = None,
        enable_hateoas: bool = True,
    ) -> ResourceController:
        methods = methods or ['GET']
        if inspect.isclass(service_class_or_instance):
            assert issubclass(service_class_or_instance, (
                Model)), 'Only subclasses of Model can be registered as class. If you want to register a controller, please use its instance.'

        from appkernel.service import expose_service
        expose_service(service_class_or_instance, self, url_base or self.root_url, methods=methods,
                       enable_hateoas=enable_hateoas)
        return ResourceController(service_class_or_instance)


def _parse_accept_language(header_value: str) -> list[str]:
    if not header_value:
        return ['en']
    parts: list[tuple[str, float]] = []
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


def _resolve_endpoint(method: str, path: str) -> tuple[str | None, dict[str, str]]:
    for pattern_key, endpoint in config.url_to_endpoint.items():
        stored_method, stored_path = pattern_key.split(':', 1)
        if stored_method != method:
            continue
        regex_pattern = re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', stored_path)
        regex_pattern = f'^{regex_pattern}$'
        match = re.match(regex_pattern, path)
        if match:
            return endpoint, match.groupdict()
    return None, {}
