from __future__ import annotations

import inspect
import re
import types
from typing import Any
from collections.abc import Callable
import appkernel.service
from .model import get_argument_spec


class QueryProcessor:
    """
    The query processor is used by the Service implementation.
    """

    def __init__(self) -> None:
        # self.query_pattern = re.compile('^(\w+:[\[\],\<\>A-Za-z0-9_\s-]+)(,\w+:[\[\],\<\>A-Za-z0-9_\s-]+)*$')
        self.csv_pattern = re.compile('^.*,.*$')
        self.json_pattern = re.compile('\\{.*\\:\\{.*\\:.*\\}\\}')
        self.date_patterns: dict[re.Pattern[str], str] = {
            re.compile('^(0?[1-9]|[12][0-9]|3[01])(\\/|-|\\.)(0?[1-9]|1[012])(\\/|-|\\.)\\d{4}$'): '%d{0}%m{0}%Y',
            # 31/02/4500
            re.compile('^\\d{4}(\\/|-|\\.)(0?[1-9]|1[012])(\\/|-|\\.)(0?[1-9]|[12][0-9]|3[01])$'): '%Y{0}%m{0}%d'
            # 4500/02/31,
        }
        self.number_pattern = re.compile('^[-+]?[0-9]+$')
        self.boolean_pattern = re.compile('^(true|false|True|False|y|yes|no)$')
        self.date_separator_patterns: dict[re.Pattern[str], str] = {
            re.compile('([0-9].*-)+.*'): '-',
            re.compile('([0-9].*\\/)+.*'): '/',
            re.compile('([0-9].*\\.)+.*'): '.',
        }
        self.expression_mapper: dict[str, Callable[[str], Any]] = {
            '<': lambda exp: ('$lte', exp),
            '>': lambda exp: ('$gte', exp),
            '~': lambda exp: {'$regex': f'.*{exp}.*', '$options': 'i'},
            '!': lambda exp: ('$ne', exp),
            '#': lambda exp: ('$size', exp),
            '[': lambda exp: {'$in': exp.strip(']').split(',')}
        }
        self.supported_expressions: list[str] = list(self.expression_mapper.keys())
        self.reserved_param_names: dict[str, set[str]] = {}

    def add_reserved_keywords(self, provisioner_method: Callable[..., Any]) -> None:
        key = QueryProcessor.create_key_from_instance_method(provisioner_method)
        self.reserved_param_names[key] = set(
            getattr(inspect.getfullargspec(provisioner_method), 'args'))

    @staticmethod
    def create_key_from_instance_method(provisioner_method: Callable[..., Any]) -> str:
        if isinstance(provisioner_method, types.FunctionType) and hasattr(provisioner_method, 'inner_function'):
            return f'{provisioner_method.inner_function.__self__.__name__}_{provisioner_method.__name__}'
        elif isinstance(provisioner_method, types.FunctionType):
            return f'{provisioner_method.__name__}'
        else:
            return f'{provisioner_method.__self__.__name__}_{provisioner_method.__name__}'

    @staticmethod
    def supports_query(provisioner_method: Callable[..., Any]) -> bool:
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
    def get_query_param_names(provisioner_method: Callable[..., Any], request_args_keys: Any) -> set[str]:
        """
        Extract all parameters which are not required directly by the method signature and could be used in building a query.
        :param provisioner_method: the method which will get the parameters
        :param request_args_keys: a set (or set-like) of query parameter names from the request
        :return: the difference between 2 sets: a.) the query parameter names from the request and b.) the reserved parameter names for this method
        """
        request_set = set(request_args_keys)
        return request_set.difference(
            appkernel.service.qp.reserved_param_names.get(QueryProcessor.create_key_from_instance_method(provisioner_method)))
