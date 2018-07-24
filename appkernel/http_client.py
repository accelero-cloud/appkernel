import asyncio

import requests
from flask import request
from aiohttp import ClientSession
from appkernel import Model, AppKernelException
from appkernel.configuration import config
from appkernel.engine import MessageType


class RequestHandlingException(AppKernelException):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code: int = status_code
        self.upstream_service: str = None


class RequestWrapper(object):

    # todo: timeout, retry, request timing,
    # todo: post to unknown url brings to infinite time...
    def __init__(self, url: str):
        self.url = url

    def get_headers(self):
        headers = {}
        if request:
            auth_header = request.headers.get('Authorization')
            if auth_header:
                headers.update(Authorization=auth_header)
        accept_lang = request.accept_languages if request else 'en'
        headers['Accept-Language'] = accept_lang.best
        return headers

    def post(self, request_object: Model, stream: bool = False, timeout: int = 3):
        try:
            response = requests.post(self.url, data=request_object.dumps(), stream=stream, headers=self.get_headers(),
                                     timeout=timeout)
            if response.status_code is requests.codes.ok:
                return response.status_code, Model.to_dict(response.json())
            else:
                content = response.json()
                if '_type' in content and content.get('_type') == MessageType.ErrorMessage.name:
                    msg = content.get('message')
                    upstream = content.get('upstream_service')
                    exc = RequestHandlingException(response.status_code, msg)
                    exc.upstream_service = upstream
                    raise exc
                else:
                    raise RequestHandlingException(response.status_code, 'Error while calling service.')
        except Exception as exc:
            raise RequestHandlingException(500, str(exc))

    def get(self, request_object: Model):
        pass


class HttpClientServiceProxy(object):

    def __init__(self, root_url: str):
        self.root_url = root_url.rstrip('/')

    def __getattr__(self, item):
        if isinstance(item, str):
            return RequestWrapper(f'{self.root_url}/{item}s/')


class HttpClientFactory(object):

    @staticmethod
    def get(root_url: str):
        return HttpClientServiceProxy(root_url=root_url)
