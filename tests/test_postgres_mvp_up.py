"""Owned PostgreSQL: the supervisor's schema installer yields the pinned F24 profile and working roles."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg_pool import ConnectionPool
from forge.account_readiness import catalog_fingerprint
from forge.mvp_local import ConfigError, ROLES
from forge.mvp_profile import F24
from forge.mvp_readiness import MvpReadiness
from forge.mvp_up import install_schema
from postgres_support import connect, settings
from test_postgres_gateway_origin import separate_database


class PostgresMvpUpTests(unittest.TestCase):
    def test_install_schema_applies_the_full_profile_and_returns_working_role_passwords(self):
        try:
            with separate_database() as conn:
                passwords = install_schema(conn)
                self.assertEqual(set(passwords), set(ROLES))
                self.assertEqual(len(set(passwords.values())), 4)
                with conn.cursor() as cursor:
                    self.assertEqual(catalog_fingerprint(cursor), F24)
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
                cleanup.execute('DROP ROLE IF EXISTS forge_directory_authority')

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
                cleanup.execute('DROP ROLE IF EXISTS forge_directory_authority')


if __name__ == '__main__':
    unittest.main()
