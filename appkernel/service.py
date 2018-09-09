import inspect
import types
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Callable

from flask import jsonify, request, url_for
from werkzeug.datastructures import MultiDict, ImmutableMultiDict

from appkernel.http_client import RequestHandlingException
from .configuration import config
from .core import AppKernelException
from .engine import AppKernelEngine
from .iam import RbacMixin, Denied
from .model import Model, PropertyRequiredException, get_argument_spec, OPS, tag_class_items
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
    def __init__(self, http_error_code, message):
        super().__init__(message)
        self.http_error_code = http_error_code


pretty_print = True
qp = QueryProcessor()  # pylint: disable=C0103
"""
The Flask App is set on this instance, so one can use the context:
with self.app_context():
    some_variable = some_context_aware_function()
"""


def _hook(cls, inner_function: Callable, hook_method: str):
    def wrapper(*args, **kws):
        before_hook_method = f'before_{hook_method}'
        after_hook_method = f'after_{hook_method}'
        if hasattr(cls, before_hook_method):
            getattr(cls, before_hook_method)(*args, **kws)
        if not args:
            inner_result = inner_function(**kws)
        else:
            inner_result = inner_function(*args, **kws)
        if hasattr(cls, after_hook_method):
            getattr(cls, after_hook_method)(inner_result, *args, **kws)
        return inner_result

    wrapper.inner_function = inner_function
    return wrapper


def _add_app_rule(cls, url_base: str, method_name: str, view_function: Callable, path_param: str = '', **options):
    """
    Registers the service in the service registry and adds the rule to flask with the view function.
    :param rule:
    :param endpoint:
    :param view_function:
    :param options:
    :return:
    """
    clazz_name = xtract(cls).lower()
    base_name = '{}{}'.format(url_base, clazz_name)
    if path_param and path_param.startswith('./'):
        rule = f'{base_name}/{path_param[2:]}'
    elif path_param and not path_param.startswith('/'):
        rule = f'{base_name}/{path_param}'
    elif path_param and path_param.startswith('/'):
        rule = path_param
    else:
        rule = f'{base_name}/'
    endpoint = '{}_{}_{}'.format(clazz_name, method_name, options.get('methods')[0].lower())
    config.service_registry[endpoint] = cls
    config.flask_app.add_url_rule(rule, endpoint, view_function, **options)


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
            'param': '<string:object_id>'
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
            'param': '<string:object_id>'
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
            'param': '<object_id>'
        }
    ]
}


def expose_service(clazz_or_instance, app_engine: AppKernelEngine, url_base: str, methods: list,
                   enable_hateoas: bool = True):
    """
    :param clazz_or_instance: the class name of the service which is going to be exposed
    :param enable_hateoas: if enabled (default) it will expose the the service descriptors
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
        url_base = '{}/'.format(url_base)

    clazz = clazz_or_instance if inspect.isclass(clazz_or_instance) else clazz_or_instance.__class__
    clazz.methods = methods  # todo: check the usage of this
    clazz.enable_hateoas = enable_hateoas  # todo: check the usage of this
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
    :param tagged_item:
    :return: the list of http methods
    """

    def default_method(args):
        return ['POST'] if len(args) > 0 else ['GET']

    tag_args = tagged_item.get('argspec')
    http_methods = tagged_item.get('decorator_kwargs').get('method', default_method(tag_args))
    if not isinstance(http_methods, list):
        http_methods = [http_methods]
    return http_methods


resource_instances = {}


def _prepare_resources(clazz_or_instance, url_base: str, enable_security: bool = False, class_items=None):
    def create_resource_executor(function_name):
        def resource_executor(**named_args):
            clazz = clazz_or_instance if inspect.isclass(clazz_or_instance) else clazz_or_instance.__class__
            try:
                # todo: check the name for the named arg from above
                instance = resource_instances.get(clazz.__name__)
                if not instance:
                    instance = clazz_or_instance() if inspect.isclass(clazz_or_instance) else clazz_or_instance
                    resource_instances[clazz.__name__] = instance
                executable_method = getattr(instance, function_name)
                request_and_posted_arguments = _get_request_args()
                request_and_posted_arguments.update(named_args)

                payload = _extract_dict_from_payload()
                if '_type' in payload:
                    mdl = Model.load_and_or_convert_object(payload)
                    result = executable_method(mdl,
                                               **_autobox_parameters(executable_method, request_and_posted_arguments))
                else:
                    request_and_posted_arguments.update(payload)
                    result = executable_method(
                        **_autobox_parameters(executable_method, request_and_posted_arguments))
                result_dic_tentative = {} if result is None else _xvert(clazz, result)
                return jsonify(result_dic_tentative), 200
            except Exception as exc:
                config.app_engine.logger.exception(exc)
                return config.app_engine.generic_error_handler(exc, upstream_service=clazz.__name__)

        return resource_executor

    if 'resources' in class_items:
        for resource in class_items.get('resources'):
            func_name = resource.get('function_name')
            methods = __get_http_methods(resource)
            path_segment = resource.get('decorator_kwargs').get('path', f'./{func_name.lower()}')
            _add_app_rule(clazz_or_instance, url_base, func_name, create_resource_executor(func_name),
                          path_param=path_segment, methods=methods)

        if enable_security:
            required_permissions = resource.get('decorator_kwargs').get('require', Denied())
            RbacMixin.set_list(cls=clazz_or_instance, methods=methods, permissions=required_permissions,
                               endpoint='{}_{}_{}'.format(xtract(clazz_or_instance).lower(), func_name,
                                                          methods[0].lower()))


def _prepare_actions(cls, url_base: str, enable_security: bool = False, class_items=None):
    def create_action_executor(function_name):
        def action_executor(**named_args):
            if 'object_id' not in named_args:
                msg = 'The object_id property is required for this action to execute'
                return create_custom_error(400, msg, cls.__name__)
            else:
                try:
                    instance = cls.find_by_id(named_args['object_id'])
                    executable_method = getattr(instance, function_name)
                    request_and_posted_arguments = _get_request_args()
                    request_and_posted_arguments.update(_extract_dict_from_payload())
                    result = executable_method(
                        **_autobox_parameters(executable_method, request_and_posted_arguments))
                    result_dic_tentative = {} if result is None else _xvert(cls, result)
                    return jsonify(result_dic_tentative), 200
                except ServiceException as sexc:
                    config.app_engine.logger.warn('Service error: {}'.format(str(sexc)))
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
                          path_param='<object_id>/{}'.format(relation), methods=methods)
            if enable_security:
                required_permissions = this_link.get('decorator_kwargs').get('require', Denied())
                RbacMixin.set_list(cls=cls, methods=methods, permissions=required_permissions,
                                   endpoint='{}_{}_{}'.format(xtract(cls).lower(), relation, methods[0].lower()))


def _extract_dict_from_payload():
    if request.data and len(request.data) > 0:
        object_dict = request.json or json.loads(request.data)
    elif request.form and len(request.form) > 0:
        object_dict = _xtract_form()
    else:
        object_dict = {}
    return object_dict


def _xtract_form():
    target = dict((key, request.form.getlist(key)) for key in list(request.form.keys()))
    return dict((key, value[0] if len(value) == 1 else value) for key, value in target.items())


def _get_merged_request_and_named_args(named_args):
    """
    Merge together the named args (url parameters) and the query parameters (from requests.args)
    :param named_args:
    :return: a dictionary with both: named and query parameters
    """
    named_and_request_arguments = named_args.copy()
    named_and_request_arguments.update(_get_request_args())
    return named_and_request_arguments


def _get_request_args():
    request_args = {}
    # extract the query parameters and add to a generic parameter dictionary
    if isinstance(request.args, MultiDict):
        # Multidict is a werkzeug only type so we should check what happens in production
        for arg in request.args:
            query_item = {arg: request.args.get(arg)}
            request_args.update(query_item)
    else:
        request_args.update(request.args)
    return request_args


def _create_simple_wrapper_executor(cls, app_engine, provisioner_method):
    def create_executor(*args, **named_args):
        try:
            result = provisioner_method(*args, **named_args)
            return jsonify(result), 200
        except Exception as genex:
            return app_engine.generic_error_handler(genex, upstream_service=cls.__name__)

    return create_executor


def _execute(cls, app_engine: AppKernelEngine, provisioner_method: Callable, model_class: Model):
    """
    The main view function for flask routes.
    :param app_engine: the app engine instance
    :param provisioner_method: the method on our service object which will be executed by the Flask reflection
    :param model_class: the class of the model
    :return: the result generated by the service
    """
    executable_method = provisioner_method.inner_function if isinstance(provisioner_method,
                                                                        types.FunctionType) and hasattr(
        provisioner_method, 'inner_function') else provisioner_method

    def create_executor(**named_args):
        try:
            return_code = 200
            named_and_request_arguments = _get_merged_request_and_named_args(named_args)
            if QueryProcessor.supports_query(executable_method):
                query_param_names = QueryProcessor.get_query_param_names(executable_method)
                if query_param_names and len(query_param_names) > 0:
                    # in case there are parameters on the query which do not belong to a service
                    named_and_request_arguments.update(
                        query=convert_to_query(query_param_names, request.args))

                    # delete the query params from the named and request arguments
                    for query_param_name in query_param_names:
                        if query_param_name in named_and_request_arguments:
                            del named_and_request_arguments[query_param_name]
                elif 'query' in list(request.args.keys()):
                    named_and_request_arguments.update(query=json.loads(request.args.get('query')))

            if request.method in ['POST', 'PUT']:
                # load and validate the posted object
                model_instance = Model.from_dict(_extract_dict_from_payload(), model_class)
                # save or update the object
                named_and_request_arguments.update(model=model_instance)
                return_code = 201
            elif request.method == 'PATCH':
                named_and_request_arguments.update(document=_extract_dict_from_payload())
            result = provisioner_method(
                **_autobox_parameters(executable_method, named_and_request_arguments))
            if request.method in ['GET', 'PUT', 'PATCH']:
                if result is None:
                    object_id = named_args.get('object_id', None)
                    return create_custom_error(404, 'Document{} is not found.'.format(
                        ' with id {}'.format(object_id) if object_id else ''), cls.__name__)
            if request.method == 'DELETE' and isinstance(result, int) and result == 0:
                return create_custom_error(404, 'Document with id {} was not deleted.'.format(
                    named_args.get('object_id', '-1')), cls.__name__)
            if result is None or isinstance(result, list) and len(result) == 0:
                return_code = 204
            result_dic_tentative = {} if result is None else _xvert(cls, result)
            return jsonify(result_dic_tentative), return_code
        except PropertyRequiredException as pexc:
            app_engine.logger.warn('missing parameter: {}/{}'.format(pexc.__class__.__name__, str(pexc)))
            return create_custom_error(400, str(pexc), cls.__name__)
        except ValidationException as vexc:
            app_engine.logger.warn('validation error: {}'.format(str(vexc)))
            return create_custom_error(400, '{}/{}'.format(vexc.__class__.__name__, str(vexc)),
                                       cls.__name__)
        except RequestHandlingException as rexc:
            app_engine.logger.error(f'request forwarding error: {str(rexc)}')
            app_engine.logger.exception(rexc)
            return create_custom_error(rexc.status_code, rexc.message, rexc.upstream_service)
        except Exception as exc:
            return app_engine.generic_error_handler(exc, upstream_service=cls.__name__)

    # add supported method parameter names to the list of reserved keywords;
    # These won't be added to query expressions (because they are already arguments of methods);
    qp.add_reserved_keywords(executable_method)
    return create_executor


def convert_to_query(query_param_names, request_args):
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
    :param request_args:the names and the values of the query parameters as an Immutable Multi Dict; example: ImmutableMultiDict([('birth_date', u'>1980'), ('birth_date', u'<1985'), ('logic', u'AND')])
    :type request_args: ImmutableMultiDict
    :return: the query expression which than can be converted to repository specific queries (eg. Mongo or SQL query)
    :rtype: dict
    """
    query_dict = defaultdict(list)
    for arg in request_args:
        if arg != 'logic' and arg in query_param_names:
            # the keyword 'logic' is handled separately
            query_dict[arg] = request_args.getlist(arg)

    expression_list = []
    for query_item in [[key, val] for key, val in query_dict.items()]:
        # where query_item[0] is the key of the future structure and query_item[1] is the value
        if isinstance(query_item[1], list) and len(query_item[1]) > 1:
            # it is a key with a list of values;
            # examples for query item:
            #   ['name', ['Jane', 'John']]          output: [{'name': 'Jane'}, {'name': 'John'}]
            #   ['locked', ['true', 'false']]       output: [{'locked': True}, {'locked': False}]
            #   ['birth_date', ['<1980','>1970']]   output: [{'$gte':' 1970', '$lt': '1980'}]
            #   ['name', ['~Jane', '~John']]        output: [{'name': {'$regex': '.*Jane.*', 'options': 'i'}}, {'$regex': '.*John.*', 'options': 'i'}]

            value_list = [_remap_expressions(expr) for expr in query_item[1]]
            if isinstance(value_list[0], tuple):
                expression_list.append(
                    {query_item[0]: dict(value_list)})
            else:
                for val in value_list:
                    expression_list.append({query_item[0]: val})
        else:
            # it is a key with a list of only 1 item
            # examples:
            #   ['name', ['~Jane']]
            #   ['name', ['John']]
            mapped_value = _remap_expressions(query_item[1][0])
            if isinstance(mapped_value, tuple):
                expression_list.append({query_item[0]: dict([mapped_value])})
            else:
                expression_list.append({query_item[0]: mapped_value})

    if len(expression_list) == 0:
        return {}
    elif len(expression_list) == 1:
        # the dictionary has 0 or 1 elements
        return expression_list[0]
    else:
        logic = str(OPS.__getattr__(request_args.get('logic', 'and').upper()))
        return {logic: expression_list}


def _remap_expressions(expression):
    """
    Takes a query expression such as >1994-12-02 and turns into a {'$gte':'1994-12-02'}.
    Additionally converts the date string into datetime object;

    :param expression:
    :return:
    """
    if expression[0] in qp.supported_expressions:
        converted_value = _convert_expressions(expression[1:])
        return qp.expression_mapper.get(expression[0])(converted_value)
    else:
        return _convert_expressions(expression)


def _convert_expressions(expression):
    """
    converts strings containing numbers to int, string containing a date to datetime, string containing a boolean expression to boolean

    :param arguments:
    :return:
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


def _autobox_parameters(provisioner_method, arguments):
    method_structure = get_argument_spec(provisioner_method)
    for arg_key, arg_value in arguments.items():
        required_type = type(method_structure.get(arg_key))
        provided_type = type(arg_value)
        if required_type is not type(None) and provided_type is not type(None) and required_type != provided_type:
            if issubclass(required_type, Enum):
                arguments[arg_key] = required_type[arg_value]
            elif issubclass(required_type, list) and provided_type in [str, str, str]:
                # if the required type should be a list
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
                    except ValueError as verr:
                        # skip boxing
                        pass
            elif issubclass(required_type, dict) and provided_type in [str, str, str]:
                # if the required type is dict, but provided string
                try:
                    arguments[arg_key] = json.loads(arg_value)
                except ValueError as verr:
                    # skip boxing
                    pass
            else:
                arguments[arg_key] = required_type(arg_value)
    return arguments


def _xvert(cls, result_item, generate_links=True):
    """
    converts the response object into Json

    :param generate_links: if True, it will add the HATEOAS links to the response
    :param result_item: the actual item which will get converted
    :return:
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
            result.update(_links={'self': {'href': url_for('{}_find_by_query_get'.format(xtract(cls).lower()))}})
        return result
    elif is_primitive(result_item) or isinstance(result_item, (str, int)) or is_noncomplex(result_item):
        return {'_type': 'OperationResult', 'result': result_item}


def _calculate_links(cls, object_id):
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
            endpoint_name = '{}_{}_{}'.format(clazz_name, rel, http_methods[0].lower() if isinstance(http_methods,
                                                                                                     list) else http_methods.lower())
            href = '{}'.format(url_for(endpoint_name, object_id=object_id))

            links[rel] = {
                'href': href,
                'methods': http_methods
            }
            if args and len(args) > 0:
                links[rel].update(args=args)

        links['self'] = {
            'href': url_for('{}_find_by_id_get'.format(clazz_name), object_id=object_id),
            'methods': cls.methods
        }
        links['collection'] = {
            'href': url_for('{}_find_by_query_get'.format(clazz_name)),
            'methods': 'GET'
        }
        return links
