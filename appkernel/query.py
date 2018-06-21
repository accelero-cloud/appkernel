import inspect, re

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
        self.reserved_param_names[QueryProcessor.create_key_from_instance_method(provisioner_method)] = set(
            getattr(inspect.getargspec(provisioner_method), 'args'))

    @staticmethod
    def create_key_from_instance_method(provisioner_method):
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
