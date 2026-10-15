"""Owned PostgreSQL: MvpReadiness attests exactly the reviewed 0001-0048 profile (F48) and nothing else."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F48, MVP_ADDITIONS
from forge.mvp_readiness import MvpReadiness
from mvp_support import at, mvp_database


def readiness(db):
    return MvpReadiness(db.pool('forge_account_service'), db.pool('forge_runtime'), db.pool('forge_gateway_service'))


class PostgresMvpReadinessTests(unittest.TestCase):
    def test_the_complete_profile_is_attested_and_its_fingerprint_is_the_pinned_f31(self):
        with mvp_database() as db:
            with db.admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F48)
            self.assertIs(readiness(db).check(), True)

    def test_a_previous_profile_missing_0031_0030_0029_0028_0027_0026_or_0025_is_refused(self):
        for dropped in range(1, len(MVP_ADDITIONS) - at('0025_org_branding.sql') + 1):
            name = MVP_ADDITIONS[-dropped][:4]
            with self.subTest(missing=name), mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:-dropped])) as db:
                with db.admin.cursor() as cursor:
                    self.assertNotEqual(catalog_fingerprint(cursor), F48)
                self.assertIs(readiness(db).check(), False)

    def test_schema_drift_is_refused(self):
        with mvp_database() as db:
            self.assertIs(readiness(db).check(), True)
            db.admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
            self.assertIs(readiness(db).check(), False)

    def test_an_authority_that_can_log_in_is_refused(self):
        for authority in ('forge_directory_authority', 'forge_branding_authority', 'forge_platform_authority',
                          'forge_capability_authority', 'forge_broker_authority'):
            with self.subTest(authority=authority), mvp_database() as db:
                self.assertIs(readiness(db).check(), True)
                db.admin.execute('ALTER ROLE %s LOGIN' % authority)
                self.assertIs(readiness(db).check(), False)


if __name__ == '__main__':
    unittest.main()
