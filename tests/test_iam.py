"""Tests for iam.py: Role, Authority, IdentityMixin, RbacMixin."""
import pytest

from appkernel.iam import (
    Anonymous,
    Authority,
    CurrentSubject,
    Denied,
    IdentityMixin,
    Permission,
    RbacMixin,
    Role,
)


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

def test_role_str_representation():
    assert str(Role('admin')) == 'ROLE_ADMIN'


def test_role_str_lowercased_input():
    assert str(Role('user')) == 'ROLE_USER'


def test_anonymous_is_role():
    anon = Anonymous()
    assert isinstance(anon, Role)
    assert str(anon) == 'ROLE_ANONYMOUS'


def test_denied_is_role():
    denied = Denied()
    assert isinstance(denied, Role)
    assert str(denied) == 'ROLE_DENIED'


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------

def test_authority_str_representation():
    assert str(Authority('read')) == 'AUTHORITY_READ'


def test_authority_with_id():
    auth = Authority('write', id='user123')
    assert auth.id == 'user123'
    assert str(auth) == 'AUTHORITY_WRITE'


def test_current_subject_is_authority():
    cs = CurrentSubject()
    assert isinstance(cs, Authority)


# ---------------------------------------------------------------------------
# IdentityMixin
# ---------------------------------------------------------------------------

def test_identity_mixin_init_with_roles():
    ident = IdentityMixin(id='U123', roles=[Role('admin')])
    assert ident.id == 'U123'
    assert len(ident.roles) == 1
    assert isinstance(ident.roles[0], Role)


def test_identity_mixin_default_roles_are_anonymous():
    ident = IdentityMixin(id='U456')
    assert len(ident.roles) == 1
    assert isinstance(ident.roles[0], Anonymous)


def test_identity_mixin_auth_token_without_id_raises():
    ident = IdentityMixin()
    with pytest.raises(AttributeError, match='id of the Identity is not defined'):
        _ = ident.auth_token


# ---------------------------------------------------------------------------
# RbacMixin.set_list
# ---------------------------------------------------------------------------

class _MockService:
    pass


def test_rbac_set_list_invalid_permission_raises():
    svc = _MockService()
    with pytest.raises(AttributeError, match='permission must be a subclass'):
        RbacMixin.set_list(svc, methods=['GET'], permissions='not-a-permission')


def test_rbac_set_list_invalid_methods_type_raises():
    svc = _MockService()
    with pytest.raises(TypeError, match='Methods must be of type list or string'):
        RbacMixin.set_list(svc, methods=123, permissions=Role('admin'))


def test_rbac_set_list_with_string_method():
    svc = _MockService()
    RbacMixin.set_list(svc, methods='GET', permissions=Role('user'))
    assert 'GET' in svc.protected_methods


def test_rbac_set_list_with_list_methods():
    svc = _MockService()
    RbacMixin.set_list(svc, methods=['GET', 'POST'], permissions=Role('admin'))
    assert 'GET' in svc.protected_methods
    assert 'POST' in svc.protected_methods


def test_rbac_set_list_with_permission_list():
    svc = _MockService()
    RbacMixin.set_list(svc, methods=['GET'], permissions=[Role('user'), Role('admin')])
    perms = svc.protected_methods['GET']['*']
    assert len(perms) == 2
    assert all(isinstance(p, Role) for p in perms)


def test_rbac_set_list_empty_permission_list_raises():
    svc = _MockService()
    with pytest.raises(AttributeError, match='permission must be a subclass'):
        RbacMixin.set_list(svc, methods=['GET'], permissions=[])


# ---------------------------------------------------------------------------
# RbacMixin.allow_all / deny_all
# ---------------------------------------------------------------------------

def _make_rbac():
    """Create a RbacMixin instance backed by a fresh mock service class."""
    svc = type('Svc', (), {})
    rc = RbacMixin.__new__(RbacMixin)
    rc.cls = svc
    rc.cls.protected_methods = {}
    return rc


def test_rbac_allow_all_sets_anonymous_on_all_methods():
    rc = _make_rbac()
    rc.allow_all()
    for method in ['GET', 'POST', 'PUT', 'DELETE']:
        perms = rc.cls.protected_methods[method]['*']
        assert any(isinstance(p, Anonymous) for p in perms)


def test_rbac_deny_all_sets_denied_on_all_methods():
    rc = _make_rbac()
    rc.deny_all()
    for method in ['GET', 'POST', 'PUT', 'DELETE']:
        perms = rc.cls.protected_methods[method]['*']
        assert any(isinstance(p, Denied) for p in perms)


def test_rbac_allow_all_is_chainable():
    rc = _make_rbac()
    result = rc.allow_all()
    assert result is rc


def test_rbac_deny_all_is_chainable():
    rc = _make_rbac()
    result = rc.deny_all()
    assert result is rc


# ---------------------------------------------------------------------------
# RbacMixin.__init__ stores self.cls
# ---------------------------------------------------------------------------

def test_rbac_init_stores_cls():
    """RbacMixin.__init__ must store cls as self.cls so instance methods work
    when RbacMixin is used directly (not via ResourceController)."""
    svc = type('Svc', (), {})
    rc = RbacMixin(svc)
    assert rc.cls is svc


# ---------------------------------------------------------------------------
# RbacMixin.deny
# ---------------------------------------------------------------------------

def test_rbac_deny_sets_permission_on_single_method():
    """deny() must register the given permission on a single HTTP method."""
    rc = _make_rbac()
    rc.deny(Denied(), 'DELETE')
    assert 'DELETE' in rc.cls.protected_methods


def test_rbac_deny_sets_permission_on_multiple_methods():
    """deny() must register the given permission on each method in a list."""
    rc = _make_rbac()
    rc.deny(Denied(), ['GET', 'DELETE'])
    assert 'GET' in rc.cls.protected_methods
    assert 'DELETE' in rc.cls.protected_methods


def test_rbac_deny_stores_correct_permission():
    """deny() must store the exact permission passed, not a default."""
    rc = _make_rbac()
    rc.deny(Denied(), 'POST')
    perms = rc.cls.protected_methods['POST']['*']
    assert any(isinstance(p, Denied) for p in perms)


def test_rbac_deny_is_chainable():
    """deny() must return self to support fluent chaining."""
    rc = _make_rbac()
    result = rc.deny(Denied(), 'DELETE')
    assert result is rc
