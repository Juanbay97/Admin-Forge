"""The member's signed effective policy over a fake store and the real signer: the service, then the hidden routes."""
import json
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.capability_api import mount_effective
from forge.capability_effective import EffectivePolicy
from forge.capability_model import CapabilityDenied, CapabilityInvalid, CapabilityUnavailable, Snapshot
from forge.capability_policy import CatalogEntry, Layer
from forge.capability_signing import LIFETIME_SECONDS, PolicySigner, verify_document
from forge.foundation import AuthenticatedIdentity
from forge.invitations import capability_digest

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
NOW = 1_800_000_000
SKILL = CatalogEntry('skill:pdf', 'skill', '1.0.0', 'low', True, 'on', 0, None, 'none')
EXEC = CatalogEntry('tool:code_execute', 'tool', '1.0.0', 'high', False, 'on', 3, None, 'none')
SHELL = CatalogEntry('tool:bash', 'tool', '1.0.0', 'high', False, 'on', 4, None, 'none')
APP = CatalogEntry('app:acme.hello', 'app', '1.2.3', 'medium', False, 'off', 0, 'a' * 64, 'none', ('ui.title', 'storage.local'), ('ui.title',))
SNAPSHOT = Snapshot(5, 3, (APP, SKILL, SHELL, EXEC), {'tool:bash': Layer(None, 'forced_off')}, {}, {'app:acme.hello': True})
SIGNER = PolicySigner(bytes(range(32)))


class Store:
    def __init__(self, value=SNAPSHOT, fail=None, attested=None, attested_fail=None):
        self.calls, self.value, self.fail, self.attested, self.attested_fail, self.attested_calls = [], value, fail, attested, attested_fail, []

    def attested_level(self, digest, org):
        self.attested_calls.append((digest, org))
        if self.attested_fail:
            raise self.attested_fail
        return self.attested

    def snapshot(self, digest, org):
        self.calls.append((digest, org))
        if self.fail:
            raise self.fail
        return self.value


def store(value=SNAPSHOT, fail=None, **options):
    return Store(value, fail, **options)


class ServiceTests(unittest.TestCase):
    def test_the_document_carries_epochs_level_expiry_and_a_verifying_signature(self):
        policy = EffectivePolicy(store(), SIGNER, clock=lambda: NOW)
        document = policy.document(TOKEN, ORG, 3)
        self.assertEqual((document['org'], document['platform_epoch'], document['org_epoch'], document['reported_level']), (str(ORG), 5, 3, 3))
        self.assertEqual((document['issued_at'], document['expires_at']), ('2027-01-15T08:00:00Z', '2027-01-16T08:00:00Z'))
        by_id = {(item['kind'], item['id']): item for item in document['capabilities']}
        self.assertEqual(by_id[('tool', 'code_execute')]['state'], 'on')
        self.assertEqual((by_id[('tool', 'bash')]['state'], by_id[('tool', 'bash')]['reason']), ('forced_off', 'forced_off'))
        self.assertEqual((by_id[('app', 'acme.hello')]['state'], by_id[('app', 'acme.hello')]['granted_permissions'], by_id[('app', 'acme.hello')]['manifest_sha256']),
                         ('on', ['ui.title'], 'a' * 64))
        verify_document(document, SIGNER.keyset(), now=NOW)
        self.assertEqual(LIFETIME_SECONDS, 86400)

    def test_a_missing_level_is_zero_and_an_invalid_one_is_refused(self):
        policy = EffectivePolicy(store(), SIGNER, clock=lambda: NOW)
        zero = policy.document(TOKEN, ORG, None)
        self.assertEqual(zero['reported_level'], 0)
        self.assertEqual(next(item for item in zero['capabilities'] if item['id'] == 'code_execute')['state'], 'blocked_attestation')
        for bad in (-1, 5, True, '3', 3.0):
            with self.subTest(level=bad), self.assertRaises(CapabilityInvalid):
                policy.document(TOKEN, ORG, bad)

    def level_for(self, attested, claimed):
        fake = store(attested=attested)
        document = EffectivePolicy(fake, SIGNER, clock=lambda: NOW).document(TOKEN, ORG, claimed)
        verify_document(document, SIGNER.keyset(), now=NOW)
        return document['reported_level'], next(item for item in document['capabilities'] if item['id'] == 'code_execute')['state'], fake

    def test_without_an_attestation_the_claimed_level_is_used_exactly_as_before(self):
        self.assertEqual(self.level_for(None, 3)[:2], (3, 'on'))
        self.assertEqual(self.level_for(None, None)[:2], (0, 'blocked_attestation'))

    def test_the_latest_attestation_caps_what_a_request_claims(self):
        # (attested, claimed) -> effective: the lower of the two, because a claim can never exceed what the device last reported
        for attested, claimed, effective in ((2, 3, 2), (2, 4, 2), (0, 3, 0), (3, 3, 3), (4, 1, 1), (4, 0, 0), (1, 4, 1)):
            with self.subTest(attested=attested, claimed=claimed):
                self.assertEqual(self.level_for(attested, claimed)[0], effective)
        self.assertEqual(self.level_for(2, 3)[1], 'blocked_attestation', 'an exec tool needs the level the device really attested')

    def test_the_latest_attestation_is_used_when_the_request_claims_nothing(self):
        self.assertEqual(self.level_for(4, None)[:2], (4, 'on'))
        self.assertEqual(self.level_for(0, None)[:2], (0, 'blocked_attestation'))

    def test_the_attestation_lookup_is_asked_with_the_digest_and_company_and_its_failure_is_not_swallowed(self):
        _, _, fake = self.level_for(3, 3)
        ((digest, org),) = fake.attested_calls
        self.assertEqual((org, digest == capability_digest(TOKEN)), (ORG, True))
        with self.assertRaises(CapabilityDenied):
            EffectivePolicy(store(attested_fail=CapabilityDenied()), SIGNER, clock=lambda: NOW).document(TOKEN, ORG, 3)

    def test_an_unexpected_attested_level_is_refused_not_trusted(self):
        for odd in (5, -1, '3', True, 2.5):
            with self.subTest(odd=odd), self.assertRaises(CapabilityUnavailable):
                EffectivePolicy(store(attested=odd), SIGNER, clock=lambda: NOW).document(TOKEN, ORG, 3)

    def test_the_document_is_never_issued_without_a_signing_key_and_the_store_is_not_even_asked(self):
        fake = store()
        policy = EffectivePolicy(fake, None, clock=lambda: NOW)
        with self.assertRaises(CapabilityUnavailable):
            policy.document(TOKEN, ORG, 3)
        with self.assertRaises(CapabilityUnavailable):
            policy.keys()
        self.assertEqual(fake.calls, [])

    def test_store_refusals_pass_through(self):
        with self.assertRaises(CapabilityDenied):
            EffectivePolicy(store(fail=CapabilityDenied()), SIGNER, clock=lambda: NOW).document(TOKEN, ORG, 0)


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class Ready:
    def check(self):
        return True


def client(policy=None, organizations=None):
    policy = policy or EffectivePolicy(store(), SIGNER, clock=lambda: NOW)
    app = create_account_app(sessions=None)
    mount_effective(app, policy=policy, sessions=Sessions(), readiness=Ready(), organizations=organizations or (lambda token: [ORG]))
    return TestClient(app, raise_server_exceptions=False), app


PATH = '/forge/v1/capabilities/effective'


class RouteTests(unittest.TestCase):
    def test_hidden_and_the_contract_pin_is_unchanged(self):
        http, app = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)), contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue({PATH, '/forge/v1/capabilities/keys'} <= {route.path for route in app.routes})

    def test_a_member_session_gets_a_signed_no_store_document_and_a_stranger_gets_401(self):
        http, _ = client()
        response = http.get(PATH + '?sandbox_level=3', headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        verify_document(response.json(), SIGNER.keyset(), now=NOW)
        self.assertEqual(response.json()['reported_level'], 3)
        for headers in ({}, {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}):
            denied = http.get(PATH, headers=headers)
            self.assertEqual(denied.status_code, 401)
            self.assertNotIn('capabilities', denied.text)

    def test_a_missing_level_is_zero_and_a_malformed_one_is_422(self):
        http, _ = client()
        self.assertEqual(http.get(PATH, headers=HEADERS).json()['reported_level'], 0)
        for query in ('?sandbox_level=abc', '?sandbox_level=-1', '?sandbox_level=5', '?sandbox_level=1&sandbox_level=2', '?sandbox_level=', '?x=1', '?sandbox_level=03'):
            self.assertEqual(http.get(PATH + query, headers=HEADERS).status_code, 422, query)

    def test_the_company_comes_from_the_session_unless_the_member_names_one_of_several(self):
        other = uuid4()
        http, _ = client(organizations=lambda token: [ORG, other])
        ambiguous = http.get(PATH, headers=HEADERS)
        self.assertEqual((ambiguous.status_code, ambiguous.json()['error']['code']), (422, 'INVALID_REQUEST'))
        self.assertEqual(http.get(PATH + '?org=' + str(ORG), headers=HEADERS).json()['org'], str(ORG))
        strange = http.get(PATH + '?org=' + str(uuid4()), headers=HEADERS)
        self.assertEqual((strange.status_code, strange.json()['error']['code']), (404, 'NOT_FOUND'), 'a company the session does not belong to')
        none, _ = client(organizations=lambda token: [])
        self.assertEqual(none.get(PATH, headers=HEADERS).status_code, 404)
        self.assertEqual(http.get(PATH + '?org=not-a-uuid', headers=HEADERS).status_code, 422)

    def test_the_key_set_is_public_and_both_routes_are_503_without_a_signing_key(self):
        http, _ = client()
        keys = http.get('/forge/v1/capabilities/keys')
        self.assertEqual((keys.status_code, keys.json()), (200, SIGNER.keyset()))
        unsigned, _ = client(EffectivePolicy(store(), None, clock=lambda: NOW))
        for path, headers in (('/forge/v1/capabilities/keys', {}), (PATH, HEADERS)):
            response = unsigned.get(path, headers=headers)
            self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'), path)

    def test_a_denied_session_company_pair_is_the_same_not_found(self):
        http, _ = client(EffectivePolicy(store(fail=CapabilityDenied()), SIGNER, clock=lambda: NOW))
        response = http.get(PATH, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))


if __name__ == '__main__':
    unittest.main()
