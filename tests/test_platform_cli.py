"""``python -m forge.platform bootstrap-owner``: arguments, environment, the private link file, delivery and finite output."""
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from uuid import UUID
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.invitation_delivery import DeliveryReceipt
from forge.platform_cli import BootstrapOutcome, build_delivery, issue_link, main, write_private_file

LINK = 'https://forge.example.test/reset-password#capability=' + 'A' * 43
ENV = {'FORGE_PUBLIC_ORIGIN': 'https://forge.example.test', 'FORGE_DB_HOST': 'postgres', 'FORGE_DB_NAME': 'forge',
       'FORGE_DB_SSLMODE': 'disable', 'FORGE_DB_ADMIN_PASSWORD': 'fixture-admin-password'}
ARGS = ['bootstrap-owner', '--email', 'Owner@Example.Test', '--name', 'Platform Owner']


def argparse_namespace(**values):
    import argparse
    return argparse.Namespace(**values)


class Recorder:
    """Stands in for the connection factory and the database work; nothing here touches a network."""
    def __init__(self, created=True, fail=None):
        self.created, self.fail, self.connected, self.requests = created, fail, [], []

    def connect(self, **settings):
        self.connected.append(settings)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, connection, **request):
        self.requests.append(request)
        if self.fail:
            raise self.fail
        if self.created:
            request['write_link'](LINK)
        return BootstrapOutcome(self.created, LINK if self.created else None)


class Mail:
    channel = 'local_test_mailbox'

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def deliver(self, message_id, recipient, name, link, *, purpose='invitation'):
        if self.fail:
            raise RuntimeError('relay down')
        self.sent.append((message_id, recipient, name, link, purpose))
        return DeliveryReceipt(self.channel, 'ref')


class CliTests(unittest.TestCase):
    def run_cli(self, arguments, *, environ=ENV, recorder=None, mail=None):
        recorder = recorder or Recorder()
        out = io.StringIO()
        code = main(arguments, environ=dict(environ), out=out, connect=recorder.connect, bootstrap_fn=recorder.run,
                    delivery_factory=(lambda arguments, environ: mail))
        return code, [json.loads(line) for line in out.getvalue().splitlines()], recorder

    def link_file(self, directory):
        return str(Path(directory)/'owner-link.txt')

    def test_a_created_owner_writes_the_private_link_file_and_prints_no_secret_or_address(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.link_file(directory)
            code, documents, recorder = self.run_cli([*ARGS, '--link-file', path])
            self.assertEqual(code, 0)
            self.assertEqual(documents, [{'status': 'created', 'link_file': path, 'delivery': None}])
            self.assertEqual(Path(path).read_text('utf-8'), LINK + '\n')
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            printed = json.dumps(documents)
            for secret in (LINK, 'A' * 43, 'owner@example.test', 'Owner@Example.Test', 'fixture-admin-password'):
                self.assertNotIn(secret, printed)
            (request,) = recorder.requests
            self.assertEqual((request['email'], request['name'], request['origin'], request['ttl_seconds']),
                             ('owner@example.test', 'Platform Owner', 'https://forge.example.test', 86400))

    def test_the_admin_connection_comes_from_the_environment_with_every_parameter_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, recorder = self.run_cli([*ARGS, '--link-file', self.link_file(directory)])
            (settings,) = recorder.connected
            self.assertEqual((settings['host'], settings['port'], settings['dbname'], settings['user'], settings['sslmode'],
                              settings['autocommit']), ('postgres', 5432, 'forge', 'postgres', 'disable', True))
            self.assertEqual(settings['password'], 'fixture-admin-password')

    def test_a_rerun_is_a_no_op_that_touches_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.link_file(directory)
            code, documents, _ = self.run_cli([*ARGS, '--link-file', path], recorder=Recorder(created=False))
            self.assertEqual((code, documents), (0, [{'status': 'exists'}]))
            self.assertFalse(Path(path).exists())

    def test_an_existing_link_file_is_never_overwritten_and_fails_with_one_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.link_file(directory)
            Path(path).write_text('earlier secret\n', 'utf-8')
            code, documents, _ = self.run_cli([*ARGS, '--link-file', path])
            self.assertEqual((code, documents), (1, [{'status': 'failed', 'code': 'LINK_FILE_EXISTS'}]))
            self.assertEqual(Path(path).read_text('utf-8'), 'earlier secret\n')

    def test_the_link_file_helper_refuses_to_overwrite_and_creates_a_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'x.txt'
            write_private_file(path, 'first\n')
            with self.assertRaises(FileExistsError):
                write_private_file(path, 'second\n')
            self.assertEqual(path.read_text('utf-8'), 'first\n')

    def test_delivery_is_reported_and_carries_the_reset_purpose_to_the_owner_address_only(self):
        with tempfile.TemporaryDirectory() as directory:
            mail = Mail()
            code, documents, _ = self.run_cli([*ARGS, '--link-file', self.link_file(directory)], mail=mail)
            self.assertEqual((code, documents[0]['delivery']), (0, 'delivered'))
            ((message, recipient, name, link, purpose),) = mail.sent
            self.assertEqual((type(message), recipient, name, link, purpose),
                             (UUID, 'owner@example.test', 'Platform Owner', LINK, 'password_reset'))
            self.assertNotIn(LINK, json.dumps(documents))

    def test_a_failed_delivery_is_a_finite_state_and_the_link_file_still_holds_the_link(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.link_file(directory)
            code, documents, _ = self.run_cli([*ARGS, '--link-file', path], mail=Mail(fail=True))
            self.assertEqual((code, documents), (0, [{'status': 'created', 'link_file': path, 'delivery': 'failed'}]))
            self.assertEqual(Path(path).read_text('utf-8'), LINK + '\n')

    def test_invalid_arguments_and_configuration_are_finite_codes_before_any_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.link_file(directory)
            cases = [([], 2, 'INVALID_ARGUMENTS'), (['bootstrap-owner'], 2, 'INVALID_ARGUMENTS'),
                     (['bootstrap-owner', '--email', 'a@b.test', '--name', 'N'], 2, 'INVALID_ARGUMENTS'),
                     (['delete-owner', '--link-file', path], 2, 'INVALID_ARGUMENTS'),
                     ([*ARGS, '--link-file', path, '--ttl-hours', '0'], 1, 'INVALID_ARGUMENTS'),
                     ([*ARGS, '--link-file', path, '--ttl-hours', '169'], 1, 'INVALID_ARGUMENTS'),
                     (['bootstrap-owner', '--email', 'not-an-email', '--name', 'N', '--link-file', path], 1, 'INVALID_OWNER'),
                     (['bootstrap-owner', '--email', 'a@b.test', '--name', 'x\ny', '--link-file', path], 1, 'INVALID_OWNER')]
            for arguments, status, expected in cases:
                with self.subTest(arguments=arguments):
                    code, documents, recorder = self.run_cli(arguments)
                    self.assertEqual((code, documents), (status, [{'status': 'failed', 'code': expected}]))
                    self.assertEqual(recorder.connected, [])
            code, documents, recorder = self.run_cli([*ARGS, '--link-file', path], environ={**ENV, 'FORGE_PUBLIC_ORIGIN': 'ftp://x'})
            self.assertEqual((code, documents, recorder.connected), (1, [{'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_PUBLIC_ORIGIN'}], []))
            code, documents, _ = self.run_cli([*ARGS, '--link-file', path], environ={**ENV, 'FORGE_DB_ADMIN_PASSWORD': ''})
            self.assertEqual((code, documents), (1, [{'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_DB_ADMIN_PASSWORD'}]))
            missing = {key: value for key, value in ENV.items() if key != 'FORGE_DB_ADMIN_PASSWORD'}
            code, documents, _ = self.run_cli([*ARGS, '--link-file', path], environ=missing)
            self.assertEqual((code, documents), (1, [{'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_DB_ADMIN_PASSWORD'}]))

    def test_libpq_environment_variables_are_refused_so_they_can_never_steer_the_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            code, documents, recorder = self.run_cli([*ARGS, '--link-file', self.link_file(directory)],
                                                     environ={**ENV, 'PGHOST': 'evil.example'})
            self.assertEqual((code, documents, recorder.connected),
                             (1, [{'status': 'failed', 'code': 'ISOLATED_CHILD_ENVIRONMENT_REQUIRED'}], []))

    def test_database_and_bootstrap_failures_are_finite_and_leak_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            for failure, expected in ((RuntimeError('password=hunter2 host=10.0.0.5'), 'BOOTSTRAP_FAILED'),
                                      (ValueError('secret'), 'BOOTSTRAP_FAILED')):
                path = self.link_file(directory) + expected + str(id(failure))
                code, documents, _ = self.run_cli([*ARGS, '--link-file', path], recorder=Recorder(fail=failure))
                self.assertEqual((code, documents), (1, [{'status': 'failed', 'code': expected}]))
                self.assertNotIn('hunter2', json.dumps(documents))

    def test_the_mailbox_option_writes_a_private_eml_with_the_link_and_smtp_builds_the_relay_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            mailbox = Path(directory)/'mail'
            mailbox.mkdir()
            adapter = build_delivery(argparse_namespace(mailbox_dir=str(mailbox), smtp=False), ENV)
            self.assertEqual(adapter.channel, 'local_test_mailbox')
            adapter.deliver(UUID(int=7), 'owner@example.test', 'Platform Owner', LINK, purpose='password_reset')
            (eml,) = mailbox.glob('*.eml')
            text = eml.read_text('utf-8')
            self.assertIn('Subject: Reset your Forge password', text)
            self.assertIn('To: owner@example.test', text)
            self.assertIn('capability=' + 'A' * 43, text.replace('=\n', '').replace('=3D', '='))
        smtp_env = {**ENV, 'FORGE_SMTP_HOST': 'smtp.example.test', 'FORGE_SMTP_FROM': 'forge@example.test'}
        relay = build_delivery(argparse_namespace(mailbox_dir=None, smtp=True), smtp_env)
        self.assertEqual((relay.channel, relay.settings.host, relay.settings.sender), ('smtp', 'smtp.example.test', 'forge@example.test'))
        self.assertIsNone(build_delivery(argparse_namespace(mailbox_dir=None, smtp=False), smtp_env))
        for bad in (argparse_namespace(mailbox_dir=str(Path(directory)/'missing'), smtp=False), argparse_namespace(mailbox_dir=None, smtp=True)):
            with self.subTest(bad=bad), self.assertRaises(Exception) as caught:
                build_delivery(bad, ENV)
            self.assertNotIn('missing', str(caught.exception))

    def test_the_set_password_link_keeps_the_capability_in_the_fragment_on_the_public_origin(self):
        capability = 'B' * 43
        link = issue_link('https://forge.example.test', capability)
        self.assertEqual(link, 'https://forge.example.test/reset-password#capability=' + capability)
        self.assertEqual(issue_link('http://127.0.0.1:3410', capability), 'http://127.0.0.1:3410/reset-password#capability=' + capability)
        for origin in ('http://forge.example.test', 'https://forge.example.test/path', 'ftp://x', ''):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                issue_link(origin, capability)


if __name__ == '__main__':
    unittest.main()
