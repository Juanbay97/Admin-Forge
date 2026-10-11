"""Real owned PostgreSQL CG2 with labelled HTTPX discovery, no remote calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
from pathlib import Path
import secrets
import sys
import unittest
from uuid import UUID,uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql, errors
from psycopg_pool import ConnectionPool
from postgres_support import (GatewayCatalogDatabaseFixture,owned_gateway_catalog_schema,
    settings,ORG_A,ORG_B,MEMBER_A,MEMBER_B,ALICE,BOB,CAROL)
from forge.accounts import ACCOUNT_ISSUER,PasswordHasher
from forge.account_sessions import SessionService,PostgresSessionStore
from forge.account_api import create_account_app
from forge.authorization_store import PostgresAuthorizationReader
from forge.postgres import PostgresBootstrapReader
from forge.account_readiness import catalog_fingerprint
from forge.gateway_configuration_readiness import GatewayAccountReadiness
from forge.gateway_configuration import (GatewayCipher,GatewayConfiguration,GatewayDenied,
    GatewayConflict,GatewayUnavailable)
from forge.gateway_configuration_store import PostgresGatewayStore
from forge.gateway_catalog import GatewayCatalog
from forge.gateway_catalog_adapter import HttpxModelsAdapter
from forge.gateway_catalog_store import PostgresGatewayCatalogStore
from forge.gateway_catalog_readiness import GatewayCatalogReadiness,_EXPECTED_SHA256

PASSWORD='a real sufficiently long fixture password'
KEY='fixture-only-central-gateway-key'
OWN_MEMBER=UUID(int=23)

class PostgresGatewayCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=GatewayCatalogDatabaseFixture();cls.encoded=PasswordHasher().hash(PASSWORD)
    def setUp(self):self.db.reset()

    @contextmanager
    def fixture(self):
        with owned_gateway_catalog_schema() as admin,ExitStack() as stack:
            roles=admin.execute('SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2,3').fetchall()
            try:
                for account,email in ((ALICE,'admin@example.com'),(CAROL,'member@example.com'),(BOB,'foreign@example.com')):
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
                key=Fernet.generate_key()
                service=GatewayConfiguration(store,GatewayCipher(key))
                ready=GatewayCatalogReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service'])
                yield admin,pools,readers,sessions,token,store,service,ready,key
            finally:
                if (ORG_A,MEMBER_A,'organization_admin') not in roles:
                    admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
                self.assertEqual(admin.execute('SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2,3').fetchall(),roles)

    def catalog(self,pools,key,handler=None):
        def models(request):
            self.assertEqual(str(request.url),'https://ia.prometheonlab.com/v1/models')
            self.assertEqual(request.headers['authorization'],'Bearer '+KEY)
            return httpx.Response(200,json={'data':[{'id':'upstream/private-a'},{'id':'upstream/private-b'}]})
        return GatewayCatalog(PostgresGatewayCatalogStore(pools['forge_gateway_service']),GatewayCipher(key),
            HttpxModelsAdapter(transport=httpx.MockTransport(handler or models)))

    def prepared(self,service,catalog,token):
        service.save(token,ORG_A,0,KEY)
        self.assertEqual(catalog.refresh(token,ORG_A)['gateway_revision'],1)
        return {'assistant':'upstream/private-a','fast':'upstream/private-b'}

    def test_00_exact_reviewed_profile_and_legacy_rejection(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            with store.connection.cursor() as cursor:actual=catalog_fingerprint(cursor)
            print('Reviewed CG2 PostgreSQL17 catalog SHA256:',actual)
            self.assertEqual(actual,_EXPECTED_SHA256)
            self.assertTrue(ready.check())
            self.assertFalse(GatewayAccountReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service']).check())

    def test_genuine_http_discovery_publication_member_projection_and_reopen(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);service.save(token,ORG_A,0,KEY)
            app=create_account_app(sessions=sessions,readiness=ready,authorization_reader=PostgresAuthorizationReader(readers),
                bootstrap_reader=PostgresBootstrapReader(readers),gateway_configuration=service,gateway_catalog=catalog)
            url='/forge/v1/orgs/'+str(ORG_A);headers={'Authorization':'Bearer '+token}
            with TestClient(app,raise_server_exceptions=False) as client:
                response=client.post(url+'/gateway/catalogue/refresh',headers=headers)
                self.assertEqual(response.status_code,200);self.assertEqual(response.json()['capability_state'],'unknown')
                request={'operation_id':str(uuid4()),'expected_catalogue_revision':0,'expected_gateway_revision':1,
                    'aliases':{'assistant':'upstream/private-a'},'default_alias':'assistant'}
                self.assertEqual(client.post(url+'/models/publish',headers=headers,json=request).status_code,200)
                member=sessions.login('member@example.com',PASSWORD).capability;employee={'Authorization':'Bearer '+member}
                response=client.get(url+'/models',headers=employee)
                self.assertEqual(response.status_code,200);self.assertEqual(response.json()['default_model'],'assistant')
                self.assertIsNone(response.json()['models'][0]['tools'])
                self.assertEqual(response.json()['models'][0]['verification'],'unverified')
                for secret in (KEY,'upstream/private-a','route_id','binding_id','evidence_id','encrypted_key'):
                    self.assertNotIn(secret,response.text)
                self.assertEqual(client.get('/forge/v1/bootstrap?organization_id='+str(ORG_A),headers=employee).status_code,200)
                self.assertEqual(client.post(url+'/models/publish',headers=employee,json=request).status_code,404)
                self.assertEqual(client.post(url+'/gateway/catalogue/refresh',headers=employee).status_code,404)
                self.assertEqual(client.get('/forge/v1/orgs/'+str(ORG_B)+'/models',headers=employee).status_code,404)
                foreign=sessions.login('foreign@example.com',PASSWORD).capability
                self.assertEqual(client.get(url+'/models',headers={'Authorization':'Bearer '+foreign}).status_code,404)
                self.assertEqual(client.post(url+'/models/publish',headers=headers,json=request).json()['revision'],1)
                self.assertEqual(self.catalog(pools,key).read(member,ORG_A),response.json())
                sessions.logout(member);self.assertEqual(client.get(url+'/models',headers=employee).status_code,401)

    def test_selection_validation_cas_replay_and_race(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);mapping=self.prepared(service,catalog,token);operation=uuid4()
            for selected,default in (({'bad':'not-discovered'},'bad'),(mapping,'absent'),({'Bad':'upstream/private-a'},'Bad')):
                with self.assertRaises(ValueError):catalog.publish(token,ORG_A,uuid4(),0,1,selected,default)
            result=catalog.publish(token,ORG_A,operation,0,1,mapping,'assistant')
            self.assertEqual(catalog.publish(token,ORG_A,operation,0,1,mapping,'assistant'),result)
            with self.assertRaises(GatewayConflict):catalog.publish(token,ORG_A,operation,0,1,mapping,'fast')
            with self.assertRaises(GatewayConflict):catalog.publish(token,ORG_A,uuid4(),0,1,mapping,'assistant')
            def publish(_):
                try:catalog.publish(token,ORG_A,uuid4(),1,1,mapping,'fast');return 'published'
                except GatewayConflict:return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:
                self.assertEqual(sorted(workers.map(publish,range(2))),['conflict','published'])
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.catalog_publication_operations').fetchone(),(2,))

    def test_rotation_during_discovery_and_publication_fails_closed(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);mapping=self.prepared(service,catalog,token)
            catalog.publish(token,ORG_A,uuid4(),0,1,mapping,'assistant')
            member=sessions.login('member@example.com',PASSWORD).capability
            def rotating(request):
                # Nested mutation succeeds only when network IO holds no org lock.
                service.save(token,ORG_A,1,KEY)
                return httpx.Response(200,json={'data':[{'id':'upstream/private-a'}]})
            with self.assertRaises(GatewayConflict):self.catalog(pools,key,rotating).refresh(token,ORG_A)
            with self.assertRaises(GatewayDenied):catalog.read(member,ORG_A)
            catalog.refresh(token,ORG_A)
            original=catalog._store.publish
            def rotate_before_publish(*args):
                service.save(token,ORG_A,2,KEY);return original(*args)
            catalog._store.publish=rotate_before_publish
            with self.assertRaises(GatewayConflict):catalog.publish(token,ORG_A,uuid4(),1,2,mapping,'assistant')
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(),(1,))

    def test_fresh_authority_before_replay_and_member_reads(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);mapping=self.prepared(service,catalog,token);operation=uuid4()
            catalog.publish(token,ORG_A,operation,0,1,mapping,'assistant')
            member=sessions.login('member@example.com',PASSWORD).capability
            self.assertEqual(catalog.read(member,ORG_A)['revision'],1)
            foreign=sessions.login('foreign@example.com',PASSWORD).capability
            with self.assertRaises(GatewayDenied):catalog.read(foreign,ORG_A)
            with self.assertRaises(GatewayDenied):catalog.publish(token,ORG_B,uuid4(),0,1,mapping,'assistant')
            admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
            with self.assertRaises(GatewayDenied):catalog.publish(token,ORG_A,operation,0,1,mapping,'assistant')
            with self.assertRaises(GatewayDenied):catalog.refresh(token,ORG_A)
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
            admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,OWN_MEMBER))
            with self.assertRaises(GatewayDenied):catalog.read(member,ORG_A)
            admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id=%s",(ORG_A,OWN_MEMBER))
            admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s',(ORG_A,))
            with self.assertRaises(GatewayDenied):catalog.read(member,ORG_A)
            admin.execute('UPDATE forge.organizations SET active=true WHERE id=%s',(ORG_A,))
            sessions.logout(token)
            with self.assertRaises(GatewayDenied):catalog.publish(token,ORG_A,operation,0,1,mapping,'assistant')

    def test_cipher_wrong_key_discovery_abort_and_private_mapping_rejection(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);service.save(token,ORG_A,0,KEY)
            wrong=self.catalog(pools,Fernet.generate_key())
            with self.assertRaises(GatewayUnavailable):wrong.refresh(token,ORG_A)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.gateway_model_discoveries').fetchone(),(0,))
            original=catalog._store.save_discovery
            def revoke_after_fetch(*args):
                sessions.logout(token);return original(*args)
            catalog._store.save_discovery=revoke_after_fetch
            with self.assertRaises(GatewayDenied):catalog.refresh(token,ORG_A)
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.gateway_model_discoveries').fetchone(),(0,))

    def test_atomic_rollback_all_publication_objects(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);mapping=self.prepared(service,catalog,token)
            admin.execute("CREATE FUNCTION forge.fixture_reject_catalog() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'labelled-fixture'; END $$")
            admin.execute('CREATE TRIGGER fixture_reject_catalog BEFORE INSERT ON forge.catalog_publication_operations FOR EACH ROW EXECUTE FUNCTION forge.fixture_reject_catalog()')
            try:
                with self.assertRaises(GatewayUnavailable):catalog.publish(token,ORG_A,uuid4(),0,1,mapping,'assistant')
                for table in ('model_catalog_snapshots','gateway_catalog_selections','outbox_events','active_model_catalogs','catalog_publication_operations'):
                    self.assertEqual(admin.execute(sql.SQL('SELECT count(*) FROM forge.{}').format(sql.Identifier(table))).fetchone(),(0,))
            finally:
                admin.execute('DROP TRIGGER fixture_reject_catalog ON forge.catalog_publication_operations')
                admin.execute('DROP FUNCTION forge.fixture_reject_catalog()')

    def test_private_role_isolation_and_exact_profile_drift(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key);mapping=self.prepared(service,catalog,token)
            catalog.publish(token,ORG_A,uuid4(),0,1,mapping,'assistant')
            for pool in (pools['forge_gateway_service'],pools['forge_account_service'],readers):
                with pool.connection() as connection:
                    for table in ('gateway_catalog_selections','gateway_model_discoveries','organization_gateways'):
                        with self.assertRaises(errors.InsufficientPrivilege):
                            connection.execute(sql.SQL('SELECT * FROM forge.{}').format(sql.Identifier(table)))
            self.assertTrue(ready.check())
            for mutation,restore in (
                ('ALTER TABLE forge.gateway_catalog_selections NO FORCE ROW LEVEL SECURITY','ALTER TABLE forge.gateway_catalog_selections FORCE ROW LEVEL SECURITY'),
                ('GRANT SELECT ON forge.gateway_catalog_selections TO forge_runtime','REVOKE SELECT ON forge.gateway_catalog_selections FROM forge_runtime'),
                ('CREATE POLICY fixture_extra ON forge.gateway_catalog_selections USING (false)','DROP POLICY fixture_extra ON forge.gateway_catalog_selections'),
                ('ALTER ROLE forge_gateway_authority LOGIN','ALTER ROLE forge_gateway_authority NOLOGIN'),
                ('ALTER FUNCTION forge.gateway_catalog_member(text,uuid) SECURITY INVOKER','ALTER FUNCTION forge.gateway_catalog_member(text,uuid) SECURITY DEFINER')):
                admin.execute(mutation)
                try:self.assertFalse(ready.check())
                finally:admin.execute(restore)
                self.assertTrue(ready.check())
