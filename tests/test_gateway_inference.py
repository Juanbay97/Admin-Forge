"""Current-authority domain checks and direct async streaming lifecycle."""
import asyncio
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher,GatewayRecord,GatewayDenied,GatewayUnavailable
from forge.gateway_inference import GatewayInference,RouteContext,TextRequest

ORG=uuid4()
TOKEN='A'*43
KEY='labelled-test-secret-key'
REQUEST=TextRequest('assistant',(('user','hello'),))


class Store:
    def __init__(self,cipher):
        binding=uuid4()
        self.route=RouteContext(ORG,'assistant',1,'private/route',
            GatewayRecord(1,binding,'https://ia.prometheonlab.com',cipher.seal(ORG,binding,1,KEY)))
        self.calls=0
        self.denied=False

    def resolve(self,digest,org,alias):
        self.calls+=1
        if self.denied or org!=ORG or alias!='assistant':
            raise GatewayDenied()
        return self.route


class Adapter:
    def __init__(self):
        self.calls=0
        self.closed=False
        self.entered=asyncio.Event()

    async def events(self,key,route,request):
        self.calls+=1
        try:
            self.entered.set()
            yield 'text','hello'
            await asyncio.sleep(5)
            yield 'finish','stop'
        finally:
            self.closed=True


class InferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cipher=GatewayCipher(Fernet.generate_key())
        self.store=Store(self.cipher)
        self.adapter=Adapter()
        self.service=GatewayInference(self.store,self.cipher,self.adapter)

    async def test_strict_text_policy(self):
        for alias,messages,budget in (('Physical/ID',REQUEST.messages,512),
                ('assistant',(('user',{'image':'bad'}),),512),
                ('assistant',(('tool','text'),),512),
                ('assistant',(('assistant','text'),),512),
                ('assistant',(('user','x'*4097),),512),
                ('assistant',(('user','x'),)*17,512),
                ('assistant',(('user','x'),),True),
                ('assistant',(('user','x'),),2049)):
            with self.subTest(alias=alias,budget=budget):
                with self.assertRaises(ValueError):TextRequest(alias,messages,budget)

    async def test_no_access_bad_alias_foreign_org_and_wrong_key_before_outbound(self):
        for org,request in ((uuid4(),REQUEST),(ORG,TextRequest('absent',REQUEST.messages))):
            with self.assertRaises(GatewayDenied):
                await self.service.prepare(TOKEN,org,request)
        self.service._cipher=GatewayCipher(Fernet.generate_key())
        with self.assertRaises(GatewayUnavailable):
            await self.service.prepare(TOKEN,ORG,REQUEST)
        self.assertEqual(self.adapter.calls,0)

    async def test_invalid_port_result_fails_closed(self):
        self.store.route=replace(self.store.route,catalog_revision=0)
        with self.assertRaises(GatewayUnavailable):
            await self.service.prepare(TOKEN,ORG,REQUEST)
        self.assertEqual(self.adapter.calls,0)

    async def test_prepare_never_exposes_private_repr(self):
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        for secret in (KEY,TOKEN,'private/route'):
            self.assertNotIn(secret,repr(prepared))

    async def test_revoked_after_prepare_no_outbound(self):
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        self.store.denied=True
        output=b''.join([part async for part in self.service.stream(prepared)])
        self.assertIn(b'INFERENCE_UNAVAILABLE',output)
        self.assertEqual(self.adapter.calls,0)

    async def test_logout_during_blocked_body_closes_without_more_output(self):
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        stream=self.service.stream(prepared)
        self.assertIn(b'hello',await anext(stream))
        self.store.denied=True
        with patch('forge.gateway_inference.REVOCATION_INTERVAL',.01):
            output=b''.join([part async for part in stream])
        self.assertIn(b'INFERENCE_UNAVAILABLE',output)
        self.assertTrue(self.adapter.closed)
        self.assertGreaterEqual(self.store.calls,3)

    async def test_rotation_during_stream_closes(self):
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        stream=self.service.stream(prepared)
        await anext(stream)
        self.store.route=replace(self.store.route,catalog_revision=2)
        with patch('forge.gateway_inference.REVOCATION_INTERVAL',.01):
            self.assertIn(b'INFERENCE_UNAVAILABLE',b''.join([x async for x in stream]))
        self.assertTrue(self.adapter.closed)

    async def test_explicit_disconnect_and_cancel_close(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                self.setUp()
                prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
                stopped=False
                async def disconnected():return stopped
                stream=self.service.stream(prepared,disconnected=disconnected)
                await anext(stream)
                if cancel:
                    task=asyncio.create_task(anext(stream))
                    await asyncio.sleep(.01)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):await task
                else:
                    await stream.aclose()
                self.assertTrue(self.adapter.closed)

    async def test_disconnect_while_provider_waits_is_monitored(self):
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        stopped=False
        async def disconnected():return stopped
        stream=self.service.stream(prepared,disconnected=disconnected)
        with patch('forge.gateway_inference.REVOCATION_INTERVAL',.01):
            await anext(stream)
            stopped=True
            await asyncio.wait_for(anext(stream),.3)
        await stream.aclose()
        self.assertTrue(self.adapter.closed)

    async def test_same_owner_whole_deadline_through_service_backpressure(self):
        import httpx
        from forge.gateway_inference_adapter import HttpxTextAdapter
        from test_gateway_inference_adapter import Body,event
        body=Body([event('hello')]+[event('slow')]*10+[event(finish='stop'),b'data: [DONE]\n\n'],delay=.01)
        async def labelled(request):
            return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=body)
        self.service._adapter=HttpxTextAdapter(transport=httpx.MockTransport(labelled))
        prepared=await self.service.prepare(TOKEN,ORG,REQUEST)
        stream=self.service.stream(prepared)
        with patch('forge.gateway_inference_adapter.TOTAL_SECONDS',1.5):
            self.assertIn(b'hello',await anext(stream))
            await asyncio.sleep(1.6)
            output=b''.join([part async for part in stream])
        self.assertIn(b'INFERENCE_UNAVAILABLE',output)
        self.assertTrue(body.closed)
