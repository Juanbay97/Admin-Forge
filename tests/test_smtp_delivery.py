"""SmtpDelivery against a real SMTP server (aiosmtpd): transport security, content, and finite failures."""
from email import policy
from email.parser import BytesParser
import logging
import secrets
from pathlib import Path
import sys
import tempfile
import time
import unittest
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from smtp_support import FakeSmtp, PASSWORD, SilentServer, USER
from forge.invitation_delivery import DeliveryReceipt, LocalTestMailbox, build_message, onboarding_link
from forge.smtp_delivery import SmtpDelivery, SmtpDeliveryError, SmtpSettings

LINK = onboarding_link('https://forge.example.test', uuid4(), secrets.token_urlsafe(32))
RECIPIENT = 'new.hire@example.test'


def settings_for(server, **overrides):
    values = dict(host='localhost', port=server.port, security='starttls', user=USER, password=PASSWORD,
                  sender='forge@example.test', ca_file=server.ca)
    values.update(overrides)
    return SmtpSettings(**values)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def server(self, mode='starttls', **options):
        server = FakeSmtp(self.directory.name, mode, **options)
        server.__enter__()
        self.addCleanup(server.__exit__)
        return server

    def deliver(self, delivery, **overrides):
        values = dict(message_id=uuid4(), recipient=RECIPIENT, name='New Hire', link=LINK)
        values.update(overrides)
        return delivery.deliver(values.pop('message_id'), values.pop('recipient'), values.pop('name'), values.pop('link'), **values)


class DeliveryTransports(Fixture):
    def test_starttls_with_auth_delivers_one_encrypted_authenticated_message(self):
        server = self.server('starttls')
        receipt = self.deliver(SmtpDelivery(settings_for(server), timeout=5))
        self.assertEqual(len(server.messages), 1)
        captured = server.messages[0]
        self.assertTrue(captured.encrypted)
        self.assertTrue(captured.authenticated)
        self.assertEqual((captured.mail_from, captured.recipients), ('forge@example.test', [RECIPIENT]))
        self.assertIsInstance(receipt, DeliveryReceipt)
        self.assertEqual(receipt.channel, 'smtp')

    def test_implicit_tls_delivers_one_encrypted_authenticated_message(self):
        server = self.server('tls')
        self.deliver(SmtpDelivery(settings_for(server, security='tls'), timeout=5))
        self.assertEqual([(m.encrypted, m.authenticated) for m in server.messages], [(True, True)])

    def test_a_cleartext_relay_without_credentials_delivers_in_none_mode(self):
        server = self.server('plain')
        self.deliver(SmtpDelivery(settings_for(server, host='127.0.0.1', security='none', user=None, password=None), timeout=5))
        self.assertEqual([(m.encrypted, m.authenticated) for m in server.messages], [(False, False)])

    def test_a_relay_that_requires_authentication_refuses_a_client_without_credentials(self):
        server = self.server('starttls')
        with self.assertRaises(SmtpDeliveryError) as caught:
            self.deliver(SmtpDelivery(settings_for(server, user=None, password=None), timeout=5))
        self.assertEqual(str(caught.exception), 'SMTP_AUTH')
        self.assertEqual(server.messages, [])


class DeliveryContent(Fixture):
    def parsed(self, server):
        return BytesParser(policy=policy.default).parsebytes(server.messages[0].content)

    def test_the_message_has_only_the_name_and_the_link_and_the_configured_sender(self):
        server = self.server('starttls')
        identifier = uuid4()
        self.deliver(SmtpDelivery(settings_for(server), timeout=5), message_id=identifier, name='Ana <b>& Co')
        message = self.parsed(server)
        self.assertEqual(str(message['From']), 'forge@example.test')
        self.assertEqual(str(message['To']), RECIPIENT)
        self.assertEqual(str(message['Message-ID']), '<%s@example.test>' % identifier)
        text = message.get_body(preferencelist=('plain',)).get_content()
        html = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn(LINK, text)
        self.assertIn('Hello Ana <b>& Co', text)
        self.assertIn('Ana &lt;b&gt;&amp; Co', html)
        self.assertNotIn('<b>', html)
        for part in (text, html, server.messages[0].content.decode('utf-8')):
            self.assertNotIn(PASSWORD, part)

    def test_a_password_reset_message_differs_only_by_subject_and_wording(self):
        server = self.server('starttls')
        link = 'https://forge.example.test/reset-password#capability=' + secrets.token_urlsafe(32)
        self.deliver(SmtpDelivery(settings_for(server), timeout=5), link=link, purpose='password_reset')
        message = self.parsed(server)
        self.assertEqual(str(message['Subject']), 'Reset your Forge password')
        self.assertIn(link, message.get_body(preferencelist=('plain',)).get_content())

    def test_header_injection_in_the_name_or_recipient_is_rejected_before_any_connection(self):
        server = self.server('starttls')
        delivery = SmtpDelivery(settings_for(server), timeout=5)
        for overrides in ({'name': 'Eve\r\nBcc: spy@example.test'}, {'recipient': 'a@example.test\r\nBcc: spy@example.test'},
                          {'name': 'Eve\nSubject: pwned'}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.deliver(delivery, **overrides)
        self.assertEqual((server.messages, server.auth_attempts), ([], []))

    def test_it_builds_exactly_what_the_local_mailbox_writes(self):
        identifier = uuid4()
        with tempfile.TemporaryDirectory() as owned:
            LocalTestMailbox(Path(owned), sender='forge@example.test').deliver(identifier, RECIPIENT, 'New Hire', LINK)
            written = BytesParser(policy=policy.default).parsebytes((Path(owned)/('%s.eml' % identifier)).read_bytes())
        built = build_message('forge@example.test', RECIPIENT, 'New Hire', LINK, 'invitation', identifier)
        for header in ('From', 'To', 'Subject', 'Message-ID'):
            self.assertEqual(str(built[header]), str(written[header]), header)
        for kind in ('plain', 'html'):
            self.assertEqual(built.get_body(preferencelist=(kind,)).get_content().replace('\r\n', '\n'),
                             written.get_body(preferencelist=(kind,)).get_content().replace('\r\n', '\n'))


class DeliveryFailures(Fixture):
    def failure(self, delivery, **overrides):
        with self.assertRaises(SmtpDeliveryError) as caught:
            self.deliver(delivery, **overrides)
        return caught.exception

    def test_a_relay_without_starttls_is_never_sent_anything_or_credentials(self):
        server = self.server('plain_auth')
        error = self.failure(SmtpDelivery(settings_for(server, host='127.0.0.1'), timeout=5))
        self.assertEqual(str(error), 'SMTP_STARTTLS_REQUIRED')
        self.assertEqual((server.messages, server.auth_attempts), ([], []))  # no AUTH, so the password never left

    def test_bad_credentials_store_nothing(self):
        server = self.server('starttls')
        error = self.failure(SmtpDelivery(settings_for(server, password='not-the-password-at-all'), timeout=5))
        self.assertEqual(str(error), 'SMTP_AUTH')
        self.assertEqual(server.messages, [])

    def test_a_refused_recipient_fails_without_delivering(self):
        server = self.server('starttls', refuse=[RECIPIENT])
        error = self.failure(SmtpDelivery(settings_for(server), timeout=5))
        self.assertEqual(str(error), 'SMTP_RECIPIENT')
        self.assertEqual(server.messages, [])

    def test_an_untrusted_certificate_is_refused_before_authentication(self):
        server = self.server('starttls')
        error = self.failure(SmtpDelivery(settings_for(server, ca_file=None), timeout=5))
        self.assertEqual(str(error), 'SMTP_TLS')
        self.assertEqual(server.auth_attempts, [])

    def test_a_certificate_for_another_name_is_refused(self):
        server = self.server('starttls', names=('other.example.test',), )
        error = self.failure(SmtpDelivery(settings_for(server, host='localhost'), timeout=5))
        self.assertEqual(str(error), 'SMTP_TLS')
        self.assertEqual((server.messages, server.auth_attempts), ([], []))

    def test_implicit_tls_against_a_cleartext_port_fails_as_tls(self):
        server = self.server('plain')
        self.assertEqual(str(self.failure(SmtpDelivery(settings_for(server, security='tls', host='127.0.0.1'), timeout=5))),
                         'SMTP_TLS')

    def test_a_stalled_server_aborts_within_the_timeout(self):
        with SilentServer() as silent:
            delivery = SmtpDelivery(SmtpSettings(host='127.0.0.1', port=silent.port, security='starttls', user=None, password=None,
                                                 sender='forge@example.test', ca_file=None), timeout=0.5)
            started = time.monotonic()
            error = self.failure(delivery)
            elapsed = time.monotonic() - started
        self.assertEqual(str(error), 'SMTP_TIMEOUT')
        self.assertLess(elapsed, 3)

    def test_the_default_timeout_is_ten_seconds(self):
        server = self.server('starttls')
        self.assertEqual(SmtpDelivery(settings_for(server)).timeout, 10)

    def test_a_closed_port_is_a_connect_failure(self):
        server = self.server('starttls')
        port = server.port
        server.__exit__()
        # Windows retries a refused connection for ~2 s, so the timeout must outlast that to see the refusal.
        self.assertEqual(str(self.failure(SmtpDelivery(settings_for(server, port=port), timeout=6))), 'SMTP_CONNECT')

    def test_no_failure_exposes_the_password_the_recipient_the_link_or_the_host(self):
        server = self.server('starttls', refuse=[RECIPIENT])
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger().addHandler(handler)
        previous = logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        self.addCleanup(logging.getLogger().setLevel, previous)
        failures = [
            self.failure(SmtpDelivery(settings_for(server), timeout=5)),                       # refused recipient
            self.failure(SmtpDelivery(settings_for(server, password='wrong-password-value'), timeout=5)),  # bad auth
            self.failure(SmtpDelivery(settings_for(server, ca_file=None), timeout=5)),         # untrusted certificate
        ]
        for error in failures:
            rendered = '%s %r %s' % (error, error, ''.join(map(str, error.args)))
            for secret in (PASSWORD, 'wrong-password-value', RECIPIENT, LINK, 'localhost', USER):
                self.assertNotIn(secret, rendered)
            self.assertIsNone(error.__cause__)
        # The in-process fake server logs its own side (logger "mail.*"); only the client's logging is under test.
        logged = ' '.join(record.getMessage() for record in records if not record.name.startswith('mail.'))
        for secret in (PASSWORD, 'wrong-password-value', RECIPIENT, LINK):
            self.assertNotIn(secret, logged)
        self.assertEqual([r.name for r in records if not r.name.startswith(('mail.', 'asyncio'))], [])  # the adapter logs nothing


class CoordinatorIntegration(Fixture):
    """The existing DeliveryCoordinator turns an adapter failure into FAILED, without a diagnostic."""

    class Store:
        def __init__(self, payload):
            self.payload, self.outcome = payload, None

        def claim(self, message, lease):
            return self.payload

        def finish(self, message, lease, delivered):
            self.outcome = delivered
            return True

    def run_dispatch(self, delivery):
        from cryptography.fernet import Fernet
        from forge.invitation_delivery import DeliveryCoordinator, DeliveryState
        key = Fernet.generate_key()
        origin = 'https://forge.example.test'
        coordinator = DeliveryCoordinator(None, delivery, origin=origin, encryption_key=key)
        payload = coordinator._payload('invitation', RECIPIENT, 'New Hire', onboarding_link(origin, uuid4(), secrets.token_urlsafe(32)))
        coordinator.store = self.Store(payload)
        return coordinator.dispatch(uuid4()), coordinator.store, DeliveryState

    def test_a_working_relay_is_delivered_and_a_downgrade_is_failed(self):
        good = self.server('starttls')
        state, store, states = self.run_dispatch(SmtpDelivery(settings_for(good), timeout=5))
        self.assertEqual((state, store.outcome, len(good.messages)), (states.DELIVERED, True, 1))
        bad = self.server('plain_auth')
        state, store, states = self.run_dispatch(SmtpDelivery(settings_for(bad, host='127.0.0.1'), timeout=5))
        self.assertEqual((state, store.outcome, bad.messages), (states.FAILED, False, []))


if __name__ == '__main__':
    unittest.main()
