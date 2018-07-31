import inspect, re
import types

from flask import request

import appkernel.service
from .model import get_argument_spec


class QueryProcessor(object):
    """
    The query processor is used by the Service implementation.
    """
    def __init__(self):
        # self.query_pattern = re.compile('^(\w+:[\[\],\<\>A-Za-z0-9_\s-]+)(,\w+:[\[\],\<\>A-Za-z0-9_\s-]+)*$')
        self.csv_pattern = re.compile('^.*,.*$')
        self.json_pattern = re.compile('\{.*\:\{.*\:.*\}\}')
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
            '~': lambda exp: {'$regex': '.*{}.*'.format(exp), '$options': 'i'},
            '!': lambda exp: ('$ne', exp),
            '#': lambda exp: ('$size', exp),
            '[': lambda exp: {'$in': exp.strip(']').split(',')}
        }
        self.supported_expressions = list(self.expression_mapper.keys())
        self.reserved_param_names = {}

    def add_reserved_keywords(self, provisioner_method):
        key = QueryProcessor.create_key_from_instance_method(provisioner_method)
        self.reserved_param_names[key] = set(
            getattr(inspect.getfullargspec(provisioner_method), 'args'))

    @staticmethod
    def create_key_from_instance_method(provisioner_method):
        if isinstance(provisioner_method, types.FunctionType) and hasattr(provisioner_method, 'inner_function'):
            return '{}_{}'.format(provisioner_method.inner_function.__self__.__name__, provisioner_method.__name__)
        elif isinstance(provisioner_method, types.FunctionType):
            return '{}'.format(provisioner_method.__name__)
        else:
            return '{}_{}'.format(provisioner_method.__self__.__name__, provisioner_method.__name__)

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

    @staticmethod
    def get_query_param_names(provisioner_method):
        """
        Extract all parameters which are not required directly by the method signature and could be used in building a query
        :param provisioner_method: the method which will get the parameters
        :return: the difference between 2 sets: a.) the argument names of the method and b.) the query parameters handed over by the client request
        """
        request_set = set(request.args.keys())
        return request_set.difference(
            appkernel.service.qp.reserved_param_names.get(QueryProcessor.create_key_from_instance_method(provisioner_method)))
