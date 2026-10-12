"""Owned PostgreSQL: MvpReadiness attests exactly the reviewed 0001-0024 profile (F24) and nothing else."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F24, MVP_ADDITIONS
from forge.mvp_readiness import MvpReadiness
from mvp_support import mvp_database


def readiness(db):
    return MvpReadiness(db.pool('forge_account_service'), db.pool('forge_runtime'), db.pool('forge_gateway_service'))


class PostgresMvpReadinessTests(unittest.TestCase):
    def test_the_complete_profile_is_attested_and_its_fingerprint_is_the_pinned_f24(self):
        with mvp_database() as db:
            with db.admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F24)
            self.assertIs(readiness(db).check(), True)

    def test_the_previous_profile_without_0024_is_refused(self):
        with mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:-1])) as db:
            with db.admin.cursor() as cursor:
                self.assertNotEqual(catalog_fingerprint(cursor), F24)
            self.assertIs(readiness(db).check(), False)

    def test_schema_drift_is_refused(self):
        with mvp_database() as db:
            self.assertIs(readiness(db).check(), True)
            db.admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
            self.assertIs(readiness(db).check(), False)

    def test_a_directory_authority_that_can_log_in_is_refused(self):
        with mvp_database() as db:
            self.assertIs(readiness(db).check(), True)
            db.admin.execute('ALTER ROLE forge_directory_authority LOGIN')
            self.assertIs(readiness(db).check(), False)


if __name__ == '__main__':
    unittest.main()
