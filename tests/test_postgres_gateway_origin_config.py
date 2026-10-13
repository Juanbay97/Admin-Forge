"""Owned PostgreSQL 0027: the database accepts any canonical https gateway origin; the app allow-list stays the authority."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.account_sessions import PostgresSessionStore, SessionService
from forge.dev_accounts import MIGRATIONS
from forge.gateway_configuration import GatewayCipher, GatewayConfiguration
from forge.gateway_configuration_store import PostgresGatewayStore
from forge.gateway_origins import DEFAULT_ENDPOINT, OriginPolicy
from forge.invitations import capability_digest
from forge.migrate import CANONICAL_ORDER, migrate
from forge.mvp_profile import F26, F27, GATEWAY_ORIGIN_CONFIG_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_migrate import DIRECTORY, fresh_database, passwords

CUSTOM = 'https://ia.example.test'
PORTED = 'https://gw.example.test:8443'
LOOPBACK = 'http://127.0.0.1:3413'
GOOD = (DEFAULT_ENDPOINT, CUSTOM, PORTED, 'https://a.b.c.example.test', 'https://x.test:1', 'https://x.test:65535',
        'https://xn--bcher-kva.example', LOOPBACK, 'http://127.0.0.1:1', 'https://a-b.test', 'https://' + 'a' * 63 + '.test')
BAD = ('https://ia.example.test/', 'https://ia.example.test/v1', 'https://ia.example.test?x=1', 'https://ia.example.test#f',
       'https://user@ia.example.test', 'https://user:pw@ia.example.test', 'https://IA.example.test', 'http://ia.example.test',
       'https://127.0.0.1', 'https://10.0.0.5', 'https://10.0.0.5:8443', 'https://x.test:0', 'https://x.test:65536',
       'https://x.test:08443', 'https://x.test:', 'https://', 'https://-bad.test', 'https://bad-.test', 'https://bad..test',
       'https://ia.example.test ', ' https://ia.example.test', 'https://ia example.test', 'ftp://ia.example.test',
       'ia.example.test', 'https://' + 'a' * 64 + '.test', 'https://' + 'a.' * 130 + 'test', '',
       'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.2:3413', 'http://localhost:3413', 'https://[::1]')


class ProfileTests(unittest.TestCase):
    """No database: the profile appends exactly 0027 and its pinned checkpoint."""
    def test_0027_is_the_last_migration_with_its_own_pinned_checkpoint(self):
        self.assertEqual(GATEWAY_ORIGIN_CONFIG_MIGRATION, '0027_gateway_origin_config.sql')
        self.assertIn(GATEWAY_ORIGIN_CONFIG_MIGRATION, MVP_ADDITIONS)
        self.assertEqual(MVP_ADDITIONS[at(GATEWAY_ORIGIN_CONFIG_MIGRATION) - 1], '0026_branding_member_code.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(GATEWAY_ORIGIN_CONFIG_MIGRATION):at(GATEWAY_ORIGIN_CONFIG_MIGRATION) + 2], (F26, F27))
        self.assertRegex(F27 or '', r'^[0-9a-f]{64}$', 'F27 must be pinned')
        self.assertNotEqual(F27, F26)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertIn(GATEWAY_ORIGIN_CONFIG_MIGRATION, CANONICAL_ORDER)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))

    def test_the_migration_keeps_the_application_allow_list_as_the_authority(self):
        text = migration_text(GATEWAY_ORIGIN_CONFIG_MIGRATION)
        self.assertIn('forge_gateway_authority', text)
        self.assertNotIn('DROP TABLE', text.upper())
        self.assertNotIn('DELETE FROM', text.upper())


class FingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0027 == upgrade from the 0026 profile, pinned as F27; the upgrade keeps saved gateways."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0026_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_ORIGIN_CONFIG_MIGRATION)])
        with fresh_database() as conn:
            for name in (*previous, GATEWAY_ORIGIN_CONFIG_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        with fresh_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F26)
            organization, identity = uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','up')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.organization_gateways(organization_id,revision,binding_id,endpoint,encrypted_key,"
                             "updated_by) VALUES(%s,1,%s,'http://127.0.0.1:3413',%s,%s)", (organization, uuid4(), 'x' * 120, identity))
            before = conn.execute('SELECT * FROM forge.organization_gateways').fetchall()
            conn.execute(migration_text(GATEWAY_ORIGIN_CONFIG_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.organization_gateways').fetchall(), before)
            upgraded = self.fingerprint(conn)
        print('Reviewed PG17 0027 gateway origin config checkpoint F27:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0026 must be identical')
        self.assertEqual(fresh, F27, 'F27 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F26)


def before_readonly():
    """The 0027 function is exercised where it is still granted: 0034 (tested on its own) revokes it from the service pool."""
    from forge.mvp_profile import GATEWAY_ADMIN_READONLY_MIGRATION
    return mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_ADMIN_READONLY_MIGRATION)]))


class OriginConfigTests(unittest.TestCase):
    def organization(self, db):
        results = provision(db.admin, SEED, lambda created: None)
        sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
        admin = results[0].accounts[0]
        return results[0].organization_id, sessions.login(admin.email, admin.password).capability

    def test_the_check_accepts_every_canonical_https_origin_and_the_dev_loopback_only(self):
        with before_readonly() as db:
            organization, token = self.organization(db)
            service = GatewayConfiguration(PostgresGatewayStore(db.pool('forge_gateway_service')),
                                           GatewayCipher(Fernet.generate_key(), policy=OriginPolicy(frozenset({DEFAULT_ENDPOINT}))))
            service.save(token, organization, 0, 'fixture-only-key')
            for good in GOOD:
                with self.subTest(good=good):
                    db.admin.execute('UPDATE forge.organization_gateways SET endpoint=%s', (good,))
            for bad in BAD:
                with self.subTest(bad=bad), self.assertRaises(errors.CheckViolation):
                    db.admin.execute('UPDATE forge.organization_gateways SET endpoint=%s', (bad,))

    def test_a_non_default_origin_chosen_by_the_allow_list_is_saved_read_back_and_bound_to_the_key(self):
        with before_readonly() as db:
            organization, token = self.organization(db)
            policy = OriginPolicy(frozenset({CUSTOM, PORTED}))
            store = PostgresGatewayStore(db.pool('forge_gateway_service'))
            service = GatewayConfiguration(store, GatewayCipher(Fernet.generate_key(), policy=policy))
            self.assertEqual(service.save(token, organization, 0, 'fixture-only-key', endpoint=CUSTOM).endpoint, CUSTOM)
            self.assertEqual(service.save(token, organization, 1, 'rotated-key', endpoint=PORTED).endpoint, PORTED)
            record = store.read(capability_digest(token), organization)
            self.assertEqual((record.revision, record.endpoint), (2, PORTED))
            self.assertEqual(db.admin.execute('SELECT endpoint FROM forge.organization_gateways').fetchall(), [(PORTED,)])
            self.assertEqual(service.read(token, organization).endpoint, PORTED)

    def test_the_function_refuses_a_non_origin_with_gateway_invalid_and_writes_nothing(self):
        with mvp_database() as db:
            organization, token = self.organization(db)
            digest = capability_digest(token)

            def save(origin):
                return db.admin.execute('SELECT * FROM forge.gateway_save(%s,%s,0,%s,%s,%s)',
                                        (digest, organization, uuid4(), 'x' * 120, origin))
            for bad in BAD + (None,):
                with self.subTest(bad=bad), self.assertRaises(errors.RaiseException) as caught:
                    save(bad)
                self.assertEqual(caught.exception.diag.message_primary, 'GATEWAY_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_gateways').fetchone(), (0,))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_configuration_audit').fetchone(), (0,))
            self.assertEqual(save(CUSTOM).fetchone()[2], CUSTOM)

    def test_the_five_argument_save_still_means_the_default_origin(self):
        with mvp_database() as db:
            organization, token = self.organization(db)
            row = db.admin.execute('SELECT * FROM forge.gateway_save(%s,%s,0,%s,%s)',
                                   (capability_digest(token), organization, uuid4(), 'x' * 120)).fetchone()
            self.assertEqual(row[2], DEFAULT_ENDPOINT)

    def test_the_function_is_still_authority_owned_definer_only_and_executable_by_the_gateway_service_alone(self):
        with before_readonly() as db:
            signature = 'forge.gateway_save(text,uuid,bigint,uuid,text,text)'
            owner, definer, config = db.admin.execute(
                'SELECT pg_get_userbyid(proowner),prosecdef,proconfig FROM pg_proc WHERE oid=%s::regprocedure', (signature,)).fetchone()
            self.assertEqual((owner, definer, config), ('forge_gateway_authority', True, ['search_path=pg_catalog']))
            for role, expected in (('forge_gateway_service', True), ('forge_account_service', False), ('forge_runtime', False),
                                   ('forge_enrollment', False), ('forge_branding_service', False)):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(),
                                 (expected,), role)
            self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', ('public', signature, 'EXECUTE')).fetchone(),
                             (False,))
            self.assertEqual(db.admin.execute("SELECT has_schema_privilege('forge_gateway_authority','forge','CREATE')").fetchone(),
                             (False,), 'the temporary schema grant is revoked again')


class RunnerUpgradeTests(unittest.TestCase):
    def test_the_runner_upgrades_a_database_adopted_at_f26_by_applying_exactly_0027(self):
        with fresh_database() as admin:
            for name in (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_ORIGIN_CONFIG_MIGRATION)]):
                admin.execute(migration_text(name))
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F26)
            known = {role: password for role, password in passwords().items() if role not in ('forge_platform_service', 'forge_capability_service')}  # not created before 0028 / 0038
            applied = migrate(admin, DIRECTORY, known, order=CANONICAL_ORDER[:CANONICAL_ORDER.index(GATEWAY_ORIGIN_CONFIG_MIGRATION) + 1],
                            checkpoints=MVP_CHECKPOINTS[:at(GATEWAY_ORIGIN_CONFIG_MIGRATION) + 2])
            self.assertEqual(applied, [GATEWAY_ORIGIN_CONFIG_MIGRATION])
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F27)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge_ops.schema_migrations').fetchone(), (CANONICAL_ORDER.index(GATEWAY_ORIGIN_CONFIG_MIGRATION) + 1,))


if __name__ == '__main__':
    unittest.main()
