import datetime
import jwt
from flask import current_app, g, request

from appkernel.configuration import config


class Permission(object):
    pass


class Role(Permission):
    def __init__(self, role_name='anonymous'):
        super(Role, self).__init__()
        self.name = role_name


class Anonymous(Role):
    def __init__(self):
        super(Anonymous, self).__init__(role_name='anonymous')


class Denied(Role):
    def __init__(self):
        super(Denied, self).__init__(role_name='denied')


class Authority(Permission):
    def __init__(self, identity_name='anonymous', id=None):
        super(Authority, self).__init__()
        self.name = identity_name
        self.id = id


class CurrentUser(Authority):
    def __init__(self):
        super(CurrentUser, self).__init__('current_user')


class IdentityMixin(object):
    def __init__(self, id=None, roles=[Anonymous()]):
        self.id = id
        self.roles = roles

    @property
    def auth_token(self):
        if not self.id:
            raise AttributeError('The id of the Identity is not defined.')
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=0, seconds=5),
            'iat': datetime.datetime.utcnow(),
            'sub': self.id
        }
        # iss: issuer
        # aud: audience
        # jti: jwt id
        if self.roles and isinstance(self.roles, list) and len(self.roles) > 0:
            payload.update(roles=self.roles)
        return jwt.encode(
            payload,
            key=config.private_key,
            algorithm='RS256'
        )


class RbacMixin(object):
    protected_methods = {}

    @staticmethod
    def __set_list(current_list, methods=[], permission='*'):
        if isinstance(methods, list):
            for method in methods:
                current_list[method] = permission
        elif isinstance(methods, (str, basestring, unicode)):
            current_list[methods] = permission
        else:
            raise TypeError('Methods must be of type list or string.')

    @classmethod
    def deny_all(cls):
        for method in ['GET', 'POST', 'PUT', 'DELETE']:
            cls.protected_methods[method] = Denied()
        return cls

    @classmethod
    def deny(cls, permission, methods=[]):
        cls.__set_list(cls.protected_methods, methods, permission)
        return cls

    @classmethod
    def exempt(cls, permission, methods):
        return cls

    @classmethod
    def require(cls, permission, methods):
        RbacMixin.__set_list(cls.protected_methods, methods, permission)
        return cls
