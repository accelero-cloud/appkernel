from types import NoneType

from enum import Enum
from flask import Flask, jsonify, current_app, request, abort
from werkzeug.datastructures import MultiDict, ImmutableMultiDict
from model import Model, ParameterRequiredException
from appkernel import AppKernelEngine
from appkernel.repository import Repository, xtract
from reflection import *
from model import Expression
import re
from collections import defaultdict
from datetime import datetime

try:
    import simplejson as json
except ImportError:
    import json


def get_argument_spec(provisioner_method):
    """
    :param provisioner_method: the method of an instance
    :return: the method arguments and default values as a dictionary, with method parameters as key and default values as dictionary value
    """
    assert inspect.ismethod(provisioner_method), 'The provisioner method must be a method'
    args = [name for name in getattr(inspect.getargspec(provisioner_method), 'args') if name not in ['cls', 'self']]
    defaults = getattr(inspect.getargspec(provisioner_method), 'defaults')
    return dict(zip(args, defaults or []))


class QueryProcessor(object):
    def __init__(self):
        self.query_pattern = re.compile('^(\w+:[\[\],\<\>A-Za-z0-9_\s-]+)(,\w+:[\[\],\<\>A-Za-z0-9_\s-]+)*$')
        self.date_patterns = {
            re.compile('^(0?[1-9]|[12][0-9]|3[01])(\/|-|\.)(0?[1-9]|1[012])(\/|-|\.)\d{4}$'): '%d{0}%m{0}%Y',
            # 31/02/4500
            re.compile('^\d{4}(\/|-|\.)(0?[1-9]|1[012])(\/|-|\.)(0?[1-9]|[12][0-9]|3[01])$'): '%Y{0}%m{0}%d'
            # 4500/02/31,
        }
        self.number_pattern = re.compile('^[-+]?[0-9]+$')
        self.boolean_pattern = re.compile('^(true|false|True|False|y|yes|no)$')
        self.date_separator_patterns = {
            re.compile('([0-9].*-)+.*'): '-',
            re.compile('([0-9].*\/)+.*'): '/',
            re.compile('([0-9].*\.)+.*'): '.',
        }
        self.expression_mapper = {
            '<': lambda exp: ('$lte', exp),
            '>': lambda exp: ('$gte', exp),
            '~': lambda exp: {'$regex': '.*{}.*'.format(exp), '$options': 'i'}
        }
        self.supported_expressions = list(self.expression_mapper.keys())
        self.reserved_param_names = {}

    def add_reserved_keywords(self, provisioner_method):
        self.reserved_param_names[QueryProcessor.create_key_from_instance_method(provisioner_method)] = set(
            getattr(inspect.getargspec(provisioner_method), 'args'))

    @staticmethod
    def create_key_from_instance_method(provisioner_method):
        return '{}_{}'.format(provisioner_method.im_self.__name__, provisioner_method.__name__)

    @staticmethod
    def supports_query(provisioner_method):
        """
        :param provisioner_method:
        :return: True if the method has a parameter named query and the default value is of type dict
        """
        method_structure = get_argument_spec(provisioner_method)
        if 'query' in method_structure:
            return isinstance(method_structure.get('query'), dict)
        else:
            return False


class Service(object):
    pretty_print = True
    qp = QueryProcessor()  # pylint: disable=C0103
    """
    The Flask App is set on this instance, so one can use the context:
    with self.app_context():
        some_varibale = some_context_aware_function()
    """

    @classmethod
    def set_app_engine(cls, app_engine, url_base, methods):
        """
        :param methods: the HTTP methods allowed for this service
        :param url_base: the url where the service is exposed
        :type url_base: basestring
        :param app_engine: the app kernel engine
        :type app_engine: AppKernelEngine
        :return:
        """
        cls.app = app_engine.app
        cls.app_engine = app_engine
        if not url_base.endswith('/'):
            url_base = '{}/'.format(url_base)
        endpoint = '{}{}'.format(url_base, xtract(cls).lower())
        class_methods = dir(cls)
        if issubclass(cls, Repository) and 'GET' in methods:
            # generate get by id
            if 'find_by_query' in class_methods:
                cls.app.add_url_rule('{}/'.format(endpoint), 'get_{}'.format(endpoint),
                                     Service.execute(app_engine, cls.find_by_query, cls),
                                     methods=['GET'])
            if 'find_by_id' in class_methods:
                cls.app.add_url_rule('{}/<string:object_id>'.format(endpoint), 'get_by_id_{}'.format(endpoint),
                                     Service.execute(app_engine, cls.find_by_id, cls),
                                     methods=['GET'])
        if issubclass(cls, Repository) and 'save_object' in class_methods and 'POST' in methods:
            cls.app.add_url_rule('{}/'.format(endpoint), 'post_{}'.format(endpoint),
                                 Service.execute(app_engine, cls.save_object, cls),
                                 methods=['POST'])
        if issubclass(cls, Repository) and 'replace_object' in class_methods and 'PUT' in methods:
            cls.app.add_url_rule('{}/'.format(endpoint), 'put_{}'.format(endpoint),
                                 Service.execute(app_engine, cls.replace_object, cls),
                                 methods=['PUT'])
        if issubclass(cls, Repository) and 'save_object' in class_methods and 'PATCH' in methods:
            cls.app.add_url_rule('{}/<string:object_id>'.format(endpoint), 'patch_{}'.format(endpoint),
                                 Service.execute(app_engine, cls.save_object, cls),
                                 methods=['PATCH'])

        if issubclass(cls, Repository) and 'delete_by_id' in class_methods and 'DELETE' in methods:
            cls.app.add_url_rule('{}/<object_id>'.format(endpoint), 'delete_{}'.format(endpoint),
                                 Service.execute(app_engine, cls.delete_by_id, cls),
                                 methods=['DELETE'])

    @staticmethod
    def __extract_json(request):
        return request.json or json.loads(request.data)

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
                # #todo: continue it here
                # #request.form | request.args | request.files
                # #request.values: combined args and form, preferring args if keys overlap
                # print 'request json {}'.format(request.json)
                return_code = 200
                # merge together the named args (url parameters) and the query parameters (from requests.args)
                named_and_request_arguments = named_args.copy()

                # extract the query parameters and add to a generic parameter dictionary
                if isinstance(request.args, MultiDict):
                    # Multidict is a werkzeug only type so we should check what happens in production
                    for arg in request.args:
                        query_item = {arg: request.args.get(arg)}
                        named_and_request_arguments.update(query_item)
                else:
                    named_and_request_arguments.update(request.args)

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

                if request.method in ['POST', 'PUT']:
                    # load and validate the posted object
                    model_instance = Model.from_dict(Service.__extract_json(request), model_class)
                    # save or update the object
                    named_and_request_arguments.update(document=Model.to_dict(model_instance, convert_id=True))
                    return_code = 201
                elif request.method == 'PATCH':
                    named_and_request_arguments.update(document=Service.__extract_json(request))

                result = provisioner_method(
                    **Service.__autobox_parameters(provisioner_method, named_and_request_arguments))
                if request.method == 'GET':
                    if result is None:
                        return app_engine.create_custom_error(404, 'Document with id {} is not found.'.format(
                            named_args.get('object_id', '-1')))
                    elif isinstance(result, list) and len(result) == 0:
                        return app_engine.create_custom_error(404, 'This query returned and empty result set.')
                if request.method == 'DELETE' and isinstance(result, int) and result == 0:
                    return app_engine.create_custom_error(404, 'Document with id {} was not deleted.'.format(
                        named_args.get('object_id', '-1')))
                if result is None:
                    return_code = 204
                result_dic_tentative = {} if result is None else Service.xvert(model_class, result)
                # todo: codify 201 or anything else what can be derived from the response
                return jsonify(result_dic_tentative), return_code
            except ParameterRequiredException as pexc:
                app_engine.logger.warn('missing parameter: {}'.format(str(pexc)))
                return app_engine.create_custom_error(400, str(pexc))
            except Exception as exc:
                app_engine.logger.exception('exception caught while executing service call: {}'.format(str(exc)))
                return app_engine.generic_error_handler(exc)

        # add supported method parameter names to the list of reserved keywords
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
        ?first_name={firstName}&last_name={lastName}&birth_date={birthDate}
        Supported query formats:
        The value of first_name, last_name and birth_date is exactly the ones in the list.
        Converted to:
        {"$and":[
            {"first_name":{firstName}},
            {"last_name":{lastName}},
            {"birth_date":{birthDate}}
            ]}

        ?first_name=~{firstName}
        The first name contains a given value;
        Converted to:
        {"first_name" : "/.*{firstName}.*/i"}

        ?birth_date=>{birthDate}
        Birth date after the given parameter (inclusive >=)
        Converted to:
        {"birth_date": {$gte:{birthDate}}}

        ?birth_date=>{birthDate}&?birth_date=<{birthDate}
        Birth date between the two parameters, with date pattern matching if applies.
        Converted to:
        {"birth_date": [{$gte:{birthDate},{"$lt":{birthDate}}]}}


        ?state:[NEW, CLOSED]
        The state of a give content among the provided patterns.
        Converted to:
        {"state":{"$in":["NEW", "CLOSED"]}}

        :param query_param_names: the names of all query parameters as a set; example set(['birth_date','logic'])
        :type query_param_names: set
        :param request_args:the names and the values of the query parameters as an Immutable Multi Dict; example: ImmutableMultiDict([('birth_date', u'>1980'), ('birth_date', u'<1985'), ('logic', u'AND')])
        :type request_args: ImmutableMultiDict
        :return: the query expression which than can be converted to repository specific queries (eg. Mongo or SQL query)
        :rtype: dict
        """

        # if not Service.qp.query_pattern.match(query_params):
        #     raise ValueError(
        #         'The provided query expression ({}) is not in the accepted format (comma separated groups with colon separated key value pairs)'.format(
        #             query_params))

        query_dict = defaultdict(list)
        for arg in request_args:
            if arg != 'logic' and arg in query_param_names:
                # the keyword 'logic' is handled separately
                query_dict[arg] = request_args.getlist(arg)

        expression_list = []
        for query_item in [[key, val] for key, val in query_dict.iteritems()]:
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
            logic = Expression.OPS.__getattr__(request_args.get('logic', 'and'))
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
        if isinstance(expression, (str, basestring, unicode)):
            if Service.qp.number_pattern.match(expression):
                return int(expression)
            if Service.qp.boolean_pattern.match(expression):
                return True if expression in ['true', 'True', 'y', 'yes'] else False
            for date_pattern in Service.qp.date_patterns.iterkeys():
                if date_pattern.match(expression):
                    for parser_format_matcher in Service.qp.date_separator_patterns.iterkeys():
                        if parser_format_matcher.match(expression):
                            date_parser_pattern = Service.qp.date_patterns.get(date_pattern)
                            separator = Service.qp.date_separator_patterns.get(parser_format_matcher)
                            return datetime.strptime(expression, date_parser_pattern.format(separator))
        return expression

    @staticmethod
    def __autobox_parameters(provisioner_method, arguments):
        method_structure = get_argument_spec(provisioner_method)
        for arg_key, arg_value in arguments.iteritems():
            required_type = type(method_structure.get(arg_key))
            provided_type = type(arg_value)
            if required_type is not NoneType and provided_type is not NoneType and required_type != provided_type:
                if issubclass(required_type, Enum):
                    arguments[arg_key] = required_type[arg_value]
                else:
                    arguments[arg_key] = required_type(arg_value)
        return arguments

    @staticmethod
    def xvert(model_class, result_item):
        """
        converts the response object into Json
        :param model_class: the name of the class of teh model
        :param result_item: the actual item which will get converted
        :return:
        """
        if isinstance(result_item, Model):
            model = Model.to_dict(result_item)
            model.update(type=model_class.__name__)
            return model
        elif is_dictionary(result_item) or is_dictionary_subclass(result_item):
            return result_item
        elif isinstance(result_item, (list, set, tuple)):
            return [Service.xvert(model_class, item) for item in result_item]
        elif is_primitive(result_item) or isinstance(result_item, (str, basestring, int)) or is_noncomplex(result_item):
            return {'result': result_item}
