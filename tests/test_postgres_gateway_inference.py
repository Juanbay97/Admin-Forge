"""Real owned PostgreSQL CG3a with labelled HTTPX discovery, no remote calls."""
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
from postgres_support import (GatewayCatalogDatabaseFixture,owned_gateway_inference_schema,
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
from forge.gateway_catalog_readiness import GatewayCatalogReadiness
from forge.gateway_inference_readiness import GatewayInferenceReadiness,_EXPECTED_SHA256
from forge.gateway_inference import GatewayInference,TextRequest
from forge.gateway_inference_store import PostgresGatewayInferenceStore
from forge.gateway_inference_adapter import HttpxTextAdapter
from forge.invitations import capability_digest
import asyncio

PASSWORD='a real sufficiently long fixture password'
KEY='fixture-only-central-gateway-key'
OWN_MEMBER=UUID(int=23)

class PostgresGatewayInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=GatewayCatalogDatabaseFixture();cls.encoded=PasswordHasher().hash(PASSWORD)
    def setUp(self):self.db.reset()

    @contextmanager
    def fixture(self):
        with owned_gateway_inference_schema() as admin,ExitStack() as stack:
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
                ready=GatewayInferenceReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service'])
                yield admin,pools,readers,sessions,token,store,service,ready,key
            finally:
                if (ORG_A,MEMBER_A,'organization_admin') not in roles:
                    admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
                self.assertEqual(admin.execute('SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2,3').fetchall(),roles)


    def prepared(self,pools,key,service,token):
        service.save(token,ORG_A,0,KEY)
        catalog=GatewayCatalog(PostgresGatewayCatalogStore(pools['forge_gateway_service']),
            GatewayCipher(key),HttpxModelsAdapter(transport=httpx.MockTransport(
                lambda request:httpx.Response(200,json={'data':[{'id':'upstream/private-a'}]}))))
        catalog.refresh(token,ORG_A)
        catalog.publish(token,ORG_A,uuid4(),0,1,{'assistant':'upstream/private-a'},'assistant')
        return catalog

    def inference(self,pools,key,handler=None):
        self.outbound=0
        def labelled(request):
            self.outbound+=1
            self.assertEqual(str(request.url),'https://ia.prometheonlab.com/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer '+KEY)
            data=__import__('json').loads(request.content)
            self.assertEqual(data['model'],'upstream/private-a')
            body=b'data: {"choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
            body+=b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
            class LabelledBody(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield body
            return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=LabelledBody())
        store=PostgresGatewayInferenceStore(pools['forge_gateway_service'])
        service=GatewayInference(store,GatewayCipher(key),
            HttpxTextAdapter(transport=httpx.MockTransport(handler or labelled)))
        return store,service

    def test_00_reviewed_profile(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            with store.connection.cursor() as cursor:actual=catalog_fingerprint(cursor)
            print('Reviewed CG3a PostgreSQL17 catalog SHA256:',actual)
            self.assertEqual(actual,_EXPECTED_SHA256)
            self.assertTrue(ready.check())
            self.assertFalse(GatewayCatalogReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service']).check())

    def test_genuine_employee_http_uses_only_published_private_route(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            self.prepared(pools,key,service,token)
            _,inference=self.inference(pools,key)
            app=create_account_app(sessions=sessions,readiness=ready,gateway_inference=inference)
            member=sessions.login('member@example.com',PASSWORD).capability
            body={'model':'assistant','messages':[{'role':'user','content':'hello'}],'stream':True}
            url='/forge/v1/orgs/'+str(ORG_A)+'/chat/completions'
            with TestClient(app,raise_server_exceptions=False) as client:
                response=client.post(url,headers={'Authorization':'Bearer '+member},json=body)
                self.assertEqual(response.status_code,200,response.text)
                self.assertIn('"content":"Hello"',response.text)
                self.assertIn('"model":"assistant"',response.text)
                for secret in (KEY,'upstream/private-a','binding_id','encrypted_key'):
                    self.assertNotIn(secret,response.text)
                self.assertEqual(self.outbound,1)
                self.assertEqual(client.post(url,headers={'Authorization':'Bearer '+member},
                    json=body|{'model':'unpublished'}).status_code,404)
                foreign=sessions.login('foreign@example.com',PASSWORD).capability
                self.assertEqual(client.post(url,headers={'Authorization':'Bearer '+foreign},json=body).status_code,404)
                sessions.logout(member)
                self.assertEqual(client.post(url,headers={'Authorization':'Bearer '+member},json=body).status_code,401)
                self.assertEqual(self.outbound,1)

    def test_current_authority_alias_binding_and_credential_denials(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            route,inference=self.inference(pools,key)
            member=sessions.login('member@example.com',PASSWORD).capability
            digest=capability_digest(member)
            with self.assertRaises(GatewayDenied):route.resolve(digest,ORG_A,'assistant')
            self.prepared(pools,key,service,token)
            for org,alias in ((ORG_B,'assistant'),(ORG_A,'absent'),(ORG_A,'private/upstream')):
                with self.assertRaises(GatewayDenied):route.resolve(digest,org,alias)
            for mutate,restore in (
                ("UPDATE forge.memberships SET status='suspended' WHERE id=%s",
                 "UPDATE forge.memberships SET status='active' WHERE id=%s"),
            ):
                admin.execute(mutate,(OWN_MEMBER,))
                try:
                    with self.assertRaises(GatewayDenied):route.resolve(digest,ORG_A,'assistant')
                finally:admin.execute(restore,(OWN_MEMBER,))
            admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s',(ORG_A,))
            try:
                with self.assertRaises(GatewayDenied):route.resolve(digest,ORG_A,'assistant')
            finally:admin.execute('UPDATE forge.organizations SET active=true WHERE id=%s',(ORG_A,))
            request=TextRequest('assistant',(('user','hello'),))
            wrong=GatewayInference(route,GatewayCipher(Fernet.generate_key()),inference._adapter)
            with self.assertRaises(GatewayUnavailable):asyncio.run(wrong.prepare(member,ORG_A,request))
            self.assertEqual(self.outbound,0)
            sessions.logout(member)
            with self.assertRaises(GatewayDenied):route.resolve(digest,ORG_A,'assistant')
            member=sessions.login('member@example.com',PASSWORD).capability
            reset=sessions.request_reset('member@example.com')
            sessions.reset(reset.capability,PASSWORD)
            with self.assertRaises(GatewayDenied):route.resolve(capability_digest(member),ORG_A,'assistant')
            member=sessions.login('member@example.com',PASSWORD).capability
            sessions.disable(member)
            with self.assertRaises(GatewayDenied):route.resolve(capability_digest(member),ORG_A,'assistant')

    def test_rotation_before_outbound_and_during_stream_closes(self):
        from unittest.mock import patch
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.prepared(pools,key,service,token)
            member=sessions.login('member@example.com',PASSWORD).capability
            route,inference=self.inference(pools,key)
            request=TextRequest('assistant',(('user','hello'),))
            prepared=asyncio.run(inference.prepare(member,ORG_A,request))
            service.save(token,ORG_A,1,KEY)
            async def collect():return b''.join([x async for x in inference.stream(prepared)])
            self.assertIn(b'INFERENCE_UNAVAILABLE',asyncio.run(collect()))
            self.assertEqual(self.outbound,0)
            catalog.refresh(token,ORG_A)
            catalog.publish(token,ORG_A,uuid4(),1,2,{'assistant':'upstream/private-a'},'assistant')

            class Blocked(httpx.AsyncByteStream):
                closed=False
                async def __aiter__(self):
                    yield b'data: {"choices":[{"index":0,"delta":{"content":"First"},"finish_reason":null}]}\n\n'
                    await asyncio.sleep(5)
                async def aclose(self):self.closed=True
            stream_body=Blocked()
            def labelled(request):
                return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream_body)
            _,inference=self.inference(pools,key,labelled)
            async def rotating():
                prepared=await inference.prepare(member,ORG_A,request)
                stream=inference.stream(prepared)
                self.assertIn(b'First',await anext(stream))
                # Actual SQL mutation succeeds: no provider-held organization lock.
                service.save(token,ORG_A,2,KEY)
                remaining=b''.join([x async for x in stream])
                self.assertIn(b'INFERENCE_UNAVAILABLE',remaining)
            with patch('forge.gateway_inference.REVOCATION_INTERVAL',.01):
                asyncio.run(rotating())
            self.assertTrue(stream_body.closed)

    def test_cipher_substitution_fails_before_outbound(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            self.prepared(pools,key,service,token)
            _,inference=self.inference(pools,key)
            member=sessions.login('member@example.com',PASSWORD).capability
            record=store.read(capability_digest(token),ORG_A)
            substituted=GatewayCipher(key).seal(ORG_B,record.binding_id,record.revision,KEY)
            admin.execute('UPDATE forge.organization_gateways SET encrypted_key=%s WHERE organization_id=%s',(substituted,ORG_A))
            with self.assertRaises(GatewayUnavailable):
                asyncio.run(inference.prepare(member,ORG_A,TextRequest('assistant',(('user','x'),))))
            self.assertEqual(self.outbound,0)

    def test_function_only_role_and_static_security_drift(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            self.prepared(pools,key,service,token)
            member=sessions.login('member@example.com',PASSWORD).capability
            for pool in (pools['forge_gateway_service'],pools['forge_account_service'],readers):
                with pool.connection() as conn:
                    for table in ('organization_gateways','gateway_catalog_selections'):
                        with self.assertRaises(errors.InsufficientPrivilege):
                            conn.execute(sql.SQL('SELECT * FROM forge.{}').format(sql.Identifier(table)))
                    if pool is not pools['forge_gateway_service']:
                        with self.assertRaises(errors.InsufficientPrivilege):
                            conn.execute('SELECT * FROM forge.gateway_inference_route(%s,%s,%s)',
                                (capability_digest(member),ORG_A,'assistant'))
            bad=PostgresGatewayInferenceStore(pools['forge_account_service'])
            with self.assertRaises(GatewayUnavailable):bad.resolve(capability_digest(member),ORG_A,'assistant')
            self.assertTrue(ready.check())
            for mutation,restore in (
                ('ALTER ROLE forge_gateway_authority LOGIN','ALTER ROLE forge_gateway_authority NOLOGIN'),
                ('GRANT EXECUTE ON FUNCTION forge.gateway_inference_route(text,uuid,text) TO PUBLIC',
                 'REVOKE EXECUTE ON FUNCTION forge.gateway_inference_route(text,uuid,text) FROM PUBLIC'),
                ('ALTER FUNCTION forge.gateway_inference_route(text,uuid,text) SECURITY INVOKER',
                 'ALTER FUNCTION forge.gateway_inference_route(text,uuid,text) SECURITY DEFINER'),
                ('ALTER TABLE forge.gateway_catalog_selections NO FORCE ROW LEVEL SECURITY',
                 'ALTER TABLE forge.gateway_catalog_selections FORCE ROW LEVEL SECURITY')):
                admin.execute(mutation)
                try:self.assertFalse(ready.check())
                finally:admin.execute(restore)
                self.assertTrue(ready.check())
