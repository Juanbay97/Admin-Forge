"""Member list service rules over a fake store; no database."""
from pathlib import Path
import secrets
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from uuid import uuid4
from forge.directory import Department, DirectoryDenied, DirectoryService, Member
from forge.invitations import capability_digest

ORG = uuid4()
MEMBER = uuid4()


def member(status='active', roles=('member',), name='Pat', email='pat@example.com', departments=(), ident=None):
    return Member(ident or MEMBER, email, name, status, roles, departments)


class Store:
    def __init__(self, members=()):
        self.members_value, self.digests = list(members), []

    def members(self, digest, org):
        self.digests.append(digest)
        return self.members_value


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


if __name__ == '__main__':
    unittest.main()
