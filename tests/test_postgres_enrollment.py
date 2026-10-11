"""Real atomic onboarding/privilege proof in the existing owned PostgreSQL harness."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import secrets
import sys
import time
import unittest
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool
from postgres_support import DatabaseFixture, connect, settings, owned_enrollment_schema, ORG_A, ORG_B, MEMBER_A, MEMBER_B, ALICE, BOB
from forge.accounts import ACCOUNT_ISSUER, PasswordHasher
from forge.account_store import PostgresEnrollmentStore
from forge.authorization_store import PostgresAuthorizationReader
from forge.foundation import AuthenticatedIdentity
from forge.invitation_store import PostgresInvitationStore
from forge.invitations import InvitationService, InvitationRequest, InvitationDenied, InvitationUnavailable, ExistingAccountAuthenticationRequired, capability_digest
from forge.postgres import PostgresReadinessProbe

DEPT_A, DEPT_B = UUID(int=501), UUID(int=502)
ACTOR = AuthenticatedIdentity("forge", ACCOUNT_ISSUER, str(ALICE))
REQUEST = InvitationRequest(ORG_A, MEMBER_A, DEPT_A, "invitee@example.com", "Invitee")


class EnrollmentPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()
        cls.password_hash = PasswordHasher().hash("a real sufficiently long password")

    def setUp(self):
        self.db.reset()

    @contextmanager
    def fixture(self):
        with owned_enrollment_schema() as admin:
            with admin.transaction():
                for account, member, org, dept in ((ALICE,MEMBER_A,ORG_A,DEPT_A),(BOB,MEMBER_B,ORG_B,DEPT_B)):
                    admin.execute("UPDATE forge.identities SET provider='forge',issuer=%s,subject=%s WHERE id=%s",
                                  (ACCOUNT_ISSUER,str(account),account))
                    admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (org,member))
                    admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Area')",(org,dept))
            password = secrets.token_urlsafe(32)
            admin.execute(sql.SQL('ALTER ROLE forge_enrollment LOGIN PASSWORD {}').format(sql.Literal(password)))
            kwargs = settings() | dict(user='forge_enrollment',password=password,application_name='forge-enrollment-test')
            with ConnectionPool('', kwargs=kwargs, min_size=1,max_size=4,open=True) as pool:
                pool.wait(5)
                invitations, enrollment = PostgresInvitationStore(pool), PostgresEnrollmentStore(pool)
                yield admin,pool,InvitationService(invitations,enrollment),enrollment

    def accept(self, enrollment, invitation):
        return enrollment.accept(invitation.invitation_id,capability_digest(invitation.capability),self.password_hash)

    def counts(self, admin):
        return tuple(admin.execute('SELECT count(*) FROM forge.'+table).fetchone()[0] for table in
                     ('identities','memberships','owned_accounts','membership_departments','account_enrollment_audit'))

    def test_pending_has_no_access_and_accept_is_atomic_real_identity(self):
        with self.fixture() as (admin,pool,service,enrollment):
            before = self.counts(admin)
            invite = service.issue(ACTOR,REQUEST)
            self.assertEqual(self.counts(admin)[:4],before[:4])
            row = admin.execute('SELECT capability_hash,state FROM forge.account_invitations WHERE id=%s',(invite.invitation_id,)).fetchone()
            self.assertEqual(row,(capability_digest(invite.capability),'pending'))
            self.assertNotIn(invite.capability,repr(row))
            result = self.accept(enrollment,invite)
            self.assertEqual(result.identity.provider,'forge')
            self.assertEqual(result.identity.issuer,ACCOUNT_ISSUER)
            identity = admin.execute('SELECT provider,issuer,subject,entra_tenant_id,entra_object_id FROM forge.identities WHERE id=%s',(result.account_id,)).fetchone()
            self.assertEqual(identity,('forge',ACCOUNT_ISSUER,str(result.account_id),None,None))
            self.assertEqual(admin.execute('SELECT role FROM forge.membership_roles WHERE membership_id=%s',(result.membership_id,)).fetchall(),[('member',)])
            self.assertEqual(admin.execute('SELECT department_id FROM forge.membership_departments WHERE membership_id=%s',(result.membership_id,)).fetchall(),[(DEPT_A,)])
            with self.db.pool() as reader_pool:
                snapshot = PostgresAuthorizationReader(reader_pool).read(result.identity,str(ORG_A))
                self.assertIsNotNone(snapshot)
                self.assertEqual(snapshot.roles,frozenset({'member'}))
                self.assertIsNone(PostgresAuthorizationReader(reader_pool).read(result.identity,str(ORG_B)))
                # Opt-in enrollment policies are outside the legacy exact attestation.
                self.assertFalse(PostgresReadinessProbe(reader_pool).check())
            audit = admin.execute('SELECT * FROM forge.account_enrollment_audit').fetchall()
            for value in (REQUEST.email,invite.capability,self.password_hash):
                self.assertNotIn(value,repr(audit))
            self.assertEqual(len(audit),2)

    def test_wrong_org_department_identity_and_inactive_authority_deny(self):
        with self.fixture() as (admin,pool,service,enrollment):
            for request,actor in ((replace(REQUEST,department_id=DEPT_B),ACTOR),
                                  (replace(REQUEST,organization_id=ORG_B),ACTOR),
                                  (REQUEST,replace(ACTOR,subject=str(BOB)))):
                with self.subTest(request=request),self.assertRaises(InvitationDenied):
                    service.issue(actor,request)
            for query in (
                "UPDATE forge.departments SET active=false WHERE id='"+str(DEPT_A)+"'",
                "UPDATE forge.organizations SET active=false WHERE id='"+str(ORG_A)+"'",
                "UPDATE forge.memberships SET status='suspended' WHERE id='"+str(MEMBER_A)+"'",
                "DELETE FROM forge.membership_roles WHERE membership_id='"+str(MEMBER_A)+"'",
            ):
                with admin.transaction():
                    admin.execute(query)
                with self.assertRaises(InvitationDenied):
                    service.issue(ACTOR,REQUEST)
                admin.execute("UPDATE forge.departments SET active=true WHERE id=%s",(DEPT_A,))
                admin.execute("UPDATE forge.organizations SET active=true WHERE id=%s",(ORG_A,))
                admin.execute("UPDATE forge.memberships SET status='active' WHERE id=%s",(MEMBER_A,))
                admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin') ON CONFLICT DO NOTHING",(ORG_A,MEMBER_A))
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_invitations').fetchone()[0],0)

    def test_expired_invalid_revoked_reused_and_foreign_revoke(self):
        with self.fixture() as (admin,pool,service,enrollment):
            invite = service.issue(ACTOR,REQUEST)
            with self.assertRaises(InvitationDenied):
                enrollment.accept(invite.invitation_id,'0'*64,self.password_hash)
            with self.assertRaises(InvitationDenied):
                enrollment.accept(uuid4(),capability_digest(invite.capability),self.password_hash)
            with self.assertRaises(InvitationDenied):
                service.revoke(ACTOR,ORG_B,MEMBER_A,invite.invitation_id)
            admin.execute("UPDATE forge.account_invitations SET expires_at=clock_timestamp()-interval '1s' WHERE id=%s",(invite.invitation_id,))
            with self.assertRaises(InvitationDenied):
                self.accept(enrollment,invite)
            second = service.issue(ACTOR,replace(REQUEST,email='second@example.com'))
            self.assertTrue(service.revoke(ACTOR,ORG_A,MEMBER_A,second.invitation_id))
            with self.assertRaises(InvitationDenied):
                self.accept(enrollment,second)
            third = service.issue(ACTOR,replace(REQUEST,email='third@example.com'))
            self.accept(enrollment,third)
            with self.assertRaises(InvitationDenied):
                self.accept(enrollment,third)

    def test_accept_rechecks_inviter_and_department_after_issuance(self):
        with self.fixture() as (admin,pool,service,enrollment):
            invite = service.issue(ACTOR,REQUEST)
            admin.execute('DELETE FROM forge.membership_roles WHERE membership_id=%s',(MEMBER_A,))
            with self.assertRaises(InvitationDenied):
                self.accept(enrollment,invite)
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
            admin.execute('UPDATE forge.departments SET active=false WHERE id=%s',(DEPT_A,))
            with self.assertRaises(InvitationDenied):
                self.accept(enrollment,invite)
            self.assertEqual(admin.execute('SELECT state FROM forge.account_invitations WHERE id=%s',(invite.invitation_id,)).fetchone()[0],'pending')

    def test_existing_account_password_cannot_be_overwritten(self):
        with self.fixture() as (admin,pool,service,enrollment):
            first = service.issue(ACTOR,REQUEST)
            result = self.accept(enrollment,first)
            duplicate = service.issue(ACTOR,REQUEST)
            before = self.counts(admin)
            with self.assertRaises(ExistingAccountAuthenticationRequired):
                self.accept(enrollment,duplicate)
            self.assertEqual(self.counts(admin),before)
            self.assertEqual(admin.execute('SELECT password_hash FROM forge.owned_accounts WHERE id=%s',(result.account_id,)).fetchone()[0],self.password_hash)
            self.assertEqual(admin.execute('SELECT state FROM forge.account_invitations WHERE id=%s',(duplicate.invitation_id,)).fetchone()[0],'pending')

    def test_audit_failure_rolls_back_consume_and_all_materialization(self):
        with self.fixture() as (admin,pool,service,enrollment):
            invite = service.issue(ACTOR,REQUEST)
            before = self.counts(admin)
            admin.execute("ALTER TABLE forge.account_enrollment_audit ADD CONSTRAINT PRIVATE_SECRET CHECK(event_type<>'invitation.accepted')")
            with self.assertRaises(InvitationUnavailable) as failure:
                self.accept(enrollment,invite)
            self.assertNotIn('PRIVATE_SECRET',str(failure.exception))
            self.assertEqual(self.counts(admin),before)
            self.assertEqual(admin.execute('SELECT state FROM forge.account_invitations WHERE id=%s',(invite.invitation_id,)).fetchone()[0],'pending')
            admin.execute('ALTER TABLE forge.account_enrollment_audit DROP CONSTRAINT PRIVATE_SECRET')
            self.accept(enrollment,invite)

    def test_concurrent_capability_consumption_has_one_winner(self):
        with self.fixture() as (admin,pool,service,enrollment):
            invite = service.issue(ACTOR,REQUEST)
            def consume():
                try:
                    return self.accept(enrollment,invite)
                except InvitationDenied:
                    return None
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _:consume(),range(2)))
            self.assertEqual(sum(value is not None for value in outcomes),1)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone()[0],1)

    def test_concurrent_same_email_different_orgs_rolls_back_loser(self):
        with self.fixture() as (admin,pool,service,enrollment):
            first = service.issue(ACTOR,REQUEST)
            second = service.issue(AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(BOB)),replace(REQUEST,organization_id=ORG_B,administrator_membership_id=MEMBER_B,department_id=DEPT_B))
            def consume(invite):
                try:
                    return self.accept(enrollment,invite)
                except ExistingAccountAuthenticationRequired:
                    return None
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(consume,(first,second)))
            self.assertEqual(sum(value is not None for value in outcomes),1)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone()[0],1)
            self.assertEqual(admin.execute("SELECT count(*) FROM forge.identities WHERE provider='forge'").fetchone()[0],3)
            self.assertEqual(admin.execute("SELECT count(*) FROM forge.account_invitations WHERE state='pending'").fetchone()[0],1)

    def test_revocation_commits_before_blocked_creation_revalidation(self):
        with self.fixture() as (admin,pool,service,enrollment),connect() as revoker:
            with ThreadPoolExecutor(max_workers=1) as executor:
                with revoker.transaction():
                    revoker.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
                    future=executor.submit(service.issue,ACTOR,REQUEST)
                    deadline=time.monotonic()+.7
                    while time.monotonic()<deadline:
                        waiting=admin.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='forge-enrollment-test' AND wait_event_type='Lock')").fetchone()[0]
                        if waiting:
                            break
                        time.sleep(.01)
                    self.assertTrue(waiting,'Creation must wait on actor row lock')
                with self.assertRaises(InvitationDenied):
                    future.result(timeout=3)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_invitations').fetchone()[0],0)

    def test_privilege_isolation_and_runtime_remain_fail_closed(self):
        with self.fixture() as (admin,pool,service,enrollment):
            for table in ('owned_accounts','account_invitations','departments','membership_departments','account_enrollment_audit'):
                self.assertEqual(admin.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",('forge.'+table,)).fetchone(),(True,True))
                for role in ('forge_runtime','forge_enrollment'):
                    self.assertFalse(admin.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",(role,'forge.'+table)).fetchone()[0])
            self.assertFalse(admin.execute("SELECT has_schema_privilege('forge_enrollment_authority','forge','CREATE')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_auth_members WHERE roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('forge_enrollment','forge_enrollment_authority')) OR member IN (SELECT oid FROM pg_roles WHERE rolname IN ('forge_enrollment','forge_enrollment_authority'))").fetchone()[0],0)
            with pool.connection() as conn:
                for query in ('SELECT * FROM forge.owned_accounts', 'SET ROLE forge_enrollment_authority', 'SELECT forge.enrollment_lock_admin(NULL,NULL,NULL,NULL,NULL)'):
                    with self.subTest(query=query),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        conn.execute(query)
            with self.db.pool() as runtime:
                with self.assertRaises(InvitationUnavailable):
                    PostgresInvitationStore(runtime).issue(ACTOR,REQUEST,uuid4(),uuid4(),'0'*64)

    def test_many_to_many_links_enforce_same_org_and_unique_triples(self):
        with self.fixture() as (admin,pool,service,enrollment):
            result=self.accept(enrollment,service.issue(ACTOR,REQUEST))
            additional=UUID(int=503)
            admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Second area')",(ORG_A,additional))
            admin.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)',(ORG_A,result.membership_id,additional))
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.membership_departments WHERE membership_id=%s',(result.membership_id,)).fetchone()[0],2)
            with self.assertRaises(psycopg.errors.UniqueViolation):
                admin.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)',(ORG_A,result.membership_id,additional))
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                admin.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)',(ORG_A,result.membership_id,DEPT_B))

    def test_additive_migration_failure_rolls_back_roles_and_preserves_records(self):
        with connect() as admin:
            before=admin.execute('SELECT * FROM forge.identities ORDER BY id').fetchall()
        with owned_enrollment_schema(fail_migration=True) as admin:
            self.assertIsNone(admin.execute("SELECT to_regclass('forge.owned_accounts')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'forge_enrollment%'").fetchone()[0],0)
            self.assertEqual(admin.execute('SELECT * FROM forge.identities ORDER BY id').fetchall(),before)


if __name__=='__main__':
    unittest.main()
