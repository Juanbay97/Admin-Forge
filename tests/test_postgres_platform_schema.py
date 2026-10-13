"""Owned PostgreSQL 0028 platform scope: roles, direct-access denial, owner-only DEFINER functions, append-only audit."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F27, F28, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, PLATFORM_SCOPE_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import mvp_database
from platform_support import PLATFORM_ROLES, add_account, add_owner, call, refusal, sign_in
from postgres_support import connect
from test_postgres_gateway_origin import migration_text, separate_database

SERVICE_FUNCTIONS = ('forge.platform_me(text)', 'forge.platform_company_list(text,text,integer)',
                     'forge.platform_company_get(text,uuid)', 'forge.platform_audit_page(text,bigint,integer)',
                     'forge.platform_company_create(text,uuid,uuid,uuid,uuid,text,text,text,text,text,text,integer)',
                     'forge.platform_company_set_active(text,uuid,boolean)', 'forge.platform_company_branding_read(text,uuid)',
                     'forge.platform_company_branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text)')
INTERNAL_FUNCTIONS = ('forge.platform_lock_owner(text,boolean)', 'forge.platform_audit_write(uuid,text,uuid)',
                      'forge.platform_owner_exists(uuid)')
AUTHORITY_GRANTS = {('organizations', 'SELECT'), ('memberships', 'SELECT'), ('identities', 'SELECT'),
                    ('platform_roles', 'SELECT'), ('platform_audit_log', 'SELECT'), ('platform_audit_log', 'INSERT'),
                    # 0029: the second factor's own tables (nothing else is added to the authority)
                    ('platform_totp', 'SELECT'), ('platform_totp', 'INSERT'), ('platform_totp', 'UPDATE'),
                    ('platform_recovery_codes', 'SELECT'), ('platform_recovery_codes', 'INSERT'),
                    ('platform_recovery_codes', 'UPDATE'), ('platform_recovery_codes', 'DELETE'),
                    ('platform_mfa_sessions', 'SELECT'), ('platform_mfa_sessions', 'INSERT'), ('platform_mfa_sessions', 'UPDATE'),
                    # 0030: the four rows of a new company, written only for the organization a function names
                    ('organizations', 'INSERT'), ('configuration_revisions', 'INSERT'), ('departments', 'INSERT'),
                    ('account_invitations', 'INSERT')}
PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')


def drop_platform_roles():
    with connect() as admin:
        for role in (*PLATFORM_ROLES, 'forge_branding_authority', 'forge_branding_service', 'forge_directory_authority'):
            admin.execute('DROP ROLE IF EXISTS ' + role)


class PlatformProfileTests(unittest.TestCase):
    """No database: the profile appends 0028 and its own pinned checkpoint after 0027."""
    def test_0028_follows_0027_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_SCOPE_MIGRATION, '0028_platform_scope.sql')
        self.assertEqual(MVP_ADDITIONS[-5:-3], ('0027_gateway_origin_config.sql', PLATFORM_SCOPE_MIGRATION))
        self.assertEqual(MVP_CHECKPOINTS[-5:-3], (F27, F28))
        self.assertRegex(F28 or '', r'^[0-9a-f]{64}$', 'F28 must be pinned')
        self.assertNotEqual(F28, F27)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class PlatformFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0028 == upgrade from the 0027 profile, pinned as F28; the upgrade keeps existing organizations."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0027_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:-4])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_SCOPE_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
            self.assertEqual(conn.execute("SELECT rolname,rolcanlogin FROM pg_roles WHERE rolname LIKE 'forge_platform_%' "
                                          'ORDER BY rolname').fetchall(),
                             [('forge_platform_authority', False), ('forge_platform_service', False)])
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F27)
            organization = uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
            before = conn.execute('SELECT * FROM forge.organizations').fetchall()
            conn.execute(migration_text(PLATFORM_SCOPE_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.organizations').fetchall(), before)
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0028 platform scope checkpoint F28:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0027 must be identical')
        self.assertEqual(fresh, F28, 'F28 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F27)


class PlatformRoleTests(unittest.TestCase):
    def test_both_roles_are_unprivileged_never_bypass_rls_and_belong_to_no_group(self):
        with mvp_database() as db:
            rows = db.admin.execute(
                'SELECT rolname,rolsuper,rolinherit,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,'
                '(SELECT count(*) FROM pg_auth_members WHERE member=r.oid OR roleid=r.oid) FROM pg_roles r '
                "WHERE rolname LIKE 'forge_platform_%' ORDER BY rolname").fetchall()
            self.assertEqual(rows, [('forge_platform_authority', False, False, False, False, False, False, 0),
                                    ('forge_platform_service', False, False, False, False, False, False, 0)])
            logins = dict(db.admin.execute("SELECT rolname,rolcanlogin FROM pg_roles WHERE rolname LIKE 'forge_platform_%'").fetchall())
            self.assertEqual(logins, {'forge_platform_authority': False, 'forge_platform_service': True},
                             'the authority never logs in; the harness gives the service role its LOGIN like the others')

    def test_the_service_pool_role_holds_no_privilege_on_any_table_or_sequence_in_the_schema(self):
        with mvp_database() as db:
            tables = [row[0] for row in db.admin.execute(
                "SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' AND c.relkind IN ('r','p','v','m')").fetchall()]
            self.assertGreaterEqual(len(tables), 30, 'the whole forge schema is covered, not a hand-picked list')
            for table in tables:
                for privilege in PRIVILEGES:
                    self.assertFalse(db.admin.execute('SELECT has_table_privilege(%s,%s,%s)',
                                                      ('forge_platform_service', table, privilege)).fetchone()[0],
                                     (table, privilege))
            for sequence in [row[0] for row in db.admin.execute(
                    "SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='forge' AND c.relkind='S'").fetchall()]:
                for privilege in ('USAGE', 'SELECT', 'UPDATE'):
                    self.assertFalse(db.admin.execute('SELECT has_sequence_privilege(%s,%s,%s)',
                                                      ('forge_platform_service', sequence, privilege)).fetchone()[0])
            for check in ("SELECT has_schema_privilege('forge_platform_service','forge','CREATE')",
                          "SELECT has_database_privilege('forge_platform_service',current_database(),'CREATE')",
                          "SELECT has_database_privilege('forge_platform_service',current_database(),'TEMP')"):
                self.assertEqual(db.admin.execute(check).fetchone(), (False,), check)

    def test_a_direct_select_on_a_tenant_table_is_denied_to_the_service_pool(self):
        with mvp_database() as db:
            for table in ('forge.memberships', 'forge.organizations', 'forge.identities', 'forge.account_invitations',
                          'forge.platform_roles', 'forge.platform_audit_log', 'forge.owned_accounts'):
                with self.subTest(table=table), self.assertRaises(errors.InsufficientPrivilege):
                    call(db, 'SELECT * FROM ' + table)

    def test_the_authority_holds_exactly_the_reviewed_grants_and_nothing_on_other_tenant_data(self):
        with mvp_database() as db:
            tables = [row[0] for row in db.admin.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' AND c.relkind IN ('r','p','v','m')").fetchall()]
            granted = {(table, privilege) for table in tables for privilege in PRIVILEGES
                       if db.admin.execute('SELECT has_table_privilege(%s,%s,%s)',
                                           ('forge_platform_authority', 'forge.' + table, privilege)).fetchone()[0]}
            self.assertEqual(granted, AUTHORITY_GRANTS)

    def test_row_level_security_is_enabled_and_forced_on_both_platform_tables(self):
        with mvp_database() as db:
            rows = db.admin.execute("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class c JOIN pg_namespace n "
                                    "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND relname IN "
                                    "('platform_roles','platform_audit_log') ORDER BY relname").fetchall()
            self.assertEqual(rows, [('platform_audit_log', True, True), ('platform_roles', True, True)])

    def test_each_function_is_definer_owned_by_the_authority_and_only_the_public_surface_is_executable_by_the_service(self):
        with mvp_database() as db:
            owner = 'SELECT pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig FROM pg_proc p WHERE p.oid=%s::regprocedure'
            execute = "SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')"
            for signature in (*SERVICE_FUNCTIONS, *INTERNAL_FUNCTIONS):
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute(owner, (signature,)).fetchone(),
                                     ('forge_platform_authority', True, ['search_path=pg_catalog']))
                    expected = {'forge_platform_service': signature in SERVICE_FUNCTIONS, 'public': False,
                                'forge_account_service': False, 'forge_enrollment': False, 'forge_runtime': False,
                                'forge_gateway_service': False, 'forge_branding_service': False}
                    for role, allowed in expected.items():
                        self.assertEqual(db.admin.execute(execute, (role, signature)).fetchone(), (allowed,), role)
            self.assertEqual(db.admin.execute("SELECT has_schema_privilege('forge_platform_authority','forge','CREATE')").fetchone(),
                             (False,), 'the temporary schema grant is revoked again')


class PlatformFunctionTests(unittest.TestCase):
    def world(self, db):
        results = provision(db.admin, SEED, lambda created: None)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.admins = {result.slug: result.accounts[0] for result in results}
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=True)

    def test_the_owner_reads_its_own_identity_and_every_other_caller_is_denied_the_same_way(self):
        with mvp_database() as db:
            self.world(db)
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_me(%s)', (self.digest,)), [(self.owner, 'platform_owner')])
            _, admin_digest = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            for digest in (admin_digest, '0' * 64, 'not-a-digest', None):
                with self.subTest(digest=digest):
                    self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_me(%s)', (digest,))),
                                     'PLATFORM_DENIED')

    def test_an_organization_admin_without_a_platform_role_is_denied_every_platform_function(self):
        with mvp_database() as db:
            self.world(db)
            _, digest = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            for text, params in (('SELECT * FROM forge.platform_company_list(%s,NULL,10)', (digest,)),
                                 ('SELECT * FROM forge.platform_company_get(%s,%s)', (digest, self.orgs['org-a'])),
                                 ('SELECT * FROM forge.platform_audit_page(%s,NULL,10)', (digest,))):
                with self.subTest(text=text):
                    self.assertEqual(refusal(self, lambda: call(db, text, params)), 'PLATFORM_DENIED')

    def test_a_viewer_role_may_identify_itself_but_not_use_the_owner_operations(self):
        with mvp_database() as db:
            self.world(db)
            add_owner(db.admin, 'viewer@platform.test', 'platform_viewer')
            _, digest = sign_in(db, 'viewer@platform.test')
            self.assertEqual(call(db, 'SELECT role FROM forge.platform_me(%s)', (digest,)), [('platform_viewer',)])
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_company_list(%s,NULL,10)', (digest,))),
                             'PLATFORM_DENIED')

    def test_a_revoked_or_disabled_owner_session_is_denied(self):
        with mvp_database() as db:
            self.world(db)
            db.admin.execute('UPDATE forge.account_sessions SET revoked=true')
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_me(%s)', (self.digest,))), 'PLATFORM_DENIED')
            _, second = sign_in(db, mfa=True)
            self.assertEqual(call(db, 'SELECT role FROM forge.platform_me(%s)', (second,)), [('platform_owner',)])
            db.admin.execute('UPDATE forge.owned_accounts SET active=false WHERE id=%s', (self.owner,))
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_me(%s)', (second,))), 'PLATFORM_DENIED')

    def test_the_owner_lists_every_company_in_slug_order_with_a_bounded_cursor(self):
        with mvp_database() as db:
            self.world(db)
            rows = call(db, 'SELECT * FROM forge.platform_company_list(%s,NULL,10)', (self.digest,))
            self.assertEqual(rows, [(self.orgs['org-a'], 'org-a', 'Organization A', True),
                                    (self.orgs['org-b'], 'org-b', 'Organization B', True)])
            self.assertEqual(call(db, 'SELECT slug FROM forge.platform_company_list(%s,NULL,1)', (self.digest,)), [('org-a',)])
            self.assertEqual(call(db, 'SELECT slug FROM forge.platform_company_list(%s,%s,1)', (self.digest, 'org-a')), [('org-b',)])
            self.assertEqual(call(db, 'SELECT slug FROM forge.platform_company_list(%s,%s,5)', (self.digest, 'org-b')), [])
            for page in (0, 101, -1, None):
                with self.subTest(page=page):
                    self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_company_list(%s,NULL,%s)',
                                                                (self.digest, page))), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_company_list(%s,%s,5)',
                                                        (self.digest, 'x' * 64))), 'PLATFORM_INVALID')
            db.admin.execute("UPDATE forge.organizations SET active=false WHERE slug='org-b'")
            self.assertEqual(call(db, 'SELECT slug,active FROM forge.platform_company_list(%s,NULL,10)', (self.digest,)),
                             [('org-a', True), ('org-b', False)])

    def test_getting_one_company_returns_exactly_that_company_and_never_a_neighbour(self):
        with mvp_database() as db:
            self.world(db)
            for slug, other in (('org-a', 'org-b'), ('org-b', 'org-a')):
                with self.subTest(slug=slug):
                    rows = call(db, 'SELECT * FROM forge.platform_company_get(%s,%s)', (self.digest, self.orgs[slug]))
                    self.assertEqual(rows, [(self.orgs[slug], slug, 'Organization ' + slug[-1].upper(), True)])
                    self.assertNotIn(self.orgs[other], [row[0] for row in rows])
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_company_get(%s,%s)', (self.digest, uuid4())), [])
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_company_get(%s,NULL)', (self.digest,)), [])

    def test_the_organization_context_set_by_a_call_does_not_survive_into_the_next_transaction(self):
        with mvp_database() as db:
            self.world(db)
            with db.pool('forge_platform_service').connection() as connection:
                connection.execute('SELECT * FROM forge.platform_company_get(%s,%s)', (self.digest, self.orgs['org-a']))
                self.assertEqual(connection.execute("SELECT coalesce(current_setting('forge.organization',true),'')").fetchone(), ('',))
                with self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute('SELECT * FROM forge.organizations')


class PlatformAuditTests(unittest.TestCase):
    def audit(self, db, actor, action, organization=None):
        return db.admin.execute('SELECT forge.platform_audit_write(%s,%s,%s)', (actor, action, organization)).fetchone()

    def test_the_audit_table_has_only_non_secret_columns_and_a_finite_action_list(self):
        with mvp_database() as db:
            columns = db.admin.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='forge' "
                                       "AND table_name='platform_audit_log' ORDER BY ordinal_position").fetchall()
            self.assertEqual([name for (name,) in columns], ['id', 'actor_id', 'action', 'organization_id', 'recorded_at'])
            owner = add_owner(db.admin)
            for action in ('company.created', 'company.suspended', 'company.reactivated', 'company.branding_saved',
                           'owner.mfa_enrolled', 'owner.mfa_recovery_used'):
                self.audit(db, owner, action)
            for action in ('company.deleted', '', 'x' * 200, None):
                with self.subTest(action=action), self.assertRaises((errors.CheckViolation, errors.NotNullViolation)):
                    self.audit(db, owner, action)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_audit_log').fetchone(), (6,))

    def test_no_role_can_update_or_delete_an_audit_row_and_the_service_cannot_write_one(self):
        with mvp_database() as db:
            owner = add_owner(db.admin)
            self.audit(db, owner, 'company.created')
            for role in ('forge_platform_authority', 'forge_platform_service', 'forge_runtime', 'forge_account_service',
                         'forge_enrollment_authority', 'forge_gateway_authority', 'forge_branding_authority'):
                for statement in ("UPDATE forge.platform_audit_log SET action='company.suspended'",
                                  'DELETE FROM forge.platform_audit_log', 'TRUNCATE forge.platform_audit_log'):
                    with self.subTest(role=role, statement=statement):
                        db.admin.execute('SET ROLE ' + role)
                        try:
                            with self.assertRaises(errors.InsufficientPrivilege):
                                db.admin.execute(statement)
                        finally:
                            db.admin.execute('RESET ROLE')
            db.admin.execute('SET ROLE forge_platform_service')
            try:
                with self.assertRaises(errors.InsufficientPrivilege):
                    db.admin.execute("INSERT INTO forge.platform_audit_log(actor_id,action) VALUES(gen_random_uuid(),'company.created')")
                with self.assertRaises(errors.InsufficientPrivilege):
                    db.admin.execute('SELECT forge.platform_audit_write(gen_random_uuid(),%s,NULL)', ('company.created',))
            finally:
                db.admin.execute('RESET ROLE')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_audit_log').fetchone(), (1,))

    def test_the_owner_pages_the_log_newest_first_with_a_bounded_page_and_a_cursor(self):
        with mvp_database() as db:
            owner = add_owner(db.admin)
            token, digest = sign_in(db, mfa=True)
            org = provision(db.admin, SEED[:1], lambda created: None)[0].organization_id
            for action in ('company.created', 'company.suspended', 'company.reactivated'):
                self.audit(db, owner, action, org)
            rows = call(db, 'SELECT * FROM forge.platform_audit_page(%s,NULL,2)', (digest,))
            self.assertEqual([(row[1], row[2], row[3]) for row in rows],
                             [(owner, 'company.reactivated', org), (owner, 'company.suspended', org)])
            self.assertGreater(rows[0][0], rows[1][0])
            older = call(db, 'SELECT action FROM forge.platform_audit_page(%s,%s,5)', (digest, rows[1][0]))
            self.assertEqual(older, [('company.created',)])
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_audit_page(%s,%s,5)', (digest, 1)), [])
            for page in (0, 101, None):
                with self.subTest(page=page):
                    self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_audit_page(%s,NULL,%s)',
                                                                (digest, page))), 'PLATFORM_INVALID')

    def test_a_company_admin_cannot_read_the_log(self):
        with mvp_database() as db:
            owner = add_owner(db.admin)
            self.audit(db, owner, 'company.created')
            admin = provision(db.admin, SEED[:1], lambda created: None)[0].accounts[0]
            _, digest = sign_in(db, admin.email, admin.password)
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_audit_page(%s,NULL,10)', (digest,))),
                             'PLATFORM_DENIED')

    def test_the_audit_row_needs_a_real_actor(self):
        with mvp_database() as db:
            with self.assertRaises(errors.ForeignKeyViolation):
                self.audit(db, uuid4(), 'company.created')
            account = add_account(db.admin, 'plain@platform.test')
            self.assertIsInstance(self.audit(db, account, 'company.created')[0], int)


if __name__ == '__main__':
    unittest.main()
