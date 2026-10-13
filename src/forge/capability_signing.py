"""Signing of the effective-policy document: canonical JSON, Ed25519, a key id and the client-side verification rules.

The client verifies offline against the published key set (``GET /forge/v1/capabilities/keys``). The signature covers the
canonical JSON of the whole document except ``sig`` (so ``kid`` is signed too): sorted keys, no whitespace, ASCII-only
escapes, exactly ``json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)``. ``verify_document`` is the
reference implementation of the client's rules: schema, known ``kid``, signature, expiry and monotonic epochs.

The private key is a deployment secret (a base64url 32-byte seed); rotation keeps the retired *public* keys in the published
set so a document signed before the rotation still verifies until it expires.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SCHEMA = 'forge.capability-policy.v1'
KEYS_SCHEMA = 'forge.capability-keys.v1'
LIFETIME_SECONDS = 24 * 3600
_B64 = re.compile(r'\A[A-Za-z0-9_-]+\Z')
_SIGNATURE_LENGTH = 86  # 64 bytes, base64url without padding


class DocumentRejected(Exception):
    """The message is one stable code: bad_schema, unknown_key, bad_signature, expired or rollback."""


def canonical(document: dict) -> bytes:
    body = {key: value for key, value in document.items() if key != 'sig'}
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def unb64u(text: str) -> bytes:
    if type(text) is not str or not _B64.match(text.rstrip('=')) or len(text) - len(text.rstrip('=')) > 2:
        raise ValueError('not base64url')
    text = text.rstrip('=')  # padding is optional: a Fernet-shaped secret and an unpadded seed are the same 32 bytes
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def kid_of(public_raw: bytes) -> str:
    return hashlib.sha256(public_raw).hexdigest()[:16]


def timestamp(seconds: float) -> str:
    return datetime.fromtimestamp(int(seconds), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _seconds(text) -> int:
    try:
        return int(datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        raise DocumentRejected('bad_schema') from None


class PolicySigner:
    def __init__(self, seed: bytes, *, retired=()):
        if type(seed) is not bytes or len(seed) != 32:
            raise ValueError('The policy signing seed must be 32 bytes.')
        self._key = Ed25519PrivateKey.from_private_bytes(seed)
        self._public = self._key.public_key().public_bytes_raw()
        self._retired = tuple(retired)
        for raw in self._retired:
            Ed25519PublicKey.from_public_bytes(raw)
        self.kid = kid_of(self._public)

    def sign(self, document: dict) -> dict:
        body = {key: value for key, value in document.items() if key not in ('sig', 'kid')}
        body['kid'] = self.kid
        return {**body, 'sig': b64u(self._key.sign(canonical(body)))}

    def public_raw(self) -> bytes:
        return self._public

    def keyset(self) -> dict:
        keys = [{'kid': self.kid, 'alg': 'Ed25519', 'public_key': b64u(self._public), 'status': 'active'}]
        keys += [{'kid': kid_of(raw), 'alg': 'Ed25519', 'public_key': b64u(raw), 'status': 'retired'} for raw in self._retired]
        return {'schema': KEYS_SCHEMA, 'keys': keys}


MAX_RETIRED = 8


def parse_retired_keys(values, *, active: str) -> tuple:
    """The retired PUBLIC keys of a rotation: base64url of 32 bytes each, at most ``MAX_RETIRED``, no duplicates, never the active key.

    ``active`` is the current signing seed. Returns the canonical (unpadded) strings; anything else raises ``ValueError`` without echoing a value.
    """
    seen, keys = set(), []
    active_public = PolicySigner(unb64u(active)).public_raw()
    for value in values:
        raw = unb64u(value)
        if len(raw) != 32 or raw in seen or raw == active_public:
            raise ValueError('The retired policy keys are invalid.')
        Ed25519PublicKey.from_public_bytes(raw)
        seen.add(raw)
        keys.append(b64u(raw))
    if len(keys) > MAX_RETIRED:
        raise ValueError('The retired policy keys are invalid.')
    return tuple(keys)


def split_retired_keys(text: str) -> list:
    """A list as an operator writes it: keys separated by whitespace or commas, ``#`` starts a comment that runs to the end of the line."""
    return [item for line in text.splitlines() for item in line.split('#', 1)[0].replace(',', ' ').split()]


def load_signer(value, *, retired=()) -> PolicySigner:
    """From the deployment secret: a base64url 32-byte seed. Anything else raises ValueError, never a partial signer."""
    try:
        seed = unb64u(value)
    except (ValueError, TypeError):
        raise ValueError('The policy signing key is invalid.') from None
    return PolicySigner(seed, retired=tuple(unb64u(item) for item in retired))


def verify_document(document: dict, keyset: dict, *, now: float, minimum_epochs=(0, 0)) -> None:
    """Raise ``DocumentRejected`` unless the document is signed by a published key, unexpired and not older than ``minimum_epochs``."""
    if type(document) is not dict or document.get('schema') != SCHEMA:
        raise DocumentRejected('bad_schema')
    key = next((item for item in keyset.get('keys', []) if item.get('kid') == document.get('kid')), None)
    if key is None:
        raise DocumentRejected('unknown_key')
    signature = document.get('sig')
    try:
        if type(signature) is not str or len(signature) != _SIGNATURE_LENGTH:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(unb64u(key['public_key'])).verify(unb64u(signature), canonical(document))
    except (ValueError, TypeError, KeyError, InvalidSignature):
        raise DocumentRejected('bad_signature') from None
    if now >= _seconds(document.get('expires_at')):
        raise DocumentRejected('expired')
    if any(type(document.get(name)) is not int or document[name] < floor
           for name, floor in zip(('platform_epoch', 'org_epoch'), minimum_epochs)):
        raise DocumentRejected('rollback')
