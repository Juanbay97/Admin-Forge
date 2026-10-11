"""CG2 transport boundaries, without any real provider connection."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fastapi.testclient import TestClient
from forge.account_api import create_account_app

ORG='11111111-1111-4111-8111-111111111111'

class CatalogApiTests(unittest.TestCase):
    def test_authentication_precedes_new_route_validation(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            for method,path in (('post','/gateway/catalogue/refresh'),('post','/models/publish'),('get','/models')):
                self.assertEqual(getattr(client,method)('/forge/v1/orgs/'+ORG+path).status_code,401)

from unittest.mock import MagicMock,AsyncMock
from uuid import UUID,uuid4
from dataclasses import replace
from forge.accounts import ACCOUNT_ISSUER
from forge.foundation import AuthenticatedIdentity,MembershipStatus
from forge.authorization import AuthorizationSnapshot
from forge.gateway_configuration import GatewayConflict
from forge.model_catalog import UnknownCapabilities

class ConfiguredCatalogApiTests(unittest.TestCase):
    def fixture(self,configured=True,catalog=None):
        sessions=MagicMock();identity=AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(uuid4()))
        sessions.validate.return_value=identity
        readiness=MagicMock();readiness.check.return_value=True
        auth=MagicMock();auth.read.return_value=AuthorizationSnapshot(identity,UUID(ORG),uuid4(),1,
            frozenset({'organization_admin'}),MembershipStatus.ACTIVE,True)
        service=MagicMock()
        service.refresh_async=AsyncMock(return_value={'gateway_revision':1,'model_ids':['private/a'],'capability_state':'unknown','verification':'unverified'})
        service.read.return_value={'organization_id':ORG,'revision':1,'default_model':'assistant',
            'models':[{'id':'assistant',**UnknownCapabilities().public_projection()}]}
        service.publish.return_value={'revision':1,'default_model':'assistant','models':['assistant']}
        client=TestClient(create_account_app(sessions=sessions,readiness=readiness,
            authorization_reader=auth,gateway_catalog=(catalog if catalog is not None else service) if configured else None),raise_server_exceptions=False)
        body={'operation_id':str(uuid4()),'expected_catalogue_revision':0,'expected_gateway_revision':1,
              'aliases':{'assistant':'private/a'},'default_alias':'assistant'}
        return client,sessions,auth,service,{'Authorization':'Bearer '+'A'*43},body

    def test_unconfigured_service_is_503_not_ready(self):
        client,_,_,_,headers,body=self.fixture(False)
        with client:
            for method,path in (('post','/gateway/catalogue/refresh'),('post','/models/publish'),('get','/models')):
                response=getattr(client,method)('/forge/v1/orgs/'+ORG+path,headers=headers,**({'json':body} if path.endswith('publish') else {}))
                self.assertEqual(response.status_code,503)

    def test_admin_and_member_projections_are_distinct_and_no_store_claims(self):
        client,_,auth,service,headers,body=self.fixture();url='/forge/v1/orgs/'+ORG
        with client:
            self.assertEqual(client.post(url+'/gateway/catalogue/refresh',headers=headers).status_code,200)
            self.assertEqual(client.post(url+'/models/publish',headers=headers,json=body).status_code,200)
            auth.read.return_value=replace(auth.read.return_value,roles=frozenset({'member'}))
            result=client.get(url+'/models',headers=headers)
            self.assertEqual(result.status_code,200);self.assertNotIn('private/a',result.text)
            self.assertEqual(client.post(url+'/models/publish',headers=headers,json=body).status_code,404)
        self.assertEqual(service.publish.call_count,1)

    def test_strict_inputs_and_bounded_body(self):
        client,_,_,service,headers,body=self.fixture();url='/forge/v1/orgs/'+ORG+'/models/publish'
        with client:
            for invalid in (body|{'expected_catalogue_revision':True},body|{'capabilities':{'tools':True}},body|{'endpoint':'https://evil.invalid'}):
                self.assertEqual(client.post(url,headers=headers,json=invalid).status_code,422)
            self.assertEqual(client.post(url,headers=headers,content=b'x'*32769).status_code,422)
        service.publish.assert_not_called()

    def test_revocation_foreign_and_suspension_fast_denial(self):
        for mutate in (lambda s:replace(s,membership_status=MembershipStatus.SUSPENDED),
                       lambda s:replace(s,organization_id=uuid4()),lambda s:replace(s,organization_active=False)):
            client,_,auth,service,headers,body=self.fixture();auth.read.return_value=mutate(auth.read.return_value)
            with client:self.assertEqual(client.post('/forge/v1/orgs/'+ORG+'/models/publish',headers=headers,json=body).status_code,404)
            service.publish.assert_not_called()
        client,sessions,_,service,headers,body=self.fixture();sessions.validate.return_value=None
        with client:self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/models',headers=headers|{'X-Role':'organization_admin'}).status_code,401)
        service.read.assert_not_called()

    def test_conflict_redaction_and_openapi(self):
        client,_,_,service,headers,body=self.fixture();url='/forge/v1/orgs/'+ORG
        with client:
            service.publish.side_effect=GatewayConflict()
            self.assertEqual(client.post(url+'/models/publish',headers=headers,json=body).status_code,409)
            service.read.side_effect=RuntimeError('PRIVATE_CIPHER_UPSTREAM_MARKER')
            response=client.get(url+'/models',headers=headers)
            self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE_CIPHER_UPSTREAM_MARKER',response.text)
            schema=client.get('/openapi.json').json()['paths']
            self.assertEqual(schema['/forge/v1/orgs/{organization_id}/models']['get']['security'],[{'ForgeBearer':[]}])

    def test_actual_async_refresh_timeout_is_redacted_and_never_saves_discovery(self):
        import asyncio
        import httpx
        from time import monotonic
        from cryptography.fernet import Fernet
        from forge.gateway_catalog import GatewayCatalog
        from forge.gateway_catalog_adapter import HttpxModelsAdapter
        from forge.gateway_configuration import GatewayCipher,GatewayRecord,GATEWAY_ENDPOINT
        org=UUID(ORG);binding=uuid4();cipher=GatewayCipher(Fernet.generate_key())
        store=MagicMock()
        store.gateway.return_value=GatewayRecord(1,binding,GATEWAY_ENDPOINT,cipher.seal(org,binding,1,'PRIVATE_TEST_KEY'))
        state={'started':False,'cancelled':False}
        async def slow_headers(request):
            state['started']=True
            try:
                await asyncio.sleep(30)
                return httpx.Response(200,json={'data':[{'id':'private/a'}]})
            finally:state['cancelled']=True
        catalog=GatewayCatalog(store,cipher,HttpxModelsAdapter(transport=httpx.MockTransport(slow_headers),deadline_seconds=0.03))
        client,_,_,_,headers,_=self.fixture(catalog=catalog)
        with client:
            started=monotonic()
            result=client.post('/forge/v1/orgs/'+ORG+'/gateway/catalogue/refresh',headers=headers)
            self.assertEqual(result.status_code,503)
            self.assertLess(monotonic()-started,1.0)
            self.assertTrue(state['started']);self.assertTrue(state['cancelled'])
            self.assertNotIn('PRIVATE_TEST_KEY',result.text)
        store.save_discovery.assert_not_called()

class AdminStatusApiRedTests(unittest.TestCase):
    def test_status_requires_auth_before_organization_validation(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/gateway/catalogue/status').status_code,401)


class AdminStatusApiTests(unittest.TestCase):
    fixture=ConfiguredCatalogApiTests.fixture
    def test_admin_status_redacted_and_fresh_authority(self):
        client,_,auth,service,headers,_=self.fixture()
        service.admin_status.return_value={'catalogue_revision':4,'default_model':'assistant','publication_state':'STALE_GATEWAY'}
        with client:
            path='/forge/v1/orgs/'+ORG+'/gateway/catalogue/status'
            result=client.get(path,headers=headers)
            self.assertEqual(result.status_code,200);self.assertEqual(result.json(),service.admin_status.return_value)
            self.assertEqual(client.get(path).status_code,401)
            auth.read.return_value=replace(auth.read.return_value,roles=frozenset({'member'}))
            self.assertEqual(client.get(path,headers=headers).status_code,404)
            self.assertEqual(service.admin_status.call_count,1)
    def test_status_unconfigured_and_openapi(self):
        client,_,_,_,headers,_=self.fixture(False)
        with client:
            path='/forge/v1/orgs/'+ORG+'/gateway/catalogue/status'
            self.assertEqual(client.get(path,headers=headers).status_code,503)
            operation=client.get('/openapi.json').json()['paths'][path.replace(ORG,'{organization_id}')]['get']
            self.assertEqual(operation['security'],[{'ForgeBearer':[]}])
