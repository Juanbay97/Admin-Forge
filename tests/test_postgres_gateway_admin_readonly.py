"""Owned PostgreSQL 0034: the company administrator's gateway is read-only. The service pool cannot execute gateway_save, the
composed application refuses PUT with a finite code, and the status shows only configured and the usable key count."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F33, F34, GATEWAY_ADMIN_READONLY_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.provisioning import SEED, provision
from mvp_support import at
from pool_support import assign_key, platform_keys
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import GATEWAY, login, stack
from test_postgres_platform_schema import drop_platform_roles

SAVE_SIGNATURES = ('forge.gateway_save(text,uuid,bigint,uuid,text)', 'forge.gateway_save(text,uuid,bigint,uuid,text,text)')


class ReadonlyProfileTests(unittest.TestCase):
    def test_0034_follows_0033_with_its_own_pinned_checkpoint(self):
        self.assertEqual(GATEWAY_ADMIN_READONLY_MIGRATION, '0034_gateway_admin_readonly.sql')
        self.assertEqual(MVP_ADDITIONS[at(GATEWAY_ADMIN_READONLY_MIGRATION) - 1], '0033_gateway_key_routing.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(GATEWAY_ADMIN_READONLY_MIGRATION):at(GATEWAY_ADMIN_READONLY_MIGRATION) + 2], (F33, F34))
        self.assertRegex(F34 or '', r'^[0-9a-f]{64}$', 'F34 must be pinned')
        self.assertNotEqual(F34, F33)


class ReadonlyFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0033_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_ADMIN_READONLY_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, GATEWAY_ADMIN_READONLY_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F33)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(GATEWAY_ADMIN_READONLY_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0034 gateway admin read-only checkpoint F34:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0033 must be identical')
        self.assertEqual(fresh, F34, 'F34 must be pinned to the reviewed value')


class ReadonlyGatewayTests(unittest.TestCase):
    def test_the_service_pool_cannot_execute_either_save_overload_while_the_other_functions_stay_executable(self):
        with stack() as (db, client, results, root, secrets):
            for signature in SAVE_SIGNATURES:
                self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_gateway_service',%s::regprocedure,'EXECUTE')",
                                                  (signature,)).fetchone(), (False,), signature)
            for signature in ('forge.gateway_status(text,uuid)', 'forge.gateway_inference_candidates(text,uuid,text)',
                              'forge.gateway_catalog_key(text,uuid)', 'forge.gateway_catalog_publish(text,uuid,uuid,bigint,bigint,uuid,jsonb,text,text,text,text)'):
                self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_gateway_service',%s::regprocedure,'EXECUTE')",
                                                  (signature,)).fetchone(), (True,), signature)
            with db.pool('forge_gateway_service').connection() as connection:
                with self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute('SELECT * FROM forge.gateway_save(%s,%s,0,gen_random_uuid(),%s)', ('0' * 64, results[0].organization_id, 'x' * 200))

    def test_put_is_forbidden_nothing_is_stored_and_the_status_counts_the_platform_keys(self):
        with stack() as (db, client, results, root, secrets):
            admin = login(client, results[0].accounts[0])
            url = '/forge/v1/orgs/%s/gateway' % results[0].organization_id
            self.assertEqual(client.get(url, headers=admin).json(), {'status': 'NOT_CONFIGURED', 'revision': 0, 'endpoint': '', 'allowed_endpoints': []})
            refused = client.put(url, headers=admin, json={'expected_revision': 0, 'api_key': results[0].gateway_key, 'endpoint': GATEWAY})
            self.assertEqual((refused.status_code, refused.json()['error']['code']), (403, 'GATEWAY_MANAGED_BY_PLATFORM'))
            self.assertNotIn(results[0].gateway_key, refused.text)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_gateways').fetchone(), (0,))
            assign_key(db, secrets['gateway_key'], GATEWAY, results[0].organization_id, results[0].gateway_key, ['fake-fast'])
            keys, owner = platform_keys(db, secrets['gateway_key'], (GATEWAY,))
            second = keys.create(owner, 'second', GATEWAY, 'second-fixture-key-SND2')
            keys.assign(owner, results[0].organization_id, [(keys.keys(owner)[0].id, 1, True), (second.id, 2, True)])
            status = client.get(url, headers=admin)
            self.assertEqual(status.json(), {'status': 'SAVED_UNVERIFIED', 'revision': 2, 'endpoint': '', 'allowed_endpoints': []})
            self.assertFalse([secret for secret in (results[0].gateway_key, 'second-fixture-key-SND2', 'second', GATEWAY) if secret in status.text])
            keys.set_status(owner, second.id, False)
            self.assertEqual(client.get(url, headers=admin).json()['revision'], 1, 'a disabled key is not counted')

    def test_another_company_and_a_plain_member_cannot_read_the_status(self):
        with stack() as (db, client, results, root, secrets):
            url = '/forge/v1/orgs/%s/gateway' % results[0].organization_id
            self.assertEqual(client.get(url, headers=login(client, results[1].accounts[0])).status_code, 404)
            self.assertEqual(client.get(url, headers=login(client, results[0].accounts[1])).status_code, 404)
            self.assertEqual(client.put(url, headers=login(client, results[1].accounts[0]),
                                        json={'expected_revision': 0, 'api_key': 'k'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
