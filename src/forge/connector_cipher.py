"""Sealing of connector credentials: org API keys and OAuth client apps, and per-user OAuth token bundles.

A dedicated deployment key (separate from the gateway, delivery, platform and policy keys, so one leak never opens another store)
seals a JSON payload that binds the organization, the scope (``org`` or ``user``), the subject (the member for ``user`` scope), the
capability id and the row revision. Moving a sealed value to another row, user, company, connector or revision makes it unreadable.
Rotation uses MultiFernet: the first key seals, every listed key opens. Every failure is the same ``ConnectorCipherError`` that never
carries key, ciphertext or plaintext.
"""
import base64
from dataclasses import dataclass
import json
import re
from uuid import UUID

from cryptography.fernet import Fernet, MultiFernet

MAX_REVISION = 2 ** 63 - 3
MAX_SECRET_BYTES = 8192
_CAPABILITY = re.compile(r'connector:[a-z0-9][a-z0-9._-]{0,127}')
_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}')


class ConnectorCipherError(ValueError):
    def __init__(self):
        super().__init__('Connector secret unavailable.')


@dataclass(frozen=True)
class Binding:
    organization: UUID
    scope: str
    subject: str
    capability: str
    revision: int

    def document(self):
        if (type(self.organization) is not UUID or self.scope not in ('org', 'user') or type(self.subject) is not str
                or len(self.subject) > 64 or not _CAPABILITY.fullmatch(self.capability if type(self.capability) is str else '')
                or type(self.revision) is not int or not 1 <= self.revision <= MAX_REVISION + 1):
            raise ConnectorCipherError()
        return {'v': 1, 'org': str(self.organization), 'scope': self.scope, 'subject': self.subject,
                'capability': self.capability, 'revision': self.revision}


def _raw(key):
    """The 32 raw bytes behind a Fernet-shaped or unpadded base64url key (used to prove two secrets are not the same one)."""
    text = key.decode('ascii') if type(key) is bytes else key
    text = text.rstrip('=')
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def _valid_secret(secret):
    if (type(secret) is not dict or not secret or len(secret) > 16
            or any(type(name) is not str or not _NAME.fullmatch(name) or type(value) is not str or not value or len(value) > 4096
                   for name, value in secret.items())):
        raise ConnectorCipherError()
    return secret


def hint(secret: str):
    """The last four characters of a long enough secret, for a write-only credential's status; never more."""
    return secret[-4:] if type(secret) is str and len(secret) >= 12 else None


class ConnectorCipher:
    def __init__(self, keys, *, distinct_from=()):
        try:
            listed = [keys] if type(keys) is bytes else list(keys)
            if not listed or any(type(key) is not bytes for key in listed):
                raise ValueError
            self._cipher = MultiFernet([Fernet(key) for key in listed])
            mine = {_raw(key) for key in listed}
            if mine & {_raw(other) for other in distinct_from}:
                raise ValueError  # one secret per purpose
        except Exception:
            raise ConnectorCipherError() from None

    def __repr__(self):
        return 'ConnectorCipher(<redacted>)'

    def seal(self, binding: Binding, secret: dict) -> str:
        payload = {**binding.document(), 'secret': _valid_secret(secret)}
        text = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        if len(text) > MAX_SECRET_BYTES:
            raise ConnectorCipherError()
        return self._cipher.encrypt(text).decode('ascii')

    def open(self, binding: Binding, sealed) -> dict:
        try:
            if type(sealed) is not str or not 80 <= len(sealed) <= 16384:
                raise ValueError
            if base64.urlsafe_b64encode(base64.urlsafe_b64decode(sealed.encode('ascii'))).decode('ascii') != sealed:
                raise ValueError  # canonical encoding only: trailing bytes after the padding are not ciphertext
            payload = json.loads(self._cipher.decrypt(sealed.encode('ascii')))
            secret = payload.pop('secret')
            if payload != binding.document():
                raise ValueError
            return _valid_secret(secret)
        except Exception:
            raise ConnectorCipherError() from None
