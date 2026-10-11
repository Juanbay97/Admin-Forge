"""Directory service rules over a fake store; no database."""
from pathlib import Path
import secrets
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from uuid import uuid4
from forge.directory import Department, DirectoryDenied, DirectoryService, DirectorySuspended, MemberRow
from forge.invitations import capability_digest

ACCOUNT = uuid4()
ORG_A, ORG_B = uuid4(), uuid4()


def row(org=ORG_A, name='Org A', status='active', roles=('organization_admin',), departments=(), account=ACCOUNT):
    return MemberRow(account, 'admin@example.com', 'Admin', org, name, status, roles, departments)


class Store:
    def __init__(self, rows=()):
        self.rows, self.digests = list(rows), []

    def me(self, digest):
        self.digests.append(digest)
        return self.rows


class MeTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(32)

    def test_admin_of_one_org(self):
        store = Store([row(departments=(Department(uuid4(), 'Legal'),))])
        me = DirectoryService(store).me(self.token)
        self.assertEqual((me.account.email, me.account.display_name), ('admin@example.com', 'Admin'))
        self.assertEqual([(o.id, o.roles, o.status) for o in me.organizations],
                         [(ORG_A, ('organization_admin',), 'active')])
        self.assertEqual(me.organizations[0].departments[0].name, 'Legal')

    def test_multi_org_lists_each_with_its_own_roles_only(self):
        store = Store([row(), row(ORG_B, 'Org B', roles=('member',))])
        orgs = DirectoryService(store).me(self.token).organizations
        self.assertEqual({o.id: o.roles for o in orgs}, {ORG_A: ('organization_admin',), ORG_B: ('member',)})

    def test_suspended_membership_is_omitted_when_another_is_active(self):
        store = Store([row(status='suspended'), row(ORG_B, 'Org B', roles=('member',))])
        orgs = DirectoryService(store).me(self.token).organizations
        self.assertEqual([o.id for o in orgs], [ORG_B])

    def test_no_active_membership_is_denied_not_empty(self):
        for status in ('suspended', 'archived'):
            with self.subTest(status=status), self.assertRaises(DirectorySuspended):
                DirectoryService(Store([row(status=status)])).me(self.token)

    def test_no_membership_at_all_is_the_uniform_denial(self):
        with self.assertRaises(DirectoryDenied):
            DirectoryService(Store([])).me(self.token)

    def test_only_a_digest_reaches_the_store_never_the_token(self):
        store = Store([row()])
        DirectoryService(store).me(self.token)
        self.assertEqual(store.digests, [capability_digest(self.token)])
        self.assertNotIn(self.token, store.digests)

    def test_rows_of_another_account_are_refused(self):
        store = Store([row(), row(ORG_B, account=uuid4())])
        with self.assertRaises(Exception):
            DirectoryService(store).me(self.token)


if __name__ == '__main__':
    unittest.main()
