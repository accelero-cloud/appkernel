import requests
from flask import request

from appkernel import Model, AppKernelException
from appkernel.core import MessageType
from appkernel.model import _get_custom_class


class RequestHandlingException(AppKernelException):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code: int = status_code
        self.upstream_service: str = None


class RequestWrapper(object):

    # todo: timeout, retry, request timing,
    # todo: post to unknown url brings to infinite time...
    def __init__(self, url: str, session=None):
        self.url = url
        self.session = session if session else requests.Session()

    @staticmethod
    def get_headers():
        headers = {}
        if request:
            auth_header = request.headers.get('Authorization')
            if auth_header:
                headers.update(Authorization=auth_header)
        accept_lang = request.accept_languages if request else 'en'
        headers['Accept-Language'] = accept_lang.best if not isinstance(accept_lang, str) else accept_lang
        return headers

    def __execute(self, func, **kwargs):
        try:
            response = func(self.url, **kwargs)
            if 200 <= response.status_code <= 299:
                try:
                    response_object = response.json()
                except ValueError:
                    response_object = {'result': response.text}
                if '_type' in response_object and response_object.get('_type') not in ['OperationResult',
                                                                                       'ErrorMessage']:
                    type_class =  _get_custom_class(response_object.pop('_type'))
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

    def post(self, request_object: any = None, stream: bool = False, timeout: int = 3):
        data_content = request_object.dumps() if isinstance(request_object, Model) else request_object
        return self.__execute(self.session.post, data=data_content,
                              stream=stream,
                              headers=self.get_headers(),
                              timeout=timeout, allow_redirects=True)

    def get(self, request_object: any = None, stream: bool = False, timeout: int = 3):
        data_content = request_object.dumps() if isinstance(request_object, Model) else request_object
        return self.__execute(self.session.get, data=data_content,
                              stream=stream,
                              headers=self.get_headers(),
                              timeout=timeout, allow_redirects=True)

    def put(self, request_object: any = None, stream: bool = False, timeout: int = 3):
        data_content = request_object.dumps() if isinstance(request_object, Model) else request_object
        return self.__execute(self.session.put, data=data_content,
                              stream=stream,
                              headers=self.get_headers(),
                              timeout=timeout, allow_redirects=True)

    def patch(self, request_object: any = None, stream: bool = False, timeout: int = 3):
        data_content = request_object.dumps() if isinstance(request_object, Model) else request_object
        return self.__execute(self.session.patch, data=data_content,
                              stream=stream,
                              headers=self.get_headers(),
                              timeout=timeout, allow_redirects=True)

    def delete(self, request_object: any = None, stream: bool = False, timeout: int = 3):
        data_content = request_object.dumps() if isinstance(request_object, Model) else request_object
        return self.__execute(self.session.delete, data=data_content,
                              stream=stream,
                              headers=self.get_headers(),
                              timeout=timeout, allow_redirects=True)


class HttpClientServiceProxy(object):

    def __init__(self, root_url: str):
        self.root_url = root_url.rstrip('/')
        self.session = requests.Session()

    def wrap(self, resource_path: str):
        return RequestWrapper(f'{self.root_url}/{resource_path.lstrip("/")}', session=self.session)

    def __getattr__(self, item):
        if isinstance(item, str):
            return RequestWrapper(f'{self.root_url}/{item}/', session=self.session)


class HttpClientFactory(object):

    @staticmethod
    def get(root_url: str):
        return HttpClientServiceProxy(root_url=root_url)
