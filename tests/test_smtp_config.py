"""FORGE_SMTP_* settings: presets, refusals and secret handling; no network, no server."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.mvp_local import ConfigError
from forge.smtp_delivery import SMTP_KEYS, SmtpSettings, load_smtp_settings

SECRET = 'relay-password-0123456789'


class Fixture:
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root/'password').write_text(SECRET + '\n', 'utf-8')
        (self.root/'ca.pem').write_text('-----BEGIN CERTIFICATE-----\n', 'utf-8')
        return self

    def __exit__(self, *exc):
        self.directory.cleanup()

    def env(self, **overrides):
        base = {'FORGE_SMTP_HOST': 'smtp.resend.com', 'FORGE_SMTP_FROM': 'Forge@Example.Test'}
        base.update(overrides)
        return {key: value for key, value in base.items() if value is not None}

    @property
    def password_file(self):
        return str(self.root/'password')


class SmtpConfigTests(unittest.TestCase):
    def failure(self, environ):
        with self.assertRaises(ConfigError) as caught:
            load_smtp_settings(environ)
        return str(caught.exception)

    def test_resend_implicit_tls_preset_is_valid(self):
        with Fixture() as fixture:
            settings = load_smtp_settings(fixture.env(
                FORGE_SMTP_PORT='465', FORGE_SMTP_SECURITY='tls', FORGE_SMTP_USER='resend',
                FORGE_SMTP_PASSWORD_FILE=fixture.password_file))
        self.assertEqual((settings.host, settings.port, settings.security, settings.user, settings.sender),
                         ('smtp.resend.com', 465, 'tls', 'resend', 'forge@example.test'))
        self.assertEqual(settings.password, SECRET)  # trailing newline of the secret file is not part of it

    def test_resend_starttls_preset_and_ses_use_the_submission_port_by_default(self):
        with Fixture() as fixture:
            resend = load_smtp_settings(fixture.env(FORGE_SMTP_USER='resend', FORGE_SMTP_PASSWORD_FILE=fixture.password_file))
            ses = load_smtp_settings(fixture.env(FORGE_SMTP_HOST='email-smtp.us-east-1.amazonaws.com', FORGE_SMTP_PORT='587',
                                                 FORGE_SMTP_USER='AKIAEXAMPLE', FORGE_SMTP_PASSWORD_FILE=fixture.password_file))
        self.assertEqual((resend.security, resend.port), ('starttls', 587))
        self.assertEqual((ses.security, ses.port, ses.host), ('starttls', 587, 'email-smtp.us-east-1.amazonaws.com'))

    def test_implicit_tls_defaults_to_465_and_cleartext_needs_an_explicit_port(self):
        self.assertEqual(load_smtp_settings(Fixture().env(FORGE_SMTP_SECURITY='tls')).port, 465)
        self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_SECURITY='none')), 'CONFIG_INVALID:FORGE_SMTP_PORT')
        mailpit = load_smtp_settings(Fixture().env(FORGE_SMTP_HOST='mailpit', FORGE_SMTP_SECURITY='none', FORGE_SMTP_PORT='1025'))
        self.assertEqual((mailpit.security, mailpit.port, mailpit.user, mailpit.password), ('none', 1025, None, None))

    def test_cleartext_with_credentials_is_refused(self):
        with Fixture() as fixture:
            with_password = fixture.env(FORGE_SMTP_SECURITY='none', FORGE_SMTP_PORT='1025', FORGE_SMTP_USER='u',
                                        FORGE_SMTP_PASSWORD_FILE=fixture.password_file)
            self.assertEqual(self.failure(with_password), 'CONFIG_INVALID:FORGE_SMTP_SECURITY')
            only_user = fixture.env(FORGE_SMTP_SECURITY='none', FORGE_SMTP_PORT='1025', FORGE_SMTP_USER='u')
            self.assertEqual(self.failure(only_user), 'CONFIG_INVALID:FORGE_SMTP_SECURITY')

    def test_unknown_security_mode_is_refused(self):
        for mode in ('ssl', 'STARTTLS', 'opportunistic', ''):
            with self.subTest(mode=mode):
                self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_SECURITY=mode)), 'CONFIG_INVALID:FORGE_SMTP_SECURITY')

    def test_bad_ports_are_refused(self):
        for port in ('0', '65536', '-1', 'abc', '587x', ' 587', ''):
            with self.subTest(port=port):
                self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_PORT=port)), 'CONFIG_INVALID:FORGE_SMTP_PORT')

    def test_missing_or_malformed_host_is_refused(self):
        self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_HOST=None)), 'CONFIG_INVALID:FORGE_SMTP_HOST')
        for host in ('', 'smtp resend.com', 'smtp.example.test/x', '-bad.example.test', 'a@b'):
            with self.subTest(host=host):
                self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_HOST=host)), 'CONFIG_INVALID:FORGE_SMTP_HOST')
        self.assertEqual(load_smtp_settings(Fixture().env(FORGE_SMTP_HOST='127.0.0.1')).host, '127.0.0.1')

    def test_missing_or_malformed_sender_is_refused(self):
        self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_FROM=None)), 'CONFIG_INVALID:FORGE_SMTP_FROM')
        for sender in ('not-an-email', 'a@localhost', 'forge@example.test\r\nBcc: x@example.test', '<forge@example.test>', ''):
            with self.subTest(sender=sender):
                self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_FROM=sender)), 'CONFIG_INVALID:FORGE_SMTP_FROM')

    def test_user_and_password_file_come_together(self):
        with Fixture() as fixture:
            self.assertEqual(self.failure(fixture.env(FORGE_SMTP_USER='resend')), 'CONFIG_INVALID:FORGE_SMTP_PASSWORD_FILE')
            self.assertEqual(self.failure(fixture.env(FORGE_SMTP_PASSWORD_FILE=fixture.password_file)), 'CONFIG_INVALID:FORGE_SMTP_USER')

    def test_the_password_file_must_be_an_absolute_readable_non_empty_file_and_is_never_echoed(self):
        with Fixture() as fixture:
            (fixture.root/'empty').write_text('\n', 'utf-8')
            for path in ('relative/password', str(fixture.root/'missing'), str(fixture.root/'empty'), str(fixture.root)):
                with self.subTest(path=path):
                    message = self.failure(fixture.env(FORGE_SMTP_USER='resend', FORGE_SMTP_PASSWORD_FILE=path))
                    self.assertEqual(message, 'CONFIG_INVALID:FORGE_SMTP_PASSWORD_FILE')
                    self.assertNotIn(path, message)

    def test_the_ca_file_must_be_an_existing_absolute_file(self):
        with Fixture() as fixture:
            self.assertEqual(load_smtp_settings(fixture.env(FORGE_SMTP_CA_FILE=str(fixture.root/'ca.pem'))).ca_file,
                             str(fixture.root/'ca.pem'))
            for path in ('ca.pem', str(fixture.root/'nope.pem'), str(fixture.root)):
                with self.subTest(path=path):
                    self.assertEqual(self.failure(fixture.env(FORGE_SMTP_CA_FILE=path)), 'CONFIG_INVALID:FORGE_SMTP_CA_FILE')

    def test_an_unknown_smtp_key_is_refused_and_unrelated_variables_are_ignored(self):
        self.assertEqual(self.failure(Fixture().env(FORGE_SMTP_TIMEOUT='5')), 'CONFIG_INVALID:unknown_key')
        settings = load_smtp_settings(Fixture().env(FORGE_PUBLIC_ORIGIN='https://forge.example.test', PATH='/bin'))
        self.assertEqual(settings.host, 'smtp.resend.com')
        self.assertEqual(sorted(SMTP_KEYS), ['FORGE_SMTP_CA_FILE', 'FORGE_SMTP_FROM', 'FORGE_SMTP_HOST',
                                              'FORGE_SMTP_PASSWORD_FILE', 'FORGE_SMTP_PORT', 'FORGE_SMTP_SECURITY',
                                              'FORGE_SMTP_USER'])

    def test_the_password_never_appears_in_repr_or_str(self):
        with Fixture() as fixture:
            settings = load_smtp_settings(fixture.env(FORGE_SMTP_USER='resend', FORGE_SMTP_PASSWORD_FILE=fixture.password_file))
        self.assertIsInstance(settings, SmtpSettings)
        self.assertNotIn(SECRET, repr(settings) + str(settings))


if __name__ == '__main__':
    unittest.main()
