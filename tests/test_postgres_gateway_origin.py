"""Owned PostgreSQL 0019 per-organization gateway origin; no provider requests or real keys."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
import unittest
from unittest import mock
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import psycopg
from psycopg import errors, sql
import test_postgres_gateway_catalog as upstream
from postgres_support import (ORG_A, ORG_B, MEMBER_B, owned_gateway_catalog_admin_extension,
    settings, connect, wait_ready)
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS, PROFILE
from forge.gateway_configuration import (GatewayCipher, GatewayConfiguration, GatewayDenied,
    GATEWAY_ENDPOINT)
from forge.gateway_configuration_store import PostgresGatewayStore
from forge.gateway_origins import DEFAULT_ENDPOINT, OriginPolicy
from forge.invitations import capability_digest
from forge.mvp_profile import F19, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, ORIGIN_MIGRATION

LOOPBACK = 'http://127.0.0.1:3413'
KEY = 'fixture-only-central-gateway-key'
ROLES = ('forge_gateway_authority', 'forge_gateway_service', 'forge_account_service',
         'forge_enrollment_authority', 'forge_enrollment', 'forge_catalog_authority',
         'forge_config_publisher', 'forge_catalog_writer', 'forge_outbox_writer',
         'forge_designator', 'forge_identity_binder', 'forge_runtime', 'forge_migrator')


def migration_text(name):
    return (ROOT/'migrations'/name).read_text('utf-8')


class MvpProfileTests(unittest.TestCase):
    """No database: the retained demo profile must stay exactly as reviewed."""
    def test_retained_profile_is_not_mutated(self):
        self.assertEqual(len(ADDITIONS), 8)
        self.assertEqual(ADDITIONS[-1], '0018_gateway_catalog_admin_status.sql')
        self.assertEqual(PROFILE, '0001-0005+0010-0018/PG17')
        self.assertEqual(len(CHECKPOINTS), 9)

    def test_mvp_profile_appends_exactly_one_migration_and_checkpoint(self):
        # Later MVP migrations only append; this slice owns the 0019 position.
        self.assertEqual(MVP_ADDITIONS[:len(ADDITIONS) + 1], (*ADDITIONS, '0019_gateway_origin.sql'))
        self.assertEqual(MVP_CHECKPOINTS[:len(CHECKPOINTS) + 1], (*CHECKPOINTS, F19))
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))
        self.assertRegex(F19 or '', r'^[0-9a-f]{64}$', 'F19 must be pinned')


@contextmanager
def separate_database():
    """Exact scripts against a throwaway database inside this owned cluster only.

    Used before any shared fixture role exists (like the repository migration probes);
    the database and the roles it created are removed afterwards.
    """
    # A fresh container accepts TCP before its final server is up; gate tests run before any
    # shared fixture (which waits), so wait here or the first connection can be reset.
    wait_ready()
    name = 'forge_origin_' + uuid4().hex
    with connect() as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        with psycopg.connect(**(settings() | {'dbname': name})) as conn:
            yield conn
    finally:
        cleanup = settings() | {'options': '-c statement_timeout=30000 -c lock_timeout=2000'}
        with psycopg.connect(**cleanup) as admin:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
            for role in ROLES:
                admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


class SeparateDatabaseReadinessTests(unittest.TestCase):
    """No database: a fresh container accepts TCP before its final server is up, so the first
    connection of a gate test used to die with "server closed the connection unexpectedly"."""
    class Fake:
        def __init__(self, events):
            self.events = events

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query):
            self.events.append('execute')

    def patched(self, events, ready):
        module = sys.modules[__name__]

        def connect():
            events.append('connect')
            return self.Fake(events)
        return (mock.patch.object(module, 'wait_ready', ready),
                mock.patch.object(module, 'connect', connect),
                mock.patch.object(module, 'settings', lambda: {}),
                mock.patch.object(psycopg, 'connect', lambda **kwargs: self.Fake(events)))

    def test_it_waits_for_the_final_server_before_the_first_connection(self):
        events = []
        with ExitStack() as stack:
            for patch in self.patched(events, lambda: events.append('ready')):
                stack.enter_context(patch)
            with separate_database() as conn:
                self.assertIsInstance(conn, self.Fake)
        self.assertEqual(events[:3], ['ready', 'connect', 'execute'])

    def test_a_server_that_never_becomes_ready_creates_nothing(self):
        events = []

        def never():
            events.append('ready')
            raise RuntimeError('Owned local PostgreSQL did not become ready within 15 seconds')
        with ExitStack() as stack:
            for patch in self.patched(events, never):
                stack.enter_context(patch)
            with self.assertRaisesRegex(RuntimeError, 'did not become ready'):
                with separate_database():
                    self.fail('must not reach the body')
        self.assertEqual(events, ['ready'])


class FingerprintGateTests(unittest.TestCase):
    """A2b gate (runs before the shared-fixture class): fresh apply == upgrade from 0018."""
    def apply(self, conn, names):
        for name in names:
            conn.execute(migration_text(name))

    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0018_share_the_pinned_fingerprint(self):
        with separate_database() as conn:
            self.apply(conn, (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION))
            fresh = self.fingerprint(conn)
        with separate_database() as conn:
            self.apply(conn, (*MIGRATIONS, *ADDITIONS))
            self.assertEqual(self.fingerprint(conn), CHECKPOINTS[-1])
            # A legacy-origin row configured before 0019 must survive the upgrade untouched.
            admin_identity, organization = uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','legacy')",
                             (admin_identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'legacy','Legacy',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
            conn.execute("INSERT INTO forge.organization_gateways(organization_id,revision,binding_id,endpoint,"
                         "encrypted_key,updated_by) VALUES(%s,1,%s,'https://ia.prometheonlab.com',%s,%s)",
                         (organization, uuid4(), 'x'*120, admin_identity))
            before = conn.execute('SELECT * FROM forge.organization_gateways').fetchall()
            self.apply(conn, (ORIGIN_MIGRATION,))
            self.assertEqual(conn.execute('SELECT * FROM forge.organization_gateways').fetchall(), before)
            upgraded = self.fingerprint(conn)
        print('Reviewed PG17 0019 gateway-origin checkpoint F19:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0018 must be identical')
        self.assertEqual(fresh, F19, 'F19 must be pinned to the reviewed value')
        self.assertNotIn(fresh, CHECKPOINTS)


class PostgresGatewayOriginTests(unittest.TestCase):
    setUpClass = classmethod(upstream.PostgresGatewayCatalogTests.setUpClass.__func__)
    setUp = upstream.PostgresGatewayCatalogTests.setUp
    policy = OriginPolicy(frozenset({DEFAULT_ENDPOINT, LOOPBACK}), dev=True)

    @contextmanager
    def fixture(self, *, migrated=True):
        """0001-0018 shared fixture; 0019 is applied (and unwound) here unless deferred."""
        with upstream.PostgresGatewayCatalogTests.fixture(self) as values:
            admin = values[0]
            with owned_gateway_catalog_admin_extension(admin):
                applied = []
                try:
                    if migrated:
                        admin.execute(migration_text(ORIGIN_MIGRATION))
                        applied.append(True)
                    yield values
                finally:
                    if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                        admin.execute('ROLLBACK')
                    if admin.execute("SELECT to_regprocedure('forge.gateway_save(text,uuid,bigint,uuid,text,text)')").fetchone()[0]:
                        admin.execute('DROP FUNCTION forge.gateway_save(text,uuid,bigint,uuid,text,text)')

    def apply_origin(self, admin):
        admin.execute(migration_text(ORIGIN_MIGRATION))

    def service(self, pools, key):
        return GatewayConfiguration(PostgresGatewayStore(pools['forge_gateway_service']),
                                    GatewayCipher(key, policy=self.policy))

    def test_widened_check_accepts_only_default_or_numeric_loopback_with_port(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            service.save(token, ORG_A, 0, KEY)
            for good in (DEFAULT_ENDPOINT, 'http://127.0.0.1:1', LOOPBACK, 'http://127.0.0.1:65535'):
                with self.subTest(good=good):
                    admin.execute('UPDATE forge.organization_gateways SET endpoint=%s', (good,))
            for bad in ('http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:65536',
                        'http://127.0.0.1:03413', LOOPBACK + '/', 'http://127.0.0.1:3413 ',
                        'http://127.0.0.2:3413', 'http://localhost:3413', 'https://127.0.0.1:3413',
                        'https://evil.example.net', DEFAULT_ENDPOINT + '/', 'http://ia.prometheonlab.com'):
                with self.subTest(bad=bad), self.assertRaises(errors.CheckViolation):
                    admin.execute('UPDATE forge.organization_gateways SET endpoint=%s', (bad,))

    def test_function_refuses_non_allowed_origin_without_writing(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            cipher = GatewayCipher(key, policy=self.policy)
            binding = uuid4()
            sealed = cipher.seal(ORG_A, binding, 1, KEY, LOOPBACK)
            for bad in ('https://evil.example.net', 'http://127.0.0.1', None, LOOPBACK + '/'):
                with self.subTest(bad=bad), self.assertRaises(Exception) as caught:
                    store.save(capability_digest(token), ORG_A, 0, binding, sealed, endpoint=bad)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.organization_gateways').fetchone(), (0,))
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.gateway_configuration_audit').fetchone(), (0,))

    def test_save_with_endpoint_round_trips_and_key_binds_the_origin(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            service = self.service(pools, key)
            status = service.save(token, ORG_A, 0, KEY, endpoint=LOOPBACK)
            self.assertEqual((status.status, status.revision, status.endpoint), ('SAVED_UNVERIFIED', 1, LOOPBACK))
            self.assertEqual(service.read(token, ORG_A).endpoint, LOOPBACK)
            record = store.read(capability_digest(token), ORG_A)
            self.assertEqual(record.endpoint, LOOPBACK)
            opened = GatewayCipher(key, policy=self.policy).open_key(ORG_A, record)
            self.assertEqual((opened, opened.endpoint), (KEY, LOOPBACK))
            # A narrower allow-list refuses the stored origin at call time.
            narrow = GatewayCipher(key, policy=OriginPolicy(frozenset({DEFAULT_ENDPOINT})))
            with self.assertRaises(Exception):
                narrow.open_key(ORG_A, record)

    def test_five_argument_save_always_means_the_default_origin(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            service = self.service(pools, key)
            service.save(token, ORG_A, 0, KEY, endpoint=LOOPBACK)
            status = service.save(token, ORG_A, 1, KEY)
            self.assertEqual((status.revision, status.endpoint), (2, GATEWAY_ENDPOINT))
            record = store.read(capability_digest(token), ORG_A)
            self.assertEqual(record.endpoint, GATEWAY_ENDPOINT)
            GatewayCipher(key, policy=self.policy).verify(ORG_A, record)

    def test_existing_rows_survive_the_migration_and_stay_decryptable(self):
        with self.fixture(migrated=False) as (admin, pools, readers, sessions, token, store, service, ready, key):
            service.save(token, ORG_A, 0, KEY)
            before = admin.execute('SELECT * FROM forge.organization_gateways').fetchall()
            self.apply_origin(admin)
            self.assertEqual(admin.execute('SELECT * FROM forge.organization_gateways').fetchall(), before)
            record = store.read(capability_digest(token), ORG_A)
            self.assertEqual(GatewayCipher(key).open_key(ORG_A, record), KEY)
            # The legacy path keeps working on the migrated schema.
            self.assertEqual(service.save(token, ORG_A, 1, 'rotated-fixture-only').endpoint, GATEWAY_ENDPOINT)

    def test_tenant_isolation_of_origin(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (ORG_B, MEMBER_B))
            try:
                foreign = sessions.login('foreign@example.com', upstream.PASSWORD).capability
                service = self.service(pools, key)
                service.save(token, ORG_A, 0, KEY, endpoint=LOOPBACK)
                service.save(foreign, ORG_B, 0, 'other-fixture-key')
                self.assertEqual(service.read(token, ORG_A).endpoint, LOOPBACK)
                self.assertEqual(service.read(foreign, ORG_B).endpoint, DEFAULT_ENDPOINT)
                for actor, organization in ((token, ORG_B), (foreign, ORG_A)):
                    with self.assertRaises(GatewayDenied):
                        service.read(actor, organization)
                    with self.assertRaises(GatewayDenied):
                        service.save(actor, organization, 0, KEY, endpoint=LOOPBACK)
                self.assertEqual(sorted(admin.execute('SELECT organization_id,endpoint FROM forge.organization_gateways').fetchall()),
                                 sorted([(ORG_A, LOOPBACK), (ORG_B, DEFAULT_ENDPOINT)]))
            finally:
                admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s "
                              "AND role='organization_admin'", (ORG_B, MEMBER_B))

    def test_new_function_is_authority_owned_function_only_and_not_public(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            signature = 'forge.gateway_save(text,uuid,bigint,uuid,text,text)'
            owner, definer, config = admin.execute(
                'SELECT pg_get_userbyid(proowner),prosecdef,proconfig FROM pg_proc WHERE oid=%s::regprocedure',
                (signature,)).fetchone()
            self.assertEqual((owner, definer, config), ('forge_gateway_authority', True, ['search_path=pg_catalog']))
            for role, expected in (('forge_gateway_service', True), ('forge_account_service', False),
                                   ('forge_runtime', False), ('forge_enrollment', False)):
                self.assertEqual(admin.execute('SELECT has_function_privilege(%s,%s,%s)',
                                               (role, signature, 'EXECUTE')).fetchone(), (expected,), role)
            self.assertEqual(admin.execute('SELECT has_function_privilege(%s,%s,%s)',
                                           ('public', signature, 'EXECUTE')).fetchone(), (False,))
            self.assertEqual(admin.execute("SELECT has_schema_privilege('forge_gateway_authority','forge','CREATE')").fetchone(),
                             (False,))
            with pools['forge_account_service'].connection() as connection:
                with self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute('SELECT * FROM forge.gateway_save(%s,%s,%s,%s,%s,%s)',
                                       ('d', ORG_A, 0, uuid4(), 'x'*120, LOOPBACK))
                connection.rollback()

    def test_failed_migration_rolls_back_to_the_reviewed_0018_profile(self):
        with self.fixture(migrated=False) as (admin, pools, readers, sessions, token, store, service, ready, key):
            text = migration_text(ORIGIN_MIGRATION)
            self.assertTrue(text.endswith('COMMIT;\n'))
            with self.assertRaises(errors.DivisionByZero):
                admin.execute(text[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            admin.execute('ROLLBACK')
            self.assertIsNone(admin.execute(
                "SELECT to_regprocedure('forge.gateway_save(text,uuid,bigint,uuid,text,text)')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT has_schema_privilege('forge_gateway_authority','forge','CREATE')").fetchone(),
                             (False,))
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), CHECKPOINTS[-1])

    def test_migrated_schema_fingerprint_is_the_pinned_f19(self):
        with self.fixture() as (admin, pools, readers, sessions, token, store, service, ready, key):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F19)


if __name__ == '__main__':
    unittest.main()
