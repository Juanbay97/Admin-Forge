"""Real opt-in session/reset/throttle/delivery privilege checks in owned PostgreSQL."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from email.parser import BytesParser
from email import policy
from urllib.parse import urlsplit,parse_qs
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from psycopg import sql, errors
from psycopg_pool import ConnectionPool
from postgres_support import AccountDatabaseFixture,settings,owned_enrollment_schema,owned_account_session_schema,ORG_A,ORG_B,MEMBER_A,ALICE
from forge.accounts import ACCOUNT_ISSUER,PasswordHasher
from forge.account_sessions import PostgresSessionStore,SessionService,SessionDenied,LoginThrottled
from forge.account_readiness import AccountReadiness,catalog_fingerprint
from forge.account_api import create_account_app
from forge.account_store import PostgresEnrollmentStore
from forge.invitation_store import PostgresInvitationStore
from forge.invitations import InvitationService
from forge.postgres import PostgresBootstrapReader
from forge.authorization_store import PostgresAuthorizationReader
from forge.invitations import InvitationUnavailable,capability_digest
from forge.invitation_delivery import DeliveryCoordinator,PostgresDeliveryStore,LocalTestMailbox,DeliveryState

PASSWORD='a real sufficiently long password'
EMAIL='member@example.com'

class PostgresAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=AccountDatabaseFixture()
        cls.encoded=PasswordHasher().hash(PASSWORD)

    def setUp(self):self.db.reset()

    def test_required_session_function_exists_after_opt_in(self):
        # Actual additive schema, not a stub or an unrelated baseline probe.
        with owned_account_session_schema() as admin:
            self.assertIsNotNone(admin.execute("SELECT to_regprocedure('forge.account_validate_session(text)')").fetchone()[0])

    @contextmanager
    def fixture(self):
        with owned_account_session_schema() as admin:
            admin.execute("UPDATE forge.identities SET provider='forge',issuer=%s,subject=%s WHERE id=%s",(ACCOUNT_ISSUER,str(ALICE),ALICE))
            admin.execute("INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) VALUES(%s,%s,'Account',%s)",(ALICE,EMAIL,self.encoded))
            password=secrets.token_urlsafe(32)
            admin.execute(sql.SQL('ALTER ROLE forge_account_service LOGIN PASSWORD {}').format(sql.Literal(password)))
            kwargs=settings()|dict(user='forge_account_service',password=password)
            original_members = [row[0] for row in admin.execute(
                'SELECT id FROM forge.memberships').fetchall()]
            role_query = ('SELECT organization_id,membership_id,role FROM forge.membership_roles '
                          'WHERE membership_id=ANY(%s::uuid[]) ORDER BY 1,2,3')
            original_roles = admin.execute(role_query,(original_members,)).fetchall()
            created_admin = (ORG_A,MEMBER_A,'organization_admin') not in original_roles
            try:
                with ConnectionPool('',kwargs=kwargs,min_size=1,max_size=4,open=True) as pool:
                    pool.wait(5)
                    yield admin,pool,PostgresSessionStore(pool)
            finally:
                # This optional role is test-created on a pre-existing member, not
                # a membership_departments enrollment row. Remove only that exact
                # owned tuple before outer enrollment teardown; retain old roles.
                if created_admin:
                    admin.execute('DELETE FROM forge.membership_roles WHERE organization_id=%s '
                                  'AND membership_id=%s AND role=%s',
                                  (ORG_A,MEMBER_A,'organization_admin'))
                self.assertEqual(admin.execute(role_query,(original_members,)).fetchall(),
                                 original_roles,'Account fixture changed pre-existing role state')

    def test_schema_security_fingerprint(self):
        with self.fixture() as (admin,pool,store),self.db.pool() as readers:
            with store.connection.cursor() as cursor:
                fingerprint=catalog_fingerprint(cursor)
            print('Pristine account catalog SHA256:',fingerprint)
            self.assertTrue(AccountReadiness(pool,readers).check())
            # Connection roles are intentionally LOGIN; internal owners are not.
            self.assertEqual(admin.execute("SELECT bool_and(rolcanlogin) FROM pg_roles "
                "WHERE rolname IN ('forge_account_service','forge_runtime')").fetchone(),(True,))
            for role in ('forge_enrollment_authority','forge_migrator'):
                admin.execute(sql.SQL('ALTER ROLE {} LOGIN').format(sql.Identifier(role)))
                try:
                    self.assertFalse(AccountReadiness(pool,readers).check(),
                                     'Internal authority LOGIN drift was not rejected')
                finally:
                    admin.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
                self.assertTrue(AccountReadiness(pool,readers).check())
            admin.execute('ALTER TABLE forge.account_sessions NO FORCE ROW LEVEL SECURITY')
            self.assertFalse(AccountReadiness(pool,readers).check())
            admin.execute('ALTER TABLE forge.account_sessions FORCE ROW LEVEL SECURITY')
            self.assertTrue(AccountReadiness(pool,readers).check())
            admin.execute('CREATE POLICY unexpected ON forge.account_sessions USING (true)')
            self.assertFalse(AccountReadiness(pool,readers).check())
            admin.execute('DROP POLICY unexpected ON forge.account_sessions')
            admin.execute('GRANT SELECT ON forge.owned_accounts TO forge_account_service')
            self.assertFalse(AccountReadiness(pool,readers).check())
            admin.execute('REVOKE SELECT ON forge.owned_accounts FROM forge_account_service')
            signature='forge.account_validate_session(text)'
            original=admin.execute('SELECT pg_get_functiondef(%s::regprocedure)',(signature,)).fetchone()[0]
            changed=original.replace('RETURN account;', 'RETURN NULL;')
            self.assertNotEqual(changed,original)
            admin.execute(changed)
            self.assertFalse(AccountReadiness(pool,readers).check())
            admin.execute(original)
            self.assertTrue(AccountReadiness(pool,readers).check())
            self.assertFalse(AccountReadiness(readers,readers).check())

    def test_real_login_hash_only_logout_and_organization_suspension_distinct(self):
        with self.fixture() as (admin,pool,store):
            service=SessionService(store)
            session=service.login(EMAIL,PASSWORD)
            self.assertEqual(service.validate(session.capability).subject,str(ALICE))
            rows=admin.execute('SELECT capability_hash FROM forge.account_sessions').fetchall()
            self.assertEqual(rows,[(capability_digest(session.capability),)])
            self.assertNotIn(session.capability,repr(rows))
            admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
            self.assertIsNotNone(service.validate(session.capability))
            self.assertTrue(service.logout(session.capability))
            self.assertIsNone(service.validate(session.capability))
            self.assertFalse(service.logout(session.capability))

    def test_expiry_and_disable_revoke_all_sessions_without_reenable(self):
        with self.fixture() as (admin,pool,store):
            service=SessionService(store); first=service.login(EMAIL,PASSWORD); second=service.login(EMAIL,PASSWORD)
            admin.execute("UPDATE forge.account_sessions SET expires_at=clock_timestamp()-interval '1 second' WHERE capability_hash=%s",(capability_digest(first.capability),))
            self.assertIsNone(service.validate(first.capability))
            self.assertTrue(service.disable(second.capability))
            self.assertIsNone(service.validate(second.capability))
            with self.assertRaises(SessionDenied):service.login(EMAIL,PASSWORD)

    def test_persistent_generic_known_and_unknown_login_throttle(self):
        with self.fixture() as (admin,pool,store):
            service=SessionService(store)
            for email in (EMAIL,'unknown@example.com'):
                for _ in range(5):
                    with self.assertRaises(SessionDenied):service.login(email,'a wrong sufficiently long password')
                with self.assertRaises(LoginThrottled) as denied:service.login(email,PASSWORD)
                self.assertGreater(denied.exception.retry_seconds,0)
                self.assertLessEqual(denied.exception.retry_seconds,900)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.owned_accounts').fetchone()[0],1)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_sessions').fetchone()[0],0)

    def test_reset_single_use_revision_and_atomic_session_revocation(self):
        with self.fixture() as (admin,pool,store):
            service=SessionService(store); original=service.login(EMAIL,PASSWORD)
            reset=service.request_reset(EMAIL)
            self.assertIsNotNone(reset)
            self.assertIsNone(service.request_reset(EMAIL))
            self.assertIsNone(service.request_reset('unknown@example.com'))
            changed='a different sufficiently long password'
            self.assertTrue(service.reset(reset.capability,changed))
            self.assertFalse(service.reset(reset.capability,PASSWORD))
            self.assertIsNone(service.validate(original.capability))
            with self.assertRaises(SessionDenied):service.login(EMAIL,PASSWORD)
            self.assertIsNotNone(service.login(EMAIL,changed))

    def test_wrong_role_and_direct_context_cannot_read_or_mutate_credentials(self):
        with self.fixture() as (admin,pool,store):
            with self.db.pool() as wrong:
                with self.assertRaises(InvitationUnavailable):PostgresSessionStore(wrong).begin_login(EMAIL)
            with pool.connection() as conn:
                conn.execute("SELECT set_config('forge.enrollment_email',%s,false)",(EMAIL,))
                with self.assertRaises(errors.InsufficientPrivilege):conn.execute('SELECT password_hash FROM forge.owned_accounts')
                conn.execute('ROLLBACK')
                self.assertEqual(conn.execute("SELECT has_table_privilege(current_user,'forge.account_sessions','SELECT')").fetchone(),(False,))
                conn.execute("SELECT set_config('forge.enrollment_email','',false)")

    def test_atomic_reset_race_and_stale_login_revision_cannot_issue(self):
        with self.fixture() as (admin,pool,store):
            attempt=store.begin_login(EMAIL)
            reset=store.request_reset(EMAIL,capability_digest(secrets.token_urlsafe(32)))
            self.assertIsNotNone(reset)
            digest=admin.execute('SELECT capability_hash FROM forge.account_password_resets').fetchone()[0]
            with ThreadPoolExecutor(max_workers=2) as workers:
                results=list(workers.map(lambda _:store.consume_reset(digest,self.encoded),range(2)))
            self.assertEqual(sorted(results),[False,True])
            self.assertIsNone(store.finish_login(attempt,capability_digest(secrets.token_urlsafe(32))))
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.account_sessions').fetchone()[0],0)

    def test_concurrent_attempts_share_one_durable_budget(self):
        with self.fixture() as (admin,pool,store):
            with ThreadPoolExecutor(max_workers=4) as workers:
                attempts=list(workers.map(lambda _:store.begin_login(EMAIL),range(6)))
            self.assertEqual(sum(a.retry_seconds==0 for a in attempts),5)
            self.assertEqual(sum(a.retry_seconds>0 for a in attempts),1)
            self.assertEqual(admin.execute('SELECT login_attempts FROM forge.owned_accounts').fetchone()[0],5)

    def test_expired_reset_has_no_effect_and_retry_message_has_exclusive_lease(self):
        with self.fixture() as (admin,pool,store),TemporaryDirectory() as owned:
            service=SessionService(store)
            reset=service.request_reset(EMAIL)
            mailbox=LocalTestMailbox(Path(owned),sender='forge@example.com')
            delivery=DeliveryCoordinator(PostgresDeliveryStore(pool),mailbox,
                origin='http://127.0.0.1:8000',encryption_key=Fernet.generate_key())
            message=delivery.queue_reset(reset)
            row=admin.execute('SELECT state,encrypted_payload FROM forge.account_message_delivery WHERE id=%s',(message,)).fetchone()
            self.assertEqual(row[0],'pending')
            self.assertNotIn(reset.capability,row[1])
            first,second=uuid4(),uuid4()
            self.assertIsNotNone(delivery.store.claim(message,first))
            self.assertIsNone(delivery.store.claim(message,second))
            self.assertFalse(delivery.store.finish(message,second,True))
            self.assertTrue(delivery.store.finish(message,first,False))
            self.assertEqual(delivery.dispatch(message),DeliveryState.DELIVERED)
            self.assertEqual(len(list(Path(owned).glob('*.eml'))),1)
            self.assertEqual(admin.execute('SELECT state FROM forge.account_message_delivery WHERE id=%s',(message,)).fetchone()[0],'delivered')
            self.assertEqual(delivery.dispatch(message),DeliveryState.PENDING)
            self.assertEqual(len(list(Path(owned).glob('*.eml'))),1)
            admin.execute("UPDATE forge.account_password_resets SET expires_at=clock_timestamp()-interval '1 second'")
            self.assertFalse(store.consume_reset(capability_digest(reset.capability),self.encoded))
            self.assertEqual(admin.execute('SELECT credential_revision FROM forge.owned_accounts').fetchone()[0],1)

    def test_actual_http_invite_accept_login_and_scoped_bootstrap(self):
        with self.fixture() as (admin,pool,store), self.db.pool() as readers, TemporaryDirectory() as owned:
            dept=uuid4()
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
            admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,'Existing Area')",(ORG_A,dept))
            enrollment_password=secrets.token_urlsafe(32)
            admin.execute(sql.SQL('ALTER ROLE forge_enrollment LOGIN PASSWORD {}').format(sql.Literal(enrollment_password)))
            kwargs=settings()|dict(user='forge_enrollment',password=enrollment_password)
            with ConnectionPool('',kwargs=kwargs,min_size=1,max_size=2,open=True) as enrollment_pool:
                enrollment_pool.wait(5)
                service=SessionService(store)
                invitations=InvitationService(PostgresInvitationStore(enrollment_pool),PostgresEnrollmentStore(enrollment_pool))
                mailbox=LocalTestMailbox(Path(owned),sender='forge@example.com')
                delivery=DeliveryCoordinator(PostgresDeliveryStore(pool),mailbox,origin='http://127.0.0.1:8000',encryption_key=Fernet.generate_key())
                readiness=AccountReadiness(pool,readers)
                self.assertTrue(readiness.check())
                app=create_account_app(sessions=service,invitations=invitations,delivery=delivery,
                    readiness=readiness,bootstrap_reader=PostgresBootstrapReader(readers),
                    authorization_reader=PostgresAuthorizationReader(readers))
                with TestClient(app,raise_server_exceptions=False) as client:
                    login=client.post('/forge/v1/accounts/login',json={'email':EMAIL,'password':PASSWORD})
                    self.assertEqual(login.status_code,200)
                    headers={'Authorization':'Bearer '+login.json()['access_token']}
                    before=admin.execute('SELECT count(*) FROM forge.memberships').fetchone()[0]
                    issued=client.post('/forge/v1/accounts/invitations',headers=headers,json={
                        'organization_id':str(ORG_A),'department_id':str(dept),
                        'email':'new-member@example.com','name':'New Member'})
                    self.assertEqual(issued.status_code,201,issued.text)
                    self.assertEqual(issued.json()['delivery_state'],'delivered')
                    self.assertEqual(issued.json()['delivery_channel'],'local_test_mailbox')
                    self.assertNotIn('capability',issued.text)
                    self.assertEqual(admin.execute('SELECT count(*) FROM forge.memberships').fetchone()[0],before)
                    message=BytesParser(policy=policy.default).parsebytes(next(Path(owned).glob('*.eml')).read_bytes())
                    link=next(line.strip() for line in message.get_body(preferencelist=('plain',)).get_content().splitlines() if line.startswith('http://'))
                    fragment=parse_qs(urlsplit(link).fragment)
                    accepted=client.post('/forge/v1/accounts/invitations/accept',json={
                        'invitation_id':fragment['invitation_id'][0],
                        'capability':fragment['capability'][0],'password':PASSWORD})
                    self.assertEqual(accepted.status_code,201,accepted.text)
                    member=accepted.json()['membership_id']
                    self.assertEqual(admin.execute('SELECT role FROM forge.membership_roles WHERE membership_id=%s',(member,)).fetchall(),[('member',)])
                    entrant=client.post('/forge/v1/accounts/login',json={'email':'new-member@example.com','password':PASSWORD})
                    self.assertEqual(entrant.status_code,200)
                    own={'Authorization':'Bearer '+entrant.json()['access_token']}
                    self.assertEqual(client.get('/forge/v1/bootstrap',params={'organization_id':str(ORG_A)},headers=own).status_code,200)
                    self.assertEqual(client.get('/forge/v1/bootstrap',params={'organization_id':str(ORG_B)},headers=own).status_code,404)
                    admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s",(member,))
                    self.assertEqual(client.get('/forge/v1/bootstrap',params={'organization_id':str(ORG_A)},headers=own).status_code,403)
                    denied=client.post('/forge/v1/accounts/invitations',headers=own,json={
                        'organization_id':str(ORG_A),'department_id':str(dept),'email':'blocked@example.com','name':'Blocked'})
                    self.assertEqual(denied.status_code,404)
                    self.assertEqual(client.post('/forge/v1/accounts/logout',headers=own).status_code,204)
                    self.assertEqual(client.get('/forge/v1/bootstrap',params={'organization_id':str(ORG_A)},headers=own).status_code,401)
