"""Strict HTTP/SSE subset using a labelled gateway transport and real service."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import MagicMock
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from fastapi.testclient import TestClient
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.foundation import AuthenticatedIdentity
from forge.gateway_inference import GatewayInference
from forge.gateway_inference_adapter import HttpxTextAdapter
from forge.gateway_configuration import GatewayCipher
from cryptography.fernet import Fernet
from test_gateway_inference import Store,ORG,KEY
from test_gateway_inference_adapter import Body,BODY

PAYLOAD={'model':'assistant','messages':[{'role':'user','content':'Hello'}],'stream':True}
TOKEN='A'*43


class InferenceApiTests(unittest.TestCase):
    def configured(self,*,port=True,valid=True):
        sessions=MagicMock()
        sessions.validate.return_value=AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(UUID(int=1))) if valid else None
        ready=MagicMock();ready.check.return_value=True
        cipher=GatewayCipher(Fernet.generate_key())
        self.store=Store(cipher);self.called=0
        def labelled(request):
            self.called+=1
            return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Body([BODY]))
        service=GatewayInference(self.store,cipher,HttpxTextAdapter(transport=httpx.MockTransport(labelled))) if port else None
        return TestClient(create_account_app(sessions=sessions,readiness=ready,gateway_inference=service),
                          raise_server_exceptions=False)

    def request(self,client,body=None,org=ORG,headers=None):
        return client.post('/forge/v1/orgs/'+str(org)+'/chat/completions',
            json=PAYLOAD if body is None else body,
            headers={'Authorization':'Bearer '+TOKEN} if headers is None else headers)

    def test_missing_auth_denies_before_body(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            response=self.request(client,{},headers={})
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers['www-authenticate'],'Bearer')

    def test_normalized_text_stream_contains_only_stable_alias(self):
        with self.configured() as client:
            response=self.request(client)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('text/event-stream',response.headers['content-type'])
            self.assertIn('"model":"assistant"',response.text)
            self.assertIn('"content":"Hello"',response.text)
            self.assertIn('data: [DONE]',response.text)
            for term in (KEY,'private/route','encrypted_key','private/upstream'):
                self.assertNotIn(term,response.text)
            self.assertEqual(self.called,1)

    def test_no_config_and_rejected_sessions_fail_closed(self):
        with self.configured(port=False) as client:self.assertEqual(self.request(client).status_code,503)
        with self.configured(valid=False) as client:
            self.assertEqual(self.request(client).status_code,401)
            self.assertEqual(self.called,0)

    def test_unpublished_and_foreign_org_are_hidden_before_outbound(self):
        with self.configured() as client:
            self.assertEqual(self.request(client,PAYLOAD|{'model':'absent'}).status_code,404)
            self.assertEqual(self.request(client,org=UUID(int=123)).status_code,404)
            self.assertEqual(self.called,0)

    def test_tools_images_extra_params_and_nonstream_are_rejected(self):
        cases=(PAYLOAD|{'tools':[]},PAYLOAD|{'temperature':1},PAYLOAD|{'stream':1},
               PAYLOAD|{'stream':False},PAYLOAD|{'max_output_tokens':True},
               PAYLOAD|{'messages':[{'role':'user','content':[{'image':'bad'}]}]},
               PAYLOAD|{'messages':[{'role':'tool','content':'bad'}]},
               PAYLOAD|{'messages':[{'role':'assistant','content':'no final user'}]})
        with self.configured() as client:
            for body in cases:
                with self.subTest(body=body):
                    self.assertEqual(self.request(client,body).status_code,422)
            self.assertEqual(self.called,0)

    def test_secret_rich_failure_is_redacted(self):
        with self.configured() as client:
            self.store.resolve=lambda *args: (_ for _ in ()).throw(RuntimeError(KEY))
            response=self.request(client)
            self.assertEqual(response.status_code,503)
            self.assertNotIn(KEY,response.text)

    def test_openapi_explicit_contract(self):
        with self.configured() as client:
            operation=client.get('/openapi.json').json()['paths']['/forge/v1/orgs/{organization_id}/chat/completions']['post']
            self.assertEqual(operation['security'],[{'ForgeBearer':[]}])
            self.assertTrue({'200','401','404','422','503'}<=set(operation['responses']))
