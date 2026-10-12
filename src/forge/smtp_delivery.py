"""Generic SMTP delivery of invitation and password-reset links (Resend, Amazon SES, any standards-compliant relay).

``SmtpSettings`` come from ``FORGE_SMTP_*`` variables and a ``*_FILE`` password secret, like every other production
setting: any problem is a finite non-secret ``CONFIG_INVALID:<KEY>`` and no value is ever echoed. ``SmtpDelivery`` is a
``MessageDelivery`` adapter on the standard-library ``smtplib``:

* ``starttls`` (default): the connection is upgraded BEFORE any credential is sent, and a relay that does not offer
  STARTTLS is refused, so a downgrade can never expose the password; ``tls``: implicit TLS; ``none``: cleartext,
  only without credentials (a local catch-all such as Mailpit).
* Certificates and host names are always verified (optionally against ``FORGE_SMTP_CA_FILE`` for a private relay).
* Every failure is an ``SmtpDeliveryError`` carrying one finite code: never a server message, host, recipient, link
  or credential, so ``DeliveryCoordinator`` can persist ``FAILED`` and nothing sensitive reaches a log.
"""
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
import re
import smtplib
import socket
import ssl
from typing import Literal
from uuid import UUID

from forge.accounts import canonical_email
from forge.invitation_delivery import DeliveryReceipt, build_message
from forge.mvp_local import ConfigError, _fail

SECURITY_MODES = ('starttls', 'tls', 'none')
DEFAULT_PORTS = {'starttls': 587, 'tls': 465}
DEFAULT_TIMEOUT = 10
SMTP_KEYS = ('FORGE_SMTP_HOST', 'FORGE_SMTP_PORT', 'FORGE_SMTP_SECURITY', 'FORGE_SMTP_USER',
             'FORGE_SMTP_PASSWORD_FILE', 'FORGE_SMTP_FROM', 'FORGE_SMTP_CA_FILE')
_HOST = re.compile(r'[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?')


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    security: Literal['starttls', 'tls', 'none']
    user: str | None
    password: str | None = field(repr=False)
    sender: str
    ca_file: str | None = None


def _is_ip(value):
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def _port(value, security):
    if value is None:
        if security not in DEFAULT_PORTS:
            _fail('FORGE_SMTP_PORT')  # cleartext relays have no standard submission port: say it explicitly
        return DEFAULT_PORTS[security]
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
        _fail('FORGE_SMTP_PORT')
    return int(value)


def _secret(path):
    if not path or not Path(path).is_absolute():
        _fail('FORGE_SMTP_PASSWORD_FILE')
    try:
        value = Path(path).read_text('utf-8').rstrip('\r\n')
    except (OSError, ValueError):
        _fail('FORGE_SMTP_PASSWORD_FILE')
    if not value:
        _fail('FORGE_SMTP_PASSWORD_FILE')
    return value


def load_smtp_settings(environ):
    """Validate ``FORGE_SMTP_*`` into ``SmtpSettings``; raises ``ConfigError('CONFIG_INVALID:<KEY>')``."""
    env = {name: value for name, value in environ.items() if name.startswith('FORGE_SMTP_')}
    if any(name not in SMTP_KEYS for name in env):
        _fail('unknown_key')
    host = env.get('FORGE_SMTP_HOST')
    if type(host) is not str or not (_HOST.fullmatch(host) or _is_ip(host)):
        _fail('FORGE_SMTP_HOST')
    security = env.get('FORGE_SMTP_SECURITY', 'starttls')
    if security not in SECURITY_MODES:
        _fail('FORGE_SMTP_SECURITY')
    port = _port(env.get('FORGE_SMTP_PORT'), security)
    try:
        sender = canonical_email(env.get('FORGE_SMTP_FROM'))
    except ValueError:
        _fail('FORGE_SMTP_FROM')
    user, password_file = env.get('FORGE_SMTP_USER'), env.get('FORGE_SMTP_PASSWORD_FILE')
    if security == 'none' and (user is not None or password_file is not None):
        _fail('FORGE_SMTP_SECURITY')  # credentials would travel in cleartext
    if user is not None and (not user or not user.isascii() or any(ord(c) < 33 for c in user) or len(user) > 256):
        _fail('FORGE_SMTP_USER')
    if (user is None) != (password_file is None):
        _fail('FORGE_SMTP_PASSWORD_FILE' if user is not None else 'FORGE_SMTP_USER')
    password = None if password_file is None else _secret(password_file)
    ca_file = env.get('FORGE_SMTP_CA_FILE')
    if ca_file is not None and (not Path(ca_file).is_absolute() or not Path(ca_file).is_file()):
        _fail('FORGE_SMTP_CA_FILE')
    return SmtpSettings(host, port, security, user, password, sender, ca_file)


class SmtpDeliveryError(Exception):
    """The message is always one of a few finite codes, never a value from the exchange."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class SmtpDelivery:
    """``MessageDelivery`` over SMTP; ``deliver`` returns a receipt or raises ``SmtpDeliveryError``."""
    channel = 'smtp'

    def __init__(self, settings: SmtpSettings, *, timeout: float = DEFAULT_TIMEOUT):
        self.settings, self.timeout = settings, timeout
        self._domain = settings.sender.rsplit('@', 1)[1]

    def deliver(self, message_id: UUID, recipient: str, name: str, link: str, *, purpose: str = 'invitation') -> DeliveryReceipt:
        message = build_message(self.settings.sender, recipient, name, link, purpose, message_id, domain=self._domain)
        try:
            self._send(message)
        except SmtpDeliveryError:
            raise
        except smtplib.SMTPAuthenticationError:
            raise SmtpDeliveryError('SMTP_AUTH') from None
        except smtplib.SMTPRecipientsRefused:
            raise SmtpDeliveryError('SMTP_RECIPIENT') from None
        except smtplib.SMTPSenderRefused as error:
            raise SmtpDeliveryError('SMTP_AUTH' if error.smtp_code in (530, 535) else 'SMTP_SENDER') from None
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as error:
            # smtplib reports a read that timed out as a dropped connection; the original error is its context.
            raise SmtpDeliveryError('SMTP_TIMEOUT' if isinstance(error.__context__, TimeoutError) else 'SMTP_CONNECT') from None
        except smtplib.SMTPResponseException:
            raise SmtpDeliveryError('SMTP_REJECTED') from None
        except smtplib.SMTPException:
            raise SmtpDeliveryError('SMTP_UNAVAILABLE') from None
        except ssl.SSLError:  # SSLCertVerificationError and handshake failures; before OSError, which it subclasses
            raise SmtpDeliveryError('SMTP_TLS') from None
        except (TimeoutError, socket.timeout):
            raise SmtpDeliveryError('SMTP_TIMEOUT') from None
        except OSError:
            raise SmtpDeliveryError('SMTP_CONNECT') from None
        return DeliveryReceipt(self.channel, str(message['Message-ID']))

    def _send(self, message):
        settings = self.settings
        context = ssl.create_default_context(cafile=settings.ca_file) if settings.security != 'none' else None
        if settings.security == 'tls':
            client = smtplib.SMTP_SSL(settings.host, settings.port, local_hostname=self._domain, timeout=self.timeout, context=context)
        else:
            client = smtplib.SMTP(settings.host, settings.port, local_hostname=self._domain, timeout=self.timeout)
        with client:
            client.ehlo()
            if settings.security == 'starttls':
                if not client.has_extn('starttls'):
                    raise SmtpDeliveryError('SMTP_STARTTLS_REQUIRED')  # nothing, least of all a password, is sent in clear
                client.starttls(context=context)
                client.ehlo()
            if settings.user is not None:
                client.login(settings.user, settings.password)
            client.send_message(message, from_addr=settings.sender, to_addrs=[canonical_email(message['To'].addresses[0].addr_spec)])
