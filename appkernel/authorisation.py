import jwt
from flask import request
from flask_babel import _, lazy_gettext as _l
import appkernel
from appkernel.configuration import config


def check_token(jwt_token):
    return jwt.decode(jwt_token, config.public_key)


def authorize_request():
    required_permission = config.service_registry.get(request.endpoint).protected_methods.get(request.method)
    if required_permission:
        if isinstance(required_permission, appkernel.Denied):
            return appkernel.Service.app_engine.create_custom_error(403, _('Not allowed to access method.'))
        else:
            authorisation_header = request.headers.get('Authorization')
            if not authorisation_header:
                return appkernel.Service.app_engine.create_custom_error(401, _('The authorisation header is missing.'))
            try:
                token = check_token(authorisation_header.split(' ')[1])
                if isinstance(required_permission, appkernel.Role):
                    if required_permission.name not in token.get('roles'):
                        return appkernel.Service.app_engine.create_custom_error(403, _('The required permission is missing.'))
                else:
                    return appkernel.Service.app_engine.create_custom_error(401, _('The required permission is not yet implemented.'))
            except Exception as exc:
                return appkernel.Service.app_engine.create_custom_error(403, str(exc))
    #self.app.view_functions.get('users_get_by_id')
    # request.url_rule
    # request,base_url
    # request.endpoint : 'users_get_by_id'
    #self.app.url_map.
    pass
