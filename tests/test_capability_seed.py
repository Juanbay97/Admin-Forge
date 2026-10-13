"""The capability seed: the OpenYak inventory as compact JSONL, its defaults and the sync CLI's argument handling (no database)."""
import io
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_seed import SEED_PATH, SyncResult, load_seed, main
from forge.capability_service import entry_document

EXEC = {'tool:code_execute': 3, 'tool:bash': 4, 'tool:powershell': 4}
OFF_TOOLS = {'tool:browser', 'tool:computer', 'tool:channels', 'tool:remote_access', 'tool:automation'}


class SeedFileTests(unittest.TestCase):
    def setUp(self):
        self.entries = load_seed()
        self.by_kind = {}
        for entry in self.entries:
            self.by_kind.setdefault(entry['id'].split(':')[0], []).append(entry)

    def test_ids_are_unique_sorted_and_the_counts_cover_the_openyak_inventory(self):
        ids = [entry['id'] for entry in self.entries]
        self.assertEqual((len(ids), ids == sorted(ids), len(set(ids))), (len(ids), True, len(ids)))
        self.assertEqual((len(self.by_kind['skill']), len(self.by_kind['connector']), len(self.by_kind['plugin'])), (25, 46, 15))
        self.assertGreaterEqual(len(self.by_kind['tool']), 22)
        self.assertNotIn('app', self.by_kind, 'the platform adds apps through the catalog API, never the seed')

    def test_every_entry_passes_the_same_validation_the_catalog_api_applies(self):
        for entry in self.entries:
            document = {key: value for key, value in entry.items() if key != 'id'}
            with self.subTest(entry=entry['id']):
                self.assertEqual(entry_document(entry['id'], document)['version'], '1.0.0')

    def test_defaults_follow_the_binding_rules(self):
        for entry in self.by_kind['skill'] + self.by_kind['connector']:
            self.assertEqual((entry['is_base'], entry['default_state']), (True, 'on'), entry['id'])
        for entry in self.by_kind['plugin']:
            self.assertEqual((entry['is_base'], entry['default_state']), (False, 'off'), entry['id'])
        tools = {entry['id']: entry for entry in self.by_kind['tool']}
        for identifier, level in EXEC.items():
            self.assertEqual((tools[identifier]['default_state'], tools[identifier]['min_sandbox_level'], tools[identifier]['risk']), ('on', level, 'high'))
        for identifier in OFF_TOOLS:
            self.assertEqual(tools[identifier]['default_state'], 'off', identifier)
        self.assertFalse([name for name, entry in tools.items() if entry['min_sandbox_level'] and name not in EXEC])

    def test_connectors_carry_what_the_broker_needs_and_stdio_ones_stay_on_the_client(self):
        for entry in self.by_kind['connector']:
            attributes = entry['attributes']
            if attributes['transport'] == 'stdio':
                self.assertEqual((entry['credential_locus'], attributes['auth']), ('client', 'none'), entry['id'])
            else:
                self.assertEqual((entry['credential_locus'], attributes['transport'], attributes['auth']), ('server', 'mcp_http', 'oauth'), entry['id'])
                self.assertTrue(attributes['mcp_url'].startswith('https://'), entry['id'])
                self.assertIn(attributes['mcp_url'].split('/')[2], attributes['egress_hosts'])
        self.assertEqual(sum(1 for entry in self.by_kind['connector'] if entry['credential_locus'] == 'client'), 3)

    def test_a_malformed_seed_is_refused_whole(self):
        bad = Path(__file__).with_name('_bad_seed.jsonl')
        for text in ('not json\n', '{"id":"skill:x"}\n', json.dumps({**self.entries[0], 'extra': 1}) + '\n', json.dumps(self.entries[0]) + '\n' + json.dumps(self.entries[0]) + '\n'):
            bad.write_text(text, 'utf-8')
            try:
                with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                    load_seed(bad)
            finally:
                bad.unlink()
        self.assertTrue(SEED_PATH.is_file())


class PackagingTests(unittest.TestCase):
    def test_the_seed_ships_inside_the_wheel(self):
        self.assertIn('"capability_seed.jsonl"', (ROOT/'pyproject.toml').read_text('utf-8'))


class CliTests(unittest.TestCase):
    def run_cli(self, argv, environ=None, connect=None):
        out = io.StringIO()
        code = main(argv, environ=environ if environ is not None else {}, out=out, connect=connect)
        return code, [json.loads(line) for line in out.getvalue().splitlines()]

    def test_bad_arguments_exit_2_and_a_missing_admin_password_exits_1_without_connecting(self):
        code, lines = self.run_cli(['frobnicate'])
        self.assertEqual((code, lines), (2, [{'status': 'failed', 'code': 'INVALID_ARGUMENTS'}]))
        code, lines = self.run_cli(['sync'], environ={'FORGE_DB_HOST': 'postgres', 'FORGE_DB_NAME': 'forge'}, connect=lambda **kwargs: self.fail('no connection'))
        self.assertEqual(code, 1)
        self.assertEqual(lines[0]['status'], 'failed')

    def test_sync_connects_once_with_the_administrator_settings_and_reports_the_counts(self):
        from unittest.mock import patch
        calls = []

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def connect(**keywords):
            calls.append(keywords)  # a duplicated keyword (admin_settings already sets autocommit) would raise right here
            return Connection()
        environ = {'FORGE_DB_HOST': 'postgres', 'FORGE_DB_NAME': 'forge', 'FORGE_DB_ADMIN_PASSWORD': 'admin-pass'}
        with patch('forge.capability_seed.sync', return_value=SyncResult(3, 0, 111)) as sync_mock:
            code, lines = self.run_cli(['sync', '--update'], environ=environ, connect=connect)
        self.assertEqual((code, lines), (0, [{'status': 'synced', 'created': 3, 'updated': 0, 'unchanged': 111}]))
        self.assertEqual((len(calls), calls[0]['host'], calls[0]['autocommit'], calls[0]['application_name']), (1, 'postgres', True, 'forge-capability-seed'))
        self.assertTrue(sync_mock.call_args.kwargs['update'])

    def test_libpq_environment_variables_are_refused(self):
        code, lines = self.run_cli(['sync'], environ={'PGHOST': 'elsewhere'})
        self.assertEqual((code, lines[0]['code']), (1, 'ISOLATED_CHILD_ENVIRONMENT_REQUIRED'))


if __name__ == '__main__':
    unittest.main()
