from __future__ import annotations

import datetime
import jwt

from appkernel.configuration import config


class Permission:

    def __init__(self, name: str) -> None:
        self.name = name


class Role(Permission):
    def __init__(self, role_name: str = 'anonymous') -> None:
        super().__init__(role_name)

    def __str__(self) -> str:
        return f'ROLE_{self.name.upper()}'


class Anonymous(Role):
    def __init__(self) -> None:
        super().__init__(role_name='anonymous')


class Denied(Role):
    def __init__(self) -> None:
        super().__init__(role_name='denied')


class Authority(Permission):
    def __init__(self, identity_name: str = 'anonymous', id: str | None = None) -> None:
        super().__init__(identity_name)
        self.id = id  # pylint: disable=C0103

    def __str__(self) -> str:
        return f'AUTHORITY_{self.name.upper()}'


class CurrentSubject(Authority):
    def __init__(self, binding_view_arg: str = 'object_id') -> None:
        super().__init__('current_user')
        self.view_arg = binding_view_arg


class IdentityMixin:
    from typing import ClassVar
    token_validity_in_seconds: ClassVar[int] = 3600

    def __init__(self, id: str | None = None, roles: list | None = None) -> None:
        self.id = id  # pylint: disable=C0103
        self.roles = roles if roles is not None else [Anonymous()]

    @staticmethod
    def set_validity(seconds: int) -> None:
        IdentityMixin.token_validity_in_seconds = seconds

    @property
    def auth_token(self) -> str:
        if not self.id:
            raise AttributeError('The id of the Identity is not defined.')
        payload = {
            'exp': datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=IdentityMixin.token_validity_in_seconds),
            'iat': datetime.datetime.now(datetime.UTC),
            'sub': self.id,
        }
        app_id = getattr(config, 'app_id', None)
        if app_id:
            payload['aud'] = app_id
        if self.roles and isinstance(self.roles, list) and len(self.roles) > 0:
            payload.update(roles=self.roles)
        return jwt.encode(
            payload,
            key=config.private_key,
            algorithm='RS256'
        )


class RbacMixin:

    # format of the method registry
    # {
    #   'GET': {
    #              'some_endpoint': [Permission1, Permission2],
    #               '*': [Permission3, Permission4],
    #           }
    # }

    def __init__(self, cls: type) -> None:
        self.cls = cls
        if not hasattr(cls, 'protected_methods'):
            cls.protected_methods = {}

    @staticmethod
    def set_list(
        cls: type,
        methods: list[str] | None = None,
        permissions: Permission = Denied(),
        endpoint: str | None = None,
    ) -> None:
        methods = methods if methods is not None else []

        def add_endpoint_and_permissions(meth: str) -> None:
            if not hasattr(cls, 'protected_methods'):
                cls.protected_methods = {}
            if meth not in cls.protected_methods:
                cls.protected_methods[meth] = {
                    endpoint or '*': permissions if isinstance(permissions, list) else [permissions]}
            else:
                cls.protected_methods[meth][endpoint or '*'] = permissions if isinstance(permissions,
                                                                                               list) else [
                    permissions]

        if (not isinstance(permissions, list) and not isinstance(permissions, Permission)) or (
                isinstance(permissions, list) and len([perm for perm in permissions if isinstance(perm, Permission)]) == 0):
            raise AttributeError('The permission must be a subclass of a Permission or list of Permissions')
        if isinstance(methods, list):
            for method in methods:
                add_endpoint_and_permissions(method)
        elif isinstance(methods, str):
            add_endpoint_and_permissions(methods)
        else:
            raise TypeError('Methods must be of type list or string.')

    def deny_all(self) -> RbacMixin:
        for method in ['GET', 'POST', 'PUT', 'DELETE']:
            if method not in self.cls.protected_methods:
                self.cls.protected_methods[method] = {'*': [Denied()]}
            else:
                self.cls.protected_methods[method]['*'] = [Denied()]
        return self

    def allow_all(self) -> RbacMixin:
        for method in ['GET', 'POST', 'PUT', 'DELETE']:
            if method not in self.cls.protected_methods:
                self.cls.protected_methods[method] = {'*': [Anonymous()]}
            else:
                self.cls.protected_methods[method]['*'] = [Anonymous()]
        return self

    def deny(self, permission: Permission, methods: list[str] | str, endpoint: str | None = None) -> RbacMixin:
        RbacMixin.set_list(self.cls, methods, permission, endpoint)
        return self

    def require(self, permission: Permission, methods: list[str] | str, endpoint: str | None = None) -> RbacMixin:
        RbacMixin.set_list(self.cls, methods, permission, endpoint)
        return self
