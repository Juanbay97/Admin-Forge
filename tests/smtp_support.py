"""A real SMTP server for tests (aiosmtpd): STARTTLS, implicit TLS, AUTH, refusals, and a server that never answers.

Certificates are generated in memory by ``cryptography`` and written to a caller-owned directory; the client trusts
them only through ``FORGE_SMTP_CA_FILE``, exactly as a deployment with a private relay would.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import socket
import ssl
import threading

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

USER = 'relay-user'
PASSWORD = 'relay-password-0123456789'


def _name(common_name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def write_pki(directory, *, names=('localhost',), addresses=('127.0.0.1',)):
    """A private CA and a server certificate for ``names``/``addresses``; returns (ca, certificate, key) paths."""
    now = datetime.now(timezone.utc)
    ca_key, server_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca = (x509.CertificateBuilder().subject_name(_name('forge test ca')).issuer_name(_name('forge test ca'))
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(ca_key, hashes.SHA256()))
    alternatives = [x509.DNSName(name) for name in names] + [x509.IPAddress(ip_address(value)) for value in addresses]
    server = (x509.CertificateBuilder().subject_name(_name(names[0])).issuer_name(ca.subject)
              .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1))
              .add_extension(x509.SubjectAlternativeName(alternatives), critical=False)
              .sign(ca_key, hashes.SHA256()))
    root = Path(directory)
    paths = (root/'ca.pem', root/'server.pem', root/'server.key')
    paths[0].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(server.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    return tuple(str(path) for path in paths)


@dataclass
class Captured:
    mail_from: str
    recipients: list
    content: bytes
    encrypted: bool
    authenticated: bool
    login: str | None


@dataclass
class Capture:
    """aiosmtpd handler: records what arrives, refuses the configured recipients."""
    refuse: tuple = ()
    messages: list = field(default_factory=list)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address in self.refuse:
            return '550 5.1.1 no such mailbox'
        envelope.rcpt_tos.append(address)
        return '250 OK'

    async def handle_DATA(self, server, session, envelope):
        login = getattr(session, 'login_data', None)
        self.messages.append(Captured(envelope.mail_from, list(envelope.rcpt_tos), envelope.content,
                                      server.transport.get_extra_info('ssl_object') is not None, bool(session.authenticated),
                                      login.decode() if isinstance(login, bytes) else login))
        return '250 OK'


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class FakeSmtp:
    """``mode``: ``starttls`` (STARTTLS required, AUTH required), ``tls`` (implicit TLS, AUTH required),
    ``plain`` (no TLS, no AUTH), ``plain_auth`` (AUTH offered on a cleartext channel: a downgrade trap)."""

    def __init__(self, directory, mode='starttls', *, refuse=(), names=('localhost',)):
        self.mode, self.handler = mode, Capture(refuse=tuple(refuse))
        self.ca, certificate, key = write_pki(directory, names=names)
        self.port, self.auth_attempts = free_port(), []
        context = None
        if mode in ('starttls', 'tls'):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
        options = dict(hostname='127.0.0.1', port=self.port, timeout=5)
        if mode == 'starttls':
            options.update(tls_context=context, require_starttls=True, auth_required=True, authenticator=self._authenticate)
        elif mode == 'tls':
            # The channel is TLS from the first byte; aiosmtpd only counts STARTTLS as secure, so allow AUTH explicitly.
            options.update(ssl_context=context, auth_required=True, auth_require_tls=False, authenticator=self._authenticate)
        elif mode == 'plain_auth':
            options.update(auth_required=True, auth_require_tls=False, authenticator=self._authenticate)
        self.controller = Controller(self.handler, **options)

    def _authenticate(self, server, session, envelope, mechanism, data):
        self.auth_attempts.append(mechanism)
        ok = getattr(data, 'login', None) == USER.encode() and getattr(data, 'password', None) == PASSWORD.encode()
        return AuthResult(success=ok, handled=False, auth_data=USER.encode() if ok else None)

    @property
    def messages(self):
        return self.handler.messages

    def __enter__(self):
        self.controller.start()
        return self

    def __exit__(self, *exc):
        if self.controller._thread is not None:
            self.controller.stop()


class SilentServer:
    """Accepts TCP connections and never says a word: the SMTP greeting never arrives."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(5)
        self.port = self.listener.getsockname()[1]
        self._connections, self._stop = [], threading.Event()
        self._thread = threading.Thread(target=self._accept, daemon=True)

    def _accept(self):
        self.listener.settimeout(0.2)
        while not self._stop.is_set():
            try:
                self._connections.append(self.listener.accept()[0])
            except OSError:
                continue

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)
        for connection in self._connections:
            connection.close()
        self.listener.close()
