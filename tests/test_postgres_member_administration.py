"""Owned PostgreSQL 0022/0023 member directory and lifecycle: list, suspend, reactivate, last-admin guard."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import sys
import threading
import time
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
from postgres_support import (ORG_A, ORG_B, MEMBER_A, MEMBER_B, ALICE, CAROL, connect,
    owned_gateway_catalog_admin_extension)
from forge.account_api import create_account_app
from forge.account_readiness import catalog_fingerprint
from forge.accounts import ACCOUNT_ISSUER
from forge.dev_accounts import MIGRATIONS
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS
from forge.directory import DirectoryDenied, DirectoryLastAdmin, DirectoryService, DirectorySuspended
from forge.directory_store import PostgresDirectoryStore
from forge.mvp_profile import (F20, F21, F22, F23, DEPARTMENT_MIGRATION, DIRECTORY_MIGRATION,
    MEMBER_DIRECTORY_MIGRATION, MEMBER_LIFECYCLE_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS, ORIGIN_MIGRATION)

MEMBER_C = UUID(int=23)
SAM, SAM_MEMBER, LEGAL = UUID(int=31), UUID(int=33), UUID(int=901)
FUNCTIONS_0022 = ('forge.directory_members(text,uuid)', 'forge.directory_member_rows(uuid,uuid)')
FUNCTIONS_0023 = ('forge.directory_member_status(text,uuid,uuid,text)',)
ORG_READ_TABLES = ('memberships', 'membership_roles', 'membership_departments', 'owned_accounts')


class MvpProfileTests(unittest.TestCase):
    def test_profile_appends_the_member_migrations_and_checkpoints(self):
        self.assertEqual(MVP_ADDITIONS[len(ADDITIONS) + 3:len(ADDITIONS) + 5],
                         ('0022_member_directory.sql', '0023_member_lifecycle.sql'))
        self.assertEqual(MVP_CHECKPOINTS[:len(CHECKPOINTS) + 5], (*CHECKPOINTS, directory_tests.F19, F20, F21, F22, F23))
        self.assertRegex(F22 or '', r'^[0-9a-f]{64}$', 'F22 must be pinned')
        self.assertRegex(F23 or '', r'^[0-9a-f]{64}$', 'F23 must be pinned')
        self.assertEqual(len({F20, F21, F22, F23}), 4)


class LifecycleFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0020-0023 == upgrade from 0022, pinned as F23 (runs before shared fixtures)."""
    prefix = (*MIGRATIONS, *ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION,
              MEMBER_DIRECTORY_MIGRATION)

    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def drop_authority(self):
        with connect() as admin:
            admin.execute('DROP ROLE IF EXISTS forge_directory_authority')

    def test_fresh_apply_and_upgrade_from_0022_share_the_pinned_fingerprint(self):
        with separate_database() as conn:
            for name in (*self.prefix, MEMBER_LIFECYCLE_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        self.drop_authority()
        with separate_database() as conn:
            for name in self.prefix:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F22)
            organization, identity, member = uuid4(), uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','u')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'suspended')", (organization, member, identity))
            before = conn.execute('SELECT * FROM forge.memberships').fetchall()
            conn.execute(migration_text(MEMBER_LIFECYCLE_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.memberships').fetchall(), before)
            upgraded = self.fingerprint(conn)
        self.drop_authority()
        print('Reviewed PG17 0023 member lifecycle checkpoint F23:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0022 must be identical')
        self.assertEqual(fresh, F23, 'F23 must be pinned to the reviewed value')
        self.assertNotIn(fresh, (*CHECKPOINTS, directory_tests.F19, F20, F21, F22))


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
    def fixture(self, *, migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION, MEMBER_DIRECTORY_MIGRATION,
                                     MEMBER_LIFECYCLE_MIGRATION)):
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
        if admin.execute("SELECT to_regprocedure('forge.directory_member_status(text,uuid,uuid,text)')").fetchone()[0]:
            for signature in FUNCTIONS_0023:
                admin.execute('DROP FUNCTION ' + signature)
            admin.execute('DROP POLICY directory_member_update ON forge.memberships')
            admin.execute('DROP POLICY directory_session_read ON forge.account_sessions')
            admin.execute('DROP POLICY directory_session_revoke ON forge.account_sessions')
        if admin.execute("SELECT to_regprocedure('forge.directory_members(text,uuid)')").fetchone()[0]:
            for signature in FUNCTIONS_0022:
                admin.execute('DROP FUNCTION ' + signature)
            for table in ORG_READ_TABLES:
                admin.execute('DROP POLICY directory_org_read ON forge.' + table)
        self.unwind_directory(admin)

    @contextmanager
    def seeded(self, admin, *, second_admin=False):
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
        if second_admin:
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (ORG_A, MEMBER_C))
        try:
            yield
        finally:
            admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id IN (%s,%s)",
                          (ORG_A, MEMBER_A, MEMBER_C))
            admin.execute('DELETE FROM forge.membership_departments')
            admin.execute('DELETE FROM forge.departments')
            admin.execute('DELETE FROM forge.membership_roles WHERE membership_id=%s', (SAM_MEMBER,))
            admin.execute('DELETE FROM forge.memberships WHERE id=%s', (SAM_MEMBER,))
            admin.execute('DELETE FROM forge.owned_accounts WHERE id=%s', (SAM,))
            admin.execute('DELETE FROM forge.identities WHERE id=%s', (SAM,))
            for org, member, role in ((ORG_A, MEMBER_C, 'member'), (ORG_A, MEMBER_C, 'organization_admin'),
                                      (ORG_B, MEMBER_B, 'organization_admin')):
                admin.execute('DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role=%s',
                              (org, member, role))

    def login(self, sessions, email):
        return sessions.login(email, upstream.PASSWORD).capability

    def status(self, admin, org, member):
        return admin.execute('SELECT status FROM forge.memberships WHERE organization_id=%s AND id=%s',
                             (org, member)).fetchone()[0]

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

    def test_non_admin_foreign_unknown_org_and_foreign_member_get_the_same_denial(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            member = self.login(sessions, 'member@example.com')
            foreign = self.login(sessions, 'foreign@example.com')
            # (actor, org, target): the first four also cannot list; the last two are a valid
            # admin of org A naming a member that does not exist there (unknown / org B's).
            cases = ((member, ORG_A, MEMBER_A), (foreign, ORG_A, MEMBER_A), (token, ORG_B, MEMBER_B),
                     (token, uuid4(), MEMBER_C), (member, ORG_A, MEMBER_C), (token, ORG_A, uuid4()),
                     (token, ORG_A, MEMBER_B))
            for actor, org, target in cases:
                with self.subTest(org=org, target=target):
                    with self.assertRaises(DirectoryDenied):
                        service.suspend_member(actor, org, target)
                    with self.assertRaises(DirectoryDenied):
                        service.reactivate_member(actor, org, target)
            for actor, org, _ in cases[:5]:
                with self.subTest(org=org, op='list'), self.assertRaises(DirectoryDenied):
                    service.members(actor, org)
            self.assertEqual(len(service.members(token, ORG_A)), 3)
            self.assertEqual([self.status(admin, *pair) for pair in ((ORG_A, MEMBER_A), (ORG_A, MEMBER_C), (ORG_B, MEMBER_B))],
                             ['active'] * 3)

    def test_suspend_revokes_sessions_and_reactivate_restores_access(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            member = self.login(sessions, 'member@example.com')
            other = self.login(sessions, 'foreign@example.com')

            class Ready:
                def check(self): return True
            app = create_account_app(sessions=sessions, readiness=Ready(), directory=service)
            headers = {'Authorization': 'Bearer ' + member}
            with TestClient(app, raise_server_exceptions=False) as client:
                self.assertEqual(client.get('/forge/v1/accounts/me', headers=headers).status_code, 200)
                suspended = service.suspend_member(token, ORG_A, MEMBER_C)
                self.assertEqual((suspended.id, suspended.status, suspended.email), (MEMBER_C, 'suspended', 'member@example.com'))
                self.assertEqual(self.status(admin, ORG_A, MEMBER_C), 'suspended')
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_sessions WHERE account_id=%s AND NOT revoked',
                                               (CAROL,)).fetchone(), (0,))
                self.assertEqual(client.get('/forge/v1/accounts/me', headers=headers).status_code, 401)
                # A fresh login works, but the suspended membership is denied, not empty.
                again = self.login(sessions, 'member@example.com')
                with self.assertRaises(DirectorySuspended):
                    service.me(again)
                self.assertEqual(client.get('/forge/v1/accounts/me', headers={'Authorization': 'Bearer ' + again}).status_code, 403)
                # Neither the admin's nor an unrelated account's session is touched.
                self.assertEqual(service.me(token).account.email, 'admin@example.com')
                self.assertEqual(service.me(other).account.email, 'foreign@example.com')
                reactivated = service.reactivate_member(token, ORG_A, MEMBER_C)
                self.assertEqual(reactivated.status, 'active')
                self.assertEqual([o.id for o in service.me(again).organizations], [ORG_A])
                self.assertEqual(client.get('/forge/v1/accounts/me', headers={'Authorization': 'Bearer ' + again}).status_code, 200)

    def test_suspend_and_reactivate_are_idempotent_and_touch_only_the_target(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            self.assertEqual(service.suspend_member(token, ORG_A, SAM_MEMBER).status, 'suspended')
            self.assertEqual(service.reactivate_member(token, ORG_A, SAM_MEMBER).status, 'active')
            self.assertEqual(service.reactivate_member(token, ORG_A, SAM_MEMBER).status, 'active')
            self.assertEqual(self.status(admin, ORG_A, MEMBER_C), 'active')
            self.assertEqual(self.status(admin, ORG_A, MEMBER_A), 'active')

    def test_the_last_active_admin_cannot_be_suspended_even_by_themselves(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            with self.assertRaises(DirectoryLastAdmin):
                service.suspend_member(token, ORG_A, MEMBER_A)
            self.assertEqual(self.status(admin, ORG_A, MEMBER_A), 'active')
            self.assertGreater(admin.execute('SELECT count(*) FROM forge.account_sessions WHERE account_id=%s AND NOT revoked',
                                             (ALICE,)).fetchone()[0], 0)
            self.assertEqual(service.me(token).account.email, 'admin@example.com')

    def test_with_two_admins_one_may_be_suspended_but_never_the_remaining_one(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin, second_admin=True):
            carol = self.login(sessions, 'member@example.com')
            self.assertEqual(service.suspend_member(token, ORG_A, MEMBER_C).status, 'suspended')
            with self.assertRaises(DirectoryLastAdmin):
                service.suspend_member(token, ORG_A, MEMBER_A)
            with self.assertRaises(DirectoryDenied):
                service.suspend_member(carol, ORG_A, MEMBER_A)
            self.assertEqual(self.status(admin, ORG_A, MEMBER_A), 'active')
            service.reactivate_member(token, ORG_A, MEMBER_C)
            self.assertEqual(service.suspend_member(token, ORG_A, MEMBER_A).status, 'suspended')
            self.assertEqual(self.status(admin, ORG_A, MEMBER_C), 'active')

    def test_concurrent_mutual_suspension_always_leaves_an_active_admin(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin, second_admin=True):
            carol = self.login(sessions, 'member@example.com')
            outcomes = {}
            barrier = threading.Barrier(2)

            def run(name, actor, target):
                try:
                    barrier.wait(5)
                    outcomes[name] = service.suspend_member(actor, ORG_A, target).status
                except Exception as error:
                    outcomes[name] = type(error)
            threads = [threading.Thread(target=run, args=('alice', token, MEMBER_C)),
                       threading.Thread(target=run, args=('carol', carol, MEMBER_A))]
            started = time.monotonic()
            with admin.transaction():
                # Hold both administrator rows so both calls pass their first check and then queue:
                # without row locking inside the function both would commit and zero admins would remain.
                admin.execute('SELECT id FROM forge.memberships WHERE organization_id=%s AND id IN (%s,%s) '
                              'ORDER BY id FOR UPDATE', (ORG_A, MEMBER_A, MEMBER_C))
                for thread in threads:
                    thread.start()
                time.sleep(0.5)
            for thread in threads:
                thread.join(10)
            self.assertGreaterEqual(time.monotonic() - started, 0.5)
            self.assertEqual(list(outcomes.values()).count('suspended'), 1, outcomes)
            failed = [v for v in outcomes.values() if v != 'suspended']
            self.assertEqual(len(failed), 1, outcomes)
            self.assertIn(failed[0], (DirectoryLastAdmin, DirectoryDenied))
            active = admin.execute("SELECT count(*) FROM forge.memberships m JOIN forge.membership_roles r "
                                   "ON r.organization_id=m.organization_id AND r.membership_id=m.id "
                                   "AND r.role='organization_admin' WHERE m.organization_id=%s AND m.status='active'",
                                   (ORG_A,)).fetchone()
            self.assertEqual(active, (1,))

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
                suspended = client.post(base + '/' + str(MEMBER_C) + '/suspend', headers=headers)
                self.assertEqual((suspended.status_code, suspended.json()['status']), (200, 'suspended'))
                last = client.post(base + '/' + str(MEMBER_A) + '/suspend', headers=headers)
                self.assertEqual((last.status_code, last.json()['error']['code']), (409, 'LAST_ADMIN'))
                self.assertEqual(client.post(base + '/' + str(uuid4()) + '/suspend', headers=headers).status_code, 404)
                reactivated = client.post(base + '/' + str(MEMBER_C) + '/reactivate', headers=headers)
                self.assertEqual((reactivated.status_code, reactivated.json()['status']), (200, 'active'))

    def test_member_functions_are_service_only_and_hold_no_table_level_write(self):
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

    def test_lifecycle_function_and_column_grants_are_narrow(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            for signature, expected in (('forge.directory_member_status(text,uuid,uuid,text)', True),):
                for role, allowed in (('forge_gateway_service', expected), ('forge_account_service', False), ('public', False)):
                    self.assertEqual(admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(),
                                     (allowed,), (signature, role))
                self.assertEqual(admin.execute('SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid=%s::regprocedure',
                                               (signature,)).fetchone(), ('forge_directory_authority',))

            def column(table, name, privilege):
                return admin.execute('SELECT has_column_privilege(%s,%s,%s,%s)',
                                     ('forge_directory_authority', 'forge.' + table, name, privilege)).fetchone()[0]
            self.assertTrue(column('memberships', 'status', 'UPDATE'))
            for name in ('organization_id', 'id', 'identity_id', 'revision'):
                self.assertFalse(column('memberships', name, 'UPDATE'), name)
            self.assertTrue(column('account_sessions', 'revoked', 'UPDATE'))
            for name in ('capability_hash', 'account_id', 'expires_at'):
                self.assertFalse(column('account_sessions', name, 'UPDATE'), name)
            self.assertFalse(column('account_sessions', 'capability_hash', 'SELECT'))
            for privilege in ('INSERT', 'DELETE'):
                for table in ('memberships', 'account_sessions', 'membership_roles'):
                    self.assertFalse(admin.execute('SELECT has_table_privilege(%s,%s,%s)',
                                                   ('forge_directory_authority', 'forge.' + table, privilege)).fetchone()[0],
                                     (table, privilege))
            self.assertFalse(admin.execute("SELECT has_column_privilege('forge_directory_authority','forge.owned_accounts','password_hash','SELECT')").fetchone()[0])

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
                    admin.execute('UPDATE forge.memberships SET identity_id=identity_id')

    def test_rls_limits_writes_to_the_pinned_organization_and_account(self):
        with self.fixture() as (admin, pools, sessions, token, service, store), self.seeded(admin):
            self.login(sessions, 'member@example.com')
            in_org_a = admin.execute('SELECT count(*) FROM forge.memberships WHERE organization_id=%s', (ORG_A,)).fetchone()
            self.assertGreater(in_org_a[0], 3, 'baseline also holds memberships without an owned account')
            with admin.transaction():
                admin.execute('SET LOCAL ROLE forge_directory_authority')
                # No context: nothing readable or writable.
                self.assertEqual(admin.execute("UPDATE forge.memberships SET status='suspended'").rowcount, 0)
                self.assertEqual(admin.execute('UPDATE forge.account_sessions SET revoked=true').rowcount, 0)
                admin.execute("SELECT set_config('forge.directory_org',%s,true)", (str(ORG_A),))
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), in_org_a)
                self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone(), (3,))
                # Org context alone never reaches another organization or any session.
                self.assertEqual(admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s",
                                               (ORG_B,)).rowcount, 0)
                self.assertEqual(admin.execute('UPDATE forge.account_sessions SET revoked=true').rowcount, 0)
                with self.assertRaises(errors.InsufficientPrivilege):
                    admin.execute("UPDATE forge.memberships SET identity_id=identity_id")
            with admin.transaction():
                admin.execute('SET LOCAL ROLE forge_directory_authority')
                admin.execute("SELECT set_config('forge.directory_target',%s,true)", (str(CAROL),))
                self.assertEqual(admin.execute('UPDATE forge.account_sessions SET revoked=true').rowcount, 1)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_sessions WHERE NOT revoked AND account_id=%s',
                                           (CAROL,)).fetchone(), (0,))

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

    def test_failed_0023_rolls_back_to_the_0022_profile(self):
        with self.fixture(migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION, MEMBER_DIRECTORY_MIGRATION)) as (
                admin, pools, sessions, token, service, store):
            text = migration_text(MEMBER_LIFECYCLE_MIGRATION)
            self.assertTrue(text.endswith('COMMIT;\n'))
            with self.assertRaises(errors.DivisionByZero):
                admin.execute(text[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            admin.execute('ROLLBACK')
            self.assertIsNone(admin.execute("SELECT to_regprocedure('forge.directory_member_status(text,uuid,uuid,text)')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_policies WHERE policyname LIKE 'directory_session%'").fetchone(), (0,))
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F22)

    def test_migrated_schema_fingerprint_is_the_pinned_f22(self):
        with self.fixture(migrations=(DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION, MEMBER_DIRECTORY_MIGRATION)) as (
                admin, pools, sessions, token, service, store):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F22)

    def test_migrated_schema_fingerprint_is_the_pinned_f23(self):
        with self.fixture() as (admin, pools, sessions, token, service, store):
            with admin.cursor() as cursor:
                self.assertEqual(catalog_fingerprint(cursor), F23)


if __name__ == '__main__':
    unittest.main()
