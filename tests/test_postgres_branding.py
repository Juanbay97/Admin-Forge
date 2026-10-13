"""Owned PostgreSQL 0025 org branding: schema profile, role isolation, RLS, CAS, audit trail, cross-org,
published-only asset delivery and the public company-code lookup."""
import hashlib
from pathlib import Path
import sys
import threading
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import psycopg
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.account_sessions import PostgresSessionStore, SessionService
from forge.dev_accounts import MIGRATIONS
from forge.invitations import capability_digest
from forge.mvp_profile import (F24, F25, F26, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, ORG_BRANDING_CODE_MIGRATION,
                              ORG_BRANDING_MIGRATION)
from forge.provisioning import SEED, provision
from mvp_support import mvp_database
from postgres_support import connect
from test_postgres_gateway_origin import migration_text, separate_database

TABLES = ('branding_assets', 'branding_codes', 'organization_branding', 'organization_branding_revisions')
LOGIN_ROLES = ('forge_account_service', 'forge_enrollment', 'forge_runtime', 'forge_gateway_service')
GATEWAY_FUNCTIONS = ('forge.branding_member_read(text,uuid)',
                     'forge.branding_save(text,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text)',
                     'forge.branding_asset_put(text,uuid,text,text,integer,integer,bytea)')
PUBLIC_FUNCTIONS = ('forge.branding_public_read(text)', 'forge.branding_asset_get(text)')
THEME = ('Acme Labs', 'Welcome to Acme.', '#0B1D26', '#E07A2D', '#E8DCC1', 'montserrat', 'inter')
DEFAULT_THEME = ('Prometheon Forge', 'Sign in to your Forge workspace.', '#0B1D26', '#E07A2D', '#E8DCC1',
                 'montserrat', 'inter')


def drop_authorities():
    with connect() as admin:
        for role in ('forge_branding_authority', 'forge_branding_service', 'forge_directory_authority',
                 'forge_platform_authority', 'forge_platform_service'):
            admin.execute('DROP ROLE IF EXISTS ' + role)


class BrandingProfileTests(unittest.TestCase):
    def test_profile_appends_the_branding_migrations_and_checkpoints(self):
        self.assertEqual(ORG_BRANDING_MIGRATION, '0025_org_branding.sql')
        self.assertEqual(ORG_BRANDING_CODE_MIGRATION, '0026_branding_member_code.sql')
        self.assertEqual(MVP_ADDITIONS[-7:-5], (ORG_BRANDING_MIGRATION, ORG_BRANDING_CODE_MIGRATION))
        self.assertEqual(MVP_CHECKPOINTS[-8:-5], (F24, F25, F26))
        for pinned in (F25, F26):
            self.assertRegex(pinned or '', r'^[0-9a-f]{64}$', 'checkpoints must be pinned')
        self.assertNotEqual(F25, F24)
        self.assertNotEqual(F26, F25)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class BrandingFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0025 == upgrade from the 0024 profile, pinned as F25 (runs before shared fixtures)."""

    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0024_share_the_pinned_fingerprint(self):
        prefix = (*MIGRATIONS, *MVP_ADDITIONS[:-7])
        with separate_database() as conn:
            for name in (*prefix, ORG_BRANDING_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
            self.assertEqual(conn.execute("SELECT rolname,rolcanlogin FROM pg_roles WHERE rolname LIKE 'forge_branding_%' "
                                          "ORDER BY rolname").fetchall(),
                             [('forge_branding_authority', False), ('forge_branding_service', False)])
        drop_authorities()
        with separate_database() as conn:
            for name in prefix:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F24)
            organization, identity = uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','u')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
            before = conn.execute('SELECT * FROM forge.organizations').fetchall()
            conn.execute(migration_text(ORG_BRANDING_MIGRATION))
            self.assertEqual(conn.execute('SELECT * FROM forge.organizations').fetchall(), before)
            self.assertEqual(conn.execute('SELECT count(*) FROM forge.organization_branding').fetchone(), (0,))
            self.assertEqual(conn.execute('SELECT organization_id,slug,active FROM forge.branding_codes').fetchall(),
                             [(organization, 'up', True)], 'existing organizations are indexed by the migration')
            upgraded = self.fingerprint(conn)
        drop_authorities()
        print('Reviewed PG17 0025 org branding checkpoint F25:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0024 must be identical')
        self.assertEqual(fresh, F25, 'F25 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F24)


class BrandingCodeFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0026 == upgrade from the 0025 profile, pinned as F26; the upgrade keeps saved branding."""

    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0025_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:-6])
        with separate_database() as conn:
            for name in (*previous, ORG_BRANDING_CODE_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_authorities()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F25)
            organization, identity = uuid4(), uuid4()
            with conn.transaction():
                conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'test','issuer','u')", (identity,))
                conn.execute("INSERT INTO forge.organizations VALUES(%s,'up','Up',true,1)", (organization,))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
                conn.execute("INSERT INTO forge.organization_branding(organization_id,revision,name,login_copy,primary_color,"
                             "accent_color,tint_color,heading_font,body_font,updated_by) "
                             "VALUES(%s,1,'Up Co','Hi','#0B1D26','#E07A2D','#E8DCC1','inter','inter',%s)", (organization, identity))
            conn.execute(migration_text(ORG_BRANDING_CODE_MIGRATION))
            self.assertEqual(conn.execute('SELECT name FROM forge.organization_branding').fetchall(), [('Up Co',)])
            self.assertEqual(conn.execute('SELECT slug FROM forge.branding_codes').fetchall(), [('up',)])
            upgraded = self.fingerprint(conn)
        drop_authorities()
        print('Reviewed PG17 0026 branding member code checkpoint F26:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0025 must be identical')
        self.assertEqual(fresh, F26, 'F26 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F25)


def refusal(test, call):
    with test.assertRaises(errors.RaiseException) as caught:
        call()
    return caught.exception.diag.message_primary


class PostgresBrandingSchemaTests(unittest.TestCase):
    def test_roles_are_nologin_unprivileged_and_not_members_of_anything(self):
        with mvp_database() as db:
            rows = db.admin.execute(
                "SELECT rolname,rolcanlogin,rolsuper,rolinherit,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,"
                "(SELECT count(*) FROM pg_auth_members WHERE member=r.oid OR roleid=r.oid) FROM pg_roles r "
                "WHERE rolname IN ('forge_branding_authority','forge_branding_service') ORDER BY rolname").fetchall()
            # The migration creates both NOLOGIN (checked in the gate test); the harness gives the service role,
            # like the other service roles, its LOGIN password afterwards. The authority never logs in.
            self.assertEqual(rows, [('forge_branding_authority', False, False, False, False, False, False, False, 0),
                                    ('forge_branding_service', True, False, False, False, False, False, False, 0)])

    def test_no_service_role_can_touch_a_branding_table_and_the_authority_cannot_rewrite_history(self):
        with mvp_database() as db:
            check = "SELECT has_table_privilege(%s,%s,%s)"
            for table in TABLES:
                for role in ('public', *LOGIN_ROLES, 'forge_branding_service'):
                    for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        with self.subTest(table=table, role=role, privilege=privilege):
                            self.assertEqual(db.admin.execute(check, (role, 'forge.' + table, privilege)).fetchone(), (False,))
            granted = {(table, privilege): db.admin.execute(check, ('forge_branding_authority', 'forge.' + table, privilege)).fetchone()[0]
                       for table in TABLES for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')}
            self.assertEqual({key for key, value in granted.items() if value}, {
                ('branding_assets', 'SELECT'), ('branding_assets', 'INSERT'),
                ('organization_branding', 'SELECT'), ('organization_branding', 'INSERT'), ('organization_branding', 'UPDATE'),
                ('organization_branding_revisions', 'SELECT'), ('organization_branding_revisions', 'INSERT'),
                ('branding_codes', 'SELECT'), ('branding_codes', 'INSERT'), ('branding_codes', 'UPDATE'),
                ('branding_codes', 'DELETE')})

    def test_row_level_security_is_enabled_and_forced_on_every_table(self):
        with mvp_database() as db:
            rows = db.admin.execute("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class c JOIN pg_namespace n "
                                    "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND relname=ANY(%s) ORDER BY relname",
                                    (list(TABLES),)).fetchall()
            self.assertEqual(rows, [(table, True, True) for table in sorted(TABLES)])

    def test_each_function_is_security_definer_owned_by_the_authority_and_granted_to_one_service(self):
        with mvp_database() as db:
            query = ("SELECT pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig FROM pg_proc p WHERE p.oid=%s::regprocedure")
            exec_privilege = "SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')"
            for signature in (*GATEWAY_FUNCTIONS, *PUBLIC_FUNCTIONS):
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute(query, (signature,)).fetchone(),
                                     ('forge_branding_authority', True, ['search_path=pg_catalog']))
                    expected = {'forge_gateway_service': signature in GATEWAY_FUNCTIONS,
                                'forge_branding_service': signature in PUBLIC_FUNCTIONS, 'public': False,
                                'forge_account_service': False, 'forge_enrollment': False, 'forge_runtime': False}
                    for role, allowed in expected.items():
                        self.assertEqual(db.admin.execute(exec_privilege, (role, signature)).fetchone(), (allowed,), role)

    def test_the_public_service_role_reads_no_business_table_directly(self):
        with mvp_database() as db:
            db.admin.execute('SET ROLE forge_branding_service')
            try:
                for table in ('forge.organizations', 'forge.memberships', 'forge.organization_branding', 'forge.branding_assets'):
                    with self.subTest(table=table):
                        with self.assertRaises(errors.InsufficientPrivilege):
                            db.admin.execute('SELECT * FROM ' + table)
            finally:
                db.admin.execute('RESET ROLE')

    def test_check_constraints_refuse_hostile_rows_even_for_the_table_owner(self):
        with mvp_database() as db:
            (result,) = provision(db.admin, SEED[:1], lambda results: None)
            org = result.organization_id
            actor = db.admin.execute("SELECT id FROM forge.identities LIMIT 1").fetchone()[0]
            base = dict(name='Acme', login_copy='Hello', primary_color='#0B1D26', accent_color='#E07A2D',
                        tint_color='#E8DCC1', heading_font='inter', body_font='inter')
            hostile = [dict(name=''), dict(name='a' * 41), dict(name=' padded'), dict(name='a<b'), dict(name='a{b'), dict(name='a`b'),
                       dict(name='a\\b'), dict(name='a\nb'), dict(name='a\x07b'), dict(login_copy='x' * 281),
                       dict(login_copy='</style>'), dict(primary_color='#0b1d26'), dict(primary_color='red'),
                       dict(accent_color='#12'), dict(tint_color=''), dict(heading_font='Comic'), dict(body_font='inter,serif'),
                       dict(logo_light='a' * 64), dict(isotipo='b' * 64)]
            for change in hostile:
                with self.subTest(change=change):
                    values = {**base, **change}
                    with self.assertRaises((errors.CheckViolation, errors.ForeignKeyViolation)):
                        with db.admin.transaction():
                            db.admin.execute(
                                'INSERT INTO forge.organization_branding(organization_id,revision,name,login_copy,primary_color,'
                                'accent_color,tint_color,heading_font,body_font,logo_light,isotipo,updated_by) '
                                'VALUES(%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                (org, values['name'], values['login_copy'], values['primary_color'], values['accent_color'],
                                 values['tint_color'], values['heading_font'], values['body_font'], values.get('logo_light'),
                                 values.get('isotipo'), actor))
            body = b'logo-bytes'
            digest = hashlib.sha256(body).hexdigest()
            for media_type, width, height, payload, sha in (('image/svg+xml', 32, 32, body, digest), ('image/png', 15, 32, body, digest),
                                                            ('image/png', 32, 1025, body, digest), ('image/png', 32, 32, body, 'f' * 64),
                                                            ('image/png', 32, 32, b'', hashlib.sha256(b'').hexdigest()),
                                                            ('image/png', 32, 32, bytes(262145), hashlib.sha256(bytes(262145)).hexdigest())):
                with self.subTest(media_type=media_type, width=width, height=height, size=len(payload)):
                    with self.assertRaises(errors.CheckViolation):
                        with db.admin.transaction():
                            db.admin.execute('INSERT INTO forge.branding_assets(organization_id,sha256,content_type,width,height,body,created_by) '
                                             'VALUES(%s,%s,%s,%s,%s,%s,%s)', (org, sha, media_type, width, height, payload, actor))


class PostgresBrandingFunctionTests(unittest.TestCase):
    def world(self, db):
        """Orgs A and B (SEED) with their admins and members signed in; returns digests by name."""
        results = provision(db.admin, SEED, lambda results: None)
        sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
        self.sessions = sessions
        digests = {}
        for result in results:
            for account in result.accounts:
                digests[(result.slug, account.role)] = capability_digest(sessions.login(account.email, account.password).capability)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.actors = {(result.slug, account.role): db.admin.execute(
            'SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (account.email,)).fetchone()[0]
            for result in results for account in result.accounts}
        return digests

    def gateway(self, db, text, params):
        with db.pool('forge_gateway_service').connection() as conn:
            return conn.execute(text, params).fetchall()

    def service(self, db, text, params):
        db.admin.execute('SET ROLE forge_branding_service')
        try:
            return db.admin.execute(text, params).fetchall()
        finally:
            db.admin.execute('RESET ROLE')

    def save(self, db, digest, org, expected, change='save', theme=THEME, assets=(None, None, None)):
        return self.gateway(db, 'SELECT * FROM forge.branding_save(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                            (digest, org, expected, change, *theme, *assets))

    def put(self, db, digest, org, body, media_type='image/png', width=32, height=32, sha=None):
        sha = sha or hashlib.sha256(body).hexdigest()
        return self.gateway(db, 'SELECT forge.branding_asset_put(%s,%s,%s,%s,%s,%s,%s)',
                            (digest, org, sha, media_type, width, height, body))[0][0]

    def history(self, db, org):
        return db.admin.execute('SELECT revision,action,name,actor_id FROM forge.organization_branding_revisions '
                                'WHERE organization_id=%s ORDER BY revision', (org,)).fetchall()

    def test_an_unbranded_organization_reads_as_revision_zero_for_its_members_and_admins(self):
        with mvp_database() as db:
            digests = self.world(db)
            for role in ('member', 'organization_admin'):
                rows = self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,%s)', (digests[('org-a', role)], self.orgs['org-a']))
                self.assertEqual(rows, [(0, None, None, None, None, None, None, None, None, None, None, 'org-a')],
                                 'revision 0 still carries the company code employees type')

    def test_members_read_only_their_own_company_code_and_the_public_read_never_returns_it(self):
        with mvp_database() as db:
            digests = self.world(db)
            for slug in ('org-a', 'org-b'):
                for role in ('member', 'organization_admin'):
                    with self.subTest(slug=slug, role=role):
                        rows = self.gateway(db, 'SELECT code FROM forge.branding_member_read(%s,%s)',
                                            (digests[(slug, role)], self.orgs[slug]))
                        self.assertEqual(rows, [(slug,)])
            self.assertEqual(refusal(self, lambda: self.gateway(db, 'SELECT code FROM forge.branding_member_read(%s,%s)',
                                                                (digests[('org-a', 'member')], self.orgs['org-b']))),
                             'BRANDING_DENIED')
            self.save(db, digests[('org-a', 'organization_admin')], self.orgs['org-a'], 0)
            (result,) = db.admin.execute("SELECT pg_get_function_result('forge.branding_public_read(text)'::regprocedure)").fetchone()
            self.assertNotIn('code', result, 'the public lookup is keyed by the code and never echoes it')

    def test_save_is_admin_only_cas_and_leaves_an_audit_row_naming_the_actor(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            first = self.save(db, admin, org, 0)
            self.assertEqual(first, [(1, *THEME, None, None, None)])
            theme2 = ('Acme Two', '', '#123456', '#ABCDEF', '#FEDCBA', 'roboto', 'nunito-sans')
            self.assertEqual(self.save(db, admin, org, 1, theme=theme2)[0][:2], (2, 'Acme Two'))
            self.assertEqual(self.history(db, org), [(1, 'save', 'Acme Labs', self.actors[('org-a', 'organization_admin')]),
                                                     (2, 'save', 'Acme Two', self.actors[('org-a', 'organization_admin')])])
            member_view = self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,%s)', (digests[('org-a', 'member')], org))
            self.assertEqual(member_view, [(2, *theme2, None, None, None, 'org-a')])

    def test_stale_or_future_revisions_conflict_and_change_nothing(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            self.save(db, admin, org, 0)
            for expected in (0, 2, 7):
                with self.subTest(expected=expected):
                    self.assertEqual(refusal(self, lambda: self.save(db, admin, org, expected, theme=('Other', *THEME[1:]))), 'BRANDING_CONFLICT')
            self.assertEqual(db.admin.execute('SELECT revision,name FROM forge.organization_branding WHERE organization_id=%s', (org,)).fetchone(), (1, 'Acme Labs'))
            self.assertEqual(len(self.history(db, org)), 1)

    def test_invalid_values_are_refused_by_the_database_too_and_change_nothing(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            hostile = [('', *THEME[1:]), ('a' * 41, *THEME[1:]), ('<b>', *THEME[1:]), (THEME[0], 'x' * 281, *THEME[2:]),
                       (*THEME[:2], 'red', *THEME[3:]), (*THEME[:5], 'Comic', THEME[6]), (*THEME[:6], 'x;color:red')]
            for theme in hostile:
                with self.subTest(theme=theme):
                    self.assertEqual(refusal(self, lambda: self.save(db, admin, org, 0, theme=theme)), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.save(db, admin, org, 0, change='publish')), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.save(db, admin, org, -1)), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.save(db, admin, org, 0, assets=('c' * 64, None, None))), 'BRANDING_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_branding').fetchone(), (0,))
            self.assertEqual(self.history(db, org), [])

    def test_members_and_foreign_admins_are_denied_uniformly(self):
        with mvp_database() as db:
            digests = self.world(db)
            org_a, org_b = self.orgs['org-a'], self.orgs['org-b']
            member, admin_b = digests[('org-a', 'member')], digests[('org-b', 'organization_admin')]
            self.assertEqual(refusal(self, lambda: self.save(db, member, org_a, 0)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.save(db, admin_b, org_a, 0)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.save(db, digests[('org-a', 'organization_admin')], uuid4(), 0)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.save(db, '0' * 64, org_a, 0)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.save(db, 'not-a-digest', org_a, 0)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,%s)', (admin_b, org_a))), 'BRANDING_DENIED')
            self.assertEqual(refusal(self, lambda: self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,%s)', (member, org_b))), 'BRANDING_DENIED')
            self.assertEqual(refusal(self, lambda: self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,NULL)', (member,))), 'BRANDING_DENIED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_branding').fetchone(), (0,))

    def test_a_suspended_member_loses_access_to_the_member_projection(self):
        with mvp_database() as db:
            digests = self.world(db)
            org = self.orgs['org-a']
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND identity_id=%s",
                             (org, self.actors[('org-a', 'member')]))
            refused = refusal(self, lambda: self.gateway(db, 'SELECT * FROM forge.branding_member_read(%s,%s)',
                                                         (digests[('org-a', 'member')], org)))
            self.assertIn(refused, ('BRANDING_DENIED', 'DIRECTORY_DENIED'))

    def test_two_simultaneous_saves_of_the_same_revision_yield_exactly_one_winner(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            barrier, outcomes = threading.Barrier(2), []

            def attempt(name):
                barrier.wait(timeout=5)
                try:
                    self.save(db, admin, org, 0, theme=(name, *THEME[1:]))
                    outcomes.append('saved')
                except errors.RaiseException as error:
                    outcomes.append(error.diag.message_primary)
            threads = [threading.Thread(target=attempt, args=(name,)) for name in ('One', 'Two')]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
            self.assertEqual(sorted(outcomes), ['BRANDING_CONFLICT', 'saved'])
            self.assertEqual(len(self.history(db, org)), 1)

    def test_assets_are_stored_per_organization_and_referenced_only_by_the_same_organization(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin_a, admin_b = digests[('org-a', 'organization_admin')], digests[('org-b', 'organization_admin')]
            org_a, org_b = self.orgs['org-a'], self.orgs['org-b']
            logo = b'\x89PNG-fixture-bytes'
            sha = hashlib.sha256(logo).hexdigest()
            self.assertIs(self.put(db, admin_a, org_a, logo), True)
            self.assertIs(self.put(db, admin_a, org_a, logo), False, 'idempotent per hash')
            self.assertEqual(refusal(self, lambda: self.put(db, admin_b, org_a, logo)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.put(db, digests[('org-a', 'member')], org_a, b'm')), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.save(db, admin_b, org_b, 0, assets=(sha, None, None))), 'BRANDING_INVALID',
                             'org B cannot reference the logo org A uploaded')
            self.assertEqual(self.save(db, admin_a, org_a, 0, assets=(sha, None, sha))[0][-3:], (sha, None, sha))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.branding_assets').fetchone(), (1,))

    def test_asset_uploads_are_validated_by_the_database_and_capped_per_organization(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            self.assertEqual(refusal(self, lambda: self.put(db, admin, org, b'x', sha='e' * 64)), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.put(db, admin, org, b'x', media_type='image/svg+xml')), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.put(db, admin, org, b'x', width=2000)), 'BRANDING_INVALID')
            self.assertEqual(refusal(self, lambda: self.put(db, admin, org, bytes(262145))), 'BRANDING_INVALID')
            for index in range(24):
                self.assertIs(self.put(db, admin, org, b'logo-%d' % index), True)
            self.assertEqual(refusal(self, lambda: self.put(db, admin, org, b'one-too-many')), 'BRANDING_LIMIT')
            self.assertIs(self.put(db, admin, org, b'logo-3'), False, 'an existing hash is still accepted at the cap')

    def test_reset_is_a_new_revision_that_keeps_the_history(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            logo = b'reset-logo'
            self.put(db, admin, org, logo)
            sha = hashlib.sha256(logo).hexdigest()
            self.save(db, admin, org, 0, assets=(sha, None, None))
            rows = self.save(db, admin, org, 1, change='reset', theme=DEFAULT_THEME)
            self.assertEqual(rows, [(2, *DEFAULT_THEME, None, None, None)])
            self.assertEqual([(rev, action) for rev, action, _, _ in self.history(db, org)], [(1, 'save'), (2, 'reset')])
            self.assertEqual(db.admin.execute('SELECT logo_light FROM forge.organization_branding_revisions WHERE revision=1').fetchone(), (sha,))

    def test_public_lookup_returns_the_default_for_unbranded_and_the_branding_for_branded_organizations(self):
        with mvp_database() as db:
            digests = self.world(db)
            self.assertEqual(self.service(db, 'SELECT * FROM forge.branding_public_read(%s)', ('org-a',)),
                             [(0, None, None, None, None, None, None, None, None, None, None)])
            self.save(db, digests[('org-a', 'organization_admin')], self.orgs['org-a'], 0)
            self.assertEqual(self.service(db, 'SELECT * FROM forge.branding_public_read(%s)', ('org-a',)),
                             [(1, *THEME, None, None, None)])
            self.assertEqual(self.service(db, 'SELECT * FROM forge.branding_public_read(%s)', ('org-b',))[0][0], 0)

    def test_unknown_inactive_and_malformed_codes_are_indistinguishable_and_return_nothing(self):
        with mvp_database() as db:
            self.world(db)
            db.admin.execute("UPDATE forge.organizations SET active=false WHERE slug='org-b'")
            for code in ('org-b', 'nope', 'ORG-A', 'org a', "org-a'--", '', '-org-a', 'a' * 64, None, 'org-a\n', '%', 'org_a', '\u00f3rg'):
                with self.subTest(code=code):
                    self.assertEqual(self.service(db, 'SELECT * FROM forge.branding_public_read(%s)', (code,)), [])

    def test_the_code_index_follows_organization_inserts_renames_deactivation_and_deletion(self):
        with mvp_database() as db:
            self.world(db)
            index = lambda: db.admin.execute('SELECT slug,active FROM forge.branding_codes ORDER BY slug').fetchall()
            self.assertEqual(index(), [('org-a', True), ('org-b', True)])
            fresh = uuid4()
            with db.admin.transaction():
                db.admin.execute("INSERT INTO forge.organizations VALUES(%s,'acme','Acme',true,1)", (fresh,))
                db.admin.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (fresh,))
            self.assertEqual(index(), [('acme', True), ('org-a', True), ('org-b', True)])
            self.assertEqual(self.service(db, 'SELECT revision FROM forge.branding_public_read(%s)', ('acme',)), [(0,)])
            db.admin.execute("UPDATE forge.organizations SET slug='acme-2' WHERE id=%s", (fresh,))
            self.assertEqual(self.service(db, 'SELECT revision FROM forge.branding_public_read(%s)', ('acme',)), [])
            self.assertEqual(self.service(db, 'SELECT revision FROM forge.branding_public_read(%s)', ('acme-2',)), [(0,)])
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (fresh,))
            self.assertEqual(self.service(db, 'SELECT revision FROM forge.branding_public_read(%s)', ('acme-2',)), [])
            db.admin.execute('UPDATE forge.organizations SET display_name=%s WHERE id=%s', ('Renamed', fresh))
            with db.admin.transaction():
                db.admin.execute('DELETE FROM forge.configuration_revisions WHERE organization_id=%s', (fresh,))
                db.admin.execute('DELETE FROM forge.organizations WHERE id=%s', (fresh,))
            self.assertEqual(index(), [('org-a', True), ('org-b', True)])

    def test_assets_are_served_only_while_a_current_revision_references_them(self):
        with mvp_database() as db:
            digests = self.world(db)
            admin, org = digests[('org-a', 'organization_admin')], self.orgs['org-a']
            logo, other = b'\x89PNG-published', b'\x89PNG-replacement'
            sha, other_sha = hashlib.sha256(logo).hexdigest(), hashlib.sha256(other).hexdigest()
            self.put(db, admin, org, logo)
            self.put(db, admin, org, other)
            get = lambda value: self.service(db, 'SELECT content_type,body FROM forge.branding_asset_get(%s)', (value,))
            self.assertEqual(get(sha), [], 'uploaded but unpublished')
            self.save(db, admin, org, 0, assets=(sha, None, None))
            self.assertEqual([(kind, bytes(body)) for kind, body in get(sha)], [('image/png', logo)])
            self.assertEqual(get(other_sha), [])
            self.save(db, admin, org, 1, assets=(other_sha, None, None))
            self.assertEqual(get(sha), [], 'replaced by a newer revision')
            self.assertEqual([bytes(body) for _, body in get(other_sha)], [other])
            for value in ('A' * 64, 'f' * 64, 'short', '', None, sha + '\n'):
                self.assertEqual(get(value), [])

    def test_the_service_role_cannot_enumerate_organizations_or_read_members_through_the_lookup(self):
        with mvp_database() as db:
            self.world(db)
            row = self.service(db, 'SELECT * FROM forge.branding_public_read(%s)', ('org-a',))[0]
            self.assertEqual(len(row), 11, 'only the eleven public columns, no id, member or secret')


if __name__ == '__main__':
    unittest.main()
