"""Owned PostgreSQL 0033: pool routing and the catalog rebinding.

A company that published a catalog on the legacy single key keeps it CURRENT through the upgrade (the backfilled profile
carries the old binding and revision); after that, rotating, reordering or disabling pool keys never stales a catalog,
routing lists the active keys by priority, a ceiling shrink denies the next request and publishing outside the ceiling is
refused.
"""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import httpx
from cryptography.fernet import Fernet
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.gateway_catalog import GatewayCatalog
from forge.gateway_catalog_adapter import HttpxModelsAdapter
from forge.gateway_catalog_store import PostgresGatewayCatalogStore
from forge.gateway_configuration import GatewayCipher, GatewayConfiguration, GatewayDenied, GatewayUnavailable
from forge.gateway_configuration_store import PostgresGatewayStore
from forge.gateway_keys import GatewayKeys
from forge.gateway_keys_store import PostgresGatewayKeyStore
from forge.gateway_origins import DEFAULT_ENDPOINT
from forge.gateway_pool_store import PostgresPoolCatalogStore, PostgresPoolInferenceStore
from forge.invitations import capability_digest
from forge.mvp_profile import F32, F33, GATEWAY_KEY_ROUTING_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

LEGACY, ONE, TWO = 'legacy-fixture-key-L000', 'pool-fixture-key-ONE1', 'pool-fixture-key-TWO2'
MODELS = ['upstream/private-a', 'upstream/private-b']


def models_handler(expected_key):
    def handler(request):
        assert request.headers['authorization'] == 'Bearer ' + expected_key[0], 'the discovery key is the served key'
        return httpx.Response(200, json={'data': [{'id': name} for name in MODELS]})
    return handler


class RoutingProfileTests(unittest.TestCase):
    def test_0033_follows_0032_with_its_own_pinned_checkpoint(self):
        self.assertEqual(GATEWAY_KEY_ROUTING_MIGRATION, '0033_gateway_key_routing.sql')
        self.assertEqual(MVP_ADDITIONS[at(GATEWAY_KEY_ROUTING_MIGRATION) - 1], '0032_gateway_key_pool.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(GATEWAY_KEY_ROUTING_MIGRATION):at(GATEWAY_KEY_ROUTING_MIGRATION) + 2], (F32, F33))
        self.assertRegex(F33 or '', r'^[0-9a-f]{64}$', 'F33 must be pinned')
        self.assertNotEqual(F33, F32)


class RoutingFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0032_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_KEY_ROUTING_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, GATEWAY_KEY_ROUTING_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F32)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(GATEWAY_KEY_ROUTING_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0033 gateway key routing checkpoint F33:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0032 must be identical')
        self.assertEqual(fresh, F33, 'F33 must be pinned to the reviewed value')


class World(unittest.TestCase):
    def build(self, db):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.org_a, self.org_b = results[0].organization_id, results[1].organization_id
        self.admin_a, self.member_a = results[0].accounts[0], results[0].accounts[1]
        self.admin_b = results[1].accounts[0]
        self.cipher = GatewayCipher(Fernet.generate_key())
        self.served = [LEGACY]
        gateway = db.pool('forge_gateway_service')
        self.legacy = GatewayConfiguration(PostgresGatewayStore(gateway), self.cipher)
        adapter = HttpxModelsAdapter(transport=httpx.MockTransport(models_handler(self.served)))
        self.old_catalog = GatewayCatalog(PostgresGatewayCatalogStore(gateway), self.cipher, adapter)
        self.catalog = GatewayCatalog(PostgresPoolCatalogStore(gateway), self.cipher, adapter)
        self.routes = PostgresPoolInferenceStore(gateway)
        self.keys = GatewayKeys(PostgresGatewayKeyStore(db.pool('forge_platform_service')), self.cipher)
        self.admin_token, _ = sign_in(db, self.admin_a.email, self.admin_a.password)
        self.member_token, _ = sign_in(db, self.member_a.email, self.member_a.password)

    def owner(self):
        add_owner(self.db.admin)
        self.owner_token, _ = sign_in(self.db, mfa=True)

    def publish(self, catalog, org, token, expected, revision, mapping=None):
        mapping = mapping or {'assistant': MODELS[0], 'fast': MODELS[1]}
        return catalog.publish(token, org, uuid4(), expected, revision, mapping, 'assistant')

    def route(self, alias='assistant', token=None, org=None):
        return self.routes.resolve(capability_digest(token or self.member_token), org or self.org_a, alias)

    def status(self, org=None, token=None):
        return self.catalog.admin_status(token or self.admin_token, org or self.org_a)['publication_state']


class UpgradeTests(World):
    def test_a_catalog_published_on_the_legacy_key_stays_current_through_the_upgrade_and_keeps_routing(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_KEY_ROUTING_MIGRATION)])
        with mvp_database(migrations=previous) as db:
            self.build(db)
            saved = self.legacy.save(self.admin_token, self.org_a, 0, LEGACY)
            self.old_catalog.refresh(self.admin_token, self.org_a)
            self.publish(self.old_catalog, self.org_a, self.admin_token, 0, saved.revision)
            self.assertEqual(self.old_catalog.admin_status(self.admin_token, self.org_a)['publication_state'], 'CURRENT')
            binding = db.admin.execute('SELECT binding_id FROM forge.organization_gateways WHERE organization_id=%s', (self.org_a,)).fetchone()[0]
            snapshots = db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone()
            db.admin.execute(migration_text(GATEWAY_KEY_ROUTING_MIGRATION))
            self.assertEqual(db.admin.execute('SELECT revision,binding_id,ceiling FROM forge.organization_gateway_profiles WHERE organization_id=%s',
                                              (self.org_a,)).fetchone(), (1, binding, None), 'the profile carries the legacy binding; no ceiling yet')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(), snapshots, 'no snapshot is rewritten')
            self.assertEqual(self.status(), 'CURRENT')
            self.assertEqual(self.catalog.read(self.member_token, self.org_a)['default_model'], 'assistant')
            route = self.route()
            self.assertEqual((route.upstream_id, route.gateway.key_id, route.fallbacks, route.gateway.binding_id), (MODELS[0], None, (), binding))
            self.assertEqual(self.cipher.open_key(self.org_a, route.gateway), LEGACY)
            self.assertEqual(self.status(org=self.org_b, token=sign_in(db, self.admin_b.email, self.admin_b.password)[0]), 'UNPUBLISHED')
            with self.assertRaises(GatewayDenied):
                self.route(org=self.org_b)


class PoolRoutingTests(World):
    def setup_pool(self, db):
        self.build(db)
        self.owner()
        self.k1 = self.keys.create(self.owner_token, 'one', DEFAULT_ENDPOINT, ONE)
        self.k2 = self.keys.create(self.owner_token, 'two', DEFAULT_ENDPOINT, TWO)
        self.keys.assign(self.owner_token, self.org_a, [(self.k1.id, 2, True), (self.k2.id, 1, True)])
        self.keys.set_ceiling(self.owner_token, self.org_a, MODELS)
        self.served[0] = TWO  # discovery uses the lowest-priority key
        self.catalog.refresh(self.admin_token, self.org_a)
        self.publish(self.catalog, self.org_a, self.admin_token, 0, 1)

    def candidates(self):
        route = self.route()
        return [(record.key_id, record.key_revision, str(self.cipher.open_key(self.org_a, record))) for record in route.candidates]

    def test_a_company_without_legacy_publishes_on_the_pool_and_routes_every_active_key_by_priority(self):
        with mvp_database() as db:
            self.setup_pool(db)
            self.assertEqual(self.status(), 'CURRENT')
            self.assertEqual(self.candidates(), [(self.k2.id, 1, TWO), (self.k1.id, 1, ONE)])
            self.assertEqual(self.route('fast').upstream_id, MODELS[1])
            self.assertEqual(self.catalog.read(self.member_token, self.org_a)['default_model'], 'assistant')

    def test_rotation_reorder_and_disabling_never_stale_the_catalog_and_disabled_keys_are_never_selected(self):
        with mvp_database() as db:
            self.setup_pool(db)
            self.keys.rotate(self.owner_token, self.k2.id, 1, 'rotated-fixture-key-R002')
            self.assertEqual((self.status(), self.candidates()[0]), ('CURRENT', (self.k2.id, 2, 'rotated-fixture-key-R002')))
            self.keys.assign(self.owner_token, self.org_a, [(self.k1.id, 1, True), (self.k2.id, 2, True)])
            self.assertEqual((self.status(), [item[0] for item in self.candidates()]), ('CURRENT', [self.k1.id, self.k2.id]))
            self.keys.set_status(self.owner_token, self.k1.id, False)
            self.assertEqual([item[0] for item in self.candidates()], [self.k2.id])
            self.keys.assign(self.owner_token, self.org_a, [(self.k1.id, 1, True), (self.k2.id, 2, False)])
            with self.assertRaises(GatewayDenied):
                self.route()  # every assigned key is disabled or inactive: nothing is selected
            self.assertEqual(self.status(), 'CURRENT')
            placeholder = self.keys.create(self.owner_token, 'spare', DEFAULT_ENDPOINT, None)
            self.keys.assign(self.owner_token, self.org_a, [(placeholder.id, 1, True)])
            with self.assertRaises(GatewayDenied):
                self.route()  # a key without a sealed value is never routed

    def test_a_ceiling_shrink_denies_the_next_request_and_publishing_outside_it_is_refused_unchanged(self):
        with mvp_database() as db:
            self.setup_pool(db)
            self.assertEqual(self.route().upstream_id, MODELS[0])
            self.keys.set_ceiling(self.owner_token, self.org_a, [MODELS[1]])
            with self.assertRaises(GatewayDenied):
                self.route('assistant')
            self.assertEqual(self.route('fast').upstream_id, MODELS[1], 'models still inside the ceiling keep working')
            with self.assertRaises(GatewayDenied):
                self.publish(self.catalog, self.org_a, self.admin_token, 1, 1, {'assistant': MODELS[0]})
            self.assertEqual(db.admin.execute('SELECT catalog_revision FROM forge.active_model_catalogs WHERE organization_id=%s', (self.org_a,)).fetchone(), (1,),
                             'the existing snapshot is unchanged')
            self.assertEqual(self.publish(self.catalog, self.org_a, self.admin_token, 1, 1, {'assistant': MODELS[1]})['revision'], 2)
            self.keys.set_ceiling(self.owner_token, self.org_a, [])
            with self.assertRaises(GatewayDenied):
                self.route('assistant')

    def test_another_company_cannot_route_use_or_read_the_pool_assignment_of_this_one(self):
        with mvp_database() as db:
            self.setup_pool(db)
            outsider, _ = sign_in(db, self.admin_b.email, self.admin_b.password)
            with self.assertRaises(GatewayDenied):
                self.route(token=outsider, org=self.org_a)
            with self.assertRaises(GatewayDenied):
                self.route(token=outsider, org=self.org_b)
            with self.assertRaises((GatewayDenied, GatewayUnavailable)):
                self.catalog.refresh(outsider, self.org_a)
            with db.pool('forge_gateway_service').connection() as connection:
                for table in ('gateway_keys', 'organization_gateway_keys', 'organization_gateway_profiles'):
                    with self.assertRaises(Exception):
                        connection.execute('SELECT * FROM forge.%s' % table).fetchall()

    def test_a_pool_that_is_assigned_but_empty_does_not_fall_back_to_a_backfilled_legacy_key(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_KEY_ROUTING_MIGRATION)])
        with mvp_database(migrations=previous) as db:
            self.build(db)
            saved = self.legacy.save(self.admin_token, self.org_a, 0, LEGACY)
            self.old_catalog.refresh(self.admin_token, self.org_a)
            self.publish(self.old_catalog, self.org_a, self.admin_token, 0, saved.revision)
            db.admin.execute(migration_text(GATEWAY_KEY_ROUTING_MIGRATION))
            self.assertEqual(self.cipher.open_key(self.org_a, self.route().gateway), LEGACY)
            self.owner()
            spare = self.keys.create(self.owner_token, 'spare', DEFAULT_ENDPOINT, None)
            self.keys.assign(self.owner_token, self.org_a, [(spare.id, 1, True)])
            with self.assertRaises(GatewayDenied):
                self.route()
            self.keys.assign(self.owner_token, self.org_a, [])
            self.assertEqual(self.cipher.open_key(self.org_a, self.route().gateway), LEGACY, 'no assignment at all: the legacy key still serves')


if __name__ == '__main__':
    unittest.main()
