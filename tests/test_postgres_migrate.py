"""Owned PostgreSQL: the migration runner on fresh, rerun, tampered, adopted, unknown, crashed, concurrent and rotated databases."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
from threading import Barrier, Thread
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import psycopg
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.migrate import BASE_COUNT, CANONICAL_ORDER, MigrationError, migrate, run_migrations
from forge.mvp_local import ROLES
from forge.mvp_profile import MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.mvp_readiness import MvpReadiness
from forge.prod_config import DbConfig
from postgres_support import connect, settings
from psycopg_pool import ConnectionPool
from test_postgres_gateway_origin import migration_text, separate_database

DIRECTORY = ROOT/'migrations'
LATEST = MVP_CHECKPOINTS[-1]


@contextmanager
def fresh_database():
    try:
        with separate_database() as admin:
            yield admin
    finally:
        with connect() as cleanup:
            for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service',
                         'forge_platform_authority', 'forge_platform_service', 'forge_capability_authority', 'forge_capability_service', 'forge_broker_authority', 'forge_broker_service'):
                cleanup.execute('DROP ROLE IF EXISTS ' + role)


def passwords():
    return {role: secrets.token_urlsafe(24) for role in ROLES}


def records(admin):
    return admin.execute('SELECT version, name, sha256 FROM forge_ops.schema_migrations ORDER BY version').fetchall()


def fingerprint(admin):
    with admin.cursor() as cursor:
        return catalog_fingerprint(cursor)


def executed_script_count(admin):
    return admin.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge'").fetchone()[0]


class FreshAndRerunTests(unittest.TestCase):
    def test_a_fresh_database_gets_every_migration_recorded_and_attested(self):
        with fresh_database() as admin:
            secret = passwords()
            self.assertEqual(migrate(admin, DIRECTORY, secret), list(CANONICAL_ORDER))
            self.assertEqual([row[1] for row in records(admin)], list(CANONICAL_ORDER))
            self.assertEqual([row[0] for row in records(admin)], list(range(1, len(CANONICAL_ORDER) + 1)))
            self.assertEqual(fingerprint(admin), LATEST)
            self.assertTrue(all(len(row[2]) == 64 for row in records(admin)))

    def test_the_service_roles_serve_and_readiness_attests_the_latest_profile(self):
        with fresh_database() as admin:
            secret = passwords()
            migrate(admin, DIRECTORY, secret)
            pools = [ConnectionPool('', kwargs={**settings(), 'dbname': admin.info.dbname, 'user': role,
                                                'password': secret[role]}, min_size=1, max_size=2, open=False)
                     for role in ('forge_account_service', 'forge_runtime', 'forge_gateway_service')]
            try:
                for pool in pools:
                    pool.open(wait=True, timeout=5)
                self.assertIs(MvpReadiness(*pools).check(), True)
            finally:
                for pool in pools:
                    pool.close(timeout=5)

    def test_a_rerun_executes_nothing_and_changes_no_schema(self):
        with fresh_database() as admin:
            secret = passwords()
            migrate(admin, DIRECTORY, secret)
            before = (records(admin), fingerprint(admin), executed_script_count(admin))
            self.assertEqual(migrate(admin, DIRECTORY, secret), [])
            self.assertEqual((records(admin), fingerprint(admin), executed_script_count(admin)), before)

    def test_the_bookkeeping_lives_outside_the_fingerprinted_forge_schema(self):
        with fresh_database() as admin:
            migrate(admin, DIRECTORY, passwords())
            self.assertIsNone(admin.execute("SELECT to_regclass('forge.schema_migrations')").fetchone()[0])
            self.assertFalse(admin.execute("SELECT has_table_privilege('forge_runtime','forge_ops.schema_migrations','SELECT')").fetchone()[0])

    def test_run_migrations_opens_the_admin_connection_from_the_config(self):
        with fresh_database() as admin:
            base = settings()
            config = type('Config', (), {'roles': passwords(), 'db': DbConfig(
                base['host'], base['port'], admin.info.dbname, 'disable', 'postgres', base['password'])})()
            self.assertEqual(run_migrations(config, DIRECTORY), list(CANONICAL_ORDER))
            self.assertEqual(run_migrations(config, DIRECTORY), [])
            self.assertEqual(fingerprint(admin), LATEST)


class IntegrityTests(unittest.TestCase):
    def copy_migrations(self, directory):
        target = Path(directory)/'migrations'
        shutil.copytree(DIRECTORY, target)
        return target

    def test_an_edited_applied_migration_aborts_before_applying_anything(self):
        with fresh_database() as admin, tempfile.TemporaryDirectory() as workspace:
            copy = self.copy_migrations(workspace)
            partial = CANONICAL_ORDER[:BASE_COUNT + 2]
            migrate(admin, copy, {}, order=partial, checkpoints=MVP_CHECKPOINTS[:3])
            with open(copy/CANONICAL_ORDER[BASE_COUNT], 'a', encoding='utf-8') as edited:
                edited.write('\n-- tampered\n')
            before = (records(admin), fingerprint(admin))
            with self.assertRaises(MigrationError) as caught:
                migrate(admin, copy, {})
            self.assertEqual((caught.exception.code, caught.exception.migration),
                             ('MIGRATION_CHECKSUM_MISMATCH', CANONICAL_ORDER[BASE_COUNT]))
            self.assertEqual((records(admin), fingerprint(admin)), before)

    def test_drift_after_a_complete_run_is_a_fingerprint_mismatch_and_runs_nothing(self):
        with fresh_database() as admin:
            migrate(admin, DIRECTORY, passwords())
            admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
            before = records(admin)
            with self.assertRaises(MigrationError) as caught:
                migrate(admin, DIRECTORY, passwords())
            self.assertEqual(caught.exception.code, 'SCHEMA_FINGERPRINT_MISMATCH')
            self.assertEqual(records(admin), before)

    def test_a_failing_script_is_a_finite_code_naming_the_migration_and_records_nothing_for_it(self):
        with fresh_database() as admin, tempfile.TemporaryDirectory() as workspace:
            copy = Path(workspace)/'migrations'
            shutil.copytree(DIRECTORY, copy)
            (copy/CANONICAL_ORDER[1]).write_text('BEGIN; SELECT 1/0; COMMIT;\n', 'utf-8')
            with self.assertRaises(MigrationError) as caught:
                migrate(admin, copy, {})
            self.assertEqual((caught.exception.code, caught.exception.migration), ('MIGRATION_FAILED', CANONICAL_ORDER[1]))
            self.assertEqual([row[1] for row in records(admin)], [CANONICAL_ORDER[0]])


class AdoptionTests(unittest.TestCase):
    def apply_manually(self, admin, count):
        for name in CANONICAL_ORDER[:count]:
            admin.execute(migration_text(name))

    def test_a_database_at_a_known_checkpoint_is_adopted_without_running_any_script(self):
        with fresh_database() as admin:
            self.apply_manually(admin, len(CANONICAL_ORDER))
            self.assertEqual(migrate(admin, DIRECTORY, passwords()), [])
            self.assertEqual([row[1] for row in records(admin)], list(CANONICAL_ORDER))

    def test_a_partially_migrated_known_checkpoint_is_adopted_then_completed(self):
        with fresh_database() as admin:
            self.apply_manually(admin, BASE_COUNT + 3)
            self.assertEqual(migrate(admin, DIRECTORY, passwords()), list(CANONICAL_ORDER[BASE_COUNT + 3:]))
            self.assertEqual(fingerprint(admin), LATEST)
            self.assertEqual(len(records(admin)), len(CANONICAL_ORDER))

    def test_an_unknown_forge_schema_is_refused_and_nothing_changes(self):
        with fresh_database() as admin:
            admin.execute('CREATE SCHEMA forge')
            with self.assertRaises(MigrationError) as caught:
                migrate(admin, DIRECTORY, passwords())
            self.assertEqual(caught.exception.code, 'UNKNOWN_SCHEMA')
            self.assertIsNone(admin.execute("SELECT to_regnamespace('forge_ops')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='forge'").fetchone()[0], 0)


class CrashAndConcurrencyTests(unittest.TestCase):
    def test_a_migration_applied_but_unrecorded_is_recorded_without_running_again(self):
        with fresh_database() as admin:
            cut = BASE_COUNT + 2
            migrate(admin, DIRECTORY, {}, order=CANONICAL_ORDER[:cut], checkpoints=MVP_CHECKPOINTS[:3])
            admin.execute(migration_text(CANONICAL_ORDER[cut]))  # the crash: script committed, record row never written
            self.assertEqual(len(records(admin)), cut)
            applied = migrate(admin, DIRECTORY, passwords())
            self.assertEqual(applied, list(CANONICAL_ORDER[cut + 1:]))
            self.assertEqual([row[1] for row in records(admin)], list(CANONICAL_ORDER))
            self.assertEqual(fingerprint(admin), LATEST)

    def test_two_concurrent_runners_apply_once_and_the_second_is_a_no_op(self):
        with fresh_database() as admin:
            results, errors = [], []
            barrier = Barrier(2)
            secret = passwords()

            def runner():
                try:
                    with psycopg.connect(**{**settings(), 'dbname': admin.info.dbname}) as connection:
                        barrier.wait(timeout=10)
                        results.append(migrate(connection, DIRECTORY, secret))
                except Exception as error:  # surfaced by the assertion below
                    errors.append(error)
            threads = [Thread(target=runner) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(120)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(results, key=len), [[], list(CANONICAL_ORDER)])
            self.assertEqual(len(records(admin)), len(CANONICAL_ORDER))
            self.assertEqual(fingerprint(admin), LATEST)


class PasswordTests(unittest.TestCase):
    def login(self, admin, role, password):
        with psycopg.connect(**{**settings(), 'dbname': admin.info.dbname, 'user': role, 'password': password}) as connection:
            return connection.execute('SELECT current_user').fetchone()[0]

    def test_rotation_leaves_only_the_new_password_working(self):
        with fresh_database() as admin:
            first, second = passwords(), passwords()
            migrate(admin, DIRECTORY, first)
            self.assertEqual(self.login(admin, 'forge_runtime', first['forge_runtime']), 'forge_runtime')
            self.assertEqual(migrate(admin, DIRECTORY, second), [])
            self.assertEqual(self.login(admin, 'forge_runtime', second['forge_runtime']), 'forge_runtime')
            with self.assertRaises(psycopg.OperationalError):
                self.login(admin, 'forge_runtime', first['forge_runtime'])

    def test_only_a_scram_verifier_is_stored_never_the_plaintext(self):
        with fresh_database() as admin:
            secret = passwords()
            migrate(admin, DIRECTORY, secret)
            stored = admin.execute("SELECT rolpassword FROM pg_authid WHERE rolname='forge_runtime'").fetchone()[0]
            self.assertTrue(stored.startswith('SCRAM-SHA-256$'))
            self.assertNotIn(secret['forge_runtime'], stored)

    def test_a_password_for_a_role_that_does_not_exist_is_refused(self):
        with fresh_database() as admin:
            with self.assertRaises(MigrationError) as caught:
                migrate(admin, DIRECTORY, {'forge_branding_service': 'x' * 20}, order=CANONICAL_ORDER[:1], checkpoints=())
            self.assertEqual(caught.exception.code, 'MIGRATION_ROLE_MISSING')
            self.assertNotIn('xxxx', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
