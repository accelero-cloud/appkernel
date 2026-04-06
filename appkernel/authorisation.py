from __future__ import annotations
from typing import Any, TYPE_CHECKING
from appkernel import iam  # noqa: E402
from .util import create_custom_error  # noqa: E402
from appkernel.configuration import config  # noqa: E402
import jwt

if TYPE_CHECKING:
    from starlette.responses import JSONResponse


def _(message: str, **kwargs: Any) -> str:
    """Minimal i18n passthrough replacing flask_babel."""
    if kwargs:
        return message % kwargs
    return message


def check_token(jwt_token: str) -> dict[str, Any]:
    return jwt.decode(jwt_token, config.public_key, algorithms=['RS256'])


def __has_current_subject_authority(token: dict[str, Any], authority: Any, view_args: dict[str, str] | None = None) -> bool:
    if not isinstance(authority, iam.CurrentSubject):
        raise TypeError(f'This method required authority of type {iam.CurrentSubject.__name__}.')
    subject = token.get('sub', None)
    view_args = view_args or {}
    binding_id = view_args.get(authority.view_arg)
    if not subject or not binding_id:
        return False
    return subject == binding_id


def __get_required_permissions(clazz: Any, method: str, endpoint: str) -> list[Any]:
    pms = clazz.protected_methods.get(method)
    if endpoint in pms:
        perms = list(pms.get(endpoint))
    else:
        perms = list(pms.get('*'))

    if perms:
        if isinstance(perms, iam.Permission):
            perms = [perms]
        elif not isinstance(perms, list):
            raise AttributeError
    return perms


def __contains(required_permissions: list[Any], permission_type: type) -> bool:
    contained_permissions = [permission for permission in required_permissions if
                             isinstance(permission, permission_type)]
    return len(contained_permissions) > 0


def __split_to_roles_and_authorities(required_permissions: list[Any]) -> tuple[set[str], set[Any]]:
    required_roles: set[str] = set()
    required_authorities: set[Any] = set()
    for item in required_permissions:
        if isinstance(item, iam.Role):
            required_roles.add(item.name)
        elif isinstance(item, iam.Authority):
            required_authorities.add(item)
    return required_roles, required_authorities


def __has_required_authority(required_authorities: set[Any], token: dict[str, Any], view_args: dict[str, str] | None = None) -> bool:
    if not required_authorities or len(required_authorities) == 0:
        return False
    else:
        for required_authority in required_authorities:
            check_authority = authority_evaluators.get(required_authority.__class__.__name__)
            has_required_authority = check_authority(token, required_authority, view_args=view_args)
            if has_required_authority:
                return True
    return False


authority_evaluators: dict[str, Any] = {
    iam.CurrentSubject.__name__: __has_current_subject_authority
}


def authorize_request(
    method: str,
    endpoint: str,
    headers: Any,
    view_args: dict[str, str] | None = None,
) -> JSONResponse | None:
    """
    Authorize a request based on the method, endpoint, headers, and view_args.
    :param method: HTTP method (GET, POST, etc.)
    :param endpoint: the endpoint name
    :param headers: request headers (dict-like, e.g. starlette Headers)
    :param view_args: path parameters (dict)
    :return: None if authorized, or a JSONResponse error
    """
    view_args = view_args or {}
    endpoint_class = config.service_registry.get(endpoint)
    required_permissions = __get_required_permissions(endpoint_class, method, endpoint)

    if __contains(required_permissions, iam.Denied):
        return create_custom_error(403, _('Not allowed to access method.'))

    if __contains(required_permissions, iam.Anonymous):
        return None

    authorisation_header = headers.get('Authorization') if hasattr(headers, 'get') else headers.get('authorization')
    if not authorisation_header:
        return create_custom_error(401, _('The authorisation header is missing.'))
    try:
        token = check_token(authorisation_header.split(' ')[1])
        required_roles, required_authorities = __split_to_roles_and_authorities(required_permissions)

        missing_required_role = len(required_roles.intersection(set(token.get('roles', [])))) == 0
        missing_required_authority = not __has_required_authority(required_authorities, token, view_args=view_args)

        if missing_required_role and missing_required_authority:
            return create_custom_error(403, _('The required permission is missing.'))
    except AttributeError:
        return create_custom_error(401, _('The permission type is not supported.'))
    except Exception as exc:
        return create_custom_error(403, str(exc))
    return None
