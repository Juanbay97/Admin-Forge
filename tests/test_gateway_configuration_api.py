"""Protected central gateway transport; no remote provider calls."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from unittest.mock import MagicMock
from uuid import UUID,uuid4
from forge.accounts import ACCOUNT_ISSUER
from forge.foundation import AuthenticatedIdentity,MembershipStatus
from forge.authorization import AuthorizationSnapshot
from forge.gateway_configuration import GatewayStatus,GatewayConflict,GatewayDenied
from fastapi.testclient import TestClient
from forge.account_api import create_account_app

ORG='11111111-1111-4111-8111-111111111111'

class GatewayApiTests(unittest.TestCase):
    def test_missing_auth_precedes_gateway_body_validation(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            response=client.put('/forge/v1/orgs/'+ORG+'/gateway',json={})
            self.assertEqual(response.status_code,401)
            self.assertNotIn('api_key',response.text)
            self.assertEqual(client.get('/forge/v1/orgs/not-a-uuid/gateway').status_code,401)

    def test_default_gateway_get_never_exposes_configuration(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/gateway').status_code,401)


    def fixture(self,**kwargs):
        sessions=MagicMock();identity=AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(uuid4()))
        sessions.validate.return_value=identity
        readiness=MagicMock();readiness.check.return_value=True
        authorization=MagicMock();authorization.read.return_value=AuthorizationSnapshot(
            identity,UUID(ORG),uuid4(),1,frozenset({'organization_admin'}),MembershipStatus.ACTIVE,True)
        service=MagicMock();service.read.return_value=GatewayStatus('NOT_CONFIGURED',0)
        service.save.return_value=GatewayStatus('SAVED_UNVERIFIED',1)
        client=TestClient(create_account_app(sessions=sessions,readiness=readiness,
            authorization_reader=authorization,gateway_configuration=kwargs.get('service',service)),raise_server_exceptions=False)
        return client,sessions,authorization,service,{'Authorization':'Bearer '+'A'*43}

    def test_real_dto_is_redacted_and_secret_write_only(self):
        client,_,_,service,headers=self.fixture()
        with client:
            result=client.put('/forge/v1/orgs/'+ORG+'/gateway',headers=headers,
                json={'expected_revision':0,'api_key':'FIXTURE_SECRET_MARKER'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json(),{'status':'SAVED_UNVERIFIED','revision':1,'endpoint':'https://ia.prometheonlab.com'})
            self.assertNotIn('FIXTURE_SECRET_MARKER',result.text)
            self.assertEqual(result.headers['cache-control'],'no-store')
            self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/gateway',headers=headers).json()['status'],'NOT_CONFIGURED')
            self.assertEqual(service.save.call_args.args[-1],'FIXTURE_SECRET_MARKER')

    def test_authenticated_unconfigured_service_fails_closed(self):
        client,_,_,_,headers=self.fixture(service=None)
        with client:self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/gateway',headers=headers).status_code,503)

    def test_member_foreign_suspended_snapshots_never_dispatch(self):
        from dataclasses import replace
        for mutate in (lambda x:replace(x,roles=frozenset({'member'})),
                       lambda x:replace(x,organization_id=uuid4()),
                       lambda x:replace(x,membership_status=MembershipStatus.SUSPENDED),
                       lambda x:replace(x,organization_active=False)):
            client,_,auth,service,headers=self.fixture();auth.read.return_value=mutate(auth.read.return_value)
            with client:self.assertEqual(client.get('/forge/v1/orgs/'+ORG+'/gateway',headers=headers).status_code,404)
            service.read.assert_not_called()

    def test_revoked_and_client_claims_never_authorize(self):
        client,sessions,_,service,headers=self.fixture();sessions.validate.return_value=None
        with client:
            response=client.put('/forge/v1/orgs/'+ORG+'/gateway',headers=headers|{'X-Role':'organization_admin'},
                                json={'expected_revision':0,'api_key':'fixture'})
            self.assertEqual(response.status_code,401)
        service.save.assert_not_called()

    def test_strict_input_conflicts_and_secret_rich_failures_redacted(self):
        client,_,_,service,headers=self.fixture()
        with client:
            for body in ({'expected_revision':True,'api_key':'fixture'},
                         {'expected_revision':0,'api_key':'fixture','endpoint':'https://attacker.invalid'}):
                self.assertEqual(client.put('/forge/v1/orgs/'+ORG+'/gateway',headers=headers,json=body).status_code,422)
            self.assertEqual(client.put('/forge/v1/orgs/'+ORG+'/gateway',headers=headers,content=b'x'*8193).status_code,422)
            service.save.assert_not_called()
            service.save.side_effect=GatewayConflict()
            self.assertEqual(client.put('/forge/v1/orgs/'+ORG+'/gateway',headers=headers,json={'expected_revision':0,'api_key':'fixture'}).status_code,409)
            service.read.side_effect=RuntimeError('PRIVATE_SECRET_MARKER')
            result=client.get('/forge/v1/orgs/'+ORG+'/gateway',headers=headers)
            self.assertEqual(result.status_code,503);self.assertNotIn('PRIVATE_SECRET_MARKER',result.text)
            schema=client.get('/openapi.json').json()['paths']['/forge/v1/orgs/{organization_id}/gateway']
            self.assertEqual(schema['put']['security'],[{'ForgeBearer':[]}])
