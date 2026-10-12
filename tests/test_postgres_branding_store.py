"""Owned PostgreSQL: the PostgresBrandingStore adapter honours the same contract as the fake."""
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from branding_contract import StoreContract
from forge.account_sessions import PostgresSessionStore, SessionService
from forge.branding_store import BrandingUnavailable, PostgresBrandingStore
from forge.invitations import capability_digest
from forge.provisioning import SEED, provision
from mvp_support import mvp_database


class PostgresHarness:
    def __init__(self, db):
        self.db = db
        results = {result.slug: result for result in provision(db.admin, SEED, lambda results: None)}
        sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
        digest = lambda slug, role: capability_digest(sessions.login(*next(
            (a.email, a.password) for a in results[slug].accounts if a.role == role)).capability)
        self.store = PostgresBrandingStore(db.pool('forge_gateway_service'), db.pool('forge_branding_service'))
        self.code_a, self.code_b = 'org-a', 'org-b'
        self.org_a, self.org_b = results['org-a'].organization_id, results['org-b'].organization_id
        self.admin_a, self.member_a = digest('org-a', 'organization_admin'), digest('org-a', 'member')
        self.admin_b = digest('org-b', 'organization_admin')

    def deactivate(self, code):
        self.db.admin.execute('UPDATE forge.organizations SET active=false WHERE slug=%s', (code,))


@contextmanager
def postgres_harness():
    with mvp_database() as db:
        yield PostgresHarness(db)


class PostgresStoreContractTests(StoreContract, unittest.TestCase):
    harness = staticmethod(postgres_harness)


class PostgresStoreFailureTests(unittest.TestCase):
    def test_a_pool_that_cannot_serve_the_expected_role_is_unavailable_not_a_leak(self):
        with postgres_harness() as h:
            wrong = PostgresBrandingStore(h.db.pool('forge_account_service'), h.db.pool('forge_account_service'))
            with self.assertRaises(BrandingUnavailable):
                wrong.public('org-a')
            with self.assertRaises(BrandingUnavailable):
                wrong.read(h.admin_a, h.org_a)


if __name__ == '__main__':
    unittest.main()
