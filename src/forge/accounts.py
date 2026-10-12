"""Versioned Forge account primitives; identity is stable, email is only lookup."""
import base64
from dataclasses import dataclass
import re
import secrets
from threading import BoundedSemaphore
import unicodedata
from uuid import UUID

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from forge.foundation import AuthenticatedIdentity

ACCOUNT_ISSUER = "urn:prometheon:forge:accounts:v1"
_PREFIX = "forge$scrypt$v1$131072$8$1$"
# Bound aggregate KDF memory to one ~128MiB derivation per worker process.
# HTTP rate/admission policy and fleet-level concurrency belong to U2 deployment.
# Members signing in at the same moment queue for the slot (bounded wait) instead of being refused: a refusal
# here is a 503 for a legitimate login. Past the wait the work is still refused without allocating.
_KDF_SLOT = BoundedSemaphore(1)
_KDF_WAIT = 5.0


class PasswordWorkUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Password work temporarily unavailable.")


def canonical_email(value: str) -> str:
    """ASCII case-insensitive policy; no provider-specific dot/plus rewriting."""
    if type(value) is not str or not value.isascii() or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid email.")
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1:
        raise ValueError("Invalid email.")
    local, domain = email.split("@")
    if (not 1 <= len(local) <= 64 or local.startswith(".") or local.endswith(".")
            or ".." in local or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", domain)):
        raise ValueError("Invalid email.")
    return email


def display_name(value: str) -> str:
    if (type(value) is not str or any(unicodedata.category(c).startswith("C") for c in value)
            or any(c in "\r\n\t" for c in value)):
        raise ValueError("Invalid name.")
    name = value.strip()
    if not 1 <= len(name) <= 120 or len(name.encode("utf-8")) > 480:
        raise ValueError("Invalid name.")
    return name


def password_bytes(value: str) -> bytes:
    if type(value) is not str or not 15 <= len(value) <= 1024 or "\x00" in value:
        raise ValueError("Invalid password.")
    try:
        data = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Invalid password.") from None
    if len(data) > 1024:
        raise ValueError("Invalid password.")
    return data


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str, length: int) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid encoding.")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(decoded) != length or _encode(decoded) != value:
        raise ValueError("Invalid encoding.")
    return decoded


def password_record(encoded: str) -> tuple[bytes, bytes]:
    """Allow only this version/cost, before allocating KDF memory."""
    if type(encoded) is not str or len(encoded) > 160 or not encoded.startswith(_PREFIX):
        raise ValueError("Unsupported password record.")
    fields = encoded[len(_PREFIX):].split("$")
    if len(fields) != 2:
        raise ValueError("Unsupported password record.")
    return _decode(fields[0], 16), _decode(fields[1], 32)


class PasswordHasher:
    def hash(self, password: str) -> str:
        data, salt = password_bytes(password), secrets.token_bytes(16)
        if not _KDF_SLOT.acquire(timeout=_KDF_WAIT):
            raise PasswordWorkUnavailable()
        try:
            derived = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(data)
            return _PREFIX + _encode(salt) + "$" + _encode(derived)
        finally:
            _KDF_SLOT.release()

    def verify(self, password: str, encoded: str) -> bool:
        try:
            data = password_bytes(password)
            salt, expected = password_record(encoded)
        except (ValueError, TypeError):
            return False
        if not _KDF_SLOT.acquire(timeout=_KDF_WAIT):
            raise PasswordWorkUnavailable()
        try:
            Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).verify(data, expected)
            return True
        except InvalidKey:
            return False
        finally:
            _KDF_SLOT.release()


@dataclass(frozen=True)
class Enrollment:
    account_id: UUID
    membership_id: UUID
    organization_id: UUID
    department_id: UUID

    @property
    def identity(self) -> AuthenticatedIdentity:
        return AuthenticatedIdentity("forge", ACCOUNT_ISSUER, str(self.account_id))
