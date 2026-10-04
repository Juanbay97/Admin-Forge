"""Offline real-RSA Entra proof; private keys exist only in test-process memory."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import base64
import json
from pathlib import Path
import sys
from threading import Lock
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
import jwt
from fastapi.testclient import TestClient

from forge.api import BootstrapRecords, create_app
from forge.entra import (
    EntraConfiguration, EntraOperationalError, EntraTokenValidator,
    HttpsJsonFetcher, ValidationLimits,
)
from forge.foundation import (
    AuthenticatedIdentity, Membership, MembershipStatus, Organization,
    OrganizationConfiguration,
)

TENANT = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT = "00000000-0000-0000-0000-000000000002"
AUDIENCE = "00000000-0000-0000-0000-000000000003"
CLIENT = "00000000-0000-0000-0000-000000000004"
OID = "00000000-0000-0000-0000-000000000005"
ORG = "00000000-0000-0000-0000-000000000006"
MEMBER = "00000000-0000-0000-0000-000000000007"
HOST = "https://login.microsoftonline.com"
KEYS = HOST + "/common/discovery/v2.0/keys"
TEMPLATE = HOST + "/{tenantid}/v2.0"
NOW = 2_000_000_000


def issuer(tenant=TENANT):
    return HOST + "/" + tenant + "/v2.0"


def metadata(tenant=TENANT):
    return issuer(tenant) + "/.well-known/openid-configuration"


def config(**changes):
    values = dict(allowed_tenants=frozenset({TENANT}), audience=AUDIENCE,
                  allowed_clients=frozenset({CLIENT}), required_scopes=frozenset({"forge.read"}))
    return EntraConfiguration(**(values | changes))


def public_jwk(key, kid="key-1", **changes):
    result = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return result | {"kid": kid, "use": "sig", "alg": "RS256", "issuer": TEMPLATE} | changes


class Clock:
    def __init__(self):
        self.wall = NOW
        self.mono = 100.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


class FakeFetcher:
    def __init__(self, key):
        self.keys = [public_jwk(key)]
        self.metadata_changes = {}
        self.calls = []
        self.error = None
        self.raw = None
        self.delay = 0
        self.active = self.max_active = 0
        self.lock = Lock()

    def fetch(self, url, *, timeout, max_bytes):
        with self.lock:
            self.calls.append((url, timeout, max_bytes))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            if self.raw is not None:
                return self.raw
            tenant = url.split("/")[3]
            result = ({"issuer": issuer(tenant), "jwks_uri": KEYS} | self.metadata_changes
                      if "/.well-known/" in url else {"keys": self.keys})
            return json.dumps(result).encode("utf-8")
        finally:
            with self.lock:
                self.active -= 1


class EntraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.clock = Clock()
        self.fetcher = FakeFetcher(self.key)
        self.validator = self.make_validator()

    def make_validator(self, configuration=None, limits=None):
        return EntraTokenValidator(
            configuration or config(), fetcher=self.fetcher,
            clock=lambda: self.clock.wall, monotonic_clock=lambda: self.clock.mono,
            limits=limits or ValidationLimits(),
        )

    def claims(self, **changes):
        return dict(iss=issuer(), aud=AUDIENCE, tid=TENANT, oid=OID,
                    sub="actual-pairwise-subject", ver="2.0", azp=CLIENT,
                    scp="forge.read", iat=NOW - 100, nbf=NOW - 100,
                    exp=NOW + 600) | changes

    def token(self, claims=None, key=None, headers=None):
        # Library encoder rejects deliberately malformed claims/headers before they
        # reach the adapter. Sign explicit JSON with vetted RSA for adversarial tests.
        def segment(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")
        header = {"alg": "RS256", "typ": "JWT", "kid": "key-1"} | (headers or {})
        message = segment(header) + b"." + segment(self.claims() if claims is None else claims)
        signature = (self.key if key is None else key).sign(
            message, padding.PKCS1v15(), hashes.SHA256())
        return (message + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()

    def test_valid_signature_and_explicit_principal(self):
        token = self.token()
        expected = AuthenticatedIdentity("entra", issuer(), OID)
        self.assertEqual(self.validator.validate(token), expected)
        principal = self.validator.validate_principal(token)
        self.assertEqual((principal.sub, principal.tid, principal.oid, principal.issuer),
                         ("actual-pairwise-subject", TENANT, OID, issuer()))
        with self.assertRaises(FrozenInstanceError):
            principal.sub = "changed"
        self.assertNotIn(OID, repr(principal))
        self.assertEqual(len(self.fetcher.calls), 2)

    def test_same_tenant_oid_different_sub_and_different_tenants(self):
        validator = self.make_validator(config(allowed_tenants=frozenset({TENANT, OTHER_TENANT})))
        first = validator.validate(self.token())
        second = validator.validate(self.token(self.claims(sub="different-sub")))
        foreign = validator.validate(self.token(self.claims(
            tid=OTHER_TENANT, iss=issuer(OTHER_TENANT))))
        self.assertEqual(first, second)
        self.assertNotEqual(first, foreign)
        self.assertEqual(foreign.subject, OID)

    def test_guests_and_email_are_not_identity_inputs(self):
        original = self.validator.validate(self.token())
        guest = self.validator.validate(self.token(self.claims(
            idp="live.com", email="guest@example.test", preferred_username="mutable")))
        self.assertEqual(original, guest)
        missing = self.claims(email="guest@example.test")
        del missing["oid"]
        self.assertIsNone(self.validator.validate(self.token(missing)))
        changed = self.validator.validate(self.token(self.claims(
            oid=OTHER_TENANT, email="guest@example.test")))
        self.assertNotEqual(original, changed)

    def test_cryptographic_tampering_and_wrong_key(self):
        self.assertIsNone(self.validator.validate(self.token(key=self.other_key)))
        parts = self.token().split(".")
        parts[1] = base64.urlsafe_b64encode(json.dumps(
            self.claims(oid=OTHER_TENANT)).encode()).decode().rstrip("=")
        self.assertIsNone(self.validator.validate(".".join(parts)))

    def test_algorithms_malformed_headers_and_oversize(self):
        hs = jwt.encode(self.claims(), "test-only-hmac-material-not-a-runtime-key",
                        algorithm="HS256", headers={"kid": "key-1"})
        for token in (hs, "bad", "a.b.c", "", None, b"bytes", "x" * 16385,
                      self.token(headers={"kid": ""}),
                      self.token(headers={"kid": "k" * 129}),
                      self.token(headers={"kid": []}),
                      self.token(headers={"crit": ["unknown"]}),
                      self.token(headers={"typ": []})):
            with self.subTest(shape=type(token).__name__):
                self.assertIsNone(self.validator.validate(token))
        self.assertEqual(self.fetcher.calls, [])

    def test_token_jku_x5u_never_supply_fetch_authority(self):
        self.assertIsNotNone(self.validator.validate(self.token(headers={
            "jku": "https://attacker.invalid/keys", "x5u": "file:///private"})))
        self.assertEqual([call[0] for call in self.fetcher.calls], [metadata(), KEYS])

    def test_mandatory_claims_and_strict_shapes(self):
        for name in ("iss", "aud", "tid", "oid", "sub", "ver", "azp", "scp", "exp", "nbf", "iat"):
            claims = self.claims()
            del claims[name]
            with self.subTest(missing=name):
                self.assertIsNone(self.validator.validate(self.token(claims)))
        for name, value in (
            ("iss", []), ("aud", [AUDIENCE]), ("tid", None), ("oid", 1),
            ("oid", "not-a-guid"), ("sub", ""), ("sub", "   "), ("sub", 1),
            ("ver", 2), ("azp", []), ("scp", ["forge.read"]),
            ("exp", str(NOW + 600)), ("exp", True), ("nbf", False),
            ("iat", None), ("exp", float("inf")), ("iat", float("nan")),
        ):
            with self.subTest(claim=name, value_type=type(value).__name__):
                self.assertIsNone(self.validator.validate(self.token(self.claims(**{name: value}))))

    def test_issuer_audience_tenant_version_and_authorized_client(self):
        for changes in (
            {"iss": issuer() + "/"}, {"iss": "https://sts.windows.net/" + TENANT + "/"},
            {"aud": CLIENT}, {"aud": "00000003-0000-0000-c000-000000000000"},
            {"tid": OTHER_TENANT}, {"ver": "1.0"}, {"azp": OTHER_TENANT},
            {"tid": "common"}, {"iss": "https://attacker.invalid"},
        ):
            with self.subTest(claims=list(changes)):
                self.assertIsNone(self.validator.validate(self.token(self.claims(**changes))))

    def test_delegated_exact_scopes_not_roles_or_app_identity(self):
        for changes in (
            {"scp": "forge.read.extra"}, {"scp": "notforge.read"}, {"scp": ""},
            {"scp": "forge.read\tother"}, {"scp": "forge.read  other"},
            {"scp": " forge.read"}, {"scp": "forge.read", "idtyp": "app"},
            {"scp": "", "roles": ["forge.read"]}, {"idtyp": []},
        ):
            with self.subTest(claims=list(changes)):
                self.assertIsNone(self.validator.validate(self.token(self.claims(**changes))))
        validator = self.make_validator(config(required_scopes=frozenset({"forge.read", "forge.write"})))
        self.assertIsNone(validator.validate(self.token()))
        self.assertIsNotNone(validator.validate(self.token(self.claims(scp="forge.write forge.read other"))))

    def test_time_chronology_and_skew_boundaries(self):
        for changes in (
            {"exp": NOW - 60}, {"exp": NOW - 61}, {"nbf": NOW + 61},
            {"iat": NOW + 61}, {"iat": NOW + 700}, {"nbf": NOW + 700},
            {"exp": NOW - 100, "iat": NOW - 1000, "nbf": NOW - 1000},
            {"exp": -1}, {"iat": 2**60},
        ):
            with self.subTest(claims=list(changes)):
                self.assertIsNone(self.validator.validate(self.token(self.claims(**changes))))
        self.assertIsNotNone(self.validator.validate(self.token(self.claims(exp=NOW - 59))))
        self.assertIsNotNone(self.validator.validate(self.token(self.claims(nbf=NOW + 60, iat=NOW + 60))))

    def test_configuration_is_bounded_and_immutable(self):
        for changes in (
            {"allowed_tenants": frozenset()}, {"allowed_clients": frozenset()},
            {"required_scopes": frozenset()}, {"audience": "not-a-guid"},
            {"allowed_tenants": TENANT}, {"allowed_clients": [True]},
            {"required_scopes": {"bad scope"}}, {"required_scopes": {"x" * 129}},
            {"allowed_tenants": {f"00000000-0000-0000-0000-{i:012d}" for i in range(17)}},
        ):
            with self.subTest(field=list(changes)):
                with self.assertRaises(ValueError):
                    config(**changes)
        mutable = {TENANT}
        configuration = config(allowed_tenants=mutable)
        mutable.add(OTHER_TENANT)
        self.assertEqual(configuration.allowed_tenants, frozenset({TENANT}))

    def test_limit_configuration_rejects_unbounded_values(self):
        for changes in (
            {"cache_ttl": 0}, {"cache_ttl": float("inf")}, {"cache_ttl": 10**400}, {"clock_skew": 301},
            {"refresh_cooldown": 0}, {"fetch_timeout": -1}, {"key_count": 1000000},
            {"fetch_concurrency": True}, {"token_bytes": 1000000000},
        ):
            with self.subTest(field=list(changes)):
                with self.assertRaises(ValueError):
                    ValidationLimits(**changes)

    def test_discovery_rejects_issuer_and_jwks_urls(self):
        urls = (
            "https://attacker.invalid/keys", "http://login.microsoftonline.com/common/discovery/v2.0/keys",
            HOST + ":443/common/discovery/v2.0/keys", HOST + "/common/discovery/v2.0/keys?appid=x",
            HOST + "/common/discovery/v2.0/keys#fragment",
            "https://user:password@login.microsoftonline.com/common/discovery/v2.0/keys",
            HOST + "/" + OTHER_TENANT + "/discovery/v2.0/keys",
            HOST + "/common/discovery/keys", HOST + "/common/discovery/v2.0/keys/",
        )
        for url in urls:
            self.fetcher.metadata_changes = {"jwks_uri": url}
            validator = self.make_validator()
            with self.subTest(url=url):
                with self.assertRaises(EntraOperationalError):
                    validator.validate(self.token())
        self.fetcher.metadata_changes = {"issuer": issuer(OTHER_TENANT)}
        with self.assertRaises(EntraOperationalError):
            self.make_validator().validate(self.token())
        self.assertTrue(all("/.well-known/" in call[0] for call in self.fetcher.calls))

    def test_configured_tenant_specific_keys_url(self):
        url = HOST + "/" + TENANT + "/discovery/v2.0/keys"
        self.fetcher.metadata_changes = {"jwks_uri": url}
        self.assertIsNotNone(self.validator.validate(self.token()))
        self.assertEqual(self.fetcher.calls[-1][0], url)

    def test_key_issuer_algorithm_use_and_private_material(self):
        for changes in (
            {"issuer": "https://attacker.invalid"},
            {"issuer": None}, {"alg": "HS256"}, {"use": "enc"}, {"kty": "EC"},
            {"d": "AQAB"}, {"key_ops": ["decrypt"]}, {"n": "AQAB"}, {"e": "Ag"},
        ):
            self.fetcher.keys = [public_jwk(self.key, **changes)]
            with self.subTest(field=list(changes)):
                with self.assertRaises(EntraOperationalError):
                    self.make_validator().validate(self.token())
        self.fetcher.keys = [public_jwk(self.key, issuer=issuer(OTHER_TENANT))]
        self.assertIsNone(self.make_validator().validate(self.token()))
        self.fetcher.keys = [public_jwk(self.key, issuer=issuer())]
        self.assertIsNotNone(self.make_validator().validate(self.token()))

    def test_duplicate_kids_key_count_and_body_bounds(self):
        for keys in ([public_jwk(self.key)] * 2, [public_jwk(self.key)] * 65, []):
            self.fetcher.keys = keys
            with self.subTest(count=len(keys)):
                with self.assertRaises(EntraOperationalError):
                    self.make_validator().validate(self.token())
        self.fetcher.raw = b"x" * 262145
        with self.assertRaises(EntraOperationalError):
            self.make_validator().validate(self.token())

    def test_json_shapes_duplicate_fields_and_nonfinite_metadata(self):
        for raw in (b"[]", b"null", b"not-json", b'{"issuer":1,"issuer":2}',
                    b'{"issuer":NaN}', b"\xff"):
            self.fetcher.raw = raw
            with self.subTest(raw_size=len(raw)):
                with self.assertRaises(EntraOperationalError):
                    self.make_validator().validate(self.token())

    def test_cache_rotation_ttl_and_removed_key(self):
        self.assertIsNotNone(self.validator.validate(self.token()))
        self.fetcher.keys = [public_jwk(self.other_key, kid="key-2")]
        rotated = self.token(key=self.other_key, headers={"kid": "key-2"})
        self.assertIsNone(self.validator.validate(rotated))
        self.assertEqual(len(self.fetcher.calls), 2)
        self.clock.advance(60)
        self.assertIsNotNone(self.validator.validate(rotated))
        self.assertEqual(len(self.fetcher.calls), 4)
        self.assertIsNone(self.validator.validate(self.token()))
        self.clock.advance(3600)
        rotated = self.token(self.claims(iat=self.clock.wall - 1, nbf=self.clock.wall - 1,
                                             exp=self.clock.wall + 600),
                             key=self.other_key, headers={"kid": "key-2"})
        self.assertIsNotNone(self.validator.validate(rotated))
        self.assertEqual(len(self.fetcher.calls), 6)

    def test_unknown_kid_flood_bounded_refresh(self):
        self.validator.validate(self.token())
        for i in range(25):
            self.assertIsNone(self.validator.validate(self.token(headers={"kid": "unknown-" + str(i)})))
        self.assertEqual(len(self.fetcher.calls), 2)
        self.clock.advance(60)
        for i in range(25):
            self.assertIsNone(self.validator.validate(self.token(headers={"kid": "next-" + str(i)})))
        self.assertEqual(len(self.fetcher.calls), 4)

    def test_fetch_failure_has_redacted_error_and_backoff(self):
        self.fetcher.error = OSError("PRIVATE_NETWORK_ERROR_MARKER")
        for _ in range(5):
            with self.assertRaises(EntraOperationalError) as caught:
                self.validator.validate(self.token())
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(len(self.fetcher.calls), 1)
        self.clock.advance(60)
        with self.assertRaises(EntraOperationalError):
            self.validator.validate(self.token())
        self.assertEqual(len(self.fetcher.calls), 2)

    def test_expired_cache_is_not_accepted_after_fetch_failure(self):
        self.validator.validate(self.token())
        self.clock.advance(3600)
        self.fetcher.error = TimeoutError("PRIVATE_TIMEOUT")
        for _ in range(3):
            with self.assertRaises(EntraOperationalError):
                self.validator.validate(self.token(self.claims(
                    iat=self.clock.wall - 1, nbf=self.clock.wall - 1, exp=self.clock.wall + 600)))
        self.assertEqual(len(self.fetcher.calls), 3)

    def test_concurrent_initial_and_unknown_kid_requests_coalesce(self):
        self.fetcher.delay = 0.02
        token = self.token()
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(self.validator.validate, [token] * 24))
        self.assertTrue(all(value is not None for value in results))
        self.assertEqual(len(self.fetcher.calls), 2)
        self.assertEqual(self.fetcher.max_active, 1)
        self.clock.advance(60)
        unknown = self.token(headers={"kid": "unknown"})
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(self.validator.validate, [unknown] * 24))
        self.assertEqual(results, [None] * 24)
        self.assertEqual(len(self.fetcher.calls), 4)

    def test_http_actual_validator_preserves_membership_and_redacts_failures(self):
        expected = AuthenticatedIdentity("entra", issuer(), OID)

        class Reader:
            calls = 0
            def read(inner, identity, organization_id):
                inner.calls += 1
                self.assertEqual(identity, expected)
                return BootstrapRecords(
                    Membership(MEMBER, ORG, expected, MembershipStatus.ACTIVE),
                    Organization(ORG, "example", "Example", True),
                    OrganizationConfiguration(ORG, 1, {"secret": "PRIVATE_CONFIG"}),
                )

        reader = Reader()
        with TestClient(create_app(self.validator, reader)) as client:
            rejected = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                  headers={"Authorization": "Bearer " + self.token(key=self.other_key)})
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(reader.calls, 0)
            success = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                 headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(success.status_code, 200)
            self.assertEqual(reader.calls, 1)
            self.assertNotIn("PRIVATE", success.text)
        failing = self.make_validator()
        self.fetcher.error = OSError("PRIVATE_NETWORK_ERROR_MARKER")
        with TestClient(create_app(failing, reader)) as client:
            response = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                  headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "SERVICE_UNAVAILABLE")
            self.assertNotIn("PRIVATE", response.text)
            self.assertEqual(reader.calls, 1)

    def test_default_application_remains_deny_all(self):
        with TestClient(create_app()) as client:
            response = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                  headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.fetcher.calls, [])

    def test_cross_tenant_fetch_concurrency_is_globally_bounded(self):
        tenants = {f"00000000-0000-0000-0000-{i:012d}" for i in range(1, 7)}
        validator = self.make_validator(config(allowed_tenants=tenants))
        self.fetcher.delay = 0.02
        tokens = [self.token(self.claims(tid=tenant, iss=issuer(tenant))) for tenant in tenants]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(validator.validate, tokens))
        self.assertTrue(all(value is not None for value in results))
        self.assertEqual(len(self.fetcher.calls), 12)
        self.assertLessEqual(self.fetcher.max_active, 2)

    def test_fetch_capacity_timeout_also_backs_off(self):
        validator = self.make_validator(limits=replace(ValidationLimits(), fetch_timeout=0.1))
        for _ in range(2):
            validator._fetch_slots.acquire()
        try:
            with self.assertRaises(EntraOperationalError):
                validator.validate(self.token())
        finally:
            for _ in range(2):
                validator._fetch_slots.release()
        with self.assertRaises(EntraOperationalError):
            validator.validate(self.token())
        self.assertEqual(self.fetcher.calls, [])
        self.clock.advance(60)
        self.assertIsNotNone(validator.validate(self.token()))

    def test_invalid_claims_do_not_fetch_and_token_json_duplicates_reject(self):
        for claims in (self.claims(aud=CLIENT), self.claims(tid=OTHER_TENANT),
                       self.claims(exp=NOW - 1000)):
            self.assertIsNone(self.validator.validate(self.token(claims)))
        parts = self.token().split(".")
        payload = json.dumps(self.claims())[:-1] + ',"tid":"' + TENANT + '"}'
        parts[1] = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        self.assertIsNone(self.validator.validate(".".join(parts)))
        parts[1] = base64.urlsafe_b64encode(
            (('{"deep":' + "[" * 1200 + "0" + "]" * 1200 + "}").encode())).decode().rstrip("=")
        self.assertIsNone(self.validator.validate(".".join(parts)))
        self.assertEqual(self.fetcher.calls, [])

    def test_suspended_membership_and_foreign_context_still_deny(self):
        identity = AuthenticatedIdentity("entra", issuer(), OID)
        active = BootstrapRecords(
            Membership(MEMBER, ORG, identity, MembershipStatus.ACTIVE),
            Organization(ORG, "example", "Example", True),
            OrganizationConfiguration(ORG, 1),
        )

        class Reader:
            value = active
            def read(inner, validated, selected):
                return inner.value

        reader = Reader()
        with TestClient(create_app(self.validator, reader)) as client:
            reader.value = replace(active, membership=replace(
                active.membership, status=MembershipStatus.SUSPENDED))
            response = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                  headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "MEMBERSHIP_SUSPENDED")
            reader.value = replace(active, membership=replace(
                active.membership, identity=replace(identity, subject=OTHER_TENANT)))
            response = client.get("/forge/v1/bootstrap", params={"organization_id": ORG},
                                  headers={"Authorization": "Bearer " + self.token()})
            self.assertEqual(response.status_code, 404)

    def test_common_jwks_mixed_issuer_keys_are_scoped_not_global_failure(self):
        consumer = "9188040d-6c67-4c5b-b112-36a304b66dad"
        self.fetcher.keys = [
            public_jwk(self.key),
            public_jwk(self.other_key, kid="consumer-key", issuer=issuer(consumer)),
        ]
        self.assertIsNotNone(self.validator.validate(self.token()))
        self.assertIsNone(self.validator.validate(self.token(
            key=self.other_key, headers={"kid": "consumer-key"})))

    def test_time_is_rechecked_after_discovery(self):
        original = self.fetcher.fetch
        def delayed(url, **kwargs):
            result = original(url, **kwargs)
            if url == KEYS:
                self.clock.wall += 1000
            return result
        self.fetcher.fetch = delayed
        self.assertIsNone(self.validator.validate(self.token()))
        self.assertEqual(len(self.fetcher.calls), 2)

    def test_configuration_and_key_limits_cover_all_allowlists(self):
        for changes in (
            {"allowed_clients": {f"00000000-0000-0000-0000-{i:012d}" for i in range(33)}},
            {"required_scopes": {"scope." + str(i) for i in range(17)}},
        ):
            with self.subTest(field=list(changes)):
                with self.assertRaises(ValueError):
                    config(**changes)
        weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        self.fetcher.keys = [public_jwk(weak)]
        with self.assertRaises(EntraOperationalError):
            self.validator.validate(self.token(key=weak))

    def test_oversized_numeric_dates_reject_directly_without_fetch(self):
        for name in ("exp", "nbf", "iat"):
            token = self.token(self.claims(**{name: 10**400}))
            token = token.rsplit(".", 1)[0] + ".AAA"
            with self.subTest(claim=name):
                try:
                    result = self.validator.validate(token)
                except OverflowError:
                    self.fail("Oversized NumericDate must reject, never overflow.")
                self.assertIsNone(result)
        self.assertEqual(self.fetcher.calls, [])

    def test_oversized_numeric_dates_return_http_401_without_reader(self):
        class Reader:
            calls = 0
            def read(inner, identity, organization_id):
                inner.calls += 1
                raise AssertionError("Invalid NumericDate reached reader.")

        reader = Reader()
        with TestClient(create_app(self.validator, reader)) as client:
            for name in ("exp", "nbf", "iat"):
                token = self.token(self.claims(**{name: 10**400}))
                token = token.rsplit(".", 1)[0] + ".AAA"
                with self.subTest(claim=name):
                    response = client.get(
                        "/forge/v1/bootstrap", params={"organization_id": ORG},
                        headers={"Authorization": "Bearer " + token})
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
        self.assertEqual(reader.calls, 0)
        self.assertEqual(self.fetcher.calls, [])


class HttpsFetcherTests(unittest.TestCase):
    class Response:
        status = 200
        def __init__(self, chunks, headers=None, url=KEYS):
            self.chunks, self.headers, self.url = list(chunks), headers or {}, url
            self.closed = False
            self.requested_sizes = []
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True
        def geturl(self):
            return self.url
        def read1(self, size):
            self.requested_sizes.append(size)
            return self.chunks.pop(0) if self.chunks else b""

    def fetch(self, response, *, max_bytes=16):
        opener = unittest.mock.Mock()
        opener.open.return_value = response
        with patch("forge.entra.build_opener", return_value=opener):
            result = HttpsJsonFetcher().fetch(KEYS, timeout=3, max_bytes=max_bytes)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 3)
        return result

    def test_bounded_read_closes_response_and_disables_proxy_redirects(self):
        response = self.Response([b'{"keys":', b"[]}"])
        opener = unittest.mock.Mock()
        opener.open.return_value = response
        with patch("forge.entra.build_opener", return_value=opener) as factory:
            self.assertEqual(HttpsJsonFetcher().fetch(KEYS, timeout=3, max_bytes=16),
                             b'{"keys":[]}')
        handlers = factory.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertTrue(handlers[1]._context.check_hostname)
        self.assertEqual(handlers[1]._context.verify_mode, 2)  # ssl.CERT_REQUIRED
        with self.assertRaises(EntraOperationalError):
            handlers[2].redirect_request(None, None, 302, "", {}, "https://attacker.invalid")
        self.assertTrue(response.closed)
        self.assertTrue(all(size <= 17 for size in response.requested_sizes))

    def test_redirect_status_url_change_and_bad_content_length(self):
        for response in (
            self.Response([], {"Content-Length": "17"}),
            self.Response([], {"Content-Length": "-1"}),
            self.Response([], {"Content-Length": "invalid"}),
            self.Response([], url="https://attacker.invalid"),
        ):
            with self.subTest(headers=response.headers, url=response.url):
                with self.assertRaises(EntraOperationalError):
                    self.fetch(response)
                self.assertTrue(response.closed)
        response = self.Response([])
        response.status = 302
        with self.assertRaises(EntraOperationalError):
            self.fetch(response)

    def test_body_limit_without_content_length_and_exact_limit(self):
        response = self.Response([b"a" * 8, b"b" * 9])
        with self.assertRaises(EntraOperationalError):
            self.fetch(response)
        self.assertTrue(response.closed)
        self.assertEqual(self.fetch(self.Response([b"a" * 16])), b"a" * 16)

    def test_deadline_and_transport_exception_are_redacted(self):
        response = self.Response([b"a", b"b"])
        opener = unittest.mock.Mock()
        opener.open.return_value = response
        with patch("forge.entra.build_opener", return_value=opener), patch(
                "forge.entra.monotonic", side_effect=[0, 1, 7]):
            with self.assertRaises(EntraOperationalError):
                HttpsJsonFetcher().fetch(KEYS, timeout=3, max_bytes=16)
        self.assertTrue(response.closed)
        opener.open.side_effect = TimeoutError("PRIVATE_NETWORK_DIAGNOSTIC")
        with patch("forge.entra.build_opener", return_value=opener):
            with self.assertRaises(EntraOperationalError) as caught:
                HttpsJsonFetcher().fetch(KEYS, timeout=3, max_bytes=16)
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_fetcher_rejects_nonofficial_urls_without_io(self):
        for url in ("file:///private", "https://attacker.invalid", KEYS + "?query=1", KEYS + "#x"):
            with patch("forge.entra.build_opener") as factory:
                with self.assertRaises(EntraOperationalError):
                    HttpsJsonFetcher().fetch(url, timeout=3, max_bytes=16)
                factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()