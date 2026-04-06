from __future__ import annotations

import asyncio
import inspect
import re
import types
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import Request
from .util import AppJSONResponse as JSONResponse

from appkernel.http_client import RequestHandlingException
from .configuration import config
from .core import AppKernelException
from .engine import AppKernelEngine
from .iam import RbacMixin, Denied
from .model import Model, PropertyRequiredException
from .dsl import get_argument_spec, OPS, tag_class_items
from .query import QueryProcessor
from .reflection import is_noncomplex, is_primitive, is_dictionary, is_dictionary_subclass
from .repository import xtract, Repository
from .util import create_custom_error
from .validators import ValidationException

try:
    import simplejson as json
except ImportError:
    import json


class ServiceException(AppKernelException):
    def __init__(self, http_error_code: int, message: str) -> None:
        super().__init__(message)
        self.http_error_code = http_error_code


pretty_print = True
qp = QueryProcessor()  # pylint: disable=C0103


def _hook(cls: type, inner_function: Callable, hook_method: str) -> Callable:
    async def wrapper(*args: Any, **kws: Any) -> Any:
        before_hook_method = f'before_{hook_method}'
        after_hook_method = f'after_{hook_method}'
        if hasattr(cls, before_hook_method):
            getattr(cls, before_hook_method)(*args, **kws)
        if not args:
            inner_result = await inner_function(**kws)
        else:
            inner_result = await inner_function(*args, **kws)
        if hasattr(cls, after_hook_method):
            # P5: run after-hooks as background tasks so they don't delay the response
            after_func = getattr(cls, after_hook_method)
            if asyncio.iscoroutinefunction(after_func):
                asyncio.create_task(after_func(inner_result, *args, **kws))
            else:
                async def _run_sync_hook(fn: Callable, *a: Any, **kw: Any) -> None:
                    fn(*a, **kw)
                asyncio.create_task(_run_sync_hook(after_func, inner_result, *args, **kws))
        return inner_result

    wrapper.inner_function = inner_function
    return wrapper


def _flask_to_fastapi_path(path_param):
    """Convert Flask-style URL parameters to FastAPI-style.
    E.g. <string:object_id> -> {object_id}, <object_id> -> {object_id}
    """
    return re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', path_param)


def url_for_endpoint(endpoint: str, **kwargs: Any) -> str:
    """Generate a URL for the given endpoint name, substituting path parameters."""
    rule = config.url_rules.get(endpoint, '/')
    url = re.sub(r'\{(\w+)\}', lambda m: str(kwargs.get(m.group(1), '')), rule)
    return url


def _add_app_rule(cls, url_base: str, method_name: str, view_function: Callable, path_param: str = '', **options):
    """
    Registers the service in the service registry and adds a route to FastAPI.
    """
    clazz_name = xtract(cls).lower()
    base_name = f'{url_base}{clazz_name}'
    if path_param and path_param.startswith('./'):
        rule = f'{base_name}/{path_param[2:]}'
    elif path_param and not path_param.startswith('/'):
        rule = f'{base_name}/{path_param}'
    elif path_param and path_param.startswith('/'):
        rule = path_param
    else:
        rule = f'{base_name}/'
    # Convert Flask-style path params to FastAPI-style
    rule = _flask_to_fastapi_path(rule)
    endpoint = f'{clazz_name}_{method_name}_{options.get("methods")[0].lower()}'
    config.service_registry[endpoint] = cls
    config.url_rules[endpoint] = rule

    http_methods = options.get('methods', ['GET'])

    # Register the URL-to-endpoint mapping for security middleware
    for m in http_methods:
        config.url_to_endpoint[f'{m}:{rule}'] = endpoint

    # Create an async wrapper that extracts request data and calls the sync view function
    async def _make_handler(request: Request):
        # Read body
        body = await request.body()
        json_body = None
        form_data = {}
        if body:
            content_type = request.headers.get('content-type', '')
            if 'json' in content_type or (body and (body.startswith(b'{') or body.startswith(b'['))):
                try:
                    json_body = await request.json()
                except Exception:
                    json_body = None
            if json_body is None and ('form' in content_type or 'urlencoded' in content_type):
                try:
                    form_data_raw = await request.form()
                    # Convert FormData to a proper dict with lists for multi-values
                    target = defaultdict(list)
                    for key, value in form_data_raw.multi_items():
                        target[key].append(value)
                    form_data = {key: value[0] if len(value) == 1 else value for key, value in target.items()}
                except Exception:
                    form_data = {}

        path_params = dict(request.path_params)

        # Build request_data dict
        request_data = {
            'method': request.method,
            'query_params': request.query_params,
            'body': body,
            'json_body': json_body,
            'form_data': form_data,
            'headers': request.headers,
            'path_params': path_params,
        }

        # Await the async view function
        return await view_function(request_data=request_data, **path_params)

    # Use include_in_schema=False to avoid FastAPI trying to parse the request parameter
    config.app.add_api_route(rule, _make_handler, methods=http_methods, name=endpoint, include_in_schema=False)


model_endpoints = {
    'find_by_query': [
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.find_by_query, 'on_get'), cls),
            'method': 'GET'
        }
    ],
    'find_by_id': [
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.find_by_id, 'get'), cls),
            'method': 'GET',
            'param': '{object_id}'
        }
    ],
    'aggregate': [
        {
            'func': lambda cls, engine: _execute(cls, engine, cls.aggregate, cls),
            'method': 'GET',
            'param': 'aggregate/'
        }
    ],
    'save_object': [
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.save_object, 'post'), cls),
            'method': 'POST'
        },
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.patch_object, 'patch'), cls),
            'method': 'PATCH',
            'param': '{object_id}'
        }
    ],
    'replace_object': [
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.replace_object, 'put'), cls),
            'method': 'PUT'
        }
    ],
    'delete_by_id': [
        {
            'func': lambda cls, engine: _execute(cls, engine, _hook(cls, cls.delete_by_id, 'delete'), cls),
            'method': 'DELETE',
            'param': '{object_id}'
        }
    ]
}


def expose_service(clazz_or_instance: type | Any, app_engine: AppKernelEngine, url_base: str, methods: list[str],
                   enable_hateoas: bool = True) -> None:
    """
    :param clazz_or_instance: the class name of the service which is going to be exposed
    :param enable_hateoas: if enabled (default) it will expose the service descriptors
    :param methods: the HTTP methods allowed for this service
    :param url_base: the url where the service is exposed
    :type url_base: basestring
    :param app_engine: the app kernel engine
    :type app_engine: AppKernelEngine
    :return:
    """
    clazz = clazz_or_instance if inspect.isclass(clazz_or_instance) else clazz_or_instance.__class__
    if not issubclass(clazz, Model):
        # tag the service class on the fly
        for key, value in tag_class_items(clazz.__name__, clazz.__dict__).items():
            setattr(clazz, key, value)

    if not url_base.endswith('/'):
        url_base = f'{url_base}/'

    clazz = clazz_or_instance if inspect.isclass(clazz_or_instance) else clazz_or_instance.__class__
    clazz.methods = methods
    clazz.enable_hateoas = enable_hateoas
    class_methods = [cm for cm in dir(clazz_or_instance) if
                     not cm.startswith('_') and callable(getattr(clazz_or_instance, cm))]
    if inspect.isclass(clazz_or_instance):
        if issubclass(clazz_or_instance, Model):
            _add_app_rule(clazz_or_instance, url_base, 'schema',
                          _create_simple_wrapper_executor(clazz_or_instance, app_engine,
                                                          clazz_or_instance.get_json_schema),
                          path_param='schema', methods=['GET'])
            _add_app_rule(clazz_or_instance, url_base, 'meta',
                          _create_simple_wrapper_executor(clazz_or_instance, app_engine,
                                                          clazz_or_instance.get_parameter_spec),
                          path_param='meta', methods=['GET'])

        if issubclass(clazz_or_instance, (Model, Repository)):
            for method in class_methods:
                mdef_list = model_endpoints.get(method)
                if mdef_list:
                    for mdef in mdef_list:
                        func = mdef.get('func')
                        path_param = mdef.get('param', '')
                        _add_app_rule(clazz_or_instance, url_base, method, func(clazz_or_instance, app_engine),
                                      path_param=path_param,
                                      methods=[mdef.get('method')])

    setup_security = hasattr(config, 'security_enabled') and config.security_enabled
    cls_items = clazz_or_instance.__dict__ if inspect.isclass(
        clazz_or_instance) else clazz_or_instance.__class__.__dict__
    _prepare_actions(clazz_or_instance if inspect.isclass(clazz_or_instance) else clazz_or_instance.__class__, url_base,
                     enable_security=setup_security, class_items=cls_items)
    _prepare_resources(clazz_or_instance, url_base, enable_security=setup_security, class_items=cls_items)


def __get_http_methods(tagged_item):
    """
    extracts the http methods for a tagged link or resource decorator
    """
    def default_method(args):
        return ['POST'] if len(args) > 0 else ['GET']

    tag_args = tagged_item.get('argspec')
    http_methods = tagged_item.get('decorator_kwargs').get('method', default_method(tag_args))
    if not isinstance(http_methods, list):
        http_methods = [http_methods]
    return http_methods


def _prepare_resources(clazz_or_instance: type | Any, url_base: str, enable_security: bool = False, class_items: dict | None = None) -> None:
    # Construct the singleton instance eagerly at registration time so there is
    # no read-check-write race when concurrent requests hit an unregistered controller.
    instance = clazz_or_instance() if inspect.isclass(clazz_or_instance) else clazz_or_instance

    def create_resource_executor(function_name):
        async def resource_executor(request_data=None, **named_args):
            clazz = instance.__class__
            try:
                executable_method = getattr(instance, function_name)
                request_and_posted_arguments = _get_request_args(request_data)
                request_and_posted_arguments.update(named_args)

                payload = _extract_dict_from_payload(request_data)
                if '_type' in payload:
                    mdl = Model.load_and_or_convert_object(payload)
                    boxed = _autobox_parameters(executable_method, request_and_posted_arguments)
                    result = await executable_method(mdl, **boxed) if asyncio.iscoroutinefunction(executable_method) \
                        else executable_method(mdl, **boxed)
                else:
                    request_and_posted_arguments.update(payload)
                    boxed = _autobox_parameters(executable_method, request_and_posted_arguments)
                    result = await executable_method(**boxed) if asyncio.iscoroutinefunction(executable_method) \
                        else executable_method(**boxed)
                result_dic_tentative = {} if result is None else _xvert(clazz, result)
                return JSONResponse(content=result_dic_tentative, status_code=200)
            except Exception as exc:
                config.app_engine.logger.exception(exc)
                return config.app_engine.generic_error_handler(exc, upstream_service=clazz.__name__)

        return resource_executor

    if 'resources' in class_items:
        # Sort resources: static paths first, parameterized paths last
        # This ensures FastAPI matches specific routes before catch-all parameterized routes
        sorted_resources = sorted(class_items.get('resources'),
                                   key=lambda r: ('<' in r.get('decorator_kwargs').get('path', ''),
                                                   r.get('function_name')))
        for resource in sorted_resources:
            func_name = resource.get('function_name')
            methods = __get_http_methods(resource)
            path_segment = resource.get('decorator_kwargs').get('path', f'./{func_name.lower()}')
            _add_app_rule(clazz_or_instance, url_base, func_name, create_resource_executor(func_name),
                          path_param=path_segment, methods=methods)

        if enable_security:
            required_permissions = resource.get('decorator_kwargs').get('require', Denied())
            RbacMixin.set_list(cls=clazz_or_instance, methods=methods, permissions=required_permissions,
                               endpoint=f'{xtract(clazz_or_instance).lower()}_{func_name}_{methods[0].lower()}')


def _prepare_actions(cls: type, url_base: str, enable_security: bool = False, class_items: dict | None = None) -> None:
    def create_action_executor(function_name):
        async def action_executor(request_data=None, **named_args):
            if 'object_id' not in named_args:
                msg = 'The object_id property is required for this action to execute'
                return create_custom_error(400, msg, cls.__name__)
            else:
                try:
                    instance = await cls.find_by_id(named_args['object_id'])
                    executable_method = getattr(instance, function_name)
                    request_and_posted_arguments = _get_request_args(request_data)
                    request_and_posted_arguments.update(_extract_dict_from_payload(request_data))
                    boxed = _autobox_parameters(executable_method, request_and_posted_arguments)
                    result = await executable_method(**boxed) if asyncio.iscoroutinefunction(executable_method) \
                        else executable_method(**boxed)
                    result_dic_tentative = {} if result is None else _xvert(cls, result)
                    return JSONResponse(content=result_dic_tentative, status_code=200)
                except ServiceException as sexc:
                    config.app_engine.logger.warning(f'Service error: {sexc}')
                    return create_custom_error(sexc.http_error_code, sexc.message, cls.__name__)
                except Exception as exc:
                    config.app_engine.logger.exception(exc)
                    return config.app_engine.generic_error_handler(exc, upstream_service=cls.__name__)

        return action_executor

    if 'actions' in class_items:
        for this_link in cls.actions:
            func_name = this_link.get('function_name')
            relation = this_link.get('decorator_kwargs').get('rel', func_name)
            methods = __get_http_methods(this_link)
            _add_app_rule(cls, url_base, relation, create_action_executor(func_name),
                          path_param=f'{{object_id}}/{relation}', methods=methods)
            if enable_security:
                required_permissions = this_link.get('decorator_kwargs').get('require', Denied())
                RbacMixin.set_list(cls=cls, methods=methods, permissions=required_permissions,
                                   endpoint=f'{xtract(cls).lower()}_{relation}_{methods[0].lower()}')


def _extract_dict_from_payload(request_data=None):
    if request_data is None:
        return {}
    json_body = request_data.get('json_body')
    body = request_data.get('body', b'')
    form_data = request_data.get('form_data', {})

    if json_body is not None:
        return json_body
    elif body and len(body) > 0:
        # Try to parse as JSON
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            pass
    if form_data and len(form_data) > 0:
        return _xtract_form(form_data)
    return {}


def _xtract_form(form_data):
    """Extract form data into a dict. Values that are single-element lists are unwrapped."""
    if hasattr(form_data, 'multi_items'):
        # Starlette FormData
        target = defaultdict(list)
        for key, value in form_data.multi_items():
            target[key].append(value)
        return {key: value[0] if len(value) == 1 else value for key, value in target.items()}
    elif isinstance(form_data, dict):
        return form_data
    else:
        return dict(form_data)


def _get_merged_request_and_named_args(named_args, request_data=None):
    """
    Merge together the named args (url parameters) and the query parameters
    """
    named_and_request_arguments = named_args.copy()
    named_and_request_arguments.update(_get_request_args(request_data))
    return named_and_request_arguments


def _get_request_args(request_data=None):
    request_args = {}
    if request_data is None:
        return request_args
    query_params = request_data.get('query_params')
    if query_params:
        for arg in query_params:
            query_item = {arg: query_params.get(arg)}
            request_args.update(query_item)
    return request_args


def _create_simple_wrapper_executor(cls, app_engine, provisioner_method):
    async def create_executor(request_data=None, *args, **named_args):
        try:
            result = provisioner_method(*args, **named_args)
            return JSONResponse(content=result, status_code=200)
        except Exception as genex:
            return app_engine.generic_error_handler(genex, upstream_service=cls.__name__)

    return create_executor


def _execute(cls, app_engine: AppKernelEngine, provisioner_method: Callable, model_class: Model):
    """
    The main view function for FastAPI routes.
    :param app_engine: the app engine instance
    :param provisioner_method: the method on our service object which will be executed
    :param model_class: the class of the model
    :return: the result generated by the service
    """
    executable_method = provisioner_method.inner_function if isinstance(provisioner_method,
                                                                        types.FunctionType) and hasattr(
        provisioner_method, 'inner_function') else provisioner_method

    async def create_executor(request_data=None, **named_args):
        try:
            return_code = 200
            named_and_request_arguments = _get_merged_request_and_named_args(named_args, request_data)
            query_params = request_data.get('query_params') if request_data else {}
            method = request_data.get('method', 'GET') if request_data else 'GET'

            if QueryProcessor.supports_query(executable_method):
                query_param_names = QueryProcessor.get_query_param_names(
                    executable_method, set(query_params.keys()) if query_params else set())
                if query_param_names and len(query_param_names) > 0:
                    named_and_request_arguments.update(
                        query=convert_to_query(query_param_names, query_params))

                    for query_param_name in query_param_names:
                        if query_param_name in named_and_request_arguments:
                            del named_and_request_arguments[query_param_name]
                elif query_params and 'query' in list(query_params.keys()):
                    named_and_request_arguments.update(query=json.loads(query_params.get('query')))

            if method in ['POST', 'PUT']:
                model_instance = Model.from_dict(_extract_dict_from_payload(request_data), model_class)
                named_and_request_arguments.update(model=model_instance)
                return_code = 201
            elif method == 'PATCH':
                named_and_request_arguments.update(document=_extract_dict_from_payload(request_data))
            result = await provisioner_method(
                **_autobox_parameters(executable_method, named_and_request_arguments))
            if method in ['GET', 'PUT', 'PATCH']:
                if result is None:
                    object_id = named_args.get('object_id', None)
                    id_part = f' with id {object_id}' if object_id else ''
                    return create_custom_error(404, f'Document{id_part} is not found.', cls.__name__)
            if method == 'DELETE' and isinstance(result, int) and result == 0:
                return create_custom_error(404,
                    f'Document with id {named_args.get("object_id", "-1")} was not deleted.', cls.__name__)
            if result is None or isinstance(result, list) and len(result) == 0:
                return_code = 204
            result_dic_tentative = {} if result is None else _xvert(cls, result)
            return JSONResponse(content=result_dic_tentative, status_code=return_code)
        except PropertyRequiredException as pexc:
            app_engine.logger.warning(f'missing parameter: {pexc.__class__.__name__}/{pexc}')
            return create_custom_error(400, str(pexc), cls.__name__)
        except ValidationException as vexc:
            app_engine.logger.warning(f'validation error: {vexc}')
            return create_custom_error(400, f'{vexc.__class__.__name__}/{vexc}', cls.__name__)
        except PermissionError as pexc:
            app_engine.logger.warning(f'permission denied: {pexc}')
            return create_custom_error(403, str(pexc), cls.__name__)
        except RequestHandlingException as rexc:
            app_engine.logger.error(f'request forwarding error: {str(rexc)}')
            app_engine.logger.exception(rexc)
            return create_custom_error(rexc.status_code, rexc.message, rexc.upstream_service)
        except Exception as exc:
            return app_engine.generic_error_handler(exc, upstream_service=cls.__name__)

    # add supported method parameter names to the list of reserved keywords
    qp.add_reserved_keywords(executable_method)
    return create_executor


def convert_to_query(query_param_names: set[str], request_args: Any) -> dict[str, Any]:
    """
    Result example: ::

        ?first_name={firstName}&last_name={lastName}&birth_date={birthDate}

    Supported query formats:
    The value of first_name, last_name and birth_date is exactly the ones in the list.
    Converted to: ::

        {"$and":[
            {"first_name":{firstName}},
            {"last_name":{lastName}},
            {"birth_date":{birthDate}}
            ]}

    ?first_name=~{firstName}
    The first name contains a given value;
    Converted to: ::

        {"first_name" : "/.*{firstName}.*/i"}

    ?birth_date=>{birthDate}
    Birth date after the given parameter (inclusive >=)
    Converted to: ::

        {"birth_date": {$gte:{birthDate}}}

    Another query format: ?birth_date=>{birthDate}&?birth_date=<{birthDate}
    Birth date between the two parameters, with date pattern matching if applies.
    Converted to: ::

        {"birth_date": [{$gte:{birthDate},{"$lt":{birthDate}}]}}

    Collection query: ?state:[NEW, CLOSED]
    The state of a give content among the provided patterns.
    Converted to: ::

        {"state":{"$in":["NEW", "CLOSED"]}}

    :param query_param_names: the names of all query parameters as a set; example set(['birth_date','logic'])
    :type query_param_names: set
    :param request_args: the names and the values of the query parameters; must support .getlist() and .get() methods
    :return: the query expression which than can be converted to repository specific queries (eg. Mongo or SQL query)
    :rtype: dict
    """
    query_dict = defaultdict(list)
    for arg in request_args:
        if arg != 'logic' and arg in query_param_names:
            # the keyword 'logic' is handled separately
            if hasattr(request_args, 'getlist'):
                query_dict[arg] = request_args.getlist(arg)
            else:
                # fallback for plain dict
                val = request_args.get(arg)
                query_dict[arg] = val if isinstance(val, list) else [val]

    expression_list = []
    for query_item in [[key, val] for key, val in query_dict.items()]:
        if isinstance(query_item[1], list) and len(query_item[1]) > 1:
            value_list = [_remap_expressions(expr) for expr in query_item[1]]
            if isinstance(value_list[0], tuple):
                expression_list.append(
                    {query_item[0]: dict(value_list)})
            else:
                for val in value_list:
                    expression_list.append({query_item[0]: val})
        else:
            mapped_value = _remap_expressions(query_item[1][0])
            if isinstance(mapped_value, tuple):
                expression_list.append({query_item[0]: dict([mapped_value])})
            else:
                expression_list.append({query_item[0]: mapped_value})

    if len(expression_list) == 0:
        return {}
    elif len(expression_list) == 1:
        return expression_list[0]
    else:
        logic = str(OPS.__getattr__(request_args.get('logic', 'and').upper()))
        return {logic: expression_list}


def _remap_expressions(expression: Any) -> Any:
    """
    Takes a query expression such as >1994-12-02 and turns into a {'$gte':'1994-12-02'}.
    Additionally converts the date string into datetime object;
    """
    if expression[0] in qp.supported_expressions:
        converted_value = _convert_expressions(expression[1:])
        return qp.expression_mapper.get(expression[0])(converted_value)
    else:
        return _convert_expressions(expression)


def _convert_expressions(expression: Any) -> Any:
    """
    converts strings containing numbers to int, string containing a date to datetime,
    string containing a boolean expression to boolean
    """
    if isinstance(expression, str):
        if qp.number_pattern.match(expression):
            return int(expression)
        if qp.boolean_pattern.match(expression):
            return True if expression in ['true', 'True', 'y', 'yes'] else False
        for date_pattern in qp.date_patterns.keys():
            if date_pattern.match(expression):
                for parser_format_matcher in qp.date_separator_patterns.keys():
                    if parser_format_matcher.match(expression):
                        date_parser_pattern = qp.date_patterns.get(date_pattern)
                        separator = qp.date_separator_patterns.get(parser_format_matcher)
                        return datetime.strptime(expression, date_parser_pattern.format(separator))
    return expression


def _autobox_parameters(provisioner_method: Callable, arguments: dict[str, Any]) -> dict[str, Any]:
    method_structure = get_argument_spec(provisioner_method)
    for arg_key, arg_value in arguments.items():
        required_type = type(method_structure.get(arg_key))
        provided_type = type(arg_value)
        if required_type is not type(None) and provided_type is not type(None) and required_type != provided_type:
            if issubclass(required_type, Enum):
                arguments[arg_key] = required_type[arg_value]
            elif issubclass(required_type, list) and provided_type in [str, str, str]:
                if qp.csv_pattern.match(arg_value):
                    arguments[arg_key] = [int(item) if item.isdigit() else item.strip('"').strip('\'') for item in
                                          arg_value.split(',')]
                else:
                    try:
                        result = json.loads(arg_value)
                        if isinstance(result, list):
                            arguments[arg_key] = result
                        else:
                            arguments[arg_key] = [result]
                    except ValueError:
                        pass
            elif issubclass(required_type, dict) and provided_type in [str, str, str]:
                try:
                    arguments[arg_key] = json.loads(arg_value)
                except ValueError:
                    pass
            else:
                arguments[arg_key] = required_type(arg_value)
    return arguments


def _xvert(cls: type, result_item: Any, generate_links: bool = True) -> dict[str, Any] | None:
    """
    converts the response object into a dict for JSON serialization
    """
    if isinstance(result_item, Model):
        model = Model.to_dict(result_item, skip_omitted_fields=True)
        if '_type' not in model:
            model.update(_type=cls.__name__)
        if hasattr(cls, 'enable_hateoas') and cls.enable_hateoas and generate_links:
            model.update(_links=_calculate_links(cls, result_item.id))
        return model
    elif is_dictionary(result_item) or is_dictionary_subclass(result_item):
        return result_item
    elif isinstance(result_item, (list, set, tuple)):
        result = {
            '_type': result_item.__class__.__name__,
            '_items': [_xvert(cls, item, generate_links=False) for item in result_item]
        }
        if hasattr(cls, 'enable_hateoas') and cls.enable_hateoas:
            result.update(_links={'self': {'href': url_for_endpoint(f'{xtract(cls).lower()}_find_by_query_get')}})
        return result
    elif is_primitive(result_item) or isinstance(result_item, (str, int)) or is_noncomplex(result_item):
        return {'_type': 'OperationResult', 'result': result_item}


def _calculate_links(cls: type, object_id: Any) -> dict[str, Any] | None:
    links = {}
    clazz_name = xtract(cls).lower()
    all_members = cls.__dict__
    if 'actions' in all_members:
        for this_link in all_members.get('actions'):
            func_name = this_link.get('function_name')
            decorator_args = this_link.get('decorator_kwargs')
            rel = decorator_args.get('rel', func_name)
            args = [key for key in this_link.get('argspec').keys()]
            http_methods = decorator_args.get('method', 'POST' if len(args) > 0 else 'GET')
            method_lower = http_methods[0].lower() if isinstance(http_methods, list) else http_methods.lower()
            endpoint_name = f'{clazz_name}_{rel}_{method_lower}'
            href = url_for_endpoint(endpoint_name, object_id=object_id)

            links[rel] = {
                'href': href,
                'methods': http_methods
            }
            if args and len(args) > 0:
                links[rel].update(args=args)

        links['self'] = {
            'href': url_for_endpoint(f'{clazz_name}_find_by_id_get', object_id=object_id),
            'methods': cls.methods
        }
        links['collection'] = {
            'href': url_for_endpoint(f'{clazz_name}_find_by_query_get'),
            'methods': 'GET'
        }
        return links
