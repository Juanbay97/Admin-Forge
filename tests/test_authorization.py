"""Deterministic exact-role/action authorization contract."""
from dataclasses import FrozenInstanceError, replace
from itertools import combinations
from pathlib import Path
import sys
import unittest
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.authorization import AuthorizationSnapshot, permits
from forge.foundation import AuthenticatedIdentity, MembershipStatus

ROLES = ('organization_admin','department_manager','skill_reviewer','member')
ACTIONS = ('members.invite','members.update','members.suspend')
def snapshot(**changes):
    fields = dict(identity=AuthenticatedIdentity('test','issuer','alice'),
        organization_id=UUID(int=1),membership_id=UUID(int=21),revision=1,
        roles=frozenset({'organization_admin'}),membership_status=MembershipStatus.ACTIVE,
        organization_active=True)
    return AuthorizationSnapshot(**(fields | changes))

class AuthorizationTests(unittest.TestCase):
    def test_exact_role_combinations_and_actions(self):
        for size in range(5):
            for roles in combinations(ROLES,size):
                for action in ACTIONS:
                    with self.subTest(roles=roles,action=action):
                        self.assertIs(permits(snapshot(roles=frozenset(roles)),action),
                            'organization_admin' in roles)
    def test_unknown_and_platform_roles_fail_closed_even_mixed(self):
        for role in ('platform_operator','unknown','Organization_Admin','organization_admin ',1,None):
            for roles in (frozenset({role}),frozenset({'organization_admin',role})):
                self.assertFalse(permits(snapshot(roles=roles),'members.invite'))
    def test_unknown_or_untyped_actions_deny(self):
        for action in ('members.delete','MEMBERS.INVITE','members.invite ','',None,1,{},[]):
            self.assertFalse(permits(snapshot(),action))
    def test_inactive_or_malformed_snapshot_denies(self):
        changes=({'revision':x} for x in (True,False,0,-1,2**63,10**400,1.0,'1',None))
        changes=list(changes)+[{'organization_id':'bad'},{'membership_id':'bad'},
            {'identity':None},{'identity':AuthenticatedIdentity('test','issuer',' ')},
            {'membership_status':MembershipStatus.SUSPENDED},
            {'membership_status':MembershipStatus.ARCHIVED},{'membership_status':'active'},
            {'organization_active':False},{'organization_active':1}]
        for change in changes:
            with self.subTest(change=list(change)):
                self.assertFalse(permits(snapshot(**change),'members.invite'))
        for value in (None,{},object()):self.assertFalse(permits(value,'members.invite'))
    def test_roles_are_copied_without_value_coercion_and_snapshot_is_frozen(self):
        roles={'organization_admin'};value=snapshot(roles=roles);roles.clear()
        self.assertEqual(value.roles,frozenset({'organization_admin'}))
        self.assertIs(type(value.roles),frozenset)
        with self.assertRaises(FrozenInstanceError):value.revision=2
        for bad in ('organization_admin',['organization_admin'],None,{}):
            with self.subTest(type=type(bad)),self.assertRaises(ValueError):snapshot(roles=bad)
        self.assertNotIn('alice',repr(value))
    def test_bigint_max_is_valid_but_snapshot_is_not_authentication(self):
        self.assertTrue(permits(snapshot(revision=2**63-1),'members.update'))

    def test_model_publication_is_exact_admin_only(self):
        for size in range(5):
            for roles in combinations(ROLES, size):
                self.assertIs(permits(snapshot(roles=frozenset(roles)), 'models.publish'),
                              'organization_admin' in roles)
        for action in ('models.Publish', 'models.publish ', 'models.delete'):
            self.assertFalse(permits(snapshot(), action))
        self.assertFalse(permits(snapshot(roles=frozenset({'platform_operator'})), 'models.publish'))
