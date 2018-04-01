from types import NoneType

from flask import Flask, jsonify, current_app, request, abort
from werkzeug.datastructures import MultiDict, ImmutableMultiDict
from model import Model
from appkernel import AppKernelEngine
from appkernel.repository import Repository, xtract
from reflection import *
from model import Expression
import re
from collections import defaultdict
import traceback, sys



class QueryProcessor(object):
    def __init__(self):
        self.query_pattern = re.compile('^(\w+:[\[\],\<\>A-Za-z0-9_\s-]+)(,\w+:[\[\],\<\>A-Za-z0-9_\s-]+)*$')
        self.expression_mapper = {
            '<': lambda exp: ('$lt', exp),
            '>': lambda exp: ('$gte', exp),
            '~': lambda exp: '/.*{}.*/i'.format(exp)
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
        args = [name for name in getattr(inspect.getargspec(provisioner_method), 'args') if name not in ['cls', 'self']]
        defaults = getattr(inspect.getargspec(provisioner_method), 'defaults')
        method_structure = dict(zip(args, defaults))
        return 'query' in method_structure and isinstance(method_structure.get('query'), dict)


class Service(object):
    pretty_print = True
    qp = QueryProcessor()
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
                    model_instance = Model.from_dict(request.json, model_class)
                    # save or update the object
                    named_and_request_arguments.update(document=Model.to_dict(model_instance, convert_id=True))
                elif request.method == 'PATCH':
                    named_and_request_arguments.update(document=request.json)

                result = provisioner_method(
                    **Service.__autobox_parameters(provisioner_method, named_and_request_arguments))
                if request.method == 'GET' and result is None:
                    return app_engine.create_custom_error(404, 'Document with id {} is not found.'.format(
                        named_args.get('object_id', '-1')))
                if request.method == 'DELETE' and isinstance(result, int) and result == 0:
                    return app_engine.create_custom_error(404, 'Document with id {} was not deleted.'.format(
                        named_args.get('object_id', '-1')))
                result_dic_tentative = {} if result is None else Service.xvert(result)
                # todo: codify 201 or anything else what can be derived from the response
                return jsonify(result_dic_tentative), 200
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
                # it is a key with a list of values
                expression_list.append(
                    {query_item[0]: dict([Service.__remap_expressions(expr) for expr in query_item[1]])})
            else:
                # it is a key with a list of only 1 item
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
            logic = Expression.OPS.from_string(request_args.get('logic', 'and'))
            return {logic: expression_list}

    @staticmethod
    def __remap_expressions(expression):
        if expression[0] in Service.qp.supported_expressions:
            return Service.qp.expression_mapper.get(expression[0])(expression[1:])
        else:
            return expression

    @staticmethod
    def __autobox_parameters(provisioner_method, arguments):
        # argspec = inspect.getargspec(provisioner_method)
        # returns a dict with the call argument names and default values
        argspec = inspect.getcallargs(provisioner_method)
        for arg_key, arg_value in arguments.iteritems():
            required_type = type(argspec.get(arg_key))
            provided_type = type(arg_value)
            if required_type is not NoneType and provided_type is not NoneType and required_type != provided_type:
                arguments[arg_key] = required_type(arg_value)
        return arguments

    @staticmethod
    def xvert(result_item):
        if isinstance(result_item, Model):
            return Model.to_dict(result_item)
        elif is_dictionary(result_item) or is_dictionary_subclass(result_item):
            return result_item
        elif isinstance(result_item, (list, set, tuple)):
            return [Service.xvert(item) for item in result_item]
        elif is_primitive(result_item) or isinstance(result_item, (str, basestring, int)) or is_noncomplex(result_item):
            return {'result': result_item}
