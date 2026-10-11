"""Real protected central gateway configuration in the owned PostgreSQL harness."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager,ExitStack
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql,errors
from psycopg_pool import ConnectionPool
from postgres_support import (AccountDatabaseFixture,owned_gateway_configuration_schema,
    settings,ORG_A,ORG_B,MEMBER_A,ALICE,BOB)
from forge.accounts import ACCOUNT_ISSUER,PasswordHasher
from forge.account_sessions import SessionService,PostgresSessionStore
from forge.account_api import create_account_app
from forge.authorization_store import PostgresAuthorizationReader
from forge.postgres import PostgresBootstrapReader
from forge.account_readiness import AccountReadiness,catalog_fingerprint
from forge.gateway_configuration_readiness import GatewayAccountReadiness,_EXPECTED_SHA256
from forge.gateway_configuration import (GatewayCipher,GatewayConfiguration,GatewayDenied,
    GatewayConflict,GatewayUnavailable,GATEWAY_ENDPOINT)
from forge.gateway_configuration_store import PostgresGatewayStore

PASSWORD='a real sufficiently long fixture password'
KEY='fixture-only-central-gateway-key'

class PostgresGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=AccountDatabaseFixture();cls.encoded=PasswordHasher().hash(PASSWORD)
    def setUp(self):self.db.reset()

    @contextmanager
    def fixture(self):
        with owned_gateway_configuration_schema() as admin,ExitStack() as stack:
            original_roles=admin.execute('SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2,3').fetchall()
            try:
                for account,email in ((ALICE,'admin@example.com'),(BOB,'member@example.com')):
                    admin.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',('forge',ACCOUNT_ISSUER,str(account),account))
                    admin.execute("INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) VALUES(%s,%s,'Fixture',%s)",(account,email,self.encoded))
                admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin') ON CONFLICT DO NOTHING",(ORG_A,MEMBER_A))
                pools={}
                for role in ('forge_account_service','forge_gateway_service'):
                    password=secrets.token_urlsafe(32)
                    admin.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
                    pool=stack.enter_context(ConnectionPool('',kwargs=settings()|dict(user=role,password=password),min_size=1,max_size=4))
                    pool.wait(5);pools[role]=pool
                readers=stack.enter_context(self.db.pool())
                sessions=SessionService(PostgresSessionStore(pools['forge_account_service']))
                token=sessions.login('admin@example.com',PASSWORD).capability
                store=PostgresGatewayStore(pools['forge_gateway_service'])
                encryption_key=Fernet.generate_key()
                service=GatewayConfiguration(store,GatewayCipher(encryption_key))
                ready=GatewayAccountReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service'])
                yield admin,pools,readers,sessions,token,store,service,ready,encryption_key
            finally:
                # Remove only this fixture's role tuple, preserving every original role.
                if (ORG_A,MEMBER_A,'organization_admin') not in original_roles:
                    admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
                self.assertEqual(admin.execute('SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2,3').fetchall(),original_roles)

    def test_00_reviewed_pristine_schema_fingerprint(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            with store.connection.cursor() as cursor:actual=catalog_fingerprint(cursor)
            print('Reviewed gateway PostgreSQL17 catalog SHA256:',actual)
            # Bounded fixture-only diagnosis: metadata symbols, never SQL parameters.
            from forge.invitations import capability_digest
            try:
                with pools['forge_gateway_service'].connection(timeout=1) as connection:
                    connection.execute('SELECT * FROM forge.gateway_read(%s,%s)',(capability_digest(token),ORG_A)).fetchall()
            except Exception as error:
                primary=getattr(getattr(error,'diag',None),'message_primary','')
                symbols=[name for name in ('revision','binding_id','endpoint','encrypted_key','enrollment_uuid','enrollment_lock_admin','account_validate_session','identities','memberships','organization_gateways','gateway_configuration_audit') if name in primary]
                print('Safe fixture SQL diagnosis:',type(error).__name__,getattr(error,'sqlstate',None),symbols)
                raise AssertionError('Gateway fixture SQL operation failed; safe category retained') from None

            self.assertEqual(actual,_EXPECTED_SHA256,'Static build artifact must be authored before activation')
            self.assertTrue(ready.check())
            self.assertFalse(AccountReadiness(pools['forge_account_service'],readers).check(),'Legacy exact profile must not silently accept0015')

    def test_genuine_account_http_save_read_and_reopen(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            app=create_account_app(sessions=sessions,readiness=ready,
                bootstrap_reader=PostgresBootstrapReader(readers),authorization_reader=PostgresAuthorizationReader(readers),gateway_configuration=service)
            with TestClient(app,raise_server_exceptions=False) as client:
                headers={'Authorization':'Bearer '+token};url='/forge/v1/orgs/'+str(ORG_A)+'/gateway'
                self.assertEqual(client.get(url,headers=headers).json(),{'status':'NOT_CONFIGURED','revision':0,'endpoint':GATEWAY_ENDPOINT,'allowed_endpoints':[GATEWAY_ENDPOINT]})
                result=client.put(url,headers=headers,json={'expected_revision':0,'api_key':KEY})
                self.assertEqual(result.status_code,200);self.assertNotIn(KEY,result.text)
                self.assertEqual(result.json()['status'],'SAVED_UNVERIFIED')
                self.assertEqual(client.get(url,headers=headers).json()['revision'],1)
                reopened=GatewayConfiguration(PostgresGatewayStore(pools['forge_gateway_service']),GatewayCipher(key))
                self.assertEqual(reopened.read(token,ORG_A).revision,1)
                self.assertEqual(client.get('/forge/v1/bootstrap?organization_id='+str(ORG_A),headers=headers).status_code,200)
                member_token=sessions.login('member@example.com',PASSWORD).capability
                self.assertEqual(client.get(url,headers={'Authorization':'Bearer '+member_token}).status_code,404)
                self.assertEqual(client.get('/forge/v1/orgs/'+str(ORG_B)+'/gateway',headers=headers).status_code,404)
                admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
                try:self.assertEqual(client.get(url,headers=headers).status_code,404)
                finally:admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))

                self.assertEqual(client.put(url,headers=headers,json={'expected_revision':0,'api_key':KEY}).status_code,409)
                self.assertEqual(client.post('/forge/v1/accounts/logout',headers=headers).status_code,204)
                self.assertEqual(client.get(url,headers=headers).status_code,401)

    def test_current_authority_and_live_session_revalidation(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            member=sessions.login('member@example.com',PASSWORD).capability
            for capability,org in ((member,ORG_A),(token,ORG_B)):
                with self.assertRaises(GatewayDenied):service.save(capability,org,0,KEY)
            admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
            with self.assertRaises(GatewayDenied):service.save(token,ORG_A,0,KEY)
            admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
            admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s',(ORG_A,))
            with self.assertRaises(GatewayDenied):service.read(token,ORG_A)
            admin.execute('UPDATE forge.organizations SET active=true WHERE id=%s',(ORG_A,))
            admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
            with self.assertRaises(GatewayDenied):service.save(token,ORG_A,0,KEY)
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
            sessions.logout(token)
            with self.assertRaises(GatewayDenied):service.save(token,ORG_A,0,KEY)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.organization_gateways').fetchone(),(0,))

    def test_compare_and_swap_race_and_transaction_rollback(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            def attempt():
                try:service.save(token,ORG_A,0,KEY);return 'saved'
                except GatewayConflict:return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:
                self.assertEqual(sorted(workers.map(lambda _:attempt(),range(2))),['conflict','saved'])
            before=admin.execute('SELECT revision,binding_id,encrypted_key FROM forge.organization_gateways').fetchone()
            from forge.invitations import capability_digest
            with self.assertRaises(GatewayUnavailable):
                with store.connection.cursor() as cursor:
                    cursor.execute('SELECT * FROM forge.gateway_save(%s,%s,%s,%s,%s)',(capability_digest(token),ORG_A,1,uuid4(),'x'*200))
                    raise RuntimeError('controlled rollback')
            self.assertEqual(admin.execute('SELECT revision,binding_id,encrypted_key FROM forge.organization_gateways').fetchone(),before)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.gateway_configuration_audit').fetchone(),(1,))

    def test_wrong_key_and_database_cipher_substitution_rejected(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            service.save(token,ORG_A,0,KEY)
            with self.assertRaises(GatewayUnavailable):GatewayConfiguration(store,GatewayCipher(Fernet.generate_key())).read(token,ORG_A)
            admin.execute('UPDATE forge.organization_gateways SET binding_id=%s WHERE organization_id=%s',(uuid4(),ORG_A))
            with self.assertRaises(GatewayUnavailable):service.read(token,ORG_A)

    def test_function_only_roles_and_readiness_security_drift(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            self.assertTrue(ready.check())
            for pool in (pools['forge_gateway_service'],pools['forge_account_service'],readers):
                with pool.connection(timeout=1) as connection:
                    with self.assertRaises(errors.InsufficientPrivilege):connection.execute('SELECT encrypted_key FROM forge.organization_gateways')
            with self.assertRaises(GatewayUnavailable):PostgresGatewayStore(pools['forge_account_service']).read('a'*64,ORG_A)
            admin.execute('ALTER TABLE forge.organization_gateways NO FORCE ROW LEVEL SECURITY')
            self.assertFalse(ready.check());admin.execute('ALTER TABLE forge.organization_gateways FORCE ROW LEVEL SECURITY')
            admin.execute('GRANT SELECT ON forge.organization_gateways TO forge_gateway_service')
            self.assertFalse(ready.check());admin.execute('REVOKE SELECT ON forge.organization_gateways FROM forge_gateway_service')
            admin.execute('ALTER ROLE forge_gateway_authority LOGIN')
            self.assertFalse(ready.check());admin.execute('ALTER ROLE forge_gateway_authority NOLOGIN')
            admin.execute('CREATE POLICY unauthorized ON forge.organization_gateways USING(true)')
            self.assertFalse(ready.check());admin.execute('DROP POLICY unauthorized ON forge.organization_gateways')
            signature='forge.gateway_read(text,uuid)'
            original=admin.execute('SELECT pg_get_functiondef(%s::regprocedure)',(signature,)).fetchone()[0]
            changed=original.replace('PERFORM forge.gateway_lock_admin(digest,org);','PERFORM 1;')
            self.assertNotEqual(original,changed);admin.execute(changed)
            self.assertFalse(ready.check());admin.execute(original);self.assertTrue(ready.check())

    def test_additive_migration_failure_rolls_back_roles_and_schema(self):
        with owned_gateway_configuration_schema(fail_migration=True) as admin:
            self.assertIsNone(admin.execute("SELECT to_regclass('forge.organization_gateways')").fetchone()[0])
            self.assertEqual(admin.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'forge_gateway_%'").fetchone(),(0,))
