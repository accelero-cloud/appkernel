from collections import defaultdict
from datetime import datetime
from enum import Enum

from flask import jsonify, request, url_for
from werkzeug.datastructures import MultiDict, ImmutableMultiDict

from appkernel.configuration import config
from .iam import RbacMixin, Anonymous
from .model import Model, PropertyRequiredException, create_tagging_decorator, get_argument_spec, ServiceException, OPS
from .query import QueryProcessor
from .reflection import *
from .repository import Repository, xtract, MongoRepository
from .validators import ValidationException

try:
    import simplejson as json
except ImportError:
    import json

# tagging decorator which will tag the decorated function
link = create_tagging_decorator('links')


class Service(RbacMixin):
    pretty_print = True
    qp = QueryProcessor()  # pylint: disable=C0103
    """
    The Flask App is set on this instance, so one can use the context:
    with self.app_context():
        some_varibale = some_context_aware_function()
    """

    @classmethod
    def __add_app_rule(cls, rule, endpoint, view_function, **options):
        config.service_registry[endpoint] = cls
        cls.app.add_url_rule(rule, endpoint, view_function, **options)

    @classmethod
    def set_app_engine(cls, app_engine, url_base, methods, enable_hateoas=True):
        """
        :param enable_hateoas:
        :param methods: the HTTP methods allowed for this service
        :param url_base: the url where the service is exposed
        :type url_base: basestring
        :param app_engine: the app kernel engine
        :type app_engine: AppKernelEngine
        :return:
        """
        Service.app = app_engine.app
        Service.app_engine = app_engine
        if not url_base.endswith('/'):
            url_base = '{}/'.format(url_base)
        clazz_name = xtract(cls).lower()
        cls.endpoint = '{}{}'.format(url_base, clazz_name)
        cls.http_methods = methods
        cls.enable_hateoas = enable_hateoas
        class_methods = dir(cls)
        if issubclass(cls, Model):
            cls.__add_app_rule('{}/schema'.format(cls.endpoint), '{}_schema'.format(clazz_name),
                               cls.create_simple_wrapper_executor(app_engine, cls.get_json_schema),
                               methods=['GET'])
            cls.__add_app_rule('{}/meta'.format(cls.endpoint), '{}_meta'.format(clazz_name),
                               cls.create_simple_wrapper_executor(app_engine, cls.get_parameter_spec),
                               methods=['GET'])

        if issubclass(cls, Repository) and 'GET' in methods:
            # generate get by id
            if 'find_by_query' in class_methods:
                cls.__add_app_rule('{}/'.format(cls.endpoint), '{}_get_by_query'.format(clazz_name),
                                   cls.execute(app_engine, cls.find_by_query, cls),
                                   methods=['GET'])
            if 'find_by_id' in class_methods:
                cls.__add_app_rule('{}/<string:object_id>'.format(cls.endpoint), '{}_get_by_id'.format(clazz_name),
                                   cls.execute(app_engine, cls.find_by_id, cls),
                                   methods=['GET'])
        if issubclass(cls, Repository) and 'save_object' in class_methods and 'POST' in methods:
            cls.__add_app_rule('{}/'.format(cls.endpoint), '{}_post'.format(clazz_name),
                               cls.execute(app_engine, cls.save_object, cls),
                               methods=['POST'])
        if issubclass(cls, Repository) and 'replace_object' in class_methods and 'PUT' in methods:
            cls.__add_app_rule('{}/'.format(cls.endpoint), '{}_put'.format(clazz_name),
                               cls.execute(app_engine, cls.replace_object, cls),
                               methods=['PUT'])
        if issubclass(cls, Repository) and 'save_object' in class_methods and 'PATCH' in methods:
            cls.__add_app_rule('{}/<string:object_id>'.format(cls.endpoint), '{}_patch'.format(clazz_name),
                               cls.execute(app_engine, cls.patch_object, cls),
                               methods=['PATCH'])

        if issubclass(cls, Repository) and 'delete_by_id' in class_methods and 'DELETE' in methods:
            cls.__add_app_rule('{}/<object_id>'.format(cls.endpoint), '{}_delete'.format(clazz_name),
                               cls.execute(app_engine, cls.delete_by_id, cls),
                               methods=['DELETE'])
        if issubclass(cls, MongoRepository) and 'GET' in methods and 'aggregate' in class_methods:
            cls.__add_app_rule('{}/aggregate/'.format(cls.endpoint), '{}_aggregate'.format(clazz_name),
                               cls.execute(app_engine, cls.aggregate, cls),
                               methods=['GET'])

        cls.prepare_actions()

    @classmethod
    def prepare_actions(cls):
        def create_action_executor(function_name):
            def action_executor(**named_args):
                if 'object_id' not in named_args:
                    return Service.app_engine.create_custom_error(400,
                                                                  'The object_id property is required for this action to execute')
                else:
                    try:
                        instance = cls.find_by_id(named_args['object_id'])
                        executable_method = getattr(instance, function_name)
                        request_and_posted_arguments = Service.get_request_args()
                        request_and_posted_arguments.update(Service.__extract_dict_from_payload())
                        result = executable_method(
                            **Service.__autobox_parameters(executable_method, request_and_posted_arguments))
                        result_dic_tentative = {} if result is None else cls.xvert(result)
                        return jsonify(result_dic_tentative), 200
                    except ServiceException as sexc:
                        Service.app_engine.logger.warn('Service error: {}'.format(str(sexc)))
                        return Service.app_engine.create_custom_error(sexc.http_error_code, sexc.message)
                    except Exception as exc:
                        Service.app_engine.logger.exception(exc)
                        return Service.app_engine.generic_error_handler(exc)

            return action_executor

        setup_security = hasattr(config, 'security_enabled') and config.security_enabled
        # if cls.enable_hateoas or setup_security:
        if 'links' in cls.__dict__:
            for this_link in cls.links:
                func_name = this_link.get('function_name')
                args = this_link.get('argspec')
                methods = this_link.get('decorator_kwargs').get('http_method',
                                                                ['POST'] if len(args) > 0 else ['GET'])
                relation = this_link.get('decorator_kwargs').get('rel', func_name)
                if not isinstance(methods, list):
                    methods = [methods]
                link_endpoint = '{}_{}'.format(xtract(cls).lower(), relation)
                cls.__add_app_rule('{}/<object_id>/{}'.format(cls.endpoint, relation),
                                   link_endpoint,
                                   create_action_executor(func_name),
                                   methods=methods)
                if setup_security:
                    required_permissions = this_link.get('decorator_kwargs').get('require', Anonymous())
                    cls.require(required_permissions, methods, link_endpoint)

    @staticmethod
    def __extract_dict_from_payload():
        if request.data and len(request.data) > 0:
            object_dict = request.json or json.loads(request.data)
        elif request.form and len(request.form) > 0:
            object_dict = Service.__xtract_form()
        else:
            object_dict = {}
        return object_dict

    @staticmethod
    def __xtract_form():
        target = dict((key, request.form.getlist(key)) for key in list(request.form.keys()))
        return dict((key, value[0] if len(value) == 1 else value) for key, value in target.items())

    @staticmethod
    def get_merged_request_and_named_args(named_args):
        """
        Merge together the named args (url parameters) and the query parameters (from requests.args)
        :param named_args:
        :return: a dictionary with both: named and query parameters
        """
        named_and_request_arguments = named_args.copy()
        named_and_request_arguments.update(Service.get_request_args())
        return named_and_request_arguments

    @staticmethod
    def get_request_args():
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

    @classmethod
    def create_simple_wrapper_executor(cls, app_engine, provisioner_method):
        def create_executor(*args, **named_args):
            try:
                result = provisioner_method(*args, **named_args)
                return jsonify(result), 200
            except Exception as genex:
                return app_engine.generic_error_handler(genex)

        return create_executor

    @classmethod
    def execute(cls, app_engine, provisioner_method, model_class):
        """
        :param app_engine: the app engine instance
        :param provisioner_method: the method on our service object which will be executed by the Flask reflection
        :param model_class: the class of the model
        :return: the result generated by the service
        """

        def create_executor(**named_args):
            try:
                # print('named args: {}'.format(named_args))
                # print '>>> current app name: {}'.format(current_app.name)
                # print 'current object: {}'.format(current_app._get_current_object())
                # print 'Request method: {}'.format(request.method)
                # print 'request form: {}'.format(request.form)
                # print 'request args: {}'.format(request.args)
                # print 'request form: {}'.format(request.form)
                # #request.form | request.args | request.files
                # #request.values: combined args and form, preferring args if keys overlap
                # print 'request json {}'.format(request.json)
                return_code = 200
                named_and_request_arguments = Service.get_merged_request_and_named_args(named_args)
                if QueryProcessor.supports_query(provisioner_method):
                    query_param_names = Service.get_query_param_names(provisioner_method)
                    if query_param_names and len(query_param_names) > 0:
                        # in case there are parameters on the query which do not belong to a service
                        named_and_request_arguments.update(
                            query=Service.convert_to_query(query_param_names, request.args))

                        # delete the query params from the named and request arguments
                        for query_param_name in query_param_names:
                            if query_param_name in named_and_request_arguments:
                                del named_and_request_arguments[query_param_name]
                    elif 'query' in list(request.args.keys()):
                        named_and_request_arguments.update(query=json.loads(request.args.get('query')))

                if request.method in ['POST', 'PUT']:
                    # load and validate the posted object
                    model_instance = Model.from_dict(Service.__extract_dict_from_payload(), model_class)
                    # save or update the object
                    named_and_request_arguments.update(document=Model.to_dict(model_instance, convert_id=True))
                    return_code = 201
                elif request.method == 'PATCH':
                    named_and_request_arguments.update(document=Service.__extract_dict_from_payload())

                result = provisioner_method(
                    **Service.__autobox_parameters(provisioner_method, named_and_request_arguments))
                if request.method in ['GET', 'PUT', 'PATCH']:
                    if result is None:
                        object_id = named_args.get('object_id', None)
                        return app_engine.create_custom_error(404, 'Document{} is not found.'.format(' with id {}'.format(object_id) if object_id else ''))
                if request.method == 'DELETE' and isinstance(result, int) and result == 0:
                    return app_engine.create_custom_error(404, 'Document with id {} was not deleted.'.format(
                        named_args.get('object_id', '-1')))
                if result is None or isinstance(result, list) and len(result) == 0:
                    return_code = 204
                result_dic_tentative = {} if result is None else cls.xvert(result)
                return jsonify(result_dic_tentative), return_code
            except PropertyRequiredException as pexc:
                app_engine.logger.warn('missing parameter: {}/{}'.format(pexc.__class__.__name__, str(pexc)))
                return app_engine.create_custom_error(400, str(pexc))
            except ValidationException as vexc:
                app_engine.logger.warn('validation error: {}'.format(str(vexc)))
                return app_engine.create_custom_error(400, '{}/{}'.format(vexc.__class__.__name__, str(vexc)))
            except Exception as exc:
                return app_engine.generic_error_handler(exc)

        # add supported method parameter names to the list of reserved keywords;
        # These won't be added to query expressions (because they are already arguments of methods);
        Service.qp.add_reserved_keywords(provisioner_method)
        return create_executor

    @staticmethod
    def get_query_param_names(provisioner_method):
        """
        Extract all parameters which are not required directly by the method signature and could be used in building a query
        :param provisioner_method: the method which will get the parameters
        :return: the difference between 2 sets: a.) the argument names of the method and b.) the query parameters handed over by the client request
        """
        request_set = set(request.args.keys())
        return request_set.difference(
            Service.qp.reserved_param_names.get(QueryProcessor.create_key_from_instance_method(provisioner_method)))

    @staticmethod
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

                value_list = [Service.__remap_expressions(expr) for expr in query_item[1]]
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
                mapped_value = Service.__remap_expressions(query_item[1][0])
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

    @staticmethod
    def __remap_expressions(expression):
        """
        Takes a query expression such as >1994-12-02 and turns into a {'$gte':'1994-12-02'}.
        Additionally converts the date string into datetime object;

        :param expression:
        :return:
        """
        if expression[0] in Service.qp.supported_expressions:
            converted_value = Service.__convert_expressions(expression[1:])
            return Service.qp.expression_mapper.get(expression[0])(converted_value)
        else:
            return Service.__convert_expressions(expression)

    @staticmethod
    def __convert_expressions(expression):
        """
        converts strings containing numbers to int, string containing a date to datetime, string containing a boolean expression to boolean

        :param arguments:
        :return:
        """
        if isinstance(expression, str):
            if Service.qp.number_pattern.match(expression):
                return int(expression)
            if Service.qp.boolean_pattern.match(expression):
                return True if expression in ['true', 'True', 'y', 'yes'] else False
            for date_pattern in Service.qp.date_patterns.keys():
                if date_pattern.match(expression):
                    for parser_format_matcher in Service.qp.date_separator_patterns.keys():
                        if parser_format_matcher.match(expression):
                            date_parser_pattern = Service.qp.date_patterns.get(date_pattern)
                            separator = Service.qp.date_separator_patterns.get(parser_format_matcher)
                            return datetime.strptime(expression, date_parser_pattern.format(separator))
        return expression

    @staticmethod
    def __autobox_parameters(provisioner_method, arguments):
        method_structure = get_argument_spec(provisioner_method)
        for arg_key, arg_value in arguments.items():
            required_type = type(method_structure.get(arg_key))
            provided_type = type(arg_value)
            if required_type is not type(None) and provided_type is not type(None) and required_type != provided_type:
                if issubclass(required_type, Enum):
                    arguments[arg_key] = required_type[arg_value]
                elif issubclass(required_type, list) and provided_type in [str, str, str]:
                    # if the required type should be a list
                    if Service.qp.csv_pattern.match(arg_value):
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

    @classmethod
    def xvert(cls, result_item, generate_links=True):
        """
        converts the response object into Json

        :param generate_links: if True, it will add the HATEOAS links to the response
        :param result_item: the actual item which will get converted
        :return:
        """
        if isinstance(result_item, Model):
            model = Model.to_dict(result_item, skip_omitted_fields=True)
            model.update(_type=cls.__name__)
            if cls.enable_hateoas and generate_links:
                model.update(_links=cls.__calculate_links(result_item.id))
            return model
        elif is_dictionary(result_item) or is_dictionary_subclass(result_item):
            return result_item
        elif isinstance(result_item, (list, set, tuple)):
            result = {
                '_type': result_item.__class__.__name__,
                '_items': [cls.xvert(item, generate_links=False) for item in result_item]
            }
            if cls.enable_hateoas:
                result.update(_links={'self': {'href': url_for('{}_get_by_query'.format(xtract(cls).lower()))}})
            return result
        elif is_primitive(result_item) or isinstance(result_item, (str, int)) or is_noncomplex(result_item):
            return {'_type': 'OperationResult', 'result': result_item}

    @classmethod
    def __calculate_links(cls, object_id):
        links = {}
        clazz_name = xtract(cls).lower()
        all_members = cls.__dict__
        if 'links' in all_members:
            for this_link in all_members.get('links'):
                func_name = this_link.get('function_name')
                rel = this_link.get('decorator_kwargs').get('rel', func_name)
                endpoint_name = '{}_{}'.format(clazz_name, rel)
                href = '{}'.format(url_for(endpoint_name, object_id=object_id))
                args = [key for key in this_link.get('argspec').keys()]

                links[rel] = {
                    'href': href,
                    'methods': this_link.get('decorator_kwargs').get('http_method',
                                                                     'POST' if len(args) > 0 else 'GET')
                }
                if args and len(args) > 0:
                    links[rel].update(args=args)
            links['self'] = {
                'href': url_for('{}_get_by_id'.format(clazz_name), object_id=object_id),
                'methods': cls.http_methods
            }
            links['collection'] = {
                'href': url_for('{}_get_by_query'.format(clazz_name)),
                'methods': 'GET'
            }
            return links
