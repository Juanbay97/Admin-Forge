"""Deployment allow-list for gateway origins; labelled fixtures, no remote calls."""
from pathlib import Path
import secrets
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from unittest.mock import MagicMock
from uuid import UUID, uuid4
import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from forge.accounts import ACCOUNT_ISSUER
from forge.account_api import create_account_app
from forge.authorization import AuthorizationSnapshot
from forge.fake_gateway import FakeGatewayConfiguration, create_fake_gateway, MODELS
from forge.foundation import AuthenticatedIdentity, MembershipStatus
from forge.gateway_catalog import GatewayCatalog
from forge.gateway_catalog_adapter import HttpxModelsAdapter
from forge.gateway_configuration import (GatewayCipher, GatewayConfiguration, GatewayConflict,
    GatewayRecord, GatewayUnavailable, GATEWAY_ENDPOINT)
from forge.gateway_inference import TextRequest
from forge.gateway_inference_adapter import HttpxTextAdapter
from forge.gateway_origins import DEFAULT_ENDPOINT, DEFAULT_POLICY, OriginDenied, OriginPolicy

LISTED = 'https://gw.example.com'
LOOPBACK = 'http://127.0.0.1:3413'
OTHER = 'https://gw.other.example.com'
KEY = 'labelled-fixture-not-live-key'
ORG = '11111111-1111-4111-8111-111111111111'


def policy(*entries, dev=False):
    return OriginPolicy(frozenset(entries), dev=dev)


class PolicyTests(unittest.TestCase):
    def test_default_is_the_single_fixed_origin(self):
        self.assertEqual(DEFAULT_ENDPOINT, GATEWAY_ENDPOINT)
        self.assertEqual(DEFAULT_POLICY.allowed, frozenset({DEFAULT_ENDPOINT}))

    def test_allow_listed_origin_is_accepted_exactly(self):
        subject = policy(LISTED, OTHER)
        self.assertEqual(subject.require(LISTED), LISTED)
        self.assertEqual(subject.require(OTHER), OTHER)
        self.assertTrue(subject.permits(LISTED))

    def test_non_listed_and_look_alike_origins_are_denied(self):
        subject = policy(LISTED)
        for value in ('https://evil.example.net', LISTED + '.evil.net', 'https://gw.example.com@evil.net',
                      LISTED + '/', LISTED + '/v1', LISTED + '?x=1', LISTED + '#frag',
                      LISTED + ':8443', LISTED + ':443', 'http://gw.example.com',
                      'https://GW.EXAMPLE.COM', 'https://user:pw@gw.example.com', ' ' + LISTED,
                      LISTED + '\n', '', None, 42, b'https://gw.example.com'):
            with self.subTest(value=value):
                self.assertFalse(subject.permits(value))
                with self.assertRaises(OriginDenied):
                    subject.require(value)

    def test_denial_is_redacted_and_is_a_value_error(self):
        with self.assertRaises(ValueError) as caught:
            policy(LISTED).require('https://evil.example.net/secret-path')
        self.assertNotIn('evil', str(caught.exception))
        self.assertIsInstance(caught.exception, OriginDenied)

    def test_loopback_http_requires_the_dev_profile(self):
        self.assertTrue(policy(LOOPBACK, dev=True).permits(LOOPBACK))
        with self.assertRaises(ValueError):
            policy(LOOPBACK)
        with self.assertRaises(ValueError):
            policy(LISTED, LOOPBACK, dev=False)

    def test_malformed_or_unsafe_entries_fail_closed_at_composition(self):
        for entry in ('http://gw.example.com', 'http://localhost:3413', 'http://10.0.0.5:3413',
                      'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:70000',
                      'ftp://gw.example.com', 'gw.example.com', 'https://', 'https://user@gw.example.com',
                      LISTED + '/', LISTED + '/v1', LISTED + '?x=1', LISTED + '#f', 'https://GW.example.com',
                      'https://gw.example.com:0', 'https://gw.example.com:notaport', '', 7):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                OriginPolicy(frozenset({entry}), dev=True)

    def test_allow_list_must_be_a_non_empty_frozenset(self):
        for value in (set(), frozenset(), [LISTED], (LISTED,), LISTED, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                OriginPolicy(value)


class Store:
    def __init__(self):
        self.records = {}
        self.saves = []

    def read(self, digest, org):
        return self.records.get(org)

    def save(self, digest, org, expected, binding, encrypted, endpoint=GATEWAY_ENDPOINT):
        current = self.records.get(org)
        if (current.revision if current else 0) != expected:
            raise GatewayConflict()
        value = GatewayRecord(expected + 1, binding, endpoint, encrypted)
        self.records[org] = value
        self.saves.append(endpoint)
        return value


class CipherTests(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key()
        self.org, self.binding = uuid4(), uuid4()
        self.cipher = GatewayCipher(self.key, policy=policy(LISTED, OTHER))

    def record(self, endpoint=LISTED, cipher=None):
        sealed = (cipher or self.cipher).seal(self.org, self.binding, 1, KEY, endpoint)
        return GatewayRecord(1, self.binding, endpoint, sealed)

    def test_ciphertext_binds_the_endpoint_and_open_key_exposes_it(self):
        opened = self.cipher.open_key(self.org, self.record(LISTED))
        self.assertEqual(opened, KEY)
        self.assertEqual(opened.endpoint, LISTED)
        self.assertNotIn(KEY, repr(opened))
        self.assertEqual(self.cipher.open_key(self.org, self.record(OTHER)).endpoint, OTHER)

    def test_endpoint_substitution_in_the_record_fails_closed(self):
        from dataclasses import replace
        sealed_for_listed = self.record(LISTED)
        with self.assertRaises(GatewayUnavailable):
            self.cipher.verify(self.org, replace(sealed_for_listed, endpoint=OTHER))

    def test_seal_refuses_a_non_listed_endpoint(self):
        for endpoint in ('https://evil.example.net', LISTED + '/', None, 5):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                self.cipher.seal(self.org, self.binding, 1, KEY, endpoint)

    def test_open_rechecks_the_allow_list_at_call_time(self):
        record = self.record(LISTED)
        narrower = GatewayCipher(self.key, policy=policy(OTHER))
        with self.assertRaises(GatewayUnavailable):
            narrower.open_key(self.org, record)

    def test_legacy_cipher_still_seals_the_fixed_origin(self):
        legacy = GatewayCipher(self.key)
        sealed = legacy.seal(self.org, self.binding, 1, KEY)
        record = GatewayRecord(1, self.binding, GATEWAY_ENDPOINT, sealed)
        self.assertEqual(legacy.open_key(self.org, record).endpoint, GATEWAY_ENDPOINT)

    def test_a_cipher_policy_must_be_an_origin_policy(self):
        with self.assertRaises(ValueError):
            GatewayCipher(self.key, policy=frozenset({LISTED}))


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.org, self.token = uuid4(), secrets.token_urlsafe(32)
        self.store = Store()
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=policy(DEFAULT_ENDPOINT, LISTED))
        self.service = GatewayConfiguration(self.store, self.cipher)

    def test_save_with_an_allow_listed_endpoint_persists_and_reads_it_back(self):
        status = self.service.save(self.token, self.org, 0, KEY, endpoint=LISTED)
        self.assertEqual((status.status, status.revision, status.endpoint), ('SAVED_UNVERIFIED', 1, LISTED))
        self.assertEqual(self.store.saves, [LISTED])
        read = self.service.read(self.token, self.org)
        self.assertEqual(read.endpoint, LISTED)
        self.assertEqual(read.allowed_endpoints, tuple(sorted((DEFAULT_ENDPOINT, LISTED))))
        self.assertNotIn(KEY, repr(read))

    def test_non_listed_endpoint_creates_no_row_and_no_call(self):
        for endpoint in ('https://evil.example.net', LISTED + '.evil.net', LISTED + '/', 3):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                self.service.save(self.token, self.org, 0, KEY, endpoint=endpoint)
        self.assertEqual(self.store.records, {})

    def test_omitted_endpoint_keeps_the_fixed_default_and_legacy_store_shape(self):
        legacy_calls = []

        class LegacyStore(Store):
            def save(self, digest, org, expected, binding, encrypted):
                legacy_calls.append(1)
                return super().save(digest, org, expected, binding, encrypted)
        service = GatewayConfiguration(LegacyStore(), self.cipher)
        status = service.save(self.token, self.org, 0, KEY)
        self.assertEqual(status.endpoint, GATEWAY_ENDPOINT)
        self.assertEqual(legacy_calls, [1])

    def test_default_must_itself_be_allow_listed(self):
        service = GatewayConfiguration(self.store, GatewayCipher(Fernet.generate_key(), policy=policy(LISTED)))
        with self.assertRaises(ValueError):
            service.save(self.token, self.org, 0, KEY)
        self.assertEqual(self.store.records, {})

    def test_origin_change_requires_a_new_key_and_keeps_the_stored_config(self):
        self.service.save(self.token, self.org, 0, KEY, endpoint=LISTED)
        before = self.store.records[self.org]
        for key in (None, '', 'with space'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.service.save(self.token, self.org, 1, key, endpoint=DEFAULT_ENDPOINT)
        self.assertEqual(self.store.records[self.org], before)

    def test_unconfigured_status_lists_the_allowed_origins(self):
        status = self.service.read(self.token, self.org)
        self.assertEqual(status.status, 'NOT_CONFIGURED')
        self.assertEqual(status.endpoint, GATEWAY_ENDPOINT)
        self.assertEqual(status.allowed_endpoints, tuple(sorted((DEFAULT_ENDPOINT, LISTED))))

    def test_allowed_endpoints_property_is_the_policy_frozenset(self):
        self.assertEqual(self.service.allowed_endpoints, frozenset({DEFAULT_ENDPOINT, LISTED}))


def models_handler(seen):
    def handler(request):
        seen.append((str(request.url), request.headers['authorization']))
        return httpx.Response(200, json={'data': [{'id': 'private/a'}]})
    return handler


class CatalogAdapterOriginTests(unittest.IsolatedAsyncioTestCase):
    def sealed(self, endpoint):
        # A cipher bound to this exact endpoint, opened server-side like the real call path.
        org, binding = uuid4(), uuid4()
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=policy(endpoint, dev=endpoint.startswith('http:')))
        return org, GatewayRecord(1, binding, endpoint, self.cipher.seal(org, binding, 1, KEY, endpoint))

    async def test_requests_go_only_to_the_record_origin(self):
        seen = []
        org, record = self.sealed(LISTED)
        key = self.cipher.open_key(org, record)
        adapter = HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(seen)), policy=policy(LISTED))
        self.assertEqual(await adapter.discover_async(key), ('private/a',))
        self.assertEqual(seen, [(LISTED + '/v1/models', 'Bearer ' + KEY)])

    async def test_adapter_denies_a_record_origin_outside_its_own_allow_list(self):
        seen = []
        org, record = self.sealed(LISTED)
        key = self.cipher.open_key(org, record)
        adapter = HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(seen)), policy=policy(OTHER))
        with self.assertRaises(GatewayUnavailable) as caught:
            await adapter.discover_async(key)
        self.assertEqual(seen, [])
        self.assertNotIn(KEY, str(caught.exception))

    async def test_a_plain_key_still_means_the_fixed_origin(self):
        seen = []
        adapter = HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(seen)))
        await adapter.discover_async(KEY)
        self.assertEqual(seen[0][0], GATEWAY_ENDPOINT + '/v1/models')
        narrow = HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(seen)), policy=policy(LISTED))
        with self.assertRaises(GatewayUnavailable):
            await narrow.discover_async(KEY)
        self.assertEqual(len(seen), 1)

    async def test_cross_origin_redirect_is_not_followed(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={'location': 'https://attacker.invalid/v1/models'})
        org, record = self.sealed(LISTED)
        adapter = HttpxModelsAdapter(transport=httpx.MockTransport(handler), policy=policy(LISTED))
        with self.assertRaises(GatewayUnavailable):
            await adapter.discover_async(self.cipher.open_key(org, record))
        self.assertEqual(seen, [LISTED + '/v1/models'])

    async def test_tenant_isolation_each_org_reaches_only_its_origin_with_its_key(self):
        seen = []
        both = policy(LISTED, LOOPBACK, dev=True)
        cipher = GatewayCipher(Fernet.generate_key(), policy=both)
        org_a, org_b, binding_a, binding_b = uuid4(), uuid4(), uuid4(), uuid4()
        records = {
            org_a: GatewayRecord(1, binding_a, LISTED, cipher.seal(org_a, binding_a, 1, 'key-of-org-a', LISTED)),
            org_b: GatewayRecord(1, binding_b, LOOPBACK, cipher.seal(org_b, binding_b, 1, 'key-of-org-b', LOOPBACK)),
        }
        store = MagicMock()
        store.gateway.side_effect = lambda digest, org: records[org]
        catalog = GatewayCatalog(store, cipher,
            HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(seen)), policy=both))
        await catalog.refresh_async(secrets.token_urlsafe(32), org_a)
        await catalog.refresh_async(secrets.token_urlsafe(32), org_b)
        self.assertEqual(seen, [(LISTED + '/v1/models', 'Bearer key-of-org-a'),
                                (LOOPBACK + '/v1/models', 'Bearer key-of-org-b')])

    async def test_discovery_against_the_fake_gateway_on_an_allow_listed_loopback_origin(self):
        gateway = create_fake_gateway(FakeGatewayConfiguration(keys=(KEY,), port=3413))
        subject = policy(LOOPBACK, dev=True)
        org, binding = uuid4(), uuid4()
        cipher = GatewayCipher(Fernet.generate_key(), policy=subject)
        key = cipher.open_key(org, GatewayRecord(1, binding, LOOPBACK, cipher.seal(org, binding, 1, KEY, LOOPBACK)))
        adapter = HttpxModelsAdapter(transport=httpx.ASGITransport(app=gateway.app), policy=subject)
        self.assertEqual(await adapter.discover_async(key), tuple(sorted(MODELS)))
        self.assertEqual([record.authorization for record in gateway.records], ['Bearer ' + KEY])


class InferenceAdapterOriginTests(unittest.IsolatedAsyncioTestCase):
    REQUEST = TextRequest('assistant', (('user', 'Hello'),))

    def bound_key(self, endpoint, subject):
        org, binding = uuid4(), uuid4()
        cipher = GatewayCipher(Fernet.generate_key(), policy=subject)
        return cipher.open_key(org, GatewayRecord(1, binding, endpoint, cipher.seal(org, binding, 1, KEY, endpoint)))

    async def test_stream_goes_to_the_record_origin_and_normalizes(self):
        gateway = create_fake_gateway(FakeGatewayConfiguration(keys=(KEY,), port=3413))
        subject = policy(LOOPBACK, dev=True)
        adapter = HttpxTextAdapter(transport=httpx.ASGITransport(app=gateway.app), policy=subject)
        events = [item async for item in adapter.events(self.bound_key(LOOPBACK, subject), 'fake-fast', self.REQUEST)]
        self.assertEqual(events[-1], ('finish', 'stop'))
        self.assertEqual(''.join(value for kind, value in events if kind == 'text'), 'This is a fake gateway reply.')
        self.assertEqual([(record.path, record.authorization) for record in gateway.records],
                         [('/v1/chat/completions', 'Bearer ' + KEY)])

    async def test_request_url_is_the_record_origin(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(500)
        subject = policy(LISTED)
        adapter = HttpxTextAdapter(transport=httpx.MockTransport(handler), policy=subject)
        with self.assertRaises(GatewayUnavailable):
            [item async for item in adapter.events(self.bound_key(LISTED, subject), 'x', self.REQUEST)]
        self.assertEqual(seen, [LISTED + '/v1/chat/completions'])

    async def test_adapter_denies_an_origin_outside_its_allow_list_without_a_request(self):
        seen = []

        def handler(request):
            seen.append(1)
            return httpx.Response(200)
        key = self.bound_key(LISTED, policy(LISTED))
        adapter = HttpxTextAdapter(transport=httpx.MockTransport(handler), policy=policy(OTHER))
        with self.assertRaises(GatewayUnavailable) as caught:
            [item async for item in adapter.events(key, 'x', self.REQUEST)]
        self.assertEqual(seen, [])
        self.assertNotIn(KEY, str(caught.exception))

    async def test_cross_origin_redirect_is_not_followed(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(307, headers={'location': 'https://attacker.invalid/v1/chat/completions'})
        subject = policy(LISTED)
        adapter = HttpxTextAdapter(transport=httpx.MockTransport(handler), policy=subject)
        with self.assertRaises(GatewayUnavailable):
            [item async for item in adapter.events(self.bound_key(LISTED, subject), 'x', self.REQUEST)]
        self.assertEqual(seen, [LISTED + '/v1/chat/completions'])


class GatewayApiOriginTests(unittest.TestCase):
    def fixture(self, subject=None):
        identity = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
        sessions = MagicMock()
        sessions.validate.return_value = identity
        readiness = MagicMock()
        readiness.check.return_value = True
        authorization = MagicMock()
        authorization.read.return_value = AuthorizationSnapshot(
            identity, UUID(ORG), uuid4(), 1, frozenset({'organization_admin'}), MembershipStatus.ACTIVE, True)
        store = Store()
        service = GatewayConfiguration(store, GatewayCipher(Fernet.generate_key(),
                                                            policy=subject or policy(DEFAULT_ENDPOINT, LISTED)))
        client = TestClient(create_account_app(sessions=sessions, readiness=readiness,
            authorization_reader=authorization, gateway_configuration=service), raise_server_exceptions=False)
        return client, store, {'Authorization': 'Bearer ' + 'A' * 43}

    url = '/forge/v1/orgs/' + ORG + '/gateway'

    def test_put_with_an_allow_listed_endpoint_echoes_it_and_never_the_key(self):
        client, store, headers = self.fixture()
        with client:
            response = client.put(self.url, headers=headers,
                                  json={'expected_revision': 0, 'api_key': KEY, 'endpoint': LISTED})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'status': 'SAVED_UNVERIFIED', 'revision': 1, 'endpoint': LISTED})
            self.assertNotIn(KEY, response.text)
            self.assertEqual(store.saves, [LISTED])

    def test_put_without_endpoint_keeps_the_fixed_default(self):
        client, store, headers = self.fixture()
        with client:
            response = client.put(self.url, headers=headers, json={'expected_revision': 0, 'api_key': KEY})
            self.assertEqual(response.json()['endpoint'], DEFAULT_ENDPOINT)

    def test_non_listed_or_malformed_endpoint_is_422_and_stores_nothing(self):
        client, store, headers = self.fixture()
        with client:
            for endpoint in ('https://evil.example.net', LISTED + '.evil.net', LISTED + '/', 7, ['x'], '', 'x' * 300):
                with self.subTest(endpoint=endpoint):
                    response = client.put(self.url, headers=headers,
                        json={'expected_revision': 0, 'api_key': KEY, 'endpoint': endpoint})
                    self.assertEqual(response.status_code, 422)
                    self.assertNotIn(KEY, response.text)
        self.assertEqual(store.records, {})

    def test_origin_change_without_a_key_is_rejected_and_unchanged(self):
        client, store, headers = self.fixture()
        with client:
            client.put(self.url, headers=headers, json={'expected_revision': 0, 'api_key': KEY, 'endpoint': LISTED})
            before = store.records[UUID(ORG)]
            response = client.put(self.url, headers=headers, json={'expected_revision': 1, 'endpoint': DEFAULT_ENDPOINT})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(store.records[UUID(ORG)], before)

    def test_get_adds_allowed_endpoints_and_still_hides_the_key(self):
        client, store, headers = self.fixture()
        with client:
            empty = client.get(self.url, headers=headers).json()
            self.assertEqual(empty, {'status': 'NOT_CONFIGURED', 'revision': 0, 'endpoint': DEFAULT_ENDPOINT,
                                     'allowed_endpoints': sorted((DEFAULT_ENDPOINT, LISTED))})
            client.put(self.url, headers=headers, json={'expected_revision': 0, 'api_key': KEY, 'endpoint': LISTED})
            saved = client.get(self.url, headers=headers)
            self.assertEqual(saved.json()['endpoint'], LISTED)
            self.assertNotIn(KEY, saved.text)

    def test_unknown_fields_remain_forbidden(self):
        client, store, headers = self.fixture()
        with client:
            response = client.put(self.url, headers=headers,
                json={'expected_revision': 0, 'api_key': KEY, 'url': LISTED})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(store.records, {})

class StoreStatementTests(unittest.TestCase):
    """Statement selection only; the real function arrives with migration 0019."""
    def store(self, row):
        from psycopg.pq import TransactionStatus
        from forge.gateway_configuration_store import PostgresGatewayStore
        pool, connection = MagicMock(), MagicMock()
        connection.autocommit = True
        connection.info.transaction_status = TransactionStatus.IDLE
        pool.connection.return_value.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [(True,), row]
        return PostgresGatewayStore(pool), cursor

    def test_default_endpoint_keeps_the_original_five_argument_function(self):
        binding = uuid4()
        store, cursor = self.store((1, binding, GATEWAY_ENDPOINT, 'c'))
        store.save('d', uuid4(), 0, binding, 'c')
        statement = cursor.execute.call_args.args[0]
        self.assertEqual(statement.count('%s'), 5)
        self.assertEqual(len(cursor.execute.call_args.args[1]), 5)

    def test_explicit_endpoint_uses_the_six_argument_function(self):
        binding, org = uuid4(), uuid4()
        store, cursor = self.store((1, binding, LOOPBACK, 'c'))
        record = store.save('d', org, 0, binding, 'c', endpoint=LOOPBACK)
        statement, values = cursor.execute.call_args.args
        self.assertEqual(statement.count('%s'), 6)
        self.assertEqual(values, ('d', org, 0, binding, 'c', LOOPBACK))
        self.assertEqual(record.endpoint, LOOPBACK)

if __name__ == '__main__':
    unittest.main()
