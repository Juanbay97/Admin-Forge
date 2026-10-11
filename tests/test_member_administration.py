"""Member administration service rules over a fake store; no database."""
from pathlib import Path
import secrets
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from uuid import uuid4
from forge.directory import (Department, DirectoryConflict, DirectoryDenied, DirectoryLastAdmin,
    DirectoryService, Member)
from forge.invitations import capability_digest

ORG = uuid4()
MEMBER = uuid4()


def member(status='active', roles=('member',), name='Pat', email='pat@example.com', departments=(), ident=None):
    return Member(ident or MEMBER, email, name, status, roles, departments)


class Store:
    def __init__(self, members=()):
        self.members_value, self.digests, self.statuses = list(members), [], []

    def members(self, digest, org):
        self.digests.append(digest)
        return self.members_value

    def set_member_status(self, digest, org, member_id, status):
        self.digests.append(digest)
        self.statuses.append((org, member_id, status))
        return member(status=status, ident=member_id)


class MemberListTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(32)

    def test_lists_every_status_with_roles_and_departments(self):
        legal = Department(uuid4(), 'Legal')
        store = Store([member('active', ('organization_admin',), 'Ada', 'ada@example.com', ident=uuid4()),
                       member('active', ('member',), 'Pat', departments=(legal,)),
                       member('suspended', ('member',), 'Sam', 'sam@example.com', ident=uuid4())])
        listed = DirectoryService(store).members(self.token, ORG)
        self.assertEqual([(m.display_name, m.status, m.roles) for m in listed],
                         [('Ada', 'active', ('organization_admin',)), ('Pat', 'active', ('member',)),
                          ('Sam', 'suspended', ('member',))])
        self.assertEqual(listed[1].departments, (legal,))

    def test_only_a_digest_reaches_the_store_never_the_token(self):
        store = Store([member()])
        DirectoryService(store).members(self.token, ORG)
        self.assertEqual(store.digests, [capability_digest(self.token)])
        self.assertNotIn(self.token, store.digests)

    def test_organization_must_be_a_uuid_before_the_store(self):
        store = Store([member()])
        for value in (str(ORG), None, 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DirectoryService(store).members(self.token, value)
        self.assertEqual(store.digests, [])

    def test_denial_propagates_uniformly(self):
        class Denying(Store):
            def members(self, digest, org):
                raise DirectoryDenied()
        with self.assertRaises(DirectoryDenied):
            DirectoryService(Denying()).members(self.token, ORG)


class MemberStatusTests(unittest.TestCase):
    def setUp(self):
        self.token, self.store = secrets.token_urlsafe(32), Store()
        self.service = DirectoryService(self.store)

    def test_suspend_requests_the_suspended_status_and_returns_the_member(self):
        result = self.service.suspend_member(self.token, ORG, MEMBER)
        self.assertEqual((result.id, result.status), (MEMBER, 'suspended'))
        self.assertEqual(self.store.statuses, [(ORG, MEMBER, 'suspended')])
        self.assertEqual(self.store.digests, [capability_digest(self.token)])

    def test_reactivate_requests_the_active_status(self):
        result = self.service.reactivate_member(self.token, ORG, MEMBER)
        self.assertEqual(result.status, 'active')
        self.assertEqual(self.store.statuses, [(ORG, MEMBER, 'active')])

    def test_identifiers_must_be_uuids_before_the_store(self):
        for org, target in ((str(ORG), MEMBER), (ORG, str(MEMBER)), (None, MEMBER), (ORG, None), (ORG, 7)):
            for operation in (self.service.suspend_member, self.service.reactivate_member):
                with self.subTest(org=org, target=target, op=operation.__name__), self.assertRaises(ValueError):
                    operation(self.token, org, target)
        self.assertEqual(self.store.statuses, [])

    def test_last_admin_refusal_is_redacted_and_distinct_from_conflict(self):
        class Guarded(Store):
            def set_member_status(self, digest, org, member_id, status):
                raise DirectoryLastAdmin()
        with self.assertRaises(DirectoryLastAdmin) as caught:
            DirectoryService(Guarded()).suspend_member(self.token, ORG, MEMBER)
        self.assertNotIn(str(MEMBER), str(caught.exception))
        self.assertNotIsInstance(caught.exception, DirectoryConflict)

    def test_denial_for_unknown_or_foreign_member_propagates(self):
        class Denying(Store):
            def set_member_status(self, digest, org, member_id, status):
                raise DirectoryDenied()
        for operation in ('suspend_member', 'reactivate_member'):
            with self.subTest(op=operation), self.assertRaises(DirectoryDenied):
                getattr(DirectoryService(Denying()), operation)(self.token, ORG, MEMBER)


if __name__ == '__main__':
    unittest.main()
