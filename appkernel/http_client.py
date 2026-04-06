from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any

import httpx

from appkernel import Model, AppKernelException
from appkernel.core import MessageType
from appkernel.model import _get_custom_class


@dataclass
class HttpClientConfig:
    """Connection pool and timeout configuration for inter-service HTTP calls.

    Pool sizing guidance:
    - max_connections: total simultaneous connections (active + queued). Set to
      your expected peak concurrency; requests queue once this is reached.
    - max_keepalive_connections: idle connections held open for reuse. Set to
      steady-state concurrency — excess idle connections waste file descriptors
      on both client and upstream server.
    - keepalive_expiry: seconds before an idle connection is proactively closed.
      Keep below the upstream server's own keep-alive timeout (typically 30–75s)
      to avoid reusing a connection the server has already closed.

    Timeout guidance:
    - connect_timeout: max seconds to establish a TCP+TLS connection.
    - read_timeout: max seconds to wait for the first response byte after sending.
    - write_timeout: max seconds to finish sending the request body.
    - pool_timeout: max seconds to wait for a connection slot in the pool when
      max_connections is exhausted. Acts as backpressure — raise it to queue
      requests, lower it to fail fast.

    Default profile: medium-traffic (20–100 req/s to each upstream service).
    """
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    connect_timeout: float = 2.0
    read_timeout: float = 10.0
    write_timeout: float = 5.0
    pool_timeout: float = 5.0


# ---------------------------------------------------------------------------
# Module-level singleton — one AsyncClient shared for the process lifetime.
# Initialised on first use with default config or explicitly by AppKernelEngine.
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def configure_http_client(cfg: HttpClientConfig | None = None) -> None:
    """Initialise (or replace) the shared AsyncClient with the given config.
    Called by AppKernelEngine at startup; falls back to HttpClientConfig defaults
    on first use if never called explicitly.
    """
    global _http_client
    c = cfg or HttpClientConfig()
    _http_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=c.max_connections,
            max_keepalive_connections=c.max_keepalive_connections,
            keepalive_expiry=c.keepalive_expiry,
        ),
        timeout=httpx.Timeout(
            connect=c.connect_timeout,
            read=c.read_timeout,
            write=c.write_timeout,
            pool=c.pool_timeout,
        ),
    )


async def close_http_client() -> None:
    """Gracefully close the shared AsyncClient. Called by AppKernelEngine on shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared AsyncClient, initialising with defaults on first use."""
    global _http_client
    if _http_client is None:
        configure_http_client()
    return _http_client


class RequestHandlingException(AppKernelException):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code: int = status_code
        self.upstream_service: str | None = None


class RequestWrapper:

    # todo: retry, request timing,
    # todo: post to unknown url brings to infinite time...
    def __init__(self, url: str) -> None:
        self.url = url

    @staticmethod
    def get_headers(auth_header: str | None = None, accept_language: str | None = 'en') -> dict[str, str]:
        """
        Build request headers.
        :param auth_header: Optional Authorization header value
        :param accept_language: Accept-Language value, defaults to 'en'
        :return: headers dict
        """
        headers: dict[str, str] = {}
        if auth_header:
            headers['Authorization'] = auth_header
        headers['Accept-Language'] = accept_language or 'en'
        return headers

    async def __execute(self, method: str, **kwargs: Any) -> tuple[int, Any]:
        try:
            path_ext = kwargs.pop('path_extension')
            if path_ext:
                endpoint_url = f'{self.url.rstrip("/")}/{path_ext.lstrip("/")}'
            else:
                endpoint_url = self.url
            response = await _get_client().request(method, endpoint_url, **kwargs)
            if 200 <= response.status_code <= 299:
                try:
                    response_object = response.json()
                except ValueError:
                    response_object = {'result': response.text}
                if '_type' in response_object and response_object.get('_type') not in ['OperationResult',
                                                                                       'ErrorMessage']:
                    type_class = _get_custom_class(response_object.pop('_type'))
                    return response.status_code, Model.from_dict(response_object, type_class)
                else:
                    return response.status_code, response_object
        except Exception as exc:
            raise RequestHandlingException(500, str(exc))
        else:
            content = response.json()
            if '_type' in content and content.get('_type') == MessageType.ErrorMessage.name:
                msg = content.get('message')
                upstream = content.get('upstream_service', self.url.rstrip('/').split('/').pop())
                exc = RequestHandlingException(response.status_code, msg)
                exc.upstream_service = upstream
                raise exc
            else:
                raise RequestHandlingException(response.status_code, 'Error while calling service.')

    @staticmethod
    def _serialize(payload: Any) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, Model):
            return payload.dumps()
        if isinstance(payload, dict):
            return _json.dumps(payload)
        return payload

    async def post(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('POST',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def get(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('GET',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def put(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('PUT',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def patch(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('PATCH',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)

    async def delete(self, payload: Any = None, path_extension: str | None = None, stream: bool = False, timeout: int = 3) -> tuple[int, Any]:
        return await self.__execute('DELETE',
                                    path_extension=path_extension,
                                    content=self._serialize(payload),
                                    headers=self.get_headers(),
                                    timeout=timeout,
                                    follow_redirects=True)


class HttpClientServiceProxy:

    def __init__(self, root_url: str) -> None:
        self.root_url = root_url.rstrip('/')

    def wrap(self, resource_path: str) -> RequestWrapper:
        return RequestWrapper(f'{self.root_url}/{resource_path.lstrip("/")}')

    def __getattr__(self, item: str) -> RequestWrapper:
        if isinstance(item, str):
            return RequestWrapper(f'{self.root_url}/{item}/')


class HttpClientFactory:

    @staticmethod
    def get(root_url: str) -> HttpClientServiceProxy:
        return HttpClientServiceProxy(root_url=root_url)
