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
from forge.gateway_configuration import GatewayCipher,GatewayRecord,GatewayDenied,GatewayUnavailable,RetryableUpstream
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


class ScriptedAdapter:
    """One script per bearer key: 'ok', 'retry' (before any byte), 'late' (a chunk, then a failure)."""
    def __init__(self, scripts):
        self.scripts, self.seen, self.closed = scripts, [], []

    async def events(self, key, route, request):
        self.seen.append(str(key))
        script = self.scripts[str(key)]
        try:
            if script == 'retry':
                raise RetryableUpstream()
            yield 'text', 'from-' + str(key)[-2:]
            if script == 'late':
                await asyncio.sleep(.02)  # the member has already been served the first chunk
                raise GatewayUnavailable()
            yield 'finish', 'stop'
        finally:
            self.closed.append(str(key))


class PoolStore:
    def __init__(self, cipher, keys, *, tamper_first=False):
        binding = uuid4()
        records = []
        for index, key in enumerate(keys):
            key_id = uuid4()
            sealed = cipher.seal_pooled(key_id, 1, key, 'https://ia.prometheonlab.com')
            records.append(GatewayRecord(1, binding, 'https://ia.prometheonlab.com', sealed, uuid4() if (tamper_first and index == 0) else key_id, 1))
        self.route = RouteContext(ORG, 'assistant', 1, 'private/route', records[0], tuple(records[1:]))
        self.calls = 0

    def resolve(self, digest, org, alias):
        self.calls += 1
        return self.route


class FailoverTests(unittest.IsolatedAsyncioTestCase):
    def build(self, keys, scripts, **options):
        self.cipher = GatewayCipher(Fernet.generate_key())
        self.store = PoolStore(self.cipher, keys, **options)
        self.adapter = ScriptedAdapter(scripts)
        self.service = GatewayInference(self.store, self.cipher, self.adapter)

    async def run_stream(self):
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        return b''.join([part async for part in self.service.stream(prepared)])

    async def test_a_rate_limited_primary_fails_over_to_the_next_key_with_one_normal_stream(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'retry', 'key-two-K2': 'ok'})
        output = await self.run_stream()
        self.assertEqual(self.adapter.seen, ['key-one-K1', 'key-two-K2'])
        self.assertIn(b'from-K2', output)
        self.assertEqual((output.count(b'[DONE]'), output.count(b'INFERENCE_UNAVAILABLE')), (1, 0))
        self.assertNotIn(b'key-one', output)

    async def test_the_lowest_priority_key_serves_first_and_a_healthy_primary_never_touches_the_rest(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'ok', 'key-two-K2': 'ok'})
        output = await self.run_stream()
        self.assertEqual((self.adapter.seen, b'from-K1' in output, b'from-K2' in output), (['key-one-K1'], True, False))

    async def test_a_failure_after_the_first_chunk_never_fails_over(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'late', 'key-two-K2': 'ok'})
        output = await self.run_stream()
        self.assertEqual(self.adapter.seen, ['key-one-K1'])
        self.assertIn(b'from-K1', output)
        self.assertEqual((output.count(b'INFERENCE_UNAVAILABLE'), output.count(b'[DONE]'), b'from-K2' in output), (1, 1, False))

    async def test_when_every_key_is_down_each_is_tried_once_and_the_error_is_finite(self):
        keys = ['key-one-K1', 'key-two-K2', 'key-three-K3']
        self.build(keys, {key: 'retry' for key in keys})
        output = await self.run_stream()
        self.assertEqual(self.adapter.seen, keys)
        self.assertEqual((output.count(b'INFERENCE_UNAVAILABLE'), output.count(b'[DONE]')), (1, 1))
        self.assertTrue(all(key.encode() not in output for key in keys))
        self.assertEqual(sorted(self.adapter.closed), sorted(keys), 'every upstream stream was closed')

    async def test_an_unreadable_candidate_is_skipped_and_no_readable_candidate_is_unavailable_before_any_call(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'ok', 'key-two-K2': 'ok'}, tamper_first=True)
        output = await self.run_stream()
        self.assertEqual(self.adapter.seen, ['key-two-K2'])
        self.assertIn(b'from-K2', output)
        self.build(['key-one-K1'], {'key-one-K1': 'ok'}, tamper_first=True)
        with self.assertRaises(GatewayUnavailable):
            await self.service.prepare(TOKEN, ORG, REQUEST)
        self.assertEqual(self.adapter.seen, [])

    async def test_a_key_rotation_or_reorder_does_not_stop_an_in_flight_stream_but_a_binding_change_does(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'ok', 'key-two-K2': 'ok'})
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        rotated = replace(self.store.route.gateway, key_revision=2, encrypted_key=self.store.route.gateway.encrypted_key[::-1])
        self.assertTrue(self.store.route.same_route(replace(self.store.route, gateway=rotated, fallbacks=())))
        self.assertNotEqual(self.store.route, replace(self.store.route, gateway=rotated))
        self.assertFalse(self.store.route.same_route(replace(self.store.route, gateway=replace(self.store.route.gateway, revision=2))))
        self.assertFalse(self.store.route.same_route(replace(self.store.route, gateway=replace(self.store.route.gateway, binding_id=uuid4()))))
        self.assertFalse(self.store.route.same_route(replace(self.store.route, upstream_id='other/route')))
        self.store.route = replace(self.store.route, gateway=rotated)
        output = b''.join([part async for part in self.service.stream(prepared)])
        self.assertEqual((b'from-K1' in output, b'INFERENCE_UNAVAILABLE' in output), (True, False))
