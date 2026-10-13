"""Owned PostgreSQL: the supervisor's schema installer yields the pinned F38 profile and working roles."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg_pool import ConnectionPool
from forge.account_readiness import catalog_fingerprint
from forge.mvp_local import ConfigError, ROLES
from forge.mvp_profile import F38
from forge.mvp_readiness import MvpReadiness
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher, GatewayRecord
from forge.gateway_origins import OriginPolicy
from forge.invitations import capability_digest
from forge.mvp_up import install_schema
from forge.pool_seed import seed_gateway_pool
from forge.provisioning import SEED, provision
from postgres_support import connect, settings
from test_postgres_gateway_origin import separate_database


class PostgresMvpUpTests(unittest.TestCase):
    def test_install_schema_applies_the_full_profile_and_returns_working_role_passwords(self):
        try:
            with separate_database() as conn:
                passwords = install_schema(conn)
                self.assertEqual(set(passwords), set(ROLES))
                self.assertEqual(len(set(passwords.values())), 6)
                with conn.cursor() as cursor:
                    self.assertEqual(catalog_fingerprint(cursor), F38)
                pools = [ConnectionPool('', kwargs={**settings(), 'dbname': conn.info.dbname, 'user': role,
                                                    'password': passwords[role]}, min_size=1, max_size=2, open=False)
                         for role in ('forge_account_service', 'forge_runtime', 'forge_gateway_service')]
                try:
                    for pool in pools:
                        pool.open(wait=True, timeout=5)
                    self.assertIs(MvpReadiness(*pools).check(), True)
                finally:
                    for pool in pools:
                        pool.close(timeout=5)
        finally:
            with connect() as cleanup:
                for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service',
                              'forge_platform_authority', 'forge_platform_service', 'forge_capability_authority', 'forge_capability_service'):
                    cleanup.execute('DROP ROLE IF EXISTS ' + role)

    def test_the_local_stack_gives_each_company_a_platform_key_with_a_ceiling_like_production_does(self):
        origin = 'http://127.0.0.1:3413'
        try:
            with separate_database() as conn:
                install_schema(conn)
                results = provision(conn, SEED, lambda created: None)
                secret = Fernet.generate_key()
                seeded = seed_gateway_pool(conn, secret, origin, results, ('fake-fast', 'fake-slow'))
                cipher = GatewayCipher(secret, policy=OriginPolicy(frozenset({origin}), dev=True))
                self.assertEqual(len(seeded), 2)
                for result in results:
                    row = conn.execute('SELECT k.id,k.origin,k.revision,k.encrypted_key,k.last4,p.revision,p.binding_id,p.ceiling,a.priority,a.active '
                                       'FROM forge.organization_gateway_keys a JOIN forge.gateway_keys k ON k.id=a.key_id '
                                       'JOIN forge.organization_gateway_profiles p ON p.organization_id=a.organization_id WHERE a.organization_id=%s',
                                       (result.organization_id,)).fetchone()
                    self.assertEqual((row[1], row[2], row[4], row[5], row[7], row[8], row[9]),
                                     (origin, 1, result.gateway_key[-4:], 1, ['fake-fast', 'fake-slow'], 1, True))
                    self.assertEqual(cipher.open_key(result.organization_id, GatewayRecord(1, row[6], origin, row[3], row[0], 1)), result.gateway_key)
                    self.assertNotIn(result.gateway_key, row[3])
                with self.assertRaises(ValueError):
                    seed_gateway_pool(conn, secret, 'ftp://not-an-origin', results, ('fake-fast',))
        finally:
            with connect() as cleanup:
                for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service',
                              'forge_platform_authority', 'forge_platform_service', 'forge_capability_authority', 'forge_capability_service'):
                    cleanup.execute('DROP ROLE IF EXISTS ' + role)

    def test_a_database_that_already_has_the_schema_is_refused_untouched(self):
        try:
            with separate_database() as conn:
                install_schema(conn)
                before = conn.execute('SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace '
                                      "WHERE n.nspname='forge'").fetchone()
                with self.assertRaises(ConfigError) as caught:
                    install_schema(conn)
                self.assertEqual(str(caught.exception), 'FRESH_DATABASE_REQUIRED')
                self.assertEqual(conn.execute('SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace '
                                              "WHERE n.nspname='forge'").fetchone(), before)
        finally:
            with connect() as cleanup:
                for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service',
                              'forge_platform_authority', 'forge_platform_service', 'forge_capability_authority', 'forge_capability_service'):
                    cleanup.execute('DROP ROLE IF EXISTS ' + role)


if __name__ == '__main__':
    unittest.main()
