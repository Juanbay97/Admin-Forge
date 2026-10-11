"""Owned PostgreSQL 0022 member directory: admin-only member list with narrow org-scoped reads."""
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
import test_postgres_directory as directory_tests
import test_postgres_gateway_catalog as upstream
from test_postgres_gateway_origin import migration_text, separate_database
from postgres_support import (ORG_A, ORG_B, MEMBER_A, MEMBER_B, connect,
    owned_gateway_catalog_admin_extension)
from forge.account_api import create_account_app
from forge.account_readiness import catalog_fingerprint
from forge.accounts import ACCOUNT_ISSUER
from forge.dev_accounts import MIGRATIONS
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS
from forge.directory import DirectoryDenied, DirectoryService
from forge.directory_store import PostgresDirectoryStore
from forge.mvp_profile import (F20, F21, F22, DEPARTMENT_MIGRATION, DIRECTORY_MIGRATION,
    MEMBER_DIRECTORY_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS, ORIGIN_MIGRATION)

MEMBER_C = UUID(int=23)
SAM, SAM_MEMBER, LEGAL = UUID(int=31), UUID(int=33), UUID(int=901)
FUNCTIONS = ('forge.directory_members(text,uuid)', 'forge.directory_member_rows(uuid,uuid)')
ORG_READ_TABLES = ('memberships', 'membership_roles', 'membership_departments', 'owned_accounts')


class MvpProfileTests(unittest.TestCase):
    def test_profile_appends_the_member_directory_migration_and_checkpoint(self):
        self.assertEqual(MVP_ADDITIONS[len(ADDITIONS) + 3], '0022_member_directory.sql')
        self.assertEqual(MVP_CHECKPOINTS[:len(CHECKPOINTS) + 4], (*CHECKPOINTS, directory_tests.F19, F20, F21, F22))
        self.assertRegex(F22 or '', r'^[0-9a-f]{64}$', 'F22 must be pinned')
        self.assertEqual(len({F20, F21, F22}), 3)


class MembersFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0020-0022 == upgrade from 0021, pinned as F22 (runs before shared fixtures)."""
    prefix = (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION)

    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def drop_authority(self):
        with connect() as admin:
            admin.execute('DROP ROLE IF EXISTS forge_directory_authority')

    def test_fresh_apply_and_upgrade_from_0021_share_the_pinned_fingerprint(self):
        with separate_database() as conn:
            for name in (*self.prefix, MEMBER_DIRECTORY_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        self.drop_authority()
        with separate_database() as conn:
            for name in self.prefix:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F21)
            organization, identity, member = uuid4(), uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','u')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'suspended')", (organization, member, identity))
            before = conn.execute('SELECT * FROM forge.memberships').fetchall()
            conn.execute(migration_text(MEMBER_DIRECTORY_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.memberships').fetchall(), before)
            upgraded = self.fingerprint(conn)
        self.drop_authority()
        print('Reviewed PG17 0022 member checkpoint F22:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0021 must be identical')
        self.assertEqual(fresh, F22, 'F22 must be pinned to the reviewed value')
        self.assertNotIn(fresh, (*CHECKPOINTS, directory_tests.F19, F20, F21))


class PostgresMemberAdministrationTests(unittest.TestCase):
    setUpClass = classmethod(upstream.PostgresGatewayCatalogTests.setUpClass.__func__)
    setUp = upstream.PostgresGatewayCatalogTests.setUp
    unwind_directory = directory_tests.PostgresDirectoryTests.unwind

    @contextmanager
    def fixture(self, *, migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION, MEMBER_DIRECTORY_MIGRATION)):
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
        if admin.execute("SELECT to_regprocedure('forge.directory_members(text,uuid)')").fetchone()[0]:
            for signature in FUNCTIONS:
                admin.execute('DROP FUNCTION ' + signature)
            for table in ORG_READ_TABLES:
                admin.execute('DROP POLICY directory_org_read ON forge.' + table)
        self.unwind_directory(admin)

    @contextmanager
    def seeded(self, admin):
        """Carol (member, Legal), Sam (suspended) and Bob as admin of org B; removed afterwards."""
        admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'member'),(%s,%s,'organization_admin')",
                      (ORG_A, MEMBER_C, ORG_B, MEMBER_B))
        admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Legal')", (ORG_A, LEGAL))
        admin.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)', (ORG_A, MEMBER_C, LEGAL))
        admin.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'forge',%s,%s)",
                      (SAM, ACCOUNT_ISSUER, str(SAM)))
        admin.execute("INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) "
                      "VALUES(%s,'sam@example.com','Sam',%s)", (SAM, self.encoded))
        admin.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'suspended')", (ORG_A, SAM_MEMBER, SAM))
        admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'member')", (ORG_A, SAM_MEMBER))
        try:
            yield
        finally:
            admin.execute('DELETE FROM forge.membership_departments')
            admin.execute('DELETE FROM forge.departments')
            admin.execute('DELETE FROM forge.membership_roles WHERE membership_id=%s', (SAM_MEMBER,))
            admin.execute('DELETE FROM forge.memberships WHERE id=%s', (SAM_MEMBER,))
            admin.execute('DELETE FROM forge.owned_accounts WHERE id=%s', (SAM,))
            admin.execute('DELETE FROM forge.identities WHERE id=%s', (SAM,))
            for org, member, role in ((ORG_A, MEMBER_C, 'member'), (ORG_B, MEMBER_B, 'organization_admin')):
                admin.execute('DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role=%s',
                              (org, member, role))

    def login(self, sessions, email):
        return sessions.login(email, upstream.PASSWORD).capability

    def test_admin_lists_members_of_the_organization_with_every_status(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            listed = {m.display_name + ':' + m.email: m for m in service.members(token, ORG_A)}
            self.assertEqual({key: (m.id, m.status, m.roles) for key, m in listed.items()},
                             {'Fixture:admin@example.com': (MEMBER_A, 'active', ('organization_admin',)),
                              'Fixture:member@example.com': (MEMBER_C, 'active', ('member',)),
                              'Sam:sam@example.com': (SAM_MEMBER, 'suspended', ('member',))})
            self.assertEqual([d.name for d in listed['Fixture:member@example.com'].departments], ['Legal'])
            self.assertEqual(listed['Fixture:admin@example.com'].departments, ())
            self.assertEqual([m.id for m in service.members(self.login(sessions, 'foreign@example.com'), ORG_B)],
                             [MEMBER_B])
            for member in listed.values():
                self.assertEqual(set(vars(member)), {'id', 'email', 'display_name', 'status', 'roles', 'departments'})

    def test_non_admin_foreign_admin_and_unknown_org_get_the_same_denial(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            member = self.login(sessions, 'member@example.com')
            foreign = self.login(sessions, 'foreign@example.com')
            for actor, org in ((member, ORG_A), (foreign, ORG_A), (token, ORG_B), (token, uuid4()), (foreign, uuid4())):
                with self.subTest(org=org), self.assertRaises(DirectoryDenied):
                    service.members(actor, org)
            other = self.login(sessions, 'member@example.com')
            sessions.logout(other)
            with self.assertRaises(DirectoryDenied):
                service.members(other, ORG_A)
            with self.assertRaises(DirectoryDenied):
                service.members(secrets.token_urlsafe(32), ORG_A)
            self.assertEqual(len(service.members(token, ORG_A)), 3)

    def test_http_members_with_real_session_and_store(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            class Ready:
                def check(self): return True
            app = create_account_app(sessions=sessions, readiness=Ready(), directory=service)
            headers = {'Authorization': 'Bearer ' + token}
            base = '/forge/v1/orgs/' + str(ORG_A) + '/members'
            with TestClient(app, raise_server_exceptions=False) as client:
                listing = client.get(base, headers=headers)
                self.assertEqual(listing.status_code, 200)
                self.assertEqual({m['status'] for m in listing.json()['members']}, {'active', 'suspended'})
                for secret in ('password', 'hash', 'argon', 'token'):
                    self.assertNotIn(secret, listing.text.lower())
                self.assertEqual(client.get('/forge/v1/orgs/' + str(ORG_B) + '/members', headers=headers).status_code, 404)
                sessions.logout(token)
                self.assertEqual(client.get(base, headers=headers).status_code, 401)

    def test_member_functions_are_service_only_and_the_authority_stays_read_only(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            for signature, expected in (('forge.directory_members(text,uuid)', True),
                                        ('forge.directory_member_rows(uuid,uuid)', False)):
                for role, allowed in (('forge_gateway_service', expected), ('forge_account_service', False), ('public', False)):
                    self.assertEqual(admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(),
                                     (allowed,), (signature, role))
                self.assertEqual(admin.execute('SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid=%s::regprocedure',
                                               (signature,)).fetchone(), ('forge_directory_authority',))
            for table in ('memberships', 'membership_roles', 'membership_departments', 'owned_accounts', 'account_sessions'):
                for privilege in ('INSERT', 'UPDATE', 'DELETE'):
                    self.assertFalse(admin.execute('SELECT has_table_privilege(%s,%s,%s)',
                                                   ('forge_directory_authority', 'forge.' + table, privilege)).fetchone()[0],
                                     (table, privilege))
            self.assertFalse(admin.execute("SELECT has_column_privilege('forge_directory_authority','forge.owned_accounts','password_hash','SELECT')").fetchone()[0])
            self.assertFalse(admin.execute("SELECT has_table_privilege('forge_directory_authority','forge.account_sessions','SELECT')").fetchone()[0])

    def test_rls_exposes_member_rows_only_for_the_pinned_organization(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            in_org_a = admin.execute('SELECT count(*) FROM forge.memberships WHERE organization_id=%s', (ORG_A,)).fetchone()
            self.assertGreater(in_org_a[0], 3, 'baseline also holds memberships without an owned account')
            with admin.transaction():
                admin.execute('SET LOCAL ROLE forge_directory_authority')
                for table in ORG_READ_TABLES:
                    self.assertEqual(admin.execute('SELECT count(*) FROM forge.' + table).fetchone(), (0,), table)
                admin.execute("SELECT set_config('forge.directory_org',%s,true)", (str(ORG_A),))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), in_org_a)
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone(), (3,))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.memberships WHERE organization_id=%s', (ORG_B,)).fetchone(), (0,))
                with self.assertRaises(errors.InsufficientPrivilege):
                    admin.execute("UPDATE forge.memberships SET status='suspended'")

    def test_failed_0022_rolls_back_to_the_0021_profile(self):
        with self.fixture(migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION)) as (admin, pools, sessions, token, service, store):
            text = migration_text(MEMBER_DIRECTORY_MIGRATION)
            self.assertTrue(text.endswith('COMMIT;\n'))
            with self.assertRaises(errors.DivisionByZero):
                admin.execute(text[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            admin.execute('ROLLBACK')
            self.assertIsNone(admin.execute("SELECT to_regprocedure('forge.directory_members(text,uuid)')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_policies WHERE policyname='directory_org_read' AND tablename='memberships'").fetchone(), (0,))
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F21)

    def test_migrated_schema_fingerprint_is_the_pinned_f22(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F22)


if __name__ == '__main__':
    unittest.main()
