"""Platform catalog service over fake ports: discovery reports a finite state per assigned key and stores the union; the
publication reuses the company snapshot code; nothing returned carries key text or a sealed value."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.gateway_catalog import publication_material, valid_selection
from forge.gateway_configuration import GatewayCipher, GatewayUnavailable
from forge.gateway_origins import OriginPolicy
from forge.model_catalog_store import decode_catalog
from forge.platform import PlatformInvalid, RevisionConflict
from forge.platform_catalog import CatalogKey, CatalogStatus, PlatformCatalog

ORIGIN = 'https://gateway.fixture.example'
TOKEN = 'A' * 43
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, rows=(), status=None):
        self.rows, self.state, self.saved, self.published = list(rows), status, [], []

    def keys(self, digest, org): return self.rows
    def status(self, digest, org): return self.state

    def save_discovery(self, digest, org, revision, binding, ids):
        self.saved.append((revision, binding, ids))
        return NOW

    def publish(self, digest, org, operation, expected, gateway_revision, binding, mapping, default, payload, checksum, selection):
        self.published.append((expected, gateway_revision, binding, mapping, default, payload, checksum, selection))
        return expected + 1


class FakeAdapter:
    def __init__(self, by_key):
        self.by_key, self.asked = by_key, []

    async def discover_async(self, key):
        self.asked.append(str(key))
        outcome = self.by_key[str(key)]
        if isinstance(outcome, Exception):
            raise outcome
        return tuple(outcome)


class World(unittest.TestCase):
    def setUp(self):
        self.org, self.binding = uuid4(), uuid4()
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=OriginPolicy(frozenset({ORIGIN})))

    def row(self, label, key=None, *, priority=1, active=True, status='active', revision=1):
        key_id = uuid4()
        sealed = None if key is None else self.cipher.seal_pooled(key_id, revision, key, ORIGIN)
        return CatalogKey(1, self.binding, key_id, label, ORIGIN, priority, active, status, revision, sealed)

    def service(self, store, adapter=None):
        return PlatformCatalog(store, self.cipher, adapter or FakeAdapter({}))

    def status(self, **change):
        values = dict(revision=1, binding_id=self.binding, ceiling=[], discovered=['m-a', 'm-b'], discovered_at=NOW,
                      catalogue_revision=0, default_alias=None, publication_state='UNPUBLISHED', mapping=None)
        values.update(change)
        return CatalogStatus(**values)


class DiscoveryTests(World):
    def test_every_key_gets_a_finite_state_and_the_union_of_the_reachable_ones_is_stored(self):
        good, other = self.row('primary', 'secret-ONE', priority=1), self.row('backup', 'secret-TWO', priority=2)
        down, off = self.row('flaky', 'secret-DOWN', priority=3), self.row('retired', 'secret-OFF', priority=4, status='disabled')
        unassigned, empty = self.row('idle', 'secret-IDLE', priority=5, active=False), self.row('placeholder', None, priority=6)
        adapter = FakeAdapter({'secret-ONE': ['m-a', 'm-b'], 'secret-TWO': ['m-b', 'm-c'], 'secret-DOWN': GatewayUnavailable()})
        store = FakeStore([good, other, down, off, unassigned, empty])
        result = asyncio.run(self.service(store, adapter).discover(TOKEN, self.org))
        self.assertEqual([(key['label'], key['state'], key['model_count']) for key in result['keys']],
                         [('primary', 'ok', 2), ('backup', 'ok', 2), ('flaky', 'unreachable', 0), ('retired', 'disabled', 0),
                          ('idle', 'inactive', 0), ('placeholder', 'no_key', 0)])
        self.assertEqual(result['model_ids'], ['m-a', 'm-b', 'm-c'])
        self.assertEqual(result['discovered_at'], NOW.isoformat())
        self.assertEqual(store.saved, [(1, self.binding, ['m-a', 'm-b', 'm-c'])])
        self.assertCountEqual(adapter.asked, ['secret-ONE', 'secret-TWO', 'secret-DOWN'], 'only active keys with a stored value are asked')
        self.assertNotIn('secret', repr(result))

    def test_when_no_key_answers_nothing_is_stored_and_every_state_is_reported(self):
        store = FakeStore([self.row('flaky', 'secret-DOWN')])
        result = asyncio.run(self.service(store, FakeAdapter({'secret-DOWN': GatewayUnavailable()})).discover(TOKEN, self.org))
        self.assertEqual((result['keys'][0]['state'], result['model_ids'], result['discovered_at'], store.saved), ('unreachable', [], None, []))

    def test_a_sealed_value_that_does_not_open_is_unreadable_not_an_error(self):
        broken = self.row('moved', 'secret-X')
        broken = CatalogKey(1, self.binding, broken.key_id, 'moved', ORIGIN, 1, True, 'active', 2, broken.encrypted_key)  # revision drift
        result = asyncio.run(self.service(FakeStore([broken])).discover(TOKEN, self.org))
        self.assertEqual(result['keys'][0]['state'], 'unreadable')

    def test_a_company_without_assignments_has_nothing_to_discover(self):
        result = asyncio.run(self.service(FakeStore([])).discover(TOKEN, self.org))
        self.assertEqual(result, {'keys': [], 'model_ids': [], 'discovered_at': None})

    def test_a_non_uuid_company_is_refused_before_any_store_call(self):
        store = FakeStore()
        with self.assertRaises(PlatformInvalid):
            asyncio.run(self.service(store).discover(TOKEN, 'not-a-uuid'))


class ReadAndPublishTests(World):
    def test_read_is_none_without_a_profile_and_projects_the_selection_otherwise(self):
        self.assertIsNone(self.service(FakeStore()).read(TOKEN, self.org))
        state = self.status(catalogue_revision=2, default_alias='fast', publication_state='CURRENT', mapping={'fast': 'm-a', 'deep': 'm-b'},
                            ceiling=['m-b', 'm-a'])
        read = self.service(FakeStore(status=state)).read(TOKEN, self.org)
        self.assertEqual(read, {'gateway_revision': 1, 'ceiling': ['m-a', 'm-b'],
                                'discovered': {'model_ids': ['m-a', 'm-b'], 'at': NOW.isoformat()},
                                'catalogue': {'revision': 2, 'default_model': 'fast', 'state': 'CURRENT', 'aliases': {'deep': 'm-b', 'fast': 'm-a'}}})

    def test_publish_builds_the_same_snapshot_the_company_flow_builds_and_binds_it_to_the_profile(self):
        store = FakeStore(status=self.status())
        operation, mapping = uuid4(), {'fast': 'm-a', 'deep': 'm-b'}
        result = self.service(store).publish(TOKEN, self.org, operation, 0, 1, mapping, 'fast')
        self.assertEqual(result, {'revision': 1, 'default_model': 'fast', 'models': ['deep', 'fast']})
        expected, gateway_revision, binding, sent, default, payload, checksum, selection = store.published[0]
        self.assertEqual((expected, gateway_revision, binding, sent, default), (0, 1, self.binding, mapping, 'fast'))
        self.assertEqual((payload, checksum, selection), publication_material(self.org, self.binding, 0, 1, mapping, 'fast'))
        snapshot = decode_catalog(payload, checksum)
        self.assertEqual((snapshot.organization_id, snapshot.router_binding_id, snapshot.revision), (self.org, self.binding, 1))
        self.assertEqual(sorted(alias.name for alias in snapshot.aliases), ['deep', 'fast'])

    def test_publish_refuses_a_model_that_was_not_discovered_and_a_stale_gateway_revision(self):
        store = FakeStore(status=self.status())
        with self.assertRaises(PlatformInvalid):
            self.service(store).publish(TOKEN, self.org, uuid4(), 0, 1, {'fast': 'never-seen'}, 'fast')
        with self.assertRaises(RevisionConflict):
            self.service(store).publish(TOKEN, self.org, uuid4(), 0, 2, {'fast': 'm-a'}, 'fast')
        with self.assertRaises(RevisionConflict):
            self.service(FakeStore()).publish(TOKEN, self.org, uuid4(), 0, 1, {'fast': 'm-a'}, 'fast')
        self.assertEqual(store.published, [])

    def test_publish_refuses_a_shape_the_company_flow_also_refuses(self):
        store = FakeStore(status=self.status())
        for mapping, default in (({}, 'x'), ({'Bad Alias': 'm-a'}, 'Bad Alias'), ({'fast': 'm-a'}, 'other'), ({'fast': 'has space'}, 'fast')):
            with self.subTest(mapping=mapping), self.assertRaises(PlatformInvalid):
                self.service(store).publish(TOKEN, self.org, uuid4(), 0, 1, mapping, default)
        self.assertFalse(valid_selection('not-a-uuid', 0, 1, {'fast': 'm-a'}, 'fast'))
        self.assertEqual(store.published, [])

    def test_publish_refuses_when_nothing_was_discovered_yet(self):
        store = FakeStore(status=self.status(discovered=None, discovered_at=None))
        with self.assertRaises(PlatformInvalid):
            self.service(store).publish(TOKEN, self.org, uuid4(), 0, 1, {'fast': 'm-a'}, 'fast')


if __name__ == '__main__':
    unittest.main()
