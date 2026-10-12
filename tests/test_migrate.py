"""migrate: canonical order, record verification and CLI contract; no database (see test_postgres_migrate)."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.dev_accounts import MIGRATIONS
from forge.migrate import (BASE_COUNT, CANONICAL_ORDER, MigrationError, file_hashes, main, verify_records)
from forge.mvp_local import ROLES
from forge.mvp_profile import MVP_ADDITIONS, MVP_CHECKPOINTS
from test_prod_config import Fixture

ROOT = Path(__file__).resolve().parents[1]


class CanonicalOrderTests(unittest.TestCase):
    def test_order_is_the_reviewed_profile_and_every_file_exists(self):
        self.assertEqual(CANONICAL_ORDER, (*MIGRATIONS, *MVP_ADDITIONS))
        self.assertEqual(BASE_COUNT, len(MIGRATIONS))
        self.assertEqual(CANONICAL_ORDER[0], '0001_bootstrap.sql')
        self.assertEqual(len(set(CANONICAL_ORDER)), len(CANONICAL_ORDER))
        for name in CANONICAL_ORDER:
            self.assertTrue((ROOT/'migrations'/name).is_file(), name)

    def test_checkpoints_cover_every_state_after_the_base_and_are_distinct(self):
        # Crash recovery tells "applied" from "not applied" by fingerprint, so no two states may collide.
        self.assertEqual(len(MVP_CHECKPOINTS), len(CANONICAL_ORDER) - BASE_COUNT + 1)
        self.assertEqual(len(set(MVP_CHECKPOINTS)), len(MVP_CHECKPOINTS))

    def test_hashes_are_sha256_of_the_lf_normalized_bytes_and_a_missing_file_is_named(self):
        # A Windows checkout may hold CRLF; the recorded checksum must not depend on the checkout.
        expected = hashlib.sha256((ROOT/'migrations'/'0001_bootstrap.sql').read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        self.assertEqual(file_hashes(ROOT/'migrations', CANONICAL_ORDER[:2])['0001_bootstrap.sql'], expected)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/CANONICAL_ORDER[0]).write_bytes(b'SELECT 1;\r\n')
            (Path(directory)/CANONICAL_ORDER[1]).write_bytes(b'SELECT 1;\n')
            hashes = file_hashes(Path(directory), CANONICAL_ORDER[:2])
            self.assertEqual(hashes[CANONICAL_ORDER[0]], hashes[CANONICAL_ORDER[1]])
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(MigrationError) as caught:
            file_hashes(Path(directory), CANONICAL_ORDER[:1])
        self.assertEqual(caught.exception.code, 'MIGRATION_FILE_MISSING')
        self.assertEqual(caught.exception.migration, '0001_bootstrap.sql')


class VerifyRecordsTests(unittest.TestCase):
    ORDER = ('a.sql', 'b.sql', 'c.sql')
    HASHES = {'a.sql': 'h' * 64, 'b.sql': 'i' * 64, 'c.sql': 'j' * 64}

    def check(self, records):
        return verify_records(records, self.HASHES, self.ORDER)

    def test_a_prefix_of_the_order_with_matching_hashes_is_the_applied_count(self):
        self.assertEqual(self.check([]), 0)
        self.assertEqual(self.check([(1, 'a.sql', 'h' * 64)]), 1)
        self.assertEqual(self.check([(1, 'a.sql', 'h' * 64), (2, 'b.sql', 'i' * 64), (3, 'c.sql', 'j' * 64)]), 3)

    def test_an_edited_file_is_a_checksum_mismatch_naming_the_migration(self):
        with self.assertRaises(MigrationError) as caught:
            self.check([(1, 'a.sql', 'h' * 64), (2, 'b.sql', 'x' * 64)])
        self.assertEqual((caught.exception.code, caught.exception.migration), ('MIGRATION_CHECKSUM_MISMATCH', 'b.sql'))

    def test_unknown_gapped_or_reordered_records_are_refused(self):
        for records in ([(1, 'zzz.sql', 'h' * 64)], [(1, 'b.sql', 'i' * 64)], [(2, 'a.sql', 'h' * 64)],
                        [(1, 'a.sql', 'h' * 64), (3, 'c.sql', 'j' * 64)],
                        [(1, 'a.sql', 'h' * 64), (2, 'b.sql', 'i' * 64), (3, 'c.sql', 'j' * 64), (4, 'd.sql', 'k' * 64)]):
            with self.subTest(records=records), self.assertRaises(MigrationError) as caught:
                self.check(records)
            self.assertEqual(caught.exception.code, 'MIGRATION_ORDER_MISMATCH')


class Runner:
    """A fake for forge.migrate.migrate: records how the CLI called it."""
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def __call__(self, connection, directory, passwords, **kwargs):
        self.calls.append((connection, Path(directory), dict(passwords)))
        if self.error:
            raise self.error
        return self.result


class CliTests(unittest.TestCase):
    def run_cli(self, argv, env, runner, connections=None):
        connections = [] if connections is None else connections

        class Connection:
            def close(self):
                pass

        def connect(**kwargs):
            connections.append(kwargs)
            return Connection()
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(argv, environ=env, connect=connect, run=runner)
        return code, output.getvalue(), connections

    def environment(self, f, password='admin-secret'):
        (f.root/'admin.pw').write_text(password, 'utf-8')
        return {**f.env, 'FORGE_DB_ADMIN_PASSWORD_FILE': str(f.root/'admin.pw'), 'PGPASSWORD': 'ambient'}

    def test_success_prints_one_json_line_with_the_applied_names_and_exits_zero(self):
        with Fixture() as f:
            runner = Runner(['0001_bootstrap.sql'])
            code, text, connections = self.run_cli([], self.environment(f), runner)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text), {'status': 'ok', 'applied': ['0001_bootstrap.sql']})
            self.assertEqual(len(runner.calls), 1)
            _, directory, passwords = runner.calls[0]
            self.assertEqual((directory, passwords), (ROOT/'migrations', {role: 'password-for-%s' % role for role in ROLES}))
            self.assertEqual((connections[0]['user'], connections[0]['password'], connections[0]['host']),
                             ('postgres', 'admin-secret', 'postgres'))
            self.assertIs(connections[0]['autocommit'], True)
            self.assertNotIn('ambient', json.dumps(connections))

    def test_a_rerun_with_nothing_pending_is_still_success(self):
        with Fixture() as f:
            code, text, _ = self.run_cli([], self.environment(f), Runner([]))
            self.assertEqual((code, json.loads(text)), (0, {'status': 'ok', 'applied': []}))

    def test_a_migration_failure_is_a_finite_code_and_never_leaks_a_secret(self):
        with Fixture() as f:
            runner = Runner(error=MigrationError('MIGRATION_CHECKSUM_MISMATCH', migration='0010_model_catalog_snapshots.sql'))
            code, text, _ = self.run_cli([], self.environment(f), runner)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(text), {'status': 'failed', 'code': 'MIGRATION_CHECKSUM_MISMATCH',
                                                'migration': '0010_model_catalog_snapshots.sql'})
            for secret in ('admin-secret', 'password-for-'):
                self.assertNotIn(secret, text)

    def test_an_unexpected_error_is_a_generic_finite_code(self):
        with Fixture() as f:
            code, text, _ = self.run_cli([], self.environment(f), Runner(error=RuntimeError('boom admin-secret')))
            self.assertEqual((code, json.loads(text)), (1, {'status': 'failed', 'code': 'MIGRATE_UNAVAILABLE'}))

    def test_invalid_config_fails_before_any_connection(self):
        with Fixture() as f:
            env = self.environment(f)
            env['FORGE_PUBLIC_ORIGIN'] = 'http://leaky.example.test'
            runner = Runner([])
            code, text, connections = self.run_cli([], env, runner)
            self.assertEqual((code, json.loads(text)), (1, {'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_PUBLIC_ORIGIN'}))
            self.assertEqual((connections, runner.calls), ([], []))

    def test_the_admin_password_is_required_for_migrate(self):
        with Fixture() as f:
            code, text, connections = self.run_cli([], dict(f.env), Runner([]))
            self.assertEqual((code, json.loads(text)), (1, {'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_DB_ADMIN_PASSWORD'}))
            self.assertEqual(connections, [])

    def test_an_unreachable_database_is_a_finite_code(self):
        import psycopg
        with Fixture() as f:
            def refuse(**kwargs):
                raise psycopg.OperationalError('connection to server at "postgres" failed: password authentication failed')
            output = io.StringIO()
            with redirect_stdout(output):
                code = main([], environ=self.environment(f), connect=refuse, run=Runner([]))
            self.assertEqual((code, json.loads(output.getvalue())), (1, {'status': 'failed', 'code': 'DB_UNAVAILABLE'}))

    def test_usage_errors_exit_two(self):
        with Fixture() as f:
            code, text, _ = self.run_cli(['--bogus'], self.environment(f), Runner([]))
            self.assertEqual((code, json.loads(text)), (2, {'status': 'failed', 'code': 'INVALID_ARGUMENTS'}))


if __name__ == '__main__':
    unittest.main()
