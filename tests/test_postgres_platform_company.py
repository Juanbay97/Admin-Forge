"""Owned PostgreSQL 0030 company creation: organization, code, department and first-admin invitation in one transaction;
the platform-issued invitation constraints; accepting it as organization_admin; the member path left as it was."""
from pathlib import Path
import sys
import threading
import time
import unittest
from uuid import UUID, uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.account_store import PostgresEnrollmentStore
from forge.dev_accounts import MIGRATIONS
from forge.invitation_delivery import LocalTestMailbox, DeliveryCoordinator, PostgresDeliveryStore
from forge.invitation_store import PostgresInvitationStore
from forge.invitations import InvitationDenied, InvitationRequest, InvitationService, capability_digest
from forge.mvp_profile import F29, F30, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, COMPANY_LIFECYCLE_MIGRATION
from forge.platform import CompanyConflict, MfaRequired, PlatformDenied, PlatformInvalid, PlatformService
from forge.platform_store import PostgresPlatformStore
from forge.platform_totp import SecretSealer
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_account, add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

ARGS = dict(slug='acme', display_name='Acme Corporation', department='Operations', admin_email='admin@acme.test', admin_name='Acme Admin')
ORIGIN = 'http://127.0.0.1:3410'


class CompanyProfileTests(unittest.TestCase):
    def test_0030_follows_0029_with_its_own_pinned_checkpoint(self):
        self.assertEqual(COMPANY_LIFECYCLE_MIGRATION, '0030_company_lifecycle.sql')
        self.assertEqual(MVP_ADDITIONS[at(COMPANY_LIFECYCLE_MIGRATION) - 1:at(COMPANY_LIFECYCLE_MIGRATION) + 1], ('0029_platform_mfa.sql', COMPANY_LIFECYCLE_MIGRATION))
        self.assertEqual(MVP_CHECKPOINTS[at(COMPANY_LIFECYCLE_MIGRATION):at(COMPANY_LIFECYCLE_MIGRATION) + 2], (F29, F30))
        self.assertRegex(F30 or '', r'^[0-9a-f]{64}$', 'F30 must be pinned')
        self.assertNotEqual(F30, F29)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class CompanyFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0030 == upgrade from the 0029 profile, pinned as F30; existing member invitations survive."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0029_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(COMPANY_LIFECYCLE_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, COMPANY_LIFECYCLE_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F29)
            result = provision(conn, SEED[:1], lambda created: None)[0]
            admin = conn.execute('SELECT m.id,m.identity_id FROM forge.memberships m JOIN forge.membership_roles r '
                                 "ON r.membership_id=m.id AND r.role='organization_admin'").fetchone()
            invitation = uuid4()
            conn.execute('INSERT INTO forge.account_invitations(id,organization_id,administrator_membership_id,administrator_identity_id,'
                         'membership_id,department_id,canonical_email,display_name,capability_hash,expires_at) '
                         "VALUES(%s,%s,%s,%s,%s,%s,'x@y.test','X',%s,clock_timestamp()+interval '1 day')",
                         (invitation, result.organization_id, admin[0], admin[1], uuid4(), result.department_id, 'a' * 64))
            conn.execute(migration_text(COMPANY_LIFECYCLE_MIGRATION))
            self.assertEqual(conn.execute('SELECT initial_role,issuer_platform_id,administrator_membership_id IS NOT NULL '
                                          'FROM forge.account_invitations').fetchall(), [('member', None, True)])
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0030 company lifecycle checkpoint F30:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0029 must be identical')
        self.assertEqual(fresh, F30, 'F30 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F29)


class CompanyWorld(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = self._temp.name

    def build(self, db, *, sessions_mfa=True):
        self.db = db
        self.mailbox = Path(self.directory)/'mail'
        self.mailbox.mkdir(exist_ok=True)
        coordinator = DeliveryCoordinator(PostgresDeliveryStore(db.pool('forge_account_service')),
                                          LocalTestMailbox(self.mailbox, sender='forge@local.test'), origin=ORIGIN,
                                          encryption_key=Fernet.generate_key())
        self.service = PlatformService(PostgresPlatformStore(db.pool('forge_platform_service')), SecretSealer(Fernet.generate_key()),
                                       delivery=coordinator)
        self.invitations = InvitationService(PostgresInvitationStore(db.pool('forge_enrollment')),
                                             PostgresEnrollmentStore(db.pool('forge_enrollment')))
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=sessions_mfa)

    def counts(self):
        return {table: self.db.admin.execute('SELECT count(*) FROM forge.' + table).fetchone()[0]
                for table in ('organizations', 'departments', 'configuration_revisions', 'account_invitations', 'platform_audit_log',
                              'branding_codes')}

    def link_parts(self):
        """The invitation id and capability from the one .eml the local mailbox holds (quoted-printable decoded)."""
        import email
        from email import policy
        from urllib.parse import parse_qs, urlsplit
        (path,) = sorted(self.mailbox.glob('*.eml'))
        message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        text = message.get_body(('plain',)).get_content()
        link = next(line for line in text.splitlines() if line.startswith(ORIGIN))
        fragment = parse_qs(urlsplit(link).fragment)
        return link, UUID(fragment['invitation_id'][0]), fragment['capability'][0]


class CreateCompanyTests(CompanyWorld):
    def test_it_creates_the_organization_code_department_and_a_pending_first_admin_invitation_atomically(self):
        with mvp_database() as db:
            self.build(db)
            before = self.counts()
            created = self.service.create_company(self.token, **ARGS)
            self.assertEqual(self.counts(), {key: value + 1 for key, value in before.items()})
            self.assertEqual((created.delivery_state, created.delivery_channel), ('delivered', 'local_test_mailbox'))
            self.assertEqual(db.admin.execute('SELECT slug,display_name,active,selected_config_revision FROM forge.organizations').fetchall(),
                             [('acme', 'Acme Corporation', True, 1)])
            self.assertEqual(db.admin.execute('SELECT name,active FROM forge.departments').fetchall(), [('Operations', True)])
            self.assertEqual(db.admin.execute('SELECT slug,active FROM forge.branding_codes').fetchall(), [('acme', True)])
            row = db.admin.execute('SELECT state,initial_role,issuer_platform_id,administrator_membership_id,administrator_identity_id,'
                                   'canonical_email,display_name FROM forge.account_invitations').fetchone()
            self.assertEqual(row, ('pending', 'organization_admin', self.owner, None, None, 'admin@acme.test', 'Acme Admin'))
            self.assertEqual(db.admin.execute('SELECT actor_id,action,organization_id FROM forge.platform_audit_log').fetchall(),
                             [(self.owner, 'company.created', created.company.organization_id)])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (0,),
                             'neither the owner nor anyone else is a member until the invitation is accepted')

    def test_only_the_digest_of_the_capability_is_stored_and_it_is_in_the_emailed_link_alone(self):
        with mvp_database() as db:
            self.build(db)
            self.service.create_company(self.token, **ARGS)
            link, invitation, capability = self.link_parts()
            self.assertTrue(link.startswith(ORIGIN + '/onboarding?c=acme#'), link)
            stored = db.admin.execute('SELECT capability_hash FROM forge.account_invitations').fetchone()[0]
            self.assertEqual(stored, capability_digest(capability))
            dump = ' '.join(db.admin.execute(f'SELECT t::text FROM forge.{table} t').fetchone()[0]
                            for table in ('account_invitations', 'platform_audit_log', 'organizations', 'account_message_delivery'))
            self.assertNotIn(capability, dump)
            self.assertNotIn('admin@acme.test', db.admin.execute('SELECT string_agg(t::text,\' \') FROM forge.platform_audit_log t').fetchone()[0] or '')

    def test_a_duplicate_code_is_a_conflict_that_creates_and_audits_nothing(self):
        with mvp_database() as db:
            self.build(db)
            self.service.create_company(self.token, **ARGS)
            before = self.counts()
            with self.assertRaises(CompanyConflict):
                self.service.create_company(self.token, **{**ARGS, 'display_name': 'Other', 'admin_email': 'x@y.test'})
            self.assertEqual(self.counts(), before)
            self.assertEqual(len(list(self.mailbox.glob('*.eml'))), 1)

    def test_two_simultaneous_creations_of_the_same_code_have_exactly_one_winner(self):
        with mvp_database() as db:
            self.build(db)
            outcomes, barrier = [], threading.Barrier(2)

            def attempt(email):
                barrier.wait(timeout=5)
                try:
                    self.service.create_company(self.token, **{**ARGS, 'admin_email': email})
                    outcomes.append('created')
                except CompanyConflict:
                    outcomes.append('conflict')
            threads = [threading.Thread(target=attempt, args=(email,)) for email in ('a@acme.test', 'b@acme.test')]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
            self.assertEqual(sorted(outcomes), ['conflict', 'created'])
            self.assertEqual(self.counts()['organizations'], 1)

    def test_a_password_only_a_stale_and_a_non_owner_session_create_nothing(self):
        with mvp_database() as db:
            self.build(db, sessions_mfa=False)
            before = self.counts()
            with self.assertRaises(MfaRequired):
                self.service.create_company(self.token, **ARGS)
            stale, stale_digest = sign_in(db, mfa=True)
            db.admin.execute("UPDATE forge.platform_mfa_sessions SET verified_at=clock_timestamp()-interval '31 minutes' WHERE capability_hash=%s", (stale_digest,))
            with self.assertRaises(MfaRequired):
                self.service.create_company(stale, **ARGS)
            self.assertEqual(self.service.companies(stale), [], 'a stale verification still reads')
            admin = provision(db.admin, SEED[:1], lambda created: None)[0].accounts[0]
            before = self.counts()
            token, _ = sign_in(db, admin.email, admin.password)
            with self.assertRaises(PlatformDenied):
                self.service.create_company(token, **ARGS)
            with self.assertRaises(PlatformDenied):
                self.service.create_company('A' * 43, **ARGS)
            self.assertEqual(self.counts(), before)

    def test_the_database_validates_every_argument_whatever_the_application_sends(self):
        with mvp_database() as db:
            self.build(db)
            good = dict(org=uuid4(), dept=uuid4(), invitation=uuid4(), membership=uuid4(), slug='ok', name='Ok', dept_name='Dept',
                        email='a@b.test', admin_name='Admin', hashed='a' * 64, lifetime=3600)

            def create(**change):
                v = {**good, **change}
                return call(db, 'SELECT forge.platform_company_create(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                            (self.digest, v['org'], v['dept'], v['invitation'], v['membership'], v['slug'], v['name'], v['dept_name'],
                             v['email'], v['admin_name'], v['hashed'], v['lifetime']))
            before = self.counts()
            for change in (dict(slug='BAD'), dict(slug='-x'), dict(slug='a' * 64), dict(slug=''), dict(slug=None), dict(name=''), dict(name=' x'),
                           dict(name='x' * 121), dict(dept_name=''), dict(email='A@B.TEST'), dict(email='nope'), dict(email='a' * 250 + '@b.test'),
                           dict(admin_name=''), dict(hashed='z' * 64), dict(hashed='a' * 63), dict(lifetime=59), dict(lifetime=604801),
                           dict(lifetime=None), dict(org=None), dict(dept=None), dict(invitation=None), dict(membership=None)):
                with self.subTest(change=change):
                    self.assertEqual(refusal(self, lambda: create(**change)), 'PLATFORM_INVALID')
            self.assertEqual(self.counts(), before)
            self.assertEqual(len(create()), 1)

    def test_the_service_role_still_cannot_touch_a_table_directly(self):
        with mvp_database() as db:
            self.build(db)
            self.service.create_company(self.token, **ARGS)
            for table in ('organizations', 'departments', 'account_invitations', 'configuration_revisions'):
                with self.subTest(table=table), self.assertRaises(errors.InsufficientPrivilege):
                    call(db, 'SELECT * FROM forge.' + table)
                with self.subTest(table=table, write=True), self.assertRaises(errors.InsufficientPrivilege):
                    call(db, 'DELETE FROM forge.' + table)


class FirstAdminTests(CompanyWorld):
    """Accepting the platform-issued invitation: the member path's account creation, with the role the invitation carries."""
    def accept(self, password='first-admin-passphrase'):
        _, invitation, capability = self.link_parts()
        return self.invitations.accept(invitation, capability, password)

    def test_the_first_admin_accepts_and_becomes_the_companys_organization_admin_in_its_department(self):
        with mvp_database() as db:
            self.build(db)
            created = self.service.create_company(self.token, **ARGS)
            enrollment = self.accept()
            self.assertEqual(enrollment.organization_id, created.company.organization_id)
            self.assertEqual(db.admin.execute('SELECT r.role FROM forge.membership_roles r WHERE r.membership_id=%s', (enrollment.membership_id,)).fetchall(),
                             [('organization_admin',)])
            self.assertEqual(db.admin.execute('SELECT department_id FROM forge.membership_departments').fetchall(), [(enrollment.department_id,)])
            self.assertEqual(db.admin.execute('SELECT state,account_id FROM forge.account_invitations').fetchall(), [('accepted', enrollment.account_id)])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (1,))
            self.assertEqual(db.admin.execute("SELECT event_type FROM forge.account_enrollment_audit").fetchall(), [('invitation.accepted',)])

    def test_a_used_an_expired_and_a_suspended_company_invitation_are_all_denied_and_reactivation_restores_it(self):
        with mvp_database() as db:
            self.build(db)
            created = self.service.create_company(self.token, **ARGS)
            org = created.company.organization_id
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (org,))
            with self.assertRaises(InvitationDenied):
                self.accept()
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (0,))
            db.admin.execute('UPDATE forge.organizations SET active=true WHERE id=%s', (org,))
            db.admin.execute("UPDATE forge.account_invitations SET expires_at=clock_timestamp()-interval '1 second'")
            with self.assertRaises(InvitationDenied):
                self.accept()
            db.admin.execute("UPDATE forge.account_invitations SET expires_at=clock_timestamp()+interval '1 day'")
            self.accept()
            with self.assertRaises(InvitationDenied):
                self.accept('another-admin-passphrase')

    def test_an_invitation_whose_issuer_lost_the_owner_role_is_denied(self):
        with mvp_database() as db:
            self.build(db)
            self.service.create_company(self.token, **ARGS)
            db.admin.execute('DELETE FROM forge.platform_mfa_sessions')
            db.admin.execute('DELETE FROM forge.platform_totp')
            db.admin.execute('DELETE FROM forge.platform_roles')
            with self.assertRaises(InvitationDenied):
                self.accept()
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (0,))

    def test_the_issuer_check_is_executable_by_the_enrollment_authority_alone(self):
        with mvp_database() as db:
            signature = 'forge.platform_owner_exists(uuid)'
            for role, allowed in (('forge_enrollment_authority', True), ('forge_platform_service', False), ('forge_enrollment', False),
                                  ('forge_account_service', False), ('forge_runtime', False), ('forge_gateway_service', False), ('public', False)):
                self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')", (role, signature)).fetchone(),
                                 (allowed,), role)

    def test_an_existing_account_address_keeps_the_existing_account_error_and_creates_nothing(self):
        from forge.invitations import ExistingAccountAuthenticationRequired
        with mvp_database() as db:
            self.build(db)
            add_account(db.admin, 'admin@acme.test')
            self.service.create_company(self.token, **ARGS)
            with self.assertRaises(ExistingAccountAuthenticationRequired):
                self.accept()
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.memberships').fetchone(), (0,))


class MemberPathUnchangedTests(unittest.TestCase):
    def world(self, db):
        results = provision(db.admin, SEED, lambda created: None)
        self.result = results[0]
        self.admin = results[0].accounts[0]
        invitations = InvitationService(PostgresInvitationStore(db.pool('forge_enrollment')), PostgresEnrollmentStore(db.pool('forge_enrollment')))
        self.invitations = invitations
        self.identity_of = lambda: None

    def test_a_member_invitation_still_creates_a_plain_member_and_a_caller_cannot_choose_the_role(self):
        from forge.accounts import PasswordHasher
        from forge.foundation import AuthenticatedIdentity
        from forge.accounts import ACCOUNT_ISSUER
        with mvp_database() as db:
            self.world(db)
            admin_id = db.admin.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (self.admin.email,)).fetchone()[0]
            member = db.admin.execute("SELECT m.id FROM forge.memberships m WHERE m.organization_id=%s AND m.identity_id=%s",
                                      (self.result.organization_id, admin_id)).fetchone()[0]
            issued = self.invitations.issue(AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(admin_id)),
                                            InvitationRequest(self.result.organization_id, member, self.result.department_id,
                                                              'new.member@acme.test', 'New Member'))
            encoded = PasswordHasher().hash('new-member-passphrase')
            with db.pool('forge_enrollment').connection() as conn:
                with conn.transaction():
                    conn.execute("SELECT set_config('forge.enrollment_role','organization_admin',true)")  # a hostile caller's attempt
                    conn.execute('SELECT * FROM forge.accept_account_invitation(%s,%s,%s,%s)',
                                 (issued.invitation_id, capability_digest(issued.capability), uuid4(), encoded))
            roles = db.admin.execute('SELECT r.role FROM forge.membership_roles r JOIN forge.memberships m ON m.id=r.membership_id '
                                     'JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s',
                                     ('new.member@acme.test',)).fetchall()
            self.assertEqual(roles, [('member',)])
            self.assertEqual(db.admin.execute("SELECT initial_role,issuer_platform_id IS NULL FROM forge.account_invitations "
                                              "WHERE canonical_email='new.member@acme.test'").fetchone(), ('member', True))

    def test_the_database_refuses_an_administrator_issued_organization_admin_invitation_and_ambiguous_issuers(self):
        with mvp_database() as db:
            self.world(db)
            owner = add_owner(db.admin)
            admin_id = db.admin.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (self.admin.email,)).fetchone()[0]
            member = db.admin.execute('SELECT m.id FROM forge.memberships m WHERE m.identity_id=%s', (admin_id,)).fetchone()[0]

            def insert(role, admin_membership, admin_identity, platform):
                with db.admin.transaction():
                    db.admin.execute('INSERT INTO forge.account_invitations(id,organization_id,administrator_membership_id,administrator_identity_id,'
                                     'issuer_platform_id,initial_role,membership_id,department_id,canonical_email,display_name,capability_hash,expires_at) '
                                     "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'z@z.test','Z',%s,clock_timestamp()+interval '1 day')",
                                     (uuid4(), self.result.organization_id, admin_membership, admin_identity, platform, role, uuid4(),
                                      self.result.department_id, uuid4().hex + uuid4().hex))
            with self.assertRaises(errors.CheckViolation):
                insert('organization_admin', member, admin_id, None)  # an administrator cannot mint administrators
            with self.assertRaises(errors.CheckViolation):
                insert('member', member, admin_id, owner)  # two issuers
            with self.assertRaises(errors.CheckViolation):
                insert('member', None, None, None)  # no issuer
            with self.assertRaises(errors.CheckViolation):
                insert('owner', None, None, owner)  # a role outside the finite list
            insert('organization_admin', None, None, owner)  # the one valid platform shape
            insert('member', member, admin_id, None)


if __name__ == '__main__':
    unittest.main()
