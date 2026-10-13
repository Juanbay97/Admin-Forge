"""Policy signing-key rotation chain: how a client learns a new public key without a new trust-on-first-use step.

A client pins the keys it got in the installer configuration (a TLS download from its control plane). When the signing key rotates, the
operator signs ONE rotation statement with the OLD private key that introduces the NEW public key (``python -m forge.capability_rotation
sign``, run before the old secret is replaced). The control plane publishes the statements next to the key set
(``GET /forge/v1/capabilities/pinning``). A client adopts a new key only through a statement signed by a key it already pinned:

* the statement is ``{schema, old_kid, new_kid, new_public_key, issued_at, sig}``; ``sig`` is Ed25519 by the old key over the canonical
  JSON of the statement without ``sig`` (the same canonicalization as the policy document);
* a pinned key that has signed an accepted statement is RETIRED at that statement's ``issued_at`` and signs nothing else;
* a retired key still verifies a policy document, but only one issued before its ``retired_at``;
* statements from keys the client has not pinned change nothing, so a replay or a forgery is harmless, and a chain of several
  rotations is walked in any order.

``apply_rotations`` and ``key_usable`` are the reference of those rules (the desktop client implements the same ones);
``parse_rotations`` validates the chain an operator configures, at start-up.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from forge.capability_signing import MAX_RETIRED, PINNING_SCHEMA, b64u, canonical, kid_of, unb64u, _SIGNATURE_LENGTH, _seconds

__all__ = ('PINNING_SCHEMA', 'ROTATION_SCHEMA', 'RotationRejected', 'apply_rotations', 'key_usable', 'main', 'parse_rotations',
           'sign_rotation', 'vectors', 'verify_rotation')

ROTATION_SCHEMA = 'forge.policy-key-rotation.v1'
_FIELDS = frozenset({'schema', 'old_kid', 'new_kid', 'new_public_key', 'issued_at', 'sig'})
_DATE = re.compile(r'\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z')


class RotationRejected(Exception):
    """The message is one stable code: bad_schema, unknown_key or bad_signature."""


def _date(text):
    if type(text) is not str or not _DATE.match(text):
        raise ValueError('Invalid rotation date.')
    try:
        _seconds(text)
    except Exception:
        raise ValueError('Invalid rotation date.') from None
    return text


def sign_rotation(old_seed: bytes, new_public: bytes, issued_at: str) -> dict:
    if type(old_seed) is not bytes or len(old_seed) != 32 or type(new_public) is not bytes or len(new_public) != 32:
        raise ValueError('Invalid rotation key.')
    key = Ed25519PrivateKey.from_private_bytes(old_seed)
    Ed25519PublicKey.from_public_bytes(new_public)
    old_public = key.public_key().public_bytes_raw()
    if new_public == old_public:
        raise ValueError('A key cannot rotate to itself.')
    body = {'schema': ROTATION_SCHEMA, 'old_kid': kid_of(old_public), 'new_kid': kid_of(new_public),
            'new_public_key': b64u(new_public), 'issued_at': _date(issued_at)}
    return {**body, 'sig': b64u(key.sign(canonical(body)))}


def verify_rotation(statement, pinned) -> bytes:
    """The new public key (raw) when ``statement`` is signed by a key in ``pinned`` (kid -> raw public key); else ``RotationRejected``."""
    if type(statement) is not dict or set(statement) != _FIELDS or statement['schema'] != ROTATION_SCHEMA:
        raise RotationRejected('bad_schema')
    try:
        new_public = unb64u(statement['new_public_key'])
        _date(statement['issued_at'])
        if (len(new_public) != 32 or type(statement['new_kid']) is not str or statement['new_kid'] != kid_of(new_public)
                or type(statement['sig']) is not str or len(statement['sig']) != _SIGNATURE_LENGTH):
            raise ValueError
        Ed25519PublicKey.from_public_bytes(new_public)
    except (ValueError, TypeError):
        raise RotationRejected('bad_schema') from None
    old_public = pinned.get(statement['old_kid']) if type(statement['old_kid']) is str else None
    if old_public is None:
        raise RotationRejected('unknown_key')
    try:
        Ed25519PublicKey.from_public_bytes(old_public).verify(unb64u(statement['sig']), canonical(statement))
    except (ValueError, TypeError, InvalidSignature):
        raise RotationRejected('bad_signature') from None
    return new_public


def apply_rotations(pinned, statements) -> dict:
    """``pinned`` maps kid -> raw public key; the result maps kid -> ``{'public': raw, 'retired_at': date or None}``."""
    keys = {kid: {'public': raw, 'retired_at': None} for kid, raw in pinned.items()}
    pending = list(statements)
    progress = True
    while progress:
        progress = False
        for statement in list(pending):
            signer = keys.get(statement.get('old_kid')) if type(statement) is dict else None
            if signer is None or signer['retired_at'] is not None:
                continue
            try:
                new_public = verify_rotation(statement, {kid: key['public'] for kid, key in keys.items()})
            except RotationRejected:
                pending.remove(statement)  # a forgery never becomes valid later
                continue
            signer['retired_at'] = statement['issued_at']
            keys.setdefault(statement['new_kid'], {'public': new_public, 'retired_at': None})
            pending.remove(statement)
            progress = True
    return keys


def key_usable(key, issued_at) -> bool:
    """Whether a pinned key (an ``apply_rotations`` entry) may verify a document issued at ``issued_at``."""
    return key['retired_at'] is None or _seconds(issued_at) < _seconds(key['retired_at'])


def parse_rotations(items, *, active_public: bytes, retired) -> tuple:
    """The chain an operator configures: a list of statements, each signed by a RETIRED key of this deployment (at most once per key)
    and introducing a retired or the active key. Anything else raises ``ValueError`` without echoing a value."""
    if type(items) is not list or len(items) > MAX_RETIRED:
        raise ValueError('The policy key rotations are invalid.')
    known = {kid_of(raw): raw for raw in (*retired, active_public)}
    signers = {kid_of(raw): raw for raw in retired}
    seen = set()
    for statement in items:
        try:
            verify_rotation(statement, signers)
        except RotationRejected:
            raise ValueError('The policy key rotations are invalid.') from None
        if statement['old_kid'] in seen or statement['new_kid'] not in known:
            raise ValueError('The policy key rotations are invalid.')
        seen.add(statement['old_kid'])
    return tuple(dict(statement) for statement in items)


def vectors() -> dict:
    """Deterministic vectors for a client implementation (Ed25519 signatures are deterministic): the pinned key, a two-step chain
    and statements that every client must refuse."""
    from forge.capability_signing import PolicySigner
    seeds = [bytes([number]) * 32 for number in (1, 2, 3)]
    publics = [PolicySigner(seed).public_raw() for seed in seeds]
    first = sign_rotation(seeds[0], publics[1], '2026-10-01T00:00:00Z')
    second = sign_rotation(seeds[1], publics[2], '2026-11-01T00:00:00Z')
    stranger = sign_rotation(bytes([9]) * 32, publics[2], '2026-10-01T00:00:00Z')
    return {
        'schema': 'forge.policy-key-rotation.vectors.v1',
        'note': 'Test vectors only: the keys derive from the seeds 0x01*32, 0x02*32 and 0x03*32 and secure nothing.',
        'pinned': [{'kid': kid_of(publics[0]), 'public_key': b64u(publics[0])}],
        'statements': [first, second],
        'expected': [{'kid': kid_of(raw), 'public_key': b64u(raw), 'retired_at': retired}
                     for raw, retired in zip(publics, ('2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z', None))],
        'rejected': [
            {'name': 'signed by a key that is not pinned', 'statement': stranger},
            {'name': 'new key swapped after signing', 'statement': {**first, 'new_public_key': b64u(publics[2]), 'new_kid': kid_of(publics[2])}},
            {'name': 'new kid does not match the key', 'statement': {**first, 'new_kid': kid_of(publics[2])}},
            {'name': 'date changed after signing', 'statement': {**first, 'issued_at': '2026-12-01T00:00:00Z'}},
            {'name': 'unknown field', 'statement': {**first, 'role': 'admin'}},
        ],
    }


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage()


def _read_seed(path):
    try:
        return unb64u(Path(path).read_text('utf-8').strip())
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        raise ValueError('KEY_FILE_INVALID') from None


def main(argv=None) -> int:
    """``sign --old-seed-file F (--new-seed-file F | --new-public-key K) [--issued-at 2026-10-13T00:00:00Z]``: one statement on stdout."""
    emit = lambda document: print(json.dumps(document), flush=True)
    try:
        parser = _Parser(prog='forge.capability_rotation', description='Sign a policy key rotation statement with the old key.')
        commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
        sign = commands.add_parser('sign')
        sign.add_argument('--old-seed-file', required=True)
        group = sign.add_mutually_exclusive_group(required=True)
        group.add_argument('--new-seed-file')
        group.add_argument('--new-public-key')
        sign.add_argument('--issued-at')
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except _Usage:
        emit({'status': 'failed', 'code': 'INVALID_ARGUMENTS'})
        return 2
    try:
        old = _read_seed(arguments.old_seed_file)
        if arguments.new_seed_file is not None:
            from forge.capability_signing import PolicySigner
            try:
                new = PolicySigner(_read_seed(arguments.new_seed_file)).public_raw()
            except ValueError:
                raise ValueError('KEY_FILE_INVALID') from None
        else:
            try:
                new = unb64u(arguments.new_public_key)
            except (ValueError, TypeError):
                raise ValueError('INVALID_KEY') from None
        if len(new) != 32:
            raise ValueError('INVALID_KEY')
        if arguments.issued_at is None:
            from forge.capability_signing import timestamp
            import time
            arguments.issued_at = timestamp(time.time())
        try:
            _date(arguments.issued_at)
        except ValueError:
            raise ValueError('INVALID_DATE') from None
        try:
            statement = sign_rotation(old, new, arguments.issued_at)
        except ValueError:
            raise ValueError('INVALID_KEY') from None
    except ValueError as error:
        emit({'status': 'failed', 'code': str(error) if str(error) in ('KEY_FILE_INVALID', 'INVALID_KEY', 'INVALID_DATE') else 'INVALID_KEY'})
        return 1
    emit(statement)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
