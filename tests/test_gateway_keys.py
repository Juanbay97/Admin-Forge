"""Gateway key pool: the v2 sealed format binds the key id, revision and origin; the service seals before the store sees
anything, checks the origin against the deployment allow-list and never returns key text."""
from pathlib import Path
import sys
import unittest
from uuid import UUID, uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher, GatewayRecord, GatewayUnavailable
from forge.gateway_keys import GatewayKeyInfo, GatewayKeys, KeyAssignment
from forge.gateway_origins import DEFAULT_ENDPOINT, OriginPolicy
from forge.platform import PlatformInvalid

OTHER = 'https://other-gateway.fixture.example'
KEY = 'pool-fixture-key-ABCD'
ORG = UUID('00000000-0000-4000-8000-0000000000a1')
BINDING = UUID('00000000-0000-4000-8000-0000000000b1')
TOKEN = 'A' * 43


class PoolStore:
    def __init__(self):
        self.calls, self.rows = [], {}

    def info(self, key_id):
        row = self.rows[key_id]
        return GatewayKeyInfo(key_id, row['label'], row['origin'], row['revision'], row['status'], row['sealed'] is not None, row['hint'], 0)

    def create(self, digest, key_id, label, origin, sealed, hint):
        self.calls.append(('create', digest, key_id, label, origin, sealed, hint))
        self.rows[key_id] = {'label': label, 'origin': origin, 'revision': 1, 'status': 'active', 'sealed': sealed, 'hint': hint}
        return self.info(key_id)

    def keys(self, digest):
        return [self.info(key_id) for key_id in self.rows]

    def rotate(self, digest, key_id, expected, sealed, hint):
        self.calls.append(('rotate', digest, key_id, expected, sealed, hint))
        self.rows[key_id].update(revision=expected + 1, sealed=sealed, hint=hint)
        return self.info(key_id)

    def set_status(self, digest, key_id, active):
        self.calls.append(('set_status', key_id, active))
        self.rows[key_id]['status'] = 'active' if active else 'disabled'
        return self.info(key_id)

    def assign(self, digest, org, entries):
        self.calls.append(('assign', org, entries))
        return [KeyAssignment(key_id, 'l', 'o', priority, active, 'active', True) for key_id, priority, active in entries]

    def assignments(self, digest, org):
        return []

    def ceiling(self, digest, org):
        return ['m1']

    def set_ceiling(self, digest, org, models):
        self.calls.append(('ceiling', org, models))
        return models


def record_for(store, key_id, *, key_revision=None):
    row = store.rows[key_id]
    return GatewayRecord(1, BINDING, row['origin'], row['sealed'], key_id, row['revision'] if key_revision is None else key_revision)


class PooledCipherTests(unittest.TestCase):
    def setUp(self):
        self.policy = OriginPolicy(frozenset({DEFAULT_ENDPOINT, OTHER}))
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=self.policy)

    def test_a_sealed_pool_key_opens_to_the_key_bound_to_its_origin(self):
        key_id = uuid4()
        sealed = self.cipher.seal_pooled(key_id, 1, KEY, OTHER)
        opened = self.cipher.open_key(ORG, GatewayRecord(3, BINDING, OTHER, sealed, key_id, 1))
        self.assertEqual((opened, opened.endpoint), (KEY, OTHER))
        self.assertNotIn(KEY, sealed)

    def test_any_drift_of_key_id_revision_origin_or_ciphertext_is_unavailable(self):
        key_id = uuid4()
        sealed = self.cipher.seal_pooled(key_id, 2, KEY, OTHER)
        base = (3, BINDING, OTHER, sealed, key_id, 2)
        drifts = {'moved to another key id': base[:4] + (uuid4(), 2), 'other revision': base[:5] + (3,),
                  'other origin': (3, BINDING, DEFAULT_ENDPOINT, sealed, key_id, 2),
                  'tampered': (3, BINDING, OTHER, sealed[:-4] + 'AAAA', key_id, 2)}
        self.assertEqual(self.cipher.open_key(ORG, GatewayRecord(*base)), KEY)
        for name, fields in drifts.items():
            with self.subTest(name):
                with self.assertRaises(GatewayUnavailable):
                    self.cipher.open_key(ORG, GatewayRecord(*fields))

    def test_the_organization_binding_of_the_legacy_format_still_rules_legacy_records_only(self):
        binding = uuid4()
        legacy = self.cipher.seal(ORG, binding, 1, KEY)
        self.assertEqual(self.cipher.open_key(ORG, GatewayRecord(1, binding, DEFAULT_ENDPOINT, legacy)), KEY)
        with self.assertRaises(GatewayUnavailable):
            self.cipher.open_key(uuid4(), GatewayRecord(1, binding, DEFAULT_ENDPOINT, legacy))
        key_id = uuid4()
        pooled = self.cipher.seal_pooled(key_id, 1, KEY, OTHER)
        with self.assertRaises(GatewayUnavailable):  # a v2 value is never accepted as a legacy record
            self.cipher.open_key(ORG, GatewayRecord(1, binding, OTHER, pooled))

    def test_a_pool_seal_refuses_a_disallowed_origin_and_bad_arguments(self):
        for arguments in ((uuid4(), 1, KEY, 'https://evil.example'), (uuid4(), 0, KEY, OTHER), ('not-a-uuid', 1, KEY, OTHER),
                          (uuid4(), 1, 'has space', OTHER)):
            with self.subTest(arguments=arguments[1:]):
                with self.assertRaises(Exception):
                    self.cipher.seal_pooled(*arguments)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.policy = OriginPolicy(frozenset({DEFAULT_ENDPOINT, OTHER}))
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=self.policy)
        self.store = PoolStore()
        self.service = GatewayKeys(self.store, self.cipher)

    def test_create_seals_before_the_store_and_the_result_never_carries_the_key(self):
        info = self.service.create(TOKEN, 'primary', OTHER, KEY)
        (_, digest, key_id, label, origin, sealed, hint), = self.store.calls
        self.assertEqual((label, origin, hint, info.hint, info.has_key, info.revision), ('primary', OTHER, 'ABCD', 'ABCD', True, 1))
        self.assertNotIn(KEY, repr(self.store.calls) + repr(info))
        self.assertNotEqual(digest, TOKEN, 'the store receives the digest, never the capability')
        self.assertEqual(self.cipher.open_key(ORG, record_for(self.store, key_id)), KEY)

    def test_a_placeholder_key_stores_no_sealed_value_and_a_disallowed_origin_stores_nothing(self):
        info = self.service.create(TOKEN, 'spare', DEFAULT_ENDPOINT, None)
        self.assertEqual((info.has_key, self.store.calls[0][5:]), (False, (None, None)))
        before = list(self.store.calls)
        for origin in ('https://evil.example', 'http://127.0.0.1:1', OTHER + '/'):
            with self.subTest(origin=origin), self.assertRaises(PlatformInvalid):
                self.service.create(TOKEN, 'bad', origin, KEY)
        self.assertEqual(self.store.calls, before)

    def test_rotate_binds_the_new_value_to_the_next_revision_and_the_key_origin(self):
        info = self.service.create(TOKEN, 'primary', OTHER, KEY)
        rotated = self.service.rotate(TOKEN, info.id, 1, 'second-fixture-key-WXYZ')
        self.assertEqual((rotated.revision, rotated.hint), (2, 'WXYZ'))
        record = record_for(self.store, info.id)
        self.assertEqual(self.cipher.open_key(ORG, record), 'second-fixture-key-WXYZ')
        with self.assertRaises(GatewayUnavailable):
            self.cipher.open_key(ORG, record_for(self.store, info.id, key_revision=1))
        with self.assertRaises(PlatformInvalid):
            self.service.rotate(TOKEN, uuid4(), 1, KEY)

    def test_assignment_entries_are_validated_before_the_store(self):
        k1, k2 = uuid4(), uuid4()
        self.service.assign(TOKEN, ORG, [(k1, 2, True), (k2, 1, False)])
        self.assertEqual(self.store.calls[-1], ('assign', ORG, [(k1, 2, True), (k2, 1, False)]))
        before = len(self.store.calls)
        for entries in ([(k1, 0, True)], [(k1, 1001, True)], [(k1, True, True)], [(k1, 1, 'yes')], [('x', 1, True)], [(k1, 1, True)] * 17,
                        [(k1, 1, True), (k2, 1, True)], [(k1, 1, True), (k1, 2, True)], 'text'):
            with self.subTest(entries=repr(entries)[:30]), self.assertRaises(PlatformInvalid):
                self.service.assign(TOKEN, ORG, entries)
        self.assertEqual(len(self.store.calls), before)

    def test_the_ceiling_is_a_distinct_bounded_list_of_upstream_ids(self):
        self.assertEqual(self.service.set_ceiling(TOKEN, ORG, ['gpt-a', 'gpt-b']), ['gpt-a', 'gpt-b'])
        self.assertEqual(self.service.set_ceiling(TOKEN, ORG, []), [])
        for models in (['gpt-a', 'gpt-a'], ['has space'], [''], ['x' * 256], [1], 'gpt-a', ['m%d' % number for number in range(501)]):
            with self.subTest(models=repr(models)[:30]), self.assertRaises(PlatformInvalid):
                self.service.set_ceiling(TOKEN, ORG, models)


if __name__ == '__main__':
    unittest.main()
