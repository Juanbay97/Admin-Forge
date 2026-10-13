"""Owned PostgreSQL 0038 capability catalog: platform-global catalog, platform default policy and epoch, a role pair that is
NOLOGIN until the operator passwords it, and no table privilege for the service role."""
from pathlib import Path
import secrets
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import psycopg
from psycopg import errors, sql
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import CAPABILITY_CATALOG_MIGRATION, F37, F38, MVP_ADDITIONS, MVP_CHECKPOINTS
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

TABLES = ('capability_catalog', 'capability_platform_policy', 'capability_platform_epoch')
ENTRY = "INSERT INTO forge.capability_catalog(id,kind,version,risk,is_base,default_state,min_sandbox_level) VALUES(%s,%s,'1.0.0',%s,true,%s,%s)"


def service_connection(db):
    """The service role as the operator would enable it: LOGIN with a password (only the profile's own roles are passworded by the harness)."""
    password = secrets.token_urlsafe(24)
    db.admin.execute(sql.SQL('ALTER ROLE forge_capability_service LOGIN PASSWORD {}').format(sql.Literal(password)))
    return psycopg.connect(**db.connection_settings(user='forge_capability_service', password=password))


class CatalogProfileTests(unittest.TestCase):
    def test_0038_follows_0037_with_its_own_pinned_checkpoint(self):
        self.assertEqual(CAPABILITY_CATALOG_MIGRATION, '0038_capability_catalog.sql')
        self.assertEqual(MVP_ADDITIONS[at(CAPABILITY_CATALOG_MIGRATION) - 1], '0037_usage_reads.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(CAPABILITY_CATALOG_MIGRATION):at(CAPABILITY_CATALOG_MIGRATION) + 2], (F37, F38))
        self.assertRegex(F38 or '', r'^[0-9a-f]{64}$', 'F38 must be pinned')
        self.assertNotEqual(F38, F37)


class CatalogFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0037_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_CATALOG_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, CAPABILITY_CATALOG_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F37)
            conn.execute(migration_text(CAPABILITY_CATALOG_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0038 capability catalog checkpoint F38:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0037 must be identical')
        self.assertEqual(fresh, F38, 'F38 must be pinned to the reviewed value')


class CatalogSchemaTests(unittest.TestCase):
    def test_the_role_pair_has_no_privileged_attribute_and_only_the_service_may_log_in_once_passworded(self):
        with mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_CATALOG_MIGRATION) + 1])) as db:
            rows = db.admin.execute("SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,rolcanlogin "
                                    "FROM pg_roles WHERE rolname LIKE 'forge_capability_%' ORDER BY 1").fetchall()
            # The authority never logs in; the service logs in only once the harness (like the operator) gives it a password.
            self.assertEqual([row[:7] for row in rows], [('forge_capability_authority', False, False, False, False, False, False),
                                                         ('forge_capability_service', False, False, False, False, False, False)])
            self.assertEqual(rows[0][7], False)

    def test_tables_are_forced_rls_and_only_the_authority_holds_privileges(self):
        with mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_CATALOG_MIGRATION) + 1])) as db:
            for table in TABLES:
                self.assertEqual(db.admin.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', ('forge.' + table,)).fetchone(),
                                 (True, True))
                for role in ('forge_capability_service', 'forge_gateway_service', 'forge_platform_service', 'forge_account_service',
                             'forge_runtime', 'forge_branding_service', 'forge_enrollment', 'public'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, 'forge.' + table)).fetchone(),
                                     (False,), (role, table))
                self.assertEqual(db.admin.execute("SELECT has_table_privilege('forge_capability_authority',%s,'SELECT,INSERT,UPDATE')", ('forge.' + table,)).fetchone(), (True,))
                self.assertEqual(db.admin.execute("SELECT has_table_privilege('forge_capability_authority',%s,'DELETE')", ('forge.' + table,)).fetchone(), (False,))
            for check in ("SELECT has_schema_privilege('forge_capability_service','forge','CREATE')",
                          "SELECT has_database_privilege('forge_capability_service',current_database(),'CREATE')",
                          "SELECT has_schema_privilege('forge_capability_authority','forge','CREATE')"):
                self.assertEqual(db.admin.execute(check).fetchone(), (False,), check)

    def test_the_service_pool_reads_nothing_and_the_epoch_starts_at_one(self):
        with mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_CATALOG_MIGRATION) + 1])) as db:
            self.assertEqual(db.admin.execute('SELECT singleton,epoch FROM forge.capability_platform_epoch').fetchall(), [], 'no row: an absent epoch is 1 (a migration must not seed data)')
            with service_connection(db) as connection:
                for table in TABLES:
                    with self.assertRaises(errors.InsufficientPrivilege):
                        connection.execute('SELECT * FROM forge.' + table)

    def test_a_freshly_migrated_database_holds_no_row_in_any_forge_table(self):
        """The backup/restore contract (deploy/backup/restore.sh restores data into an empty, freshly migrated database): a migration seeds nothing."""
        with mvp_database() as db:
            rows = db.admin.execute("SELECT coalesce(sum((xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', schemaname, tablename), false, true, '')))[1]::text::bigint), 0) "
                                    "FROM pg_tables WHERE schemaname = 'forge'").fetchone()[0]
            self.assertEqual(rows, 0)

    def test_catalog_rows_are_validated_by_the_database(self):
        with mvp_database(migrations=(*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_CATALOG_MIGRATION) + 1])) as db:
            db.admin.execute(ENTRY, ('skill:pdf', 'skill', 'low', 'on', 0))
            bad = (('skill:Pdf', 'skill', 'low', 'on', 0), ('gadget:x', 'gadget', 'low', 'on', 0), ('skill:x', 'tool', 'low', 'on', 0),
                   ('skill:y', 'skill', 'severe', 'on', 0), ('skill:y', 'skill', 'low', 'maybe', 0), ('skill:y', 'skill', 'low', 'on', 5),
                   ('app:acme.hello', 'app', 'low', 'on', 0), ('skill:pdf', 'skill', 'low', 'on', 0))
            for values in bad:
                with self.subTest(values=values), self.assertRaises((errors.CheckViolation, errors.UniqueViolation)):
                    db.admin.execute(ENTRY, values)
            db.admin.execute(ENTRY, ('app:acme.hello', 'app', 'low', 'off', 0))
            self.assertEqual(db.admin.execute("SELECT credential_locus,revision,attributes FROM forge.capability_catalog WHERE id='skill:pdf'").fetchone(),
                             ('server', 1, {}))
            with self.assertRaises(errors.ForeignKeyViolation):
                db.admin.execute("INSERT INTO forge.capability_platform_policy(capability_id,state) VALUES('skill:ghost','on')")
            with self.assertRaises(errors.CheckViolation):
                db.admin.execute("INSERT INTO forge.capability_platform_policy(capability_id,lock) VALUES('skill:pdf','locked')")
            with self.assertRaises(errors.CheckViolation):
                db.admin.execute('INSERT INTO forge.capability_platform_epoch(singleton,epoch) VALUES(false,2)')


if __name__ == '__main__':
    unittest.main()
