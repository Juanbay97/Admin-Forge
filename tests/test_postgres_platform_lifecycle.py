"""Owned PostgreSQL 0031 company operations: suspend/reactivate (audited, owner-only, fresh MFA) and the platform's branding
edit through a branding-authority function that reuses the branding validation and history."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.account_readiness import catalog_fingerprint
from forge.branding import DEFAULT_INPUT, parse
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F30, F31, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, PLATFORM_OPERATIONS_MIGRATION
from forge.platform import MfaRequired, PlatformDenied, PlatformInvalid, PlatformNotFound, PlatformService, RevisionConflict
from forge.platform_store import PostgresPlatformStore
from forge.platform_totp import SecretSealer
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

THEME = {'name': 'Acme Labs', 'loginCopy': 'Welcome to Acme.', 'assets': {},
         'theme': {'primary': '#0B1D26', 'accent': '#B45309', 'tint': '#E8DCC1', 'heading': 'montserrat', 'body': 'inter'}}


class OperationsProfileTests(unittest.TestCase):
    def test_0031_follows_0030_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_OPERATIONS_MIGRATION, '0031_platform_company_operations.sql')
        self.assertEqual(MVP_ADDITIONS[at(PLATFORM_OPERATIONS_MIGRATION) - 1:at(PLATFORM_OPERATIONS_MIGRATION) + 1], ('0030_company_lifecycle.sql', PLATFORM_OPERATIONS_MIGRATION))
        self.assertEqual(MVP_CHECKPOINTS[at(PLATFORM_OPERATIONS_MIGRATION):at(PLATFORM_OPERATIONS_MIGRATION) + 2], (F30, F31))
        self.assertRegex(F31 or '', r'^[0-9a-f]{64}$', 'F31 must be pinned')
        self.assertNotEqual(F31, F30)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class OperationsFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0031 == upgrade from the 0030 profile, pinned as F31; the upgrade keeps organizations and branding."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0030_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(PLATFORM_OPERATIONS_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_OPERATIONS_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F30)
            result = provision(conn, SEED[:1], lambda created: None)[0]
            conn.execute(migration_text(PLATFORM_OPERATIONS_MIGRATION))
            self.assertEqual(conn.execute('SELECT slug,active FROM forge.organizations').fetchall(), [(result.slug, True)])
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0031 platform company operations checkpoint F31:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0030 must be identical')
        self.assertEqual(fresh, F31, 'F31 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F30)


class OperationsWorld(unittest.TestCase):
    def build(self, db, *, mfa=True):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.admins = {result.slug: result.accounts[0] for result in results}
        self.service = PlatformService(PostgresPlatformStore(db.pool('forge_platform_service')), SecretSealer(Fernet.generate_key()))
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=mfa)

    def audit(self):
        return self.db.admin.execute('SELECT action,organization_id,actor_id FROM forge.platform_audit_log ORDER BY id').fetchall()

    def active(self, slug):
        return self.db.admin.execute('SELECT active FROM forge.organizations WHERE slug=%s', (slug,)).fetchone()[0]


class SuspendReactivateTests(OperationsWorld):
    def test_suspending_deactivates_only_that_company_and_writes_exactly_one_audit_row(self):
        with mvp_database() as db:
            self.build(db)
            company = self.service.suspend_company(self.token, self.orgs['org-a'])
            self.assertEqual((company.slug, company.active), ('org-a', False))
            self.assertEqual((self.active('org-a'), self.active('org-b')), (False, True))
            self.assertEqual(self.audit(), [('company.suspended', self.orgs['org-a'], self.owner)])
            self.assertEqual(db.admin.execute("SELECT active FROM forge.branding_codes WHERE slug='org-a'").fetchone(), (False,),
                             'the public company-code lookup stops resolving a suspended company')

    def test_reactivating_restores_it_and_each_change_is_audited_once_while_a_repeat_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            org = self.orgs['org-a']
            self.service.suspend_company(self.token, org)
            self.service.suspend_company(self.token, org)  # already suspended: idempotent, no second row
            self.assertEqual(self.service.reactivate_company(self.token, org).active, True)
            self.service.reactivate_company(self.token, org)
            self.assertEqual(self.active('org-a'), True)
            self.assertEqual([row[0] for row in self.audit()], ['company.suspended', 'company.reactivated'])

    def test_an_unknown_company_is_not_found_and_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            for run in (self.service.suspend_company, self.service.reactivate_company):
                with self.assertRaises(PlatformNotFound):
                    run(self.token, uuid4())
            self.assertEqual(self.audit(), [])

    def test_only_a_fresh_verified_owner_session_may_change_state(self):
        with mvp_database() as db:
            self.build(db, mfa=False)
            org = self.orgs['org-a']
            with self.assertRaises(MfaRequired):
                self.service.suspend_company(self.token, org)
            stale, digest = sign_in(db, mfa=True)
            db.admin.execute("UPDATE forge.platform_mfa_sessions SET verified_at=clock_timestamp()-interval '31 minutes' WHERE capability_hash=%s", (digest,))
            with self.assertRaises(MfaRequired):
                self.service.suspend_company(stale, org)
            admin, _ = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            with self.assertRaises(PlatformDenied):
                self.service.suspend_company(admin, org)
            self.assertEqual((self.active('org-a'), self.audit()), (True, []))

    def test_the_authority_may_update_only_the_active_column_of_organizations(self):
        with mvp_database() as db:
            privilege = 'SELECT has_column_privilege(%s,%s,%s,%s)'
            for column, expected in (('active', True), ('slug', False), ('display_name', False), ('id', False), ('selected_config_revision', False)):
                self.assertEqual(db.admin.execute(privilege, ('forge_platform_authority', 'forge.organizations', column, 'UPDATE')).fetchone(),
                                 (expected,), column)
            self.assertEqual(db.admin.execute(privilege, ('forge_platform_service', 'forge.organizations', 'active', 'UPDATE')).fetchone(), (False,))


class PlatformBrandingTests(OperationsWorld):
    def save(self, org, expected, document=THEME, token=None):
        return self.service.save_company_branding(token or self.token, org, expected, parse(document))

    def test_the_owner_edits_any_company_branding_and_only_that_company_changes(self):
        with mvp_database() as db:
            self.build(db)
            saved = self.save(self.orgs['org-a'], 0)
            self.assertEqual((saved.revision, saved.name, saved.primary, saved.accent), (1, 'Acme Labs', '#0B1D26', '#B45309'))
            self.assertEqual(self.service.company_branding(self.token, self.orgs['org-a']).name, 'Acme Labs')
            self.assertEqual(self.service.company_branding(self.token, self.orgs['org-b']).revision, 0, 'company B is untouched')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_branding WHERE organization_id=%s', (self.orgs['org-b'],)).fetchone(), (0,))
            self.assertEqual(db.admin.execute('SELECT revision,action,actor_id FROM forge.organization_branding_revisions').fetchall(),
                             [(1, 'save', self.owner)])
            self.assertEqual(self.audit(), [('company.branding_saved', self.orgs['org-a'], self.owner)])

    def test_the_compare_and_swap_continues_across_the_platform_and_the_company_admin(self):
        with mvp_database() as db:
            self.build(db)
            org = self.orgs['org-a']
            self.save(org, 0)
            with self.assertRaises(RevisionConflict):
                self.save(org, 0)
            with self.assertRaises(RevisionConflict):
                self.save(org, 5)
            admin_token, admin_digest = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            rows = call(db, 'SELECT revision,name FROM forge.branding_save(%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL)',
                        (admin_digest, org, 'save', 'Admin Edit', 'Hi', '#0B1D26', '#B45309', '#E8DCC1', 'inter', 'inter'),
                        role='forge_gateway_service')
            self.assertEqual(rows, [(2, 'Admin Edit')], 'the company admin keeps editing its own branding')
            self.assertEqual(self.save(org, 2, {**THEME, 'name': 'Platform Again'}).revision, 3)
            self.assertEqual([row[:2] for row in db.admin.execute('SELECT revision,action FROM forge.organization_branding_revisions ORDER BY revision').fetchall()],
                             [(1, 'save'), (2, 'save'), (3, 'save')])

    def test_a_reset_document_is_a_new_revision_and_hostile_values_are_refused_by_the_database_too(self):
        with mvp_database() as db:
            self.build(db)
            org = self.orgs['org-a']
            self.save(org, 0)
            reset = self.service.reset_company_branding(self.token, org, 1)
            self.assertEqual((reset.revision, reset.name), (2, DEFAULT_INPUT.name))
            for hostile in ('<b>', '', 'x' * 41):
                with self.subTest(name=hostile):
                    self.assertEqual(refusal(self, lambda: call(
                        db, 'SELECT * FROM forge.platform_company_branding_save(%s,%s,2,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL)',
                        (self.digest, org, 'save', hostile, 'Hi', '#0B1D26', '#B45309', '#E8DCC1', 'inter', 'inter'))), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: call(
                db, 'SELECT * FROM forge.platform_company_branding_save(%s,%s,2,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)',
                (self.digest, org, 'save', 'Ok', 'Hi', '#0B1D26', '#B45309', '#E8DCC1', 'inter', 'inter', 'c' * 64))), 'PLATFORM_INVALID',
                'a logo the company never uploaded cannot be referenced')
            self.assertEqual(len(db.admin.execute('SELECT 1 FROM forge.organization_branding_revisions').fetchall()), 2)

    def test_non_owners_unverified_sessions_and_unknown_companies_cannot_edit_or_read(self):
        with mvp_database() as db:
            self.build(db, mfa=False)
            org = self.orgs['org-a']
            with self.assertRaises(MfaRequired):
                self.save(org, 0)
            with self.assertRaises(MfaRequired):
                self.service.company_branding(self.token, org)
            admin, _ = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            with self.assertRaises(PlatformDenied):
                self.save(org, 0, token=admin)
            verified, _ = sign_in(db, mfa=True)
            with self.assertRaises(PlatformNotFound):
                self.save(uuid4(), 0, token=verified)
            with self.assertRaises(PlatformNotFound):
                self.service.company_branding(verified, uuid4())
            self.assertEqual((self.audit(), db.admin.execute('SELECT count(*) FROM forge.organization_branding').fetchone()), ([], (0,)))

    def test_the_branding_authority_functions_are_executable_by_the_platform_authority_alone(self):
        with mvp_database() as db:
            for signature in ('forge.branding_platform_read(uuid)',
                              'forge.branding_platform_apply(uuid,uuid,bigint,text,text,text,text,text,text,text,text,text,text,text)'):
                self.assertEqual(db.admin.execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=%s::regprocedure', (signature,)).fetchone(),
                                 ('forge_branding_authority', True))
                for role, allowed in (('forge_platform_authority', True), ('forge_platform_service', False), ('forge_gateway_service', False),
                                      ('forge_branding_service', False), ('forge_account_service', False), ('forge_runtime', False), ('public', False)):
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')", (role, signature)).fetchone(),
                                     (allowed,), (signature, role))


if __name__ == '__main__':
    unittest.main()
