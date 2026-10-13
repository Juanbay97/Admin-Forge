"""Owned PostgreSQL 0039 capability policy: who may write which layer, force-off locks, epochs, atomic append-only audit, tenant isolation."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import CAPABILITY_POLICY_MIGRATION, F38, F39, MVP_ADDITIONS, MVP_CHECKPOINTS
from capability_support import GovernanceWorld, entry
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

PUBLIC_FUNCTIONS = ('cap_catalog_put(text,text,bigint,jsonb)', 'cap_catalog_list(text)', 'cap_platform_policy_set(text,text,text,text)',
                    'cap_company_override_set(text,uuid,text,text,text)', 'cap_company_policy_get(text,uuid)', 'cap_org_set(text,uuid,text,boolean)',
                    'cap_read_layers(text,uuid)', 'cap_admin_layers(text,uuid)', 'cap_org_audit_page(text,uuid,bigint,integer)',
                    'cap_platform_audit_page(text,bigint,integer)')
INTERNAL_FUNCTIONS = ('cap_lock_admin(text,uuid)', 'cap_lock_member(text,uuid)', 'cap_audit(text,uuid,uuid,text,text,text,text)', 'cap_word(text,text)',
                      'cap_bump_platform()', 'cap_bump_org(uuid)', 'cap_layers(uuid)')
SKILL, CONNECTOR, EXEC = 'skill:pdf', 'connector:github', 'tool:code_execute'


class PolicyProfileTests(unittest.TestCase):
    def test_0039_follows_0038_with_its_own_pinned_checkpoint(self):
        self.assertEqual(CAPABILITY_POLICY_MIGRATION, '0039_capability_policy.sql')
        self.assertEqual(MVP_ADDITIONS[at(CAPABILITY_POLICY_MIGRATION) - 1], '0038_capability_catalog.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(CAPABILITY_POLICY_MIGRATION):at(CAPABILITY_POLICY_MIGRATION) + 2], (F38, F39))
        self.assertRegex(F39 or '', r'^[0-9a-f]{64}$', 'F39 must be pinned')
        self.assertNotEqual(F39, F38)


class PolicyFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0038_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(CAPABILITY_POLICY_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, CAPABILITY_POLICY_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F38)
            conn.execute(migration_text(CAPABILITY_POLICY_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0039 capability policy checkpoint F39:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0038 must be identical')
        self.assertEqual(fresh, F39, 'F39 must be pinned to the reviewed value')


class CatalogWriteTests(GovernanceWorld, unittest.TestCase):
    def test_a_platform_owner_creates_updates_and_the_seed_is_idempotent(self):
        with mvp_database() as db:
            self.build(db)
            created = self.put(SKILL)[0]
            self.assertEqual((created[0], created[1], created[-1]), (SKILL, 'skill', 1))
            self.assertEqual(self.epochs(self.org_a), (2, 1), 'a catalog change bumps the platform epoch only')
            audits = self.audit_count()
            self.put(SKILL, 1)  # identical content
            self.assertEqual((self.epochs(self.org_a), self.audit_count()), ((2, 1), audits), 'a no-op write changes no epoch and appends no audit row')
            self.assertEqual(self.put(SKILL, 1, risk='medium')[0][-1], 2)
            self.assertEqual(self.epochs(self.org_a)[0], 3)
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,%s,%s::jsonb)', (self.owner, SKILL, 1, entry())), 'CAP_CONFLICT', 'stale revision')
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,%s,%s::jsonb)', (self.owner, SKILL, 0, entry())), 'CAP_CONFLICT', 'duplicate id')

    def test_invalid_entries_and_unknown_kinds_are_refused_and_nothing_is_written(self):
        with mvp_database() as db:
            self.build(db)
            bad = (('gadget:x', entry()), ('skill:Bad Id', entry()), (SKILL, entry(risk='severe')), (SKILL, entry(min_sandbox_level=9)),
                   (SKILL, entry(default_state='maybe')), ('app:acme.hello', entry(default_state='on')), (SKILL, '{"version":"1"}'),
                   (SKILL, entry(is_base='perhaps')), (SKILL, entry(manifest_sha256='nope')))
            for identifier, document in bad:
                with self.subTest(identifier=identifier, document=document[:40]):
                    self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,0,%s::jsonb)', (self.owner, identifier, document)), 'CAP_INVALID')
            self.assertEqual((db.admin.execute('SELECT count(*) FROM forge.capability_catalog').fetchone()[0], self.audit_count()), (0, 0))

    def test_only_a_fresh_verified_platform_owner_may_write_the_catalog(self):
        with mvp_database() as db:
            self.build(db)
            for who in ('admin_a', 'member_a'):
                self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,0,%s::jsonb)', (self.digest[who], SKILL, entry())), 'PLATFORM_DENIED', who)
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,0,%s::jsonb)', (self.owner_password_only, SKILL, entry())), 'MFA_REQUIRED')
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_put(%s,%s,0,%s::jsonb)', ('0' * 64, SKILL, entry())), 'PLATFORM_DENIED')
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_catalog_list(%s)', (self.digest['admin_a'],)), 'PLATFORM_DENIED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.capability_catalog').fetchone(), (0,))


class LayerWriteTests(GovernanceWorld, unittest.TestCase):
    def seed(self):
        self.put(SKILL)
        self.put(CONNECTOR)
        self.put(EXEC, risk='high', is_base=False, min_sandbox_level=3)

    def test_platform_default_and_company_override_bump_their_own_epoch_and_leave_the_other_company_alone(self):
        with mvp_database() as db:
            self.build(db)
            self.seed()
            before = self.epochs(self.org_a)
            self.assertTrue(self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, SKILL, 'off', 'none'))[0][0])
            self.assertEqual(self.epochs(self.org_a), (before[0] + 1, before[1]))
            self.assertFalse(self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, SKILL, 'off', 'none'))[0][0], 'unchanged = no bump')
            self.assertEqual(self.epochs(self.org_a)[0], before[0] + 1)
            self.assertTrue(self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, 'off', 'forced_off'))[0][0])
            self.assertEqual((self.epochs(self.org_a)[1], self.epochs(self.org_b)[1]), (2, 1), 'the override affects only its company')

    def test_force_off_is_rejected_for_the_administrator_whether_set_by_the_platform_or_for_the_company(self):
        with mvp_database() as db:
            self.build(db)
            self.seed()
            self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, SKILL, None, 'forced_off'))
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, None, 'forced_off'))
            audits, epochs = self.audit_count(), self.epochs(self.org_a)
            for target in (SKILL, CONNECTOR):
                self.assertEqual(self.role.refusal('SELECT forge.cap_org_set(%s,%s,%s,true)', (self.digest['admin_a'], self.org_a, target)), 'CAP_LOCKED', target)
            self.assertEqual((self.audit_count(), self.epochs(self.org_a)), (audits, epochs), 'a rejected write leaves no audit row and no epoch bump')
            self.assertTrue(self.role.call('SELECT forge.cap_org_set(%s,%s,%s,true)', (self.digest['admin_b'], self.org_b, CONNECTOR))[0][0], 'the lock is per company')
            self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, SKILL, None, 'none'))
            self.assertTrue(self.role.call('SELECT forge.cap_org_set(%s,%s,%s,false)', (self.digest['admin_a'], self.org_a, SKILL))[0][0], 'unlocked again')

    def test_the_administrator_enables_disables_and_clears_and_each_change_is_audited_with_the_actor(self):
        with mvp_database() as db:
            self.build(db)
            self.seed()
            admin = self.digest['admin_a']
            for want, expected in (('true', True), ('true', False), ('false', True), ('null', True), ('null', False)):
                self.assertEqual(self.role.call('SELECT forge.cap_org_set(%%s,%%s,%%s,%s)' % want, (admin, self.org_a, SKILL))[0][0], expected, want)
            rows = db.admin.execute("SELECT scope,organization_id,action,target,before_state,after_state,actor_id IS NOT NULL FROM forge.capability_change_audit "
                                    "WHERE action LIKE 'org.%' ORDER BY id").fetchall()
            self.assertEqual(rows, [('org', self.org_a, 'org.setting_set', SKILL, None, 'on', True), ('org', self.org_a, 'org.setting_set', SKILL, 'on', 'off', True),
                                    ('org', self.org_a, 'org.setting_cleared', SKILL, 'off', 'inherit', True)])
            self.assertEqual(self.epochs(self.org_a)[1], 4)

    def test_members_other_companies_and_unknown_ids_are_denied_without_leaking_existence(self):
        with mvp_database() as db:
            self.build(db)
            self.seed()
            audits = self.audit_count()
            calls = ((self.digest['member_a'], self.org_a, SKILL), (self.digest['admin_a'], self.org_b, SKILL), (self.digest['admin_b'], self.org_a, SKILL),
                     ('0' * 64, self.org_a, SKILL), (self.digest['admin_a'], uuid4(), SKILL))
            codes = {self.role.refusal('SELECT forge.cap_org_set(%s,%s,%s,true)', call) for call in calls}
            self.assertEqual(codes, {'CAP_DENIED'}, 'cross-company and non-admin look identical to a missing company')
            self.assertEqual(self.role.refusal('SELECT forge.cap_org_set(%s,%s,%s,true)', (self.digest['admin_a'], self.org_a, 'skill:ghost')), 'CAP_NOT_FOUND')
            self.assertEqual(self.audit_count(), audits)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.capability_org_settings').fetchone(), (0,))

    def test_a_company_override_for_an_unknown_company_or_capability_is_not_found_and_leaves_no_audit_row(self):
        with mvp_database() as db:
            self.build(db)
            self.seed()
            audits = self.audit_count()
            self.assertEqual(self.role.refusal('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, uuid4(), SKILL, 'on', 'none')), 'CAP_NOT_FOUND')
            self.assertEqual(self.role.refusal('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, 'skill:ghost', 'on', 'none')), 'CAP_NOT_FOUND')
            self.assertEqual(self.role.refusal('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, SKILL, 'maybe', 'none')), 'CAP_INVALID')
            self.assertEqual(self.audit_count(), audits)


class ReadTests(GovernanceWorld, unittest.TestCase):
    def test_a_member_reads_the_layers_of_the_own_company_only(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            self.put(CONNECTOR)
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, 'off', 'forced_off'))
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,false)', (self.digest['admin_a'], self.org_a, SKILL))
            rows = {row['id']: row for row in self.layers(self.digest['member_a'], self.org_a)}
            self.assertEqual((rows[CONNECTOR]['company_state'], rows[CONNECTOR]['company_lock']), ('off', 'forced_off'))
            self.assertEqual(rows[SKILL]['org_enabled'], False)
            self.assertEqual((rows[SKILL]['platform_epoch'], rows[SKILL]['org_epoch']), self.epochs(self.org_a))
            other = {row['id']: row for row in self.layers(self.digest['member_b'], self.org_b)}
            self.assertEqual((other[CONNECTOR]['company_lock'], other[SKILL]['org_enabled'], other[SKILL]['org_epoch']), ('none', None, 1), 'company B sees only its own layers')
            for digest, org in ((self.digest['member_a'], self.org_b), (self.digest['member_b'], self.org_a), ('0' * 64, self.org_a), (self.digest['member_a'], uuid4())):
                self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_read_layers(%s,%s)', (digest, org)), 'CAP_DENIED')

    def test_a_suspended_company_member_is_denied(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org_a,))
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_read_layers(%s,%s)', (self.digest['member_a'], self.org_a)), 'CAP_DENIED')

    def test_the_administrator_reads_layers_and_a_member_cannot_use_the_admin_read(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            self.assertEqual([row['id'] for row in self.layers(self.digest['admin_a'], self.org_a, 'cap_admin_layers')], [SKILL])
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_admin_layers(%s,%s)', (self.digest['member_a'], self.org_a)), 'CAP_DENIED')


class AuditTests(GovernanceWorld, unittest.TestCase):
    def test_a_company_administrator_reads_only_the_own_company_audit_and_the_owner_reads_everything(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, SKILL, 'off', 'none'))
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_b, SKILL, 'on', 'none'))
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,false)', (self.digest['admin_a'], self.org_a, SKILL))
            own = self.role.call('SELECT * FROM forge.cap_org_audit_page(%s,%s,NULL,50)', (self.digest['admin_a'], self.org_a))
            self.assertEqual([(row[1], row[3]) for row in own], [('org', 'org.setting_set'), ('org', 'company.policy_set')])
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_org_audit_page(%s,%s,NULL,50)', (self.digest['admin_a'], self.org_b)), 'CAP_DENIED')
            everything = self.role.call('SELECT * FROM forge.cap_platform_audit_page(%s,NULL,50)', (self.owner,))
            self.assertEqual([row[4] for row in everything], ['org.setting_set', 'company.policy_set', 'company.policy_set', 'catalog.created'])
            self.assertEqual(self.role.refusal('SELECT * FROM forge.cap_platform_audit_page(%s,NULL,50)', (self.digest['admin_a'],)), 'PLATFORM_DENIED')
            self.assertEqual(len(self.role.call('SELECT * FROM forge.cap_platform_audit_page(%s,%s,1)', (self.owner, everything[0][0]))), 1, 'keyset paging')

    def test_a_write_that_fails_after_validation_leaves_no_audit_row(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            audits = self.audit_count()
            # The audit insert is the last step; make it impossible and the whole write must roll back, epoch included.
            db.admin.execute('ALTER TABLE forge.capability_change_audit ADD CONSTRAINT never CHECK(action<>%s) NOT VALID' % "'platform.policy_set'")
            with self.assertRaises(errors.CheckViolation):
                self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, SKILL, 'off', 'none'))
            self.assertEqual((self.audit_count(), self.epochs(self.org_a)[0], db.admin.execute('SELECT count(*) FROM forge.capability_platform_policy').fetchone()[0]),
                             (audits, 2, 0))

    def test_no_role_can_update_or_delete_an_audit_row(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            for role in ('forge_capability_authority', 'forge_capability_service', 'forge_platform_authority', 'forge_gateway_authority', 'forge_runtime'):
                for privilege in ('UPDATE', 'DELETE', 'TRUNCATE'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.capability_change_audit',%s)", (role, privilege)).fetchone(), (False,), (role, privilege))
            db.admin.execute('SET ROLE forge_capability_authority')
            try:
                with self.assertRaises(errors.InsufficientPrivilege):
                    db.admin.execute("UPDATE forge.capability_change_audit SET action='catalog.updated'")
                with self.assertRaises(errors.InsufficientPrivilege):
                    db.admin.execute('DELETE FROM forge.capability_change_audit')
            finally:
                db.admin.execute('RESET ROLE')

    def test_the_audit_has_no_free_text_column(self):
        with mvp_database() as db:
            columns = db.admin.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='forge' AND table_name='capability_change_audit' "
                                       "AND data_type='text' ORDER BY 1").fetchall()
            self.assertEqual(columns, [('action',), ('after_state',), ('before_state',), ('scope',), ('target',)])
            self.assertEqual(db.admin.execute("SELECT conname FROM pg_constraint WHERE conrelid='forge.capability_change_audit'::regclass AND contype='c' "
                                              "AND pg_get_constraintdef(oid) LIKE '%~%' ORDER BY 1").fetchall(),
                             [('capability_change_audit_after_state_check',), ('capability_change_audit_before_state_check',), ('capability_change_audit_target_check',)])


class IsolationTests(GovernanceWorld, unittest.TestCase):
    def test_the_service_role_executes_exactly_the_public_functions_and_nothing_internal(self):
        with mvp_database() as db:
            for name in PUBLIC_FUNCTIONS:
                self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_capability_service',%s::regprocedure,'EXECUTE')", ('forge.' + name,)).fetchone(), (True,), name)
            for name in INTERNAL_FUNCTIONS:
                for role in ('forge_capability_service', 'forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'public'):
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')", (role, 'forge.' + name)).fetchone(), (False,), (role, name))
            for name in (*PUBLIC_FUNCTIONS, *INTERNAL_FUNCTIONS):
                self.assertEqual(db.admin.execute("SELECT pg_get_userbyid(proowner),proconfig FROM pg_proc WHERE oid=%s::regprocedure", ('forge.' + name,)).fetchone(),
                                 ('forge_capability_authority', ['search_path=pg_catalog']), name)
            for role in ('forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'forge_runtime', 'forge_enrollment', 'forge_branding_service'):
                for name in PUBLIC_FUNCTIONS:
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')", (role, 'forge.' + name)).fetchone(), (False,), (role, name))

    def test_tables_stay_closed_to_the_service_role_and_rls_is_forced_everywhere(self):
        with mvp_database() as db:
            self.build(db)
            for table in ('capability_company_overrides', 'capability_org_settings', 'capability_org_epochs', 'capability_change_audit'):
                self.assertEqual(db.admin.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', ('forge.' + table,)).fetchone(), (True, True))
                self.assertEqual(db.admin.execute("SELECT has_table_privilege('forge_capability_service',%s,'SELECT,INSERT,UPDATE,DELETE')", ('forge.' + table,)).fetchone(), (False,))
            with self.assertRaises(errors.InsufficientPrivilege):
                self.role.call('SELECT * FROM forge.capability_org_settings')

    def test_the_authority_sees_no_other_company_without_a_context(self):
        with mvp_database() as db:
            self.build(db)
            self.put(SKILL)
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,true)', (self.digest['admin_a'], self.org_a, SKILL))
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,true)', (self.digest['admin_b'], self.org_b, SKILL))
            db.admin.execute('SET ROLE forge_capability_authority')
            try:
                self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.capability_org_settings').fetchone(), (0,), 'no organization context, no rows')
                db.admin.execute("SELECT set_config('forge.organization',%s,false)", (str(self.org_a),))
                self.assertEqual(db.admin.execute('SELECT organization_id FROM forge.capability_org_settings').fetchall(), [(self.org_a,)])
            finally:
                db.admin.execute('RESET ROLE')
                db.admin.execute("SELECT set_config('forge.organization','',false)")


if __name__ == '__main__':
    unittest.main()
