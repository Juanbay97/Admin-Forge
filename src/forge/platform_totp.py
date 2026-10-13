"""Time-based one-time passwords for the platform owner, standard library only (RFC 4226 / RFC 6238, HMAC-SHA1).

Pure functions: this module knows nothing about the database. The shared secret is 20 random bytes, stored only
sealed (Fernet, a key of its own); recovery codes are 80-bit random codes stored only as SHA-256 digests. The replay
guard (a step is accepted once) lives in the database, next to the state it protects.
"""
import base64
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # one step either side of "now": clock drift, never more
SECRET_BYTES = 20
RECOVERY_CODES = 10
ISSUER = 'Prometheon Forge'
_ALPHABET = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')


class SecretUnreadable(Exception):
    """The sealed secret cannot be opened (wrong key, tampering, junk); never says which."""
    def __init__(self):
        super().__init__('The stored secret cannot be read.')


def hotp(secret, counter, digits=DIGITS):
    mac = hmac.new(secret, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def totp(secret, step, digits=DIGITS):
    return hotp(secret, step, digits)


def match_step(secret, code, now, *, window=WINDOW):
    """The step whose code equals ``code`` within ``window`` steps of ``now`` (seconds), else None.

    Every candidate is compared in constant time and the loop never exits early on a hit, so timing reveals nothing.
    """
    if type(code) is not str or len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    current, found = int(now) // STEP_SECONDS, None
    for step in range(current - window, current + window + 1):
        if hmac.compare_digest(totp(secret, step).encode('ascii'), code.encode('ascii')):
            found = step
    return found


def generate_secret():
    return secrets.token_bytes(SECRET_BYTES)


def otpauth_uri(secret, account):
    if type(account) is not str or not account or any(ord(c) < 32 or ord(c) == 127 for c in account):
        raise ValueError('Invalid account label.')
    encoded = base64.b32encode(secret).decode('ascii').rstrip('=')
    return ('otpauth://totp/%s:%s?secret=%s&issuer=%s&algorithm=SHA1&digits=%d&period=%d'
            % (quote(ISSUER, safe=''), quote(account, safe=''), encoded, quote(ISSUER, safe=''), DIGITS, STEP_SECONDS))


def generate_recovery_codes(count=RECOVERY_CODES):
    """Distinct codes of 16 base32 characters (80 bits), shown once as four dash-separated groups."""
    codes = set()
    while len(codes) < count:
        raw = base64.b32encode(secrets.token_bytes(10)).decode('ascii')
        codes.add('-'.join(raw[index:index + 4] for index in range(0, 16, 4)))
    return sorted(codes, key=lambda _: secrets.randbits(32))


def normalize_recovery_code(code):
    """The canonical 16 characters of a typed code (case, dashes and spaces ignored), or None when malformed."""
    if type(code) is not str or len(code) > 64:
        return None
    cleaned = code.upper().replace('-', '').replace(' ', '')
    if len(cleaned) != 16 or not set(cleaned) <= _ALPHABET:
        return None
    return cleaned


def hash_recovery_code(code):
    canonical = normalize_recovery_code(code)
    if canonical is None:
        raise ValueError('Invalid recovery code.')
    return hashlib.sha256(canonical.encode('ascii')).hexdigest()


class SecretSealer:
    """Fernet over the TOTP secret with the explicit platform key (never the delivery or gateway key)."""
    def __init__(self, key):
        if type(key) is not bytes:
            raise ValueError('An explicit Fernet key is required.')
        try:
            self._cipher = Fernet(key)
        except (ValueError, TypeError):
            raise ValueError('An explicit Fernet key is required.') from None

    def seal(self, secret):
        if type(secret) is not bytes or len(secret) != SECRET_BYTES:
            raise ValueError('A TOTP secret is exactly 20 bytes.')
        return self._cipher.encrypt(secret).decode('ascii')

    def open(self, token):
        try:
            secret = self._cipher.decrypt(token.encode('ascii'))
        except (InvalidToken, AttributeError, UnicodeEncodeError):
            raise SecretUnreadable() from None
        if len(secret) != SECRET_BYTES:
            raise SecretUnreadable()
        return secret
