"""Strict Entra v2 access-token adapter; authentication never grants membership.

Trusted configuration selects the authority and audience. Unverified token fields
only route to a preconfigured tenant; they never authorize a caller or a URL.
PyJWT/cryptography verify RS256; this module owns resource bounds and claim policy.
"""
import base64
from dataclasses import dataclass, field
import json
import math
import re
import ssl
from threading import BoundedSemaphore, Lock
from time import monotonic, time
from typing import Callable, Protocol
from urllib.request import (
    HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
import jwt

from forge.foundation import AuthenticatedIdentity

HOST = "https://login.microsoftonline.com"
GUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
SCOPE = re.compile(r"[A-Za-z0-9._:/-]{1,128}")
UNAVAILABLE = "Entra signing metadata unavailable."


class EntraOperationalError(Exception):
    """Redacted operational failure, distinct from invalid caller credentials."""


def _number_within(value: object, low: float, high: float) -> bool:
    # Python integers are arbitrary precision; float conversion in isfinite can
    # overflow. Compare the typed value to finite policy bounds BEFORE conversion.
    return (type(value) in (int, float) and low <= value <= high
            and math.isfinite(value))


def _guid(value: object) -> str:
    if not isinstance(value, str) or GUID.fullmatch(value) is None:
        raise ValueError("Expected a GUID.")
    return str(UUID(value))


def _bounded_set(values: object, maximum: int, convert) -> frozenset[str]:
    if not isinstance(values, (set, frozenset, list, tuple)) or not 1 <= len(values) <= maximum:
        raise ValueError("Expected a nonempty bounded allowlist.")
    return frozenset(convert(value) for value in values)


def _scope(value: object) -> str:
    if not isinstance(value, str) or SCOPE.fullmatch(value) is None:
        raise ValueError("Expected a scope identifier.")
    return value


@dataclass(frozen=True)
class EntraConfiguration:
    allowed_tenants: frozenset[str]
    audience: str
    allowed_clients: frozenset[str]
    required_scopes: frozenset[str]

    def __post_init__(self):
        object.__setattr__(self, "allowed_tenants", _bounded_set(self.allowed_tenants, 16, _guid))
        object.__setattr__(self, "audience", _guid(self.audience))
        object.__setattr__(self, "allowed_clients", _bounded_set(self.allowed_clients, 32, _guid))
        object.__setattr__(self, "required_scopes", _bounded_set(self.required_scopes, 16, _scope))


@dataclass(frozen=True)
class ValidationLimits:
    token_bytes: int = 16384
    kid_chars: int = 128
    body_bytes: int = 262144
    key_count: int = 64
    cache_ttl: float = 3600
    refresh_cooldown: float = 60
    fetch_timeout: float = 3
    fetch_concurrency: int = 2
    clock_skew: float = 60

    def __post_init__(self):
        integer_bounds = {
            "token_bytes": (1024, 65536), "kid_chars": (1, 256),
            "body_bytes": (1024, 1048576), "key_count": (1, 128),
            "fetch_concurrency": (1, 4),
        }
        numeric_bounds = {
            "cache_ttl": (1, 86400), "refresh_cooldown": (1, 3600),
            "fetch_timeout": (0.1, 10), "clock_skew": (0, 300),
        }
        for name, (low, high) in integer_bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid integer validation limit.")
        for name, (low, high) in numeric_bounds.items():
            value = getattr(self, name)
            if not _number_within(value, low, high):
                raise ValueError("Invalid numeric validation limit.")


@dataclass(frozen=True, repr=False)
class VerifiedPrincipal:
    """Verified claim values; sub is never silently replaced by the domain subject."""
    sub: str
    tid: str
    oid: str
    issuer: str

    @property
    def identity(self) -> AuthenticatedIdentity:
        return AuthenticatedIdentity("entra", self.issuer, self.oid)


class JsonFetcher(Protocol):
    """Trusted transport must enforce timeout, size and redirect policy."""
    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EntraOperationalError(UNAVAILABLE)


class HttpsJsonFetcher:
    """TLS-verified bounded transport: no ambient proxy, cookies or credentials."""

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        # Resolver supplies an exact allowlisted URL. Recheck at this public boundary.
        if not _official_url(url):
            raise EntraOperationalError(UNAVAILABLE)
        try:
            opener = build_opener(
                ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
            deadline = monotonic() + 2 * timeout
            request = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError("Unexpected HTTP response.")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) > max_bytes):
                    raise ValueError("Response exceeds size limit.")
                chunks, size = [], 0
                while True:
                    if monotonic() >= deadline:
                        raise TimeoutError()
                    # read1 performs a bounded buffered read, not an unbounded
                    # read(n) waiting for all n bytes against a slow-drip peer.
                    chunk = response.read1(min(4096, max_bytes - size + 1))
                    if monotonic() >= deadline:
                        raise TimeoutError()
                    if not chunk:
                        return b"".join(chunks)
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Response exceeds size limit.")
                    chunks.append(chunk)
        except Exception:
            raise EntraOperationalError(UNAVAILABLE) from None


def _official_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    return re.fullmatch(
        re.escape(HOST) + r"/(?:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/v2\.0/\.well-known/openid-configuration"
        r"|(?:common|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})/discovery/v2\.0/keys)",
        url,
    ) is not None


def _json_object(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError("Duplicate JSON member.")
            result[name] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON value.")

    result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object.")
    return result


def _segment(value: str) -> dict:
    if BASE64URL.fullmatch(value) is None:
        raise ValueError("Invalid compact JWT.")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    return _json_object(raw)


@dataclass
class _TenantCache:
    lock: Lock = field(default_factory=Lock)
    keys: dict[str, RSAPublicKey] = field(default_factory=dict)
    expires: float = 0
    next_attempt: float = 0
    failed: bool = False


class EntraTokenValidator:
    """Synchronous trusted port; caches are tenant-bounded and thread-safe."""

    def __init__(
        self, configuration: EntraConfiguration, *, fetcher: JsonFetcher | None = None,
        clock: Callable[[], float] = time, monotonic_clock: Callable[[], float] = monotonic,
        limits: ValidationLimits | None = None,
    ):
        if not isinstance(configuration, EntraConfiguration):
            raise ValueError("Explicit Entra configuration is required.")
        if limits is not None and not isinstance(limits, ValidationLimits):
            raise ValueError("Explicit validation limits are required.")
        self.configuration = configuration
        self.limits = limits or ValidationLimits()
        self.fetcher = fetcher if fetcher is not None else HttpsJsonFetcher()
        self.clock, self.monotonic_clock = clock, monotonic_clock
        self._cache = {tenant: _TenantCache() for tenant in configuration.allowed_tenants}
        self._fetch_slots = BoundedSemaphore(self.limits.fetch_concurrency)

    def validate(self, token: str) -> AuthenticatedIdentity | None:
        principal = self.validate_principal(token)
        return principal.identity if principal is not None else None

    def validate_principal(self, token: str) -> VerifiedPrincipal | None:
        try:
            if not isinstance(token, str) or not token.isascii() or not 1 <= len(token) <= self.limits.token_bytes:
                return None
            parts = token.split(".")
            if len(parts) != 3 or not all(parts):
                return None
            header, claims = _segment(parts[0]), _segment(parts[1])
            kid = header.get("kid")
            if (
                header.get("alg") != "RS256" or header.get("typ", "JWT") != "JWT"
                or "crit" in header or not isinstance(kid, str) or not kid.isascii()
                or not 1 <= len(kid) <= self.limits.kid_chars
                or any(character.isspace() or ord(character) < 33 for character in kid)
            ):
                return None
            principal = self._principal(claims)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return None
        if principal is None:
            return None
        key = self._resolve(principal.tid, kid)
        if key is None:
            return None
        try:
            # Numeric dates are checked strictly below with the injected clock;
            # library defaults coerce types and read its own wall clock instead.
            verified = jwt.decode(
                token, key, algorithms=["RS256"], issuer=principal.issuer,
                audience=self.configuration.audience,
                options={"strict_aud": True, "verify_exp": False,
                         "verify_nbf": False, "verify_iat": False},
            )
            # Preserve strict parsing (including duplicate-member rejection), and
            # repeat time policy after potentially slow discovery/signature work.
            if verified != claims:
                return None
            return self._principal(verified)
        except (jwt.InvalidTokenError, ValueError, TypeError, UnicodeError):
            return None

    def _principal(self, claims: dict) -> VerifiedPrincipal | None:
        tenant, oid = _guid(claims.get("tid")), _guid(claims.get("oid"))
        expected = HOST + "/" + tenant + "/v2.0"
        sub, scopes = claims.get("sub"), claims.get("scp")
        if (
            tenant not in self.configuration.allowed_tenants or claims.get("iss") != expected
            or claims.get("aud") != self.configuration.audience or claims.get("ver") != "2.0"
            or _guid(claims.get("azp")) not in self.configuration.allowed_clients
            or not isinstance(sub, str) or not sub.strip() or len(sub) > 1024
            or not isinstance(scopes, str) or not 1 <= len(scopes) <= 4096
            or claims.get("idtyp", "user") != "user"
        ):
            return None
        tokens = scopes.split(" ")
        if any(SCOPE.fullmatch(scope) is None for scope in tokens):
            return None
        if not self.configuration.required_scopes.issubset(tokens):
            return None
        dates = [claims.get(name) for name in ("exp", "nbf", "iat")]
        if any(not _number_within(value, 0, 2**53) for value in dates):
            return None
        exp, nbf, iat = dates
        now, skew = self.clock(), self.limits.clock_skew
        if not _number_within(now, 0, 2**53):
            raise EntraOperationalError(UNAVAILABLE)
        if not (iat < exp and nbf < exp and now - skew < exp
                and nbf <= now + skew and iat <= now + skew):
            return None
        return VerifiedPrincipal(sub, tenant, oid, expected)

    def _resolve(self, tenant: str, kid: str) -> RSAPublicKey | None:
        cache = self._cache[tenant]
        if not cache.lock.acquire(timeout=self.limits.fetch_timeout):
            raise EntraOperationalError(UNAVAILABLE)
        try:
            now = self.monotonic_clock()
            fresh = now < cache.expires
            if fresh and kid in cache.keys:
                return cache.keys[kid]
            if now < cache.next_attempt:
                if cache.failed or not fresh:
                    raise EntraOperationalError(UNAVAILABLE)
                return None
            # Admission happens before I/O and backoff is retained on every outcome.
            cache.next_attempt = now + self.limits.refresh_cooldown
            cache.failed = True
            acquired = self._fetch_slots.acquire(timeout=self.limits.fetch_timeout)
            try:
                if not acquired:
                    raise EntraOperationalError(UNAVAILABLE)
                discovery = self._fetch_json(HOST + "/" + tenant + "/v2.0/.well-known/openid-configuration")
                expected = HOST + "/" + tenant + "/v2.0"
                allowed_urls = {HOST + "/" + tenant + "/discovery/v2.0/keys",
                                HOST + "/common/discovery/v2.0/keys"}
                if discovery.get("issuer") != expected or discovery.get("jwks_uri") not in allowed_urls:
                    raise ValueError("Unexpected discovery authority.")
                keys = self._public_keys(self._fetch_json(discovery["jwks_uri"]), expected)
                cache.keys = keys
                cache.expires = self.monotonic_clock() + self.limits.cache_ttl
                cache.failed = False
                return keys.get(kid)
            except Exception:
                raise EntraOperationalError(UNAVAILABLE) from None
            finally:
                cache.next_attempt = self.monotonic_clock() + self.limits.refresh_cooldown
                if acquired:
                    self._fetch_slots.release()
        finally:
            cache.lock.release()

    def _fetch_json(self, url: str) -> dict:
        raw = self.fetcher.fetch(
            url, timeout=self.limits.fetch_timeout, max_bytes=self.limits.body_bytes)
        if not isinstance(raw, bytes) or len(raw) > self.limits.body_bytes:
            raise ValueError("Invalid bounded response.")
        return _json_object(raw)

    def _public_keys(self, document: dict, expected: str) -> dict[str, RSAPublicKey]:
        entries = document.get("keys")
        if not isinstance(entries, list) or not 1 <= len(entries) <= self.limits.key_count:
            raise ValueError("Invalid key set.")
        result, seen = {}, set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Invalid public key.")
            kid, key_issuer = entry.get("kid"), entry.get("issuer")
            if (
                not isinstance(kid, str) or not kid.isascii()
                or not 1 <= len(kid) <= self.limits.kid_chars or kid in seen
                or any(character.isspace() or ord(character) < 33 for character in kid)
                or entry.get("kty") != "RSA" or entry.get("alg", "RS256") != "RS256"
                or entry.get("use") != "sig"
                or entry.get("key_ops", ["verify"]) != ["verify"]
                or any(name in entry for name in ("d", "p", "q", "dp", "dq", "qi", "oth"))
                or not isinstance(key_issuer, str)
                or (key_issuer != HOST + "/{tenantid}/v2.0" and re.fullmatch(
                    re.escape(HOST) + r"/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/v2\.0",
                    key_issuer) is None)
            ):
                raise ValueError("Invalid public signing key.")
            seen.add(kid)
            for name, maximum in (("n", 1024), ("e", 8)):
                value = entry.get(name)
                if not isinstance(value, str) or len(value) > maximum or BASE64URL.fullmatch(value) is None:
                    raise ValueError("Invalid RSA component.")
            key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(entry))
            if not isinstance(key, RSAPublicKey) or not 2048 <= key.key_size <= 4096:
                raise ValueError("Unsafe public key size.")
            if key.public_numbers().e != 65537:
                raise ValueError("Unsafe public exponent.")
            # Common JWKS legitimately mixes consumer and templated issuers.
            # Validate all public key shapes, but admit only this tenant's keys.
            if key_issuer in (expected, HOST + "/{tenantid}/v2.0"):
                result[kid] = key
        return result