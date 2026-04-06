"""
Unit tests for the pure-logic helpers in appkernel/authorisation.py.

Module-level functions with double-underscore names are accessible directly
from the module dict (Python name mangling only applies inside class bodies).

No running FastAPI app or MongoDB required.
"""
import pytest

import appkernel.authorisation as _auth
from appkernel.iam import (
    Anonymous,
    Authority,
    CurrentSubject,
    Denied,
    Role,
)

# Retrieve private module-level functions via the module dict.
# These names are NOT name-mangled (mangling is class-body only), but they
# ARE excluded from star-imports, so we fetch them explicitly.
_contains = vars(_auth)['__contains']
_split = vars(_auth)['__split_to_roles_and_authorities']
_has_current_subject = vars(_auth)['__has_current_subject_authority']
_has_required_authority = vars(_auth)['__has_required_authority']


# ---------------------------------------------------------------------------
# __contains
# ---------------------------------------------------------------------------

def test_contains_finds_matching_permission_type():
    perms = [Role('admin'), Anonymous()]
    assert _contains(perms, Role) is True


def test_contains_finds_anonymous():
    perms = [Anonymous()]
    assert _contains(perms, Anonymous) is True


def test_contains_returns_false_when_absent():
    perms = [Role('admin')]
    assert _contains(perms, Denied) is False


def test_contains_empty_list_returns_false():
    assert _contains([], Role) is False


def test_contains_finds_denied():
    perms = [Denied(), Role('user')]
    assert _contains(perms, Denied) is True


# ---------------------------------------------------------------------------
# __split_to_roles_and_authorities
# ---------------------------------------------------------------------------

def test_split_separates_roles_from_authorities():
    perms = [Role('admin'), Role('user'), CurrentSubject()]
    roles, authorities = _split(perms)
    assert roles == {'admin', 'user'}
    assert len(authorities) == 1
    assert any(isinstance(a, CurrentSubject) for a in authorities)


def test_split_roles_only():
    perms = [Role('admin'), Role('editor')]
    roles, authorities = _split(perms)
    assert roles == {'admin', 'editor'}
    assert len(authorities) == 0


def test_split_authorities_only():
    cs = CurrentSubject()
    perms = [cs]
    roles, authorities = _split(perms)
    assert len(roles) == 0
    assert cs in authorities


def test_split_empty_input():
    roles, authorities = _split([])
    assert roles == set()
    assert len(authorities) == 0


# ---------------------------------------------------------------------------
# __has_current_subject_authority
# ---------------------------------------------------------------------------

def test_has_current_subject_matching_subject_and_binding():
    cs = CurrentSubject()  # view_arg='object_id'
    token = {'sub': 'user123'}
    assert _has_current_subject(token, cs, view_args={'object_id': 'user123'}) is True


def test_has_current_subject_mismatched_binding():
    cs = CurrentSubject()
    token = {'sub': 'user123'}
    assert _has_current_subject(token, cs, view_args={'object_id': 'other_user'}) is False


def test_has_current_subject_missing_subject_in_token():
    cs = CurrentSubject()
    token = {}
    assert _has_current_subject(token, cs, view_args={'object_id': 'user123'}) is False


def test_has_current_subject_missing_binding_in_view_args():
    cs = CurrentSubject()
    token = {'sub': 'user123'}
    assert _has_current_subject(token, cs, view_args={}) is False


def test_has_current_subject_none_view_args_treated_as_empty():
    cs = CurrentSubject()
    token = {'sub': 'user123'}
    assert _has_current_subject(token, cs, view_args=None) is False


def test_has_current_subject_wrong_authority_type_raises():
    plain_auth = Authority('read')
    token = {'sub': 'user123'}
    with pytest.raises(TypeError, match='CurrentSubject'):
        _has_current_subject(token, plain_auth, view_args={'object_id': 'user123'})


# ---------------------------------------------------------------------------
# __has_required_authority
# ---------------------------------------------------------------------------

def test_has_required_authority_empty_set_returns_false():
    result = _has_required_authority(set(), {'sub': 'x'})
    assert result is False


def test_has_required_authority_matching_current_subject_returns_true():
    cs = CurrentSubject()
    token = {'sub': 'user42'}
    result = _has_required_authority({cs}, token, view_args={'object_id': 'user42'})
    assert result is True


def test_has_required_authority_mismatched_current_subject_returns_false():
    cs = CurrentSubject()
    token = {'sub': 'user42'}
    result = _has_required_authority({cs}, token, view_args={'object_id': 'other'})
    assert result is False
