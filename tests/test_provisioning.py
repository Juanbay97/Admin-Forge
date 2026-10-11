"""Trusted provisioning CLI contracts that need no database: validation, secrets handling, redaction."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import MagicMock
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.accounts import password_bytes
from forge.provisioning import (NewAccount, OrganizationSpec, Provisioned, SEED, main, new_password,
                                write_credentials)

BASE = dict(slug='org-a', display_name='Organization A', department='Operations',
            admin_email='Admin@Example.com', admin_name='Ada Admin')


def provisioned(password='P' * 30, key=None):
    return Provisioned(uuid4(), uuid4(), 'org-a', (NewAccount('admin@example.com', 'Ada', 'organization_admin', password),), key)


class SpecTests(unittest.TestCase):
    def test_valid_spec_canonicalizes_the_admin_email(self):
        spec = OrganizationSpec(**BASE)
        self.assertEqual((spec.slug, spec.admin_email, spec.member_email), ('org-a', 'admin@example.com', None))
        with_member = OrganizationSpec(**BASE, member_email='M@Example.com', member_name='Mia')
        self.assertEqual((with_member.member_email, with_member.member_name), ('m@example.com', 'Mia'))

    def test_invalid_values_are_refused(self):
        bad = ({'slug': 'Org A'}, {'slug': ''}, {'slug': '-a'}, {'slug': 'a' * 64}, {'display_name': ' '},
               {'department': ''}, {'admin_email': 'not-an-email'}, {'admin_name': 'x' * 121},
               {'member_email': 'm@example.com'}, {'member_name': 'Mia'},
               {'member_email': 'bad', 'member_name': 'Mia'}, {'member_email': 'ADMIN@example.com', 'member_name': 'Mia'})
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                OrganizationSpec(**{**BASE, **change})

    def test_the_seed_defines_two_organizations_with_distinct_everything(self):
        self.assertEqual(len(SEED), 2)
        for field in ('slug', 'display_name', 'admin_email', 'member_email'):
            self.assertEqual(len({getattr(spec, field) for spec in SEED}), 2, field)
        self.assertTrue(all(spec.issue_gateway_key and spec.member_email for spec in SEED))


class SecretTests(unittest.TestCase):
    def test_generated_passwords_satisfy_the_policy_and_never_repeat(self):
        values = {new_password() for _ in range(20)}
        self.assertEqual(len(values), 20)
        for value in values:
            self.assertEqual(password_bytes(value), value.encode())

    def test_secrets_do_not_appear_in_reprs(self):
        result = provisioned(password='SECRET-PASSWORD-VALUE', key='SECRET-KEY-VALUE')
        self.assertNotIn('SECRET', repr(result) + repr(result.accounts[0]) + str(result))

    def test_credentials_file_is_created_exclusively_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'credentials.json'
            write_credentials(path, (provisioned('A' * 30, 'key-1'),))
            document = json.loads(path.read_text('utf-8'))
            self.assertEqual(document['organizations'][0]['accounts'][0]['password'], 'A' * 30)
            self.assertEqual(document['organizations'][0]['gateway_key'], 'key-1')
            with self.assertRaises(FileExistsError):
                write_credentials(path, (provisioned('B' * 30),))
            self.assertEqual(json.loads(path.read_text('utf-8')), document)


class CliTests(unittest.TestCase):
    def operator(self, directory, **change):
        path = Path(directory)/('operator-' + '-'.join(sorted(change)) + '.json')
        values = dict(host='127.0.0.1', port=5432, dbname='forge', user='postgres', password='OPERATOR-DB-PASSWORD')
        values.update(change)
        path.write_text(json.dumps(values), 'utf-8')
        return str(path)

    def run_cli(self, argv, **kwargs):
        out = StringIO()
        code = main(argv, out=out, environ=kwargs.pop('environ', {}), **kwargs)
        return code, out.getvalue()

    def org_args(self, directory, **change):
        return ['--operator-file', self.operator(directory, **change), '--credentials-file', str(Path(directory)/'c.json'),
                'org', '--slug', 'org-a', '--name', 'Organization A', '--department', 'Operations',
                '--admin-email', 'admin@example.com', '--admin-name', 'Ada']

    def test_success_prints_ids_but_never_a_password_key_or_operator_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def fake_provision(connection, specs, deliver, **kwargs):
                result = provisioned('NEW-ADMIN-PASSWORD-123', 'NEW-GATEWAY-KEY')
                deliver((result,))
                calls.append(specs)
                return (result,)
            connect = MagicMock()
            code, text = self.run_cli(self.org_args(directory), connect=connect, provision_fn=fake_provision)
            self.assertEqual(code, 0)
            report = json.loads(text)
            self.assertEqual(report['status'], 'provisioned')
            self.assertEqual([(o['slug'], o['created']) for o in report['organizations']], [('org-a', True)])
            for secret in ('NEW-ADMIN-PASSWORD-123', 'NEW-GATEWAY-KEY', 'OPERATOR-DB-PASSWORD'):
                self.assertNotIn(secret, text)
            self.assertIn('NEW-ADMIN-PASSWORD-123', (Path(directory)/'c.json').read_text('utf-8'))
            self.assertEqual(calls[0][0].slug, 'org-a')
            self.assertEqual(connect.call_args.kwargs['host'], '127.0.0.1')

    def test_a_rerun_reports_existing_and_writes_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            code, text = self.run_cli(self.org_args(directory), connect=MagicMock(),
                                      provision_fn=lambda connection, specs, deliver, **kw: ())
            self.assertEqual(code, 0)
            self.assertEqual([(o['slug'], o['created']) for o in json.loads(text)['organizations']], [('org-a', False)])
            self.assertFalse((Path(directory)/'c.json').exists())

    def test_invalid_operator_files_and_arguments_fail_closed_without_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            connect = MagicMock()
            bad_email = self.org_args(directory)
            bad_email[bad_email.index('--admin-email') + 1] = 'bad'
            base = self.org_args(directory)[:4]
            cases = {'OPERATOR_FILE_INVALID': [self.org_args(directory, host='10.0.0.5'),
                                               self.org_args(directory, port='5432'),
                                               self.org_args(directory, extra='x')],
                     'INVALID_ARGUMENTS': [['org'], [], base + ['seed', '--bogus']],
                     'INVALID_ORGANIZATION': [bad_email]}
            for code, variants in cases.items():
                for argv in variants:
                    with self.subTest(code=code, argv=argv[-2:]):
                        status, text = self.run_cli(argv, connect=connect)
                        self.assertEqual((status, json.loads(text)), (1, {'status': 'failed', 'code': code}))
            self.assertEqual(connect.call_count, 0)
            self.assertNotIn('OPERATOR-DB-PASSWORD', text)

    def test_ambient_libpq_environment_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            connect = MagicMock()
            status, text = self.run_cli(self.org_args(directory), connect=connect, environ={'PGHOST': 'elsewhere'})
            self.assertEqual((status, json.loads(text)['code']), (1, 'ISOLATED_CHILD_ENVIRONMENT_REQUIRED'))
            self.assertEqual(connect.call_count, 0)

    def test_database_errors_are_reported_as_a_finite_code_without_their_text(self):
        with tempfile.TemporaryDirectory() as directory:
            def boom(*args, **kwargs):
                raise RuntimeError('password authentication failed for OPERATOR-DB-PASSWORD')
            status, text = self.run_cli(self.org_args(directory), connect=boom)
            self.assertEqual((status, json.loads(text)), (1, {'status': 'failed', 'code': 'PROVISIONING_FAILED'}))
            self.assertNotIn('OPERATOR-DB-PASSWORD', text)


if __name__ == '__main__':
    unittest.main()
