"""
OpenAPI 3.1.0 schema generator for AppKernel.

Introspects the service registry populated at route-registration time and
produces an OpenAPI document from registered Model schemas, type hints, and
decorator metadata.

Usage::

    from appkernel.openapi import OpenAPISchemaGenerator

    generator = OpenAPISchemaGenerator(title='My API', version='1.0.0')
    spec = generator.generate()
"""
from __future__ import annotations

import inspect
from typing import Any, get_type_hints

from .configuration import config


# ---------------------------------------------------------------------------
# Python type → OpenAPI schema fragment
# ---------------------------------------------------------------------------

_PY_TO_OAS: dict[str, dict] = {
    'str':      {'type': 'string'},
    'int':      {'type': 'integer'},
    'float':    {'type': 'number', 'format': 'float'},
    'bool':     {'type': 'boolean'},
    'datetime': {'type': 'string', 'format': 'date-time'},
    'date':     {'type': 'string', 'format': 'date'},
    'list':     {'type': 'array'},
    'dict':     {'type': 'object'},
}

_STANDARD_ERROR_RESPONSES: dict[str, Any] = {
    '400': {'description': 'Bad Request',          'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorMessage'}}}},
    '401': {'description': 'Unauthorized',         'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorMessage'}}}},
    '403': {'description': 'Forbidden',            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorMessage'}}}},
    '404': {'description': 'Not Found',            'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorMessage'}}}},
    '500': {'description': 'Internal Server Error','content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorMessage'}}}},
}

_ERROR_MESSAGE_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        '_type':   {'type': 'string', 'example': 'ErrorMessage'},
        'code':    {'type': 'integer'},
        'message': {'type': 'string'},
    },
}

# Standard AppKernel response envelope for collection endpoints
_ENVELOPE_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'properties': {
        '_type':  {'type': 'string'},
        '_items': {'type': 'array', 'items': {'type': 'object'}},
        '_links': {
            'type': 'object',
            'additionalProperties': {
                'type': 'object',
                'properties': {
                    'href':    {'type': 'string'},
                    'methods': {},
                },
            },
        },
    },
}

# Standard pagination / query parameters added to collection GET routes
_COLLECTION_QUERY_PARAMS = ('page', 'page_size', 'sort_by', 'sort_order', 'query')


class OpenAPISchemaGenerator:
    """Builds an OpenAPI 3.1.0 document from the AppKernel service registry.

    Model field schemas, validator constraints, and type information are
    derived from :meth:`~appkernel.Model.get_json_schema`.  Per-endpoint
    metadata (summary, tags, ``request_model``, ``response_model``,
    ``query_params``) are collected at route-registration time and stored in
    ``config.openapi_endpoints``.

    When ``request_model`` or ``response_model`` are absent the generator
    falls back to method type-hint inspection, then to ``{"type": "object"}``
    if no type information is available.
    """

    def __init__(
        self,
        title: str = 'AppKernel API',
        version: str = '1.0.0',
        description: str = '',
    ) -> None:
        self.title = title
        self.version = version
        self.description = description
        # Component schemas accumulated during generation; pre-seed shared types
        self._components: dict[str, Any] = {
            'ErrorMessage': _ERROR_MESSAGE_SCHEMA,
            'Envelope': _ENVELOPE_SCHEMA,
        }

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def generate(self) -> dict[str, Any]:
        """Build and return the complete OpenAPI 3.1.0 specification dict."""
        paths: dict[str, Any] = {}
        openapi_endpoints: dict[str, Any] = getattr(config, 'openapi_endpoints', {})

        for endpoint_name, meta in openapi_endpoints.items():
            if meta.get('internal'):
                continue
            path = meta['path']
            for method in meta['methods']:
                operation = self._build_operation(endpoint_name, method, meta)
                if path not in paths:
                    paths[path] = {}
                paths[path][method.lower()] = operation

        return {
            'openapi': '3.1.0',
            'info': {
                'title': self.title,
                'version': self.version,
                'description': self.description,
            },
            'paths': paths,
            'components': {'schemas': self._components},
        }

    # -----------------------------------------------------------------------
    # Per-operation builder
    # -----------------------------------------------------------------------

    def _build_operation(self, endpoint_name: str, method: str, meta: dict) -> dict[str, Any]:
        operation: dict[str, Any] = {
            'operationId': endpoint_name,
            'summary': meta.get('summary') or _default_summary(endpoint_name, method, meta),
        }

        if meta.get('tags'):
            operation['tags'] = meta['tags']

        if meta.get('deprecated'):
            operation['deprecated'] = True

        params = [
            *self._path_params(meta.get('path_params', [])),
            *self._query_params(meta.get('query_params', []), meta),
        ]
        if params:
            operation['parameters'] = params

        req_body = self._request_body(method, meta)
        if req_body:
            operation['requestBody'] = req_body

        operation['responses'] = self._responses(method, meta)
        return operation

    # -----------------------------------------------------------------------
    # Parameter helpers
    # -----------------------------------------------------------------------

    def _path_params(self, param_names: list[str]) -> list[dict]:
        return [
            {'name': name, 'in': 'path', 'required': True, 'schema': {'type': 'string'}}
            for name in param_names
        ]

    def _query_params(self, declared: list[str], meta: dict) -> list[dict]:
        """Build query parameter list from decorator ``query_params`` kwarg.

        For CRUD collection GET routes the standard pagination parameters
        (``page``, ``page_size``, ``sort_by``, ``sort_order``, ``query``) are
        appended automatically.
        """
        params: list[dict] = []
        seen: set[str] = set()

        for name in declared:
            params.append({'name': name, 'in': 'query', 'required': False, 'schema': {'type': 'string'}})
            seen.add(name)

        if meta.get('crud_operation') == 'find_by_query':
            for std in _COLLECTION_QUERY_PARAMS:
                if std not in seen:
                    params.append({'name': std, 'in': 'query', 'required': False, 'schema': {'type': 'string'}})

        return params

    # -----------------------------------------------------------------------
    # Request body
    # -----------------------------------------------------------------------

    def _request_body(self, method: str, meta: dict) -> dict | None:
        if method not in ('POST', 'PUT', 'PATCH'):
            return None

        # 1. Explicit override from decorator kwarg
        if meta.get('request_model'):
            return {'required': True, 'content': {'application/json': {'schema': self._model_schema_ref(meta['request_model'])}}}

        # 2. Type-hint inference from the original handler method
        inferred = self._infer_request_schema(meta.get('handler_func'))
        if inferred:
            return {'required': True, 'content': {'application/json': {'schema': inferred}}}

        # 3. CRUD model (POST/PUT on a Model class)
        if meta.get('model_class') and method in ('POST', 'PUT'):
            return {'required': True, 'content': {'application/json': {'schema': self._model_schema_ref(meta['model_class'])}}}

        # 4. Generic fallback
        return {'required': False, 'content': {'application/json': {'schema': {'type': 'object'}}}}

    def _infer_request_schema(self, handler_func: Any) -> dict | None:
        """Return a ``$ref`` schema for the first Model-typed parameter of *handler_func*.

        Returns ``None`` when no suitable type hint is found.
        """
        if handler_func is None:
            return None
        try:
            hints = get_type_hints(handler_func)
        except Exception:
            return None

        from .model import Model
        skip = {'self', 'cls', 'request', 'request_data', 'return'}
        for param_name, hint in hints.items():
            if param_name in skip:
                continue
            actual = _unwrap_optional(hint)
            if inspect.isclass(actual) and issubclass(actual, Model):
                return self._model_schema_ref(actual)
        return None

    # -----------------------------------------------------------------------
    # Responses
    # -----------------------------------------------------------------------

    def _responses(self, method: str, meta: dict) -> dict:
        success_code = '201' if method == 'POST' else '200'

        if meta.get('response_model'):
            schema = self._model_schema_ref(meta['response_model'])
        elif meta.get('model_class'):
            schema = self._crud_response_schema(method, meta)
        else:
            inferred = self._infer_response_schema(meta.get('handler_func'))
            schema = inferred if inferred else {'type': 'object'}

        responses: dict[str, Any] = {
            success_code: {
                'description': 'Success',
                'content': {'application/json': {'schema': schema}},
            }
        }
        responses.update(_STANDARD_ERROR_RESPONSES)
        return responses

    def _crud_response_schema(self, method: str, meta: dict) -> dict:
        model_class = meta['model_class']
        model_name = model_class.__name__
        self._ensure_model_in_components(model_class)

        if method == 'GET' and 'object_id' not in meta.get('path_params', []):
            # Collection: wrap items in the AppKernel envelope
            return {
                'type': 'object',
                'properties': {
                    '_type':  {'type': 'string'},
                    '_items': {'type': 'array', 'items': {'$ref': f'#/components/schemas/{model_name}'}},
                    '_links': {'type': 'object'},
                },
            }
        elif method == 'DELETE':
            return {
                'type': 'object',
                'properties': {
                    '_type':  {'type': 'string', 'example': 'OperationResult'},
                    'result': {'type': 'integer'},
                },
            }
        else:
            return {'$ref': f'#/components/schemas/{model_name}'}

    def _infer_response_schema(self, handler_func: Any) -> dict | None:
        if handler_func is None:
            return None
        try:
            hints = get_type_hints(handler_func)
        except Exception:
            return None

        from .model import Model
        ret = hints.get('return')
        if ret is None:
            return None
        actual = _unwrap_optional(ret)
        if inspect.isclass(actual) and issubclass(actual, Model):
            return self._model_schema_ref(actual)
        return _python_type_to_oas(actual)

    # -----------------------------------------------------------------------
    # Component schema helpers
    # -----------------------------------------------------------------------

    def _model_schema_ref(self, model_class: type) -> dict:
        self._ensure_model_in_components(model_class)
        return {'$ref': f'#/components/schemas/{model_class.__name__}'}

    def _ensure_model_in_components(self, model_class: type) -> None:
        """Add *model_class* to ``components/schemas`` if not already present.

        Uses :meth:`~appkernel.Model.get_json_schema` so that validator
        constraints (Min, Max, Email, Regexp, NotEmpty, Unique) and nested
        model definitions are included automatically.
        """
        from .model import Model
        name = model_class.__name__
        if name in self._components:
            return
        if inspect.isclass(model_class) and issubclass(model_class, Model):
            raw = model_class.get_json_schema(additional_properties=False)
            # Remove draft-04 $schema key — not valid inside OAS 3.1 components
            raw.pop('$schema', None)
            self._components[name] = raw
        else:
            self._components[name] = {'type': 'object'}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _default_summary(endpoint_name: str, method: str, meta: dict) -> str:
    crud_op = meta.get('crud_operation', '')
    model_cls = meta.get('model_class')
    model_name = model_cls.__name__ if model_cls else ''
    summaries = {
        'find_by_query':  f'List {model_name}',
        'find_by_id':     f'Get {model_name} by ID',
        'save_object':    f'Create {model_name}' if method == 'POST' else f'Patch {model_name}',
        'replace_object': f'Replace {model_name}',
        'delete_by_id':   f'Delete {model_name} by ID',
        'aggregate':      f'Aggregate {model_name}',
    }
    if crud_op in summaries:
        return summaries[crud_op]
    return endpoint_name.replace('_', ' ').title()


def _unwrap_optional(hint: Any) -> Any:
    """Strip ``Optional`` / ``X | None`` wrappers and return the base type."""
    import types as _types
    origin = getattr(hint, '__origin__', None)
    # Union types: Optional[X] == Union[X, None], X | None uses types.UnionType in 3.10+
    if origin is _types.UnionType if hasattr(_types, 'UnionType') else False:
        args = [a for a in hint.__args__ if a is not type(None)]
        return args[0] if args else hint
    # typing.Union
    try:
        import typing
        if origin is typing.Union:
            args = [a for a in hint.__args__ if a is not type(None)]
            return args[0] if args else hint
    except Exception:
        pass
    return hint


def _python_type_to_oas(python_type: Any) -> dict | None:
    """Map a Python type annotation to an OpenAPI schema fragment."""
    if python_type is None:
        return None
    type_name = getattr(python_type, '__name__', str(python_type))
    return _PY_TO_OAS.get(type_name, {'type': 'object'})
