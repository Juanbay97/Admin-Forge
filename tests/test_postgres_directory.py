"""Owned PostgreSQL 0020/0021 directory: me, departments, narrow RLS; no providers."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import sys
import unittest
from uuid import UUID, uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import psycopg
from psycopg import errors
from fastapi.testclient import TestClient
import test_postgres_gateway_catalog as upstream
from test_postgres_gateway_origin import migration_text, separate_database
from postgres_support import (ORG_A, ORG_B, MEMBER_A, MEMBER_B, ALICE, CAROL, connect,
    owned_gateway_catalog_admin_extension)
from forge.account_api import create_account_app
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS
from forge.directory import DirectoryConflict, DirectoryDenied, DirectoryService, DirectorySuspended
from forge.directory_store import PostgresDirectoryStore
from forge.invitations import capability_digest
from forge.mvp_profile import (F19, F20, F21, DEPARTMENT_MIGRATION, DIRECTORY_MIGRATION, MVP_ADDITIONS,
    MVP_CHECKPOINTS, ORIGIN_MIGRATION)

MEMBER_C = UUID(int=23)
LEGAL = UUID(int=901)
FUNCTIONS_0020 = ('forge.directory_account(text)', 'forge.directory_me(text)')
FUNCTIONS_0021 = ('forge.directory_admin(text,uuid)', 'forge.directory_departments(text,uuid)',
                  'forge.directory_department_create(text,uuid,text)')
TABLES = ('identities', 'owned_accounts', 'memberships', 'organizations', 'membership_roles', 'membership_departments')


class MvpProfileTests(unittest.TestCase):
    def test_profile_appends_the_directory_migrations_and_checkpoints(self):
        self.assertEqual(MVP_ADDITIONS[:len(ADDITIONS) + 3],
                         (*ADDITIONS, ORIGIN_MIGRATION, '0020_directory_identity.sql', '0021_department_directory.sql'))
        self.assertEqual(MVP_CHECKPOINTS[:len(CHECKPOINTS) + 3], (*CHECKPOINTS, F19, F20, F21))
        self.assertRegex(F20 or '', r'^[0-9a-f]{64}$', 'F20 must be pinned')
        self.assertRegex(F21 or '', r'^[0-9a-f]{64}$', 'F21 must be pinned')
        self.assertEqual(len({F19, F20, F21}), 3)


class DepartmentsFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0020+0021 == upgrade from 0020, pinned as F21 (runs before shared fixtures)."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def drop_authority(self):
        with connect() as admin:
            admin.execute('DROP ROLE IF EXISTS forge_directory_authority')

    def test_fresh_apply_and_upgrade_from_0020_share_the_pinned_fingerprint(self):
        everything = (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION)
        with separate_database() as conn:
            for name in everything:
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        self.drop_authority()
        with separate_database() as conn:
            for name in everything[:-1]:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F20)
            organization = uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Legal')",
                             (organization, uuid4()))
            before = conn.execute('SELECT * FROM forge.departments').fetchall()
            conn.execute(migration_text(DEPARTMENT_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.departments').fetchall(), before)
            upgraded = self.fingerprint(conn)
        self.drop_authority()
        print('Reviewed PG17 0021 department checkpoint F21:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0020 must be identical')
        self.assertEqual(fresh, F21, 'F21 must be pinned to the reviewed value')
        self.assertNotIn(fresh, (*CHECKPOINTS, F19, F20))

    def test_preexisting_duplicate_names_abort_the_migration_atomically(self):
        everything = (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION)
        with separate_database() as conn:
            for name in everything:
                conn.execute(migration_text(name))
            organization = uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'dup','Dup',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                for label in ('Legal', ' legal '):
                    conn.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)",
                                 (organization, uuid4(), label))
            with self.assertRaises(errors.UniqueViolation):
                conn.execute(migration_text(DEPARTMENT_MIGRATION))
            conn.execute('ROLLBACK')
            self.assertIsNone(conn.execute("SELECT to_regprocedure('forge.directory_admin(text,uuid)')").fetchone()[0])
            self.assertEqual(self.fingerprint(conn), F20)
        self.drop_authority()


class FingerprintGateTests(unittest.TestCase):
    """Runs before the shared-fixture class: fresh apply == upgrade from 0019, pinned as F20."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0019_share_the_pinned_fingerprint(self):
        everything = (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION)
        with separate_database() as conn:
            for name in everything:
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        # Roles are cluster-global; the shared helper predates this role, so drop it here.
        with connect() as admin:
            admin.execute('DROP ROLE IF EXISTS forge_directory_authority')
        with separate_database() as conn:
            for name in everything[:-1]:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F19)
            organization, member, identity = uuid4(), uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','u')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'active')", (organization, member, identity))
                conn.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Legal')",
                             (organization, uuid4()))
            before = conn.execute('SELECT * FROM forge.departments').fetchall()
            conn.execute(migration_text(DIRECTORY_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.departments').fetchall(), before)
            upgraded = self.fingerprint(conn)
        with connect() as admin:
            admin.execute('DROP ROLE IF EXISTS forge_directory_authority')
        print('Reviewed PG17 0020 directory checkpoint F20:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0019 must be identical')
        self.assertEqual(fresh, F20, 'F20 must be pinned to the reviewed value')
        self.assertNotIn(fresh, (*CHECKPOINTS, F19))


class PostgresDirectoryTests(unittest.TestCase):
    setUpClass = classmethod(upstream.PostgresGatewayCatalogTests.setUpClass.__func__)
    setUp = upstream.PostgresGatewayCatalogTests.setUp

    @contextmanager
    def fixture(self, *, migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION)):
        with upstream.PostgresGatewayCatalogTests.fixture(self) as values:
            admin, pools, readers, sessions, token = values[:5]
            with owned_gateway_catalog_admin_extension(admin):
                admin.execute(migration_text(ORIGIN_MIGRATION))
                try:
                    for name in migrations:
                        admin.execute(migration_text(name))
                    store = PostgresDirectoryStore(pools['forge_gateway_service'])
                    yield admin, pools, sessions, token, DirectoryService(store), store
                finally:
                    if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                        admin.execute('ROLLBACK')
                    self.unwind(admin)

    def unwind(self, admin):
        if admin.execute("SELECT to_regprocedure('forge.directory_admin(text,uuid)')").fetchone()[0]:
            for signature in FUNCTIONS_0021:
                admin.execute('DROP FUNCTION ' + signature)
            admin.execute('DROP POLICY directory_org_read ON forge.departments')
            admin.execute('DROP POLICY directory_write ON forge.departments')
            admin.execute('DROP INDEX forge.departments_name_unique')
        if admin.execute("SELECT to_regprocedure('forge.directory_me(text)')").fetchone()[0]:
            for signature in FUNCTIONS_0020:
                admin.execute('DROP FUNCTION ' + signature)
            for table in TABLES:
                admin.execute('DROP POLICY directory_scope ON forge.' + table)
            admin.execute('DROP POLICY directory_read ON forge.departments')
            admin.execute('DROP OWNED BY forge_directory_authority')
            admin.execute('DROP ROLE forge_directory_authority')
        admin.execute('DROP FUNCTION forge.gateway_save(text,uuid,bigint,uuid,text,text)')

    @contextmanager
    def seeded(self, admin):
        """Departments and roles beyond the shared baseline, removed again afterwards."""
        admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'member'),(%s,%s,'member')",
                      (ORG_A, MEMBER_C, ORG_B, MEMBER_B))
        admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Legal')", (ORG_A, LEGAL))
        admin.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)', (ORG_A, MEMBER_C, LEGAL))
        try:
            yield
        finally:
            admin.execute('DELETE FROM forge.membership_departments')
            admin.execute('DELETE FROM forge.departments')
            admin.execute("DELETE FROM forge.membership_roles WHERE role='member'")

    def login(self, sessions, email):
        return sessions.login(email, upstream.PASSWORD).capability

    def test_me_for_admin_member_and_nothing_foreign(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            mine = service.me(token)
            self.assertEqual((mine.account.id, mine.account.email), (ALICE, 'admin@example.com'))
            self.assertEqual([(o.id, o.roles, o.status) for o in mine.organizations],
                             [(ORG_A, ('organization_admin',), 'active')])
            member = service.me(self.login(sessions, 'member@example.com'))
            self.assertEqual([(o.id, o.roles, [d.name for d in o.departments]) for o in member.organizations],
                             [(ORG_A, ('member',), ['Legal'])])
            foreign = service.me(self.login(sessions, 'foreign@example.com'))
            self.assertEqual([o.id for o in foreign.organizations], [ORG_B])

    def test_multi_org_user_sees_each_membership_and_no_third_org(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            extra = uuid4()
            admin.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'active')", (ORG_B, extra, ALICE))
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'member')", (ORG_B, extra))
            try:
                roles = {o.id: o.roles for o in service.me(token).organizations}
                self.assertEqual(roles, {ORG_A: ('organization_admin',), ORG_B: ('member',)})
            finally:
                admin.execute('DELETE FROM forge.membership_roles WHERE membership_id=%s', (extra,))
                admin.execute('DELETE FROM forge.memberships WHERE id=%s', (extra,))

    def test_invalid_and_logged_out_sessions_are_denied_alike(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            with self.assertRaises(DirectoryDenied):
                service.me(secrets.token_urlsafe(32))
            other = self.login(sessions, 'member@example.com')
            sessions.logout(other)
            with self.assertRaises(DirectoryDenied):
                service.me(other)
            with self.assertRaises(DirectoryDenied):
                service.departments(other, ORG_A)

    def test_suspended_membership_is_omitted_or_denied(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            member = self.login(sessions, 'member@example.com')
            admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",
                          (ORG_A, MEMBER_C))
            try:
                with self.assertRaises(DirectorySuspended):
                    service.me(member)
            finally:
                admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id=%s",
                              (ORG_A, MEMBER_C))
            self.assertEqual([o.id for o in service.me(member).organizations], [ORG_A])

    def test_admin_lists_creates_and_duplicates_are_refused_without_a_second_row(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            self.assertEqual([d.name for d in service.departments(token, ORG_A)], ['Legal'])
            created = service.create_department(token, ORG_A, '  Finance ')
            self.assertEqual(created.name, 'Finance')
            self.assertEqual([d.name for d in service.departments(token, ORG_A)], ['Finance', 'Legal'])
            for duplicate in ('Finance', 'finance', ' FINANCE '):
                with self.subTest(duplicate=duplicate), self.assertRaises(DirectoryConflict):
                    service.create_department(token, ORG_A, duplicate)
            for invalid in ('', '   ', 'x' * 121):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    service.create_department(token, ORG_A, invalid)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.departments').fetchone(), (2,))

    def test_non_admin_foreign_admin_and_unknown_org_get_the_same_denial(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            member = self.login(sessions, 'member@example.com')
            foreign = self.login(sessions, 'foreign@example.com')
            for actor, org in ((member, ORG_A), (token, ORG_B), (foreign, ORG_A), (foreign, ORG_B), (token, uuid4())):
                with self.subTest(org=org), self.assertRaises(DirectoryDenied):
                    service.departments(actor, org)
                with self.subTest(org=org, op='create'), self.assertRaises(DirectoryDenied):
                    service.create_department(actor, org, 'Intruder')
            self.assertEqual(admin.execute("SELECT count(*) FROM forge.departments WHERE name='Intruder'").fetchone(), (0,))

    def test_http_me_and_departments_with_real_session_and_store(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            class Ready:
                def check(self): return True
            app = create_account_app(sessions=sessions, readiness=Ready(), directory=service)
            headers = {'Authorization': 'Bearer ' + token}
            with TestClient(app, raise_server_exceptions=False) as client:
                me = client.get('/forge/v1/accounts/me', headers=headers)
                self.assertEqual(me.status_code, 200)
                self.assertEqual(me.json()['organizations'][0]['id'], str(ORG_A))
                self.assertNotIn('password', me.text)
                self.assertEqual(client.get('/forge/v1/orgs/' + str(ORG_B) + '/departments', headers=headers).status_code, 404)
                made = client.post('/forge/v1/orgs/' + str(ORG_A) + '/departments', headers=headers, json={'name': 'Ops'})
                self.assertEqual(made.status_code, 201)
                self.assertEqual(client.post('/forge/v1/orgs/' + str(ORG_A) + '/departments', headers=headers,
                                             json={'name': 'ops'}).status_code, 409)
                sessions.logout(token)
                self.assertEqual(client.get('/forge/v1/accounts/me', headers=headers).status_code, 401)

    def test_authority_is_narrow_and_functions_are_service_only(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            for signature, expected in (('forge.directory_me(text)', True), ('forge.directory_departments(text,uuid)', True),
                    ('forge.directory_department_create(text,uuid,text)', True),
                    ('forge.directory_account(text)', False), ('forge.directory_admin(text,uuid)', False)):
                for role, allowed in (('forge_gateway_service', expected), ('forge_account_service', False), ('public', False)):
                    self.assertEqual(admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(),
                                     (allowed,), (signature, role))
                self.assertEqual(admin.execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=%s::regprocedure',
                                               (signature,)).fetchone(), ('forge_directory_authority', True))
            self.assertEqual(admin.execute("SELECT rolcanlogin,rolbypassrls,rolsuper FROM pg_roles WHERE rolname='forge_directory_authority'").fetchone(),
                             (False, False, False))
            self.assertEqual(admin.execute("SELECT has_schema_privilege('forge_directory_authority','forge','CREATE')").fetchone(), (False,))
            self.assertEqual(admin.execute("SELECT has_column_privilege('forge_directory_authority','forge.owned_accounts','password_hash','SELECT')").fetchone(), (False,))
            with pools['forge_gateway_service'].connection() as connection:
                for statement in ('SELECT * FROM forge.departments', 'SELECT * FROM forge.memberships'):
                    with self.assertRaises(errors.InsufficientPrivilege):
                        connection.execute(statement)
                    connection.rollback()

    def test_rls_exposes_nothing_without_a_validated_account_context(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            with admin.transaction():
                admin.execute('SET LOCAL ROLE forge_directory_authority')
                for table in TABLES + ('departments',):
                    self.assertEqual(admin.execute('SELECT count(*) FROM forge.' + table).fetchone(), (0,), table)
                admin.execute("SELECT set_config('forge.directory_account',%s,true)", (str(CAROL),))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (1,))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.organizations').fetchone(), (1,))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone(), (1,))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.identities').fetchone(), (1,))
                with self.assertRaises(errors.InsufficientPrivilege):
                    admin.execute('INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)', (ORG_A, uuid4(), 'X'))

    def test_admin_org_context_widens_department_reads_and_allows_only_scoped_inserts(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            with admin.transaction():
                admin.execute('SET LOCAL ROLE forge_directory_authority')
                admin.execute("SELECT set_config('forge.directory_account',%s,true)", (str(ALICE),))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.departments').fetchone(), (0,))
                admin.execute("SELECT set_config('forge.directory_org',%s,true)", (str(ORG_A),))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.departments').fetchone(), (1,))
                admin.execute('INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)', (ORG_A, uuid4(), 'Ok'))
                with self.assertRaises(errors.InsufficientPrivilege):
                    admin.execute('INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)', (ORG_B, uuid4(), 'Bad'))

    def test_failed_migration_rolls_back_to_the_0019_profile(self):
        with self.fixture(migrations=()) as (admin, pools, sessions, token, service, store):
            text = migration_text(DIRECTORY_MIGRATION)
            self.assertTrue(text.endswith('COMMIT;\n'))
            with self.assertRaises(errors.DivisionByZero):
                admin.execute(text[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            admin.execute('ROLLBACK')
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_directory_authority'").fetchone(), (0,))
            self.assertIsNone(admin.execute("SELECT to_regprocedure('forge.directory_me(text)')").fetchone()[0])
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F19)

    def test_failed_0021_rolls_back_to_the_0020_profile(self):
        with self.fixture(migrations=(DIRECTORY_MIGRATION,)) as (admin, pools, sessions, token, service, store):
            text = migration_text(DEPARTMENT_MIGRATION)
            self.assertTrue(text.endswith('COMMIT;\n'))
            with self.assertRaises(errors.DivisionByZero):
                admin.execute(text[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            admin.execute('ROLLBACK')
            self.assertIsNone(admin.execute("SELECT to_regprocedure('forge.directory_admin(text,uuid)')").fetchone()[0])
            self.assertIsNone(admin.execute("SELECT to_regclass('forge.departments_name_unique')").fetchone()[0])
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F20)

    def test_migrated_schema_fingerprint_is_the_pinned_f20(self):
        with self.fixture(migrations=(DIRECTORY_MIGRATION,)) as (admin, pools, sessions, token, service, store):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F20)

    def test_migrated_schema_fingerprint_is_the_pinned_f21(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F21)


if __name__ == '__main__':
    unittest.main()
