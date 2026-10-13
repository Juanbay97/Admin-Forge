"""Owned PostgreSQL: PlatformService over the real store and the dedicated pool, with the cross-organization denial matrix."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.platform import AuditEntry, Company, PlatformDenied, PlatformIdentity, PlatformService, PlatformUnavailable
from forge.platform_store import PostgresPlatformStore
from forge.provisioning import SEED, provision
from mvp_support import mvp_database
from platform_support import add_account, add_owner, sign_in


class PlatformStoreTests(unittest.TestCase):
    def world(self, db):
        results = provision(db.admin, SEED, lambda created: None)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.people = {(result.slug, account.role): account for result in results for account in result.accounts}
        self.owner = add_owner(db.admin)
        self.service = PlatformService(PostgresPlatformStore(db.pool('forge_platform_service')))
        self.token, _ = sign_in(db, mfa=True)

    def operations(self, token):
        return {'me': lambda: self.service.me(token), 'companies': lambda: self.service.companies(token),
                'company': lambda: self.service.company(token, self.orgs['org-a']), 'audit': lambda: self.service.audit(token)}

    def test_the_owner_reads_its_identity_the_companies_one_company_and_the_audit_log(self):
        with mvp_database() as db:
            self.world(db)
            self.assertEqual(self.service.me(self.token), PlatformIdentity(self.owner, 'platform_owner'))
            self.assertEqual(self.service.companies(self.token), [Company(self.orgs['org-a'], 'org-a', 'Organization A', True),
                                                                  Company(self.orgs['org-b'], 'org-b', 'Organization B', True)])
            self.assertEqual(self.service.companies(self.token, after='org-a', page=1),
                             [Company(self.orgs['org-b'], 'org-b', 'Organization B', True)])
            self.assertEqual(self.service.company(self.token, self.orgs['org-b']),
                             Company(self.orgs['org-b'], 'org-b', 'Organization B', True))
            db.admin.execute("SELECT forge.platform_audit_write(%s,'company.created',%s)", (self.owner, self.orgs['org-a']))
            (entry,) = self.service.audit(self.token)
            self.assertEqual((type(entry), entry.actor_id, entry.action, entry.organization_id),
                             (AuditEntry, self.owner, 'company.created', self.orgs['org-a']))

    def test_every_non_owner_is_denied_every_operation_the_same_way(self):
        with mvp_database() as db:
            self.world(db)
            add_owner(db.admin, 'viewer@platform.test', 'platform_viewer')
            add_account(db.admin, 'plain@platform.test')
            callers = {
                'admin of A': sign_in(db, self.people[('org-a', 'organization_admin')].email, self.people[('org-a', 'organization_admin')].password)[0],
                'member of A': sign_in(db, self.people[('org-a', 'member')].email, self.people[('org-a', 'member')].password)[0],
                'admin of B': sign_in(db, self.people[('org-b', 'organization_admin')].email, self.people[('org-b', 'organization_admin')].password)[0],
                'viewer': sign_in(db, 'viewer@platform.test')[0],
                'account without any role': sign_in(db, 'plain@platform.test')[0],
                'unknown capability': 'A' * 43,
            }
            for name, token in callers.items():
                for operation, run in self.operations(token).items():
                    if name == 'viewer' and operation == 'me':
                        self.assertEqual(run().role, 'platform_viewer')
                        continue
                    with self.subTest(caller=name, operation=operation), self.assertRaises(PlatformDenied):
                        run()

    def test_a_revoked_session_and_a_disabled_owner_are_denied(self):
        with mvp_database() as db:
            self.world(db)
            self.assertEqual(self.service.me(self.token).role, 'platform_owner')
            db.admin.execute('UPDATE forge.account_sessions SET revoked=true')
            for operation, run in self.operations(self.token).items():
                with self.subTest(operation=operation), self.assertRaises(PlatformDenied):
                    run()
            second, _ = sign_in(db, mfa=True)
            db.admin.execute('UPDATE forge.owned_accounts SET active=false WHERE id=%s', (self.owner,))
            for operation, run in self.operations(second).items():
                with self.subTest(after='disabled', operation=operation), self.assertRaises(PlatformDenied):
                    run()

    def test_the_owner_sees_exactly_the_requested_company_and_a_missing_one_is_not_found(self):
        with mvp_database() as db:
            self.world(db)
            for slug in ('org-a', 'org-b'):
                self.assertEqual(self.service.company(self.token, self.orgs[slug]).slug, slug)
            from forge.platform import PlatformNotFound
            with self.assertRaises(PlatformNotFound):
                self.service.company(self.token, uuid4())
            db.admin.execute("UPDATE forge.organizations SET active=false WHERE slug='org-b'")
            self.assertEqual([(c.slug, c.active) for c in self.service.companies(self.token)], [('org-a', True), ('org-b', False)])

    def test_the_store_refuses_a_pool_that_is_not_the_platform_role(self):
        with mvp_database() as db:
            self.world(db)
            for role in ('forge_runtime', 'forge_gateway_service', 'forge_account_service'):
                with self.subTest(role=role), self.assertRaises(PlatformUnavailable):
                    PlatformService(PostgresPlatformStore(db.pool(role))).me(self.token)

    def test_a_database_failure_is_the_finite_unavailable_code_not_a_leak(self):
        with mvp_database() as db:
            self.world(db)
            db.admin.execute('REVOKE EXECUTE ON FUNCTION forge.platform_me(text) FROM forge_platform_service')
            with self.assertRaises(PlatformUnavailable) as caught:
                self.service.me(self.token)
            self.assertEqual((caught.exception.code, str(caught.exception)), ('PLATFORM_UNAVAILABLE', 'Platform administration is unavailable.'))


if __name__ == '__main__':
    unittest.main()
