"""Fake OpenAI-compatible gateway: contract-exact, loopback-only, test/dev only."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.fake_gateway import FakeGatewayConfiguration, create_fake_gateway, MODELS, REPLY
from forge.gateway_catalog_adapter import HttpxModelsAdapter
from forge.gateway_configuration import GatewayUnavailable
from forge.gateway_inference import TextRequest
from forge.gateway_inference_adapter import HttpxTextAdapter

KEY = 'sk-fake-7f3a9c1d'
OTHER = 'sk-fake-other-0b5e'
MESSAGES = [{'role': 'user', 'content': 'Hello'}]
FRAGMENTS = ('sk-fake', '7f3a9c1d', '0b5e')


def chat(model='fake-fast', **extra):
    return {'model': model, 'messages': MESSAGES, 'stream': True, **extra}


def sse_events(text):
    events = [block for block in text.split('\n\n') if block]
    for block in events:
        assert block.startswith('data: '), block
    return [block[len('data: '):] for block in events]


class GatewayCase(unittest.IsolatedAsyncioTestCase):
    def make(self, keys=(KEY,), **options):
        self.sleeps = []

        async def sleep(seconds):
            self.sleeps.append(seconds)
        self.gateway = create_fake_gateway(FakeGatewayConfiguration(keys=keys, **options), sleep=sleep)
        return self.gateway

    def client(self):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.gateway.app),
                                   base_url='http://127.0.0.1:3413')
        self.addAsyncCleanup(client.aclose)
        return client

    def assertNoSecret(self, text):
        for fragment in FRAGMENTS:
            self.assertNotIn(fragment, text)


class ModelsTests(GatewayCase):
    async def test_models_lists_bounded_ids(self):
        self.make()
        response = await self.client().get('/v1/models', headers={'Authorization': 'Bearer ' + KEY})
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertEqual(document['object'], 'list')
        self.assertEqual([item['id'] for item in document['data']],
                         ['fake-error', 'fake-fast', 'fake-malformed', 'fake-slow'])
        self.assertEqual(tuple(item['id'] for item in document['data']), tuple(sorted(MODELS)))
        self.assertTrue(all(item['object'] == 'model' for item in document['data']))


class StreamedChatTests(GatewayCase):
    async def stream(self, model):
        self.make()
        response = await self.client().post('/v1/chat/completions', json=chat(model),
                                            headers={'Authorization': 'Bearer ' + KEY})
        self.assertEqual(response.status_code, 200)
        return response

    async def test_sse_shape_role_deltas_stop_and_done(self):
        response = await self.stream('fake-fast')
        self.assertEqual(response.headers['content-type'].split(';')[0], 'text/event-stream')
        self.assertNotIn('content-encoding', response.headers)
        events = sse_events(response.text)
        self.assertEqual(events[-1], '[DONE]')
        chunks = [json.loads(event) for event in events[:-1]]
        self.assertGreater(len(chunks), 3)
        self.assertEqual(chunks[0]['choices'][0]['delta']['role'], 'assistant')
        for chunk in chunks:
            self.assertEqual(chunk['object'], 'chat.completion.chunk')
            self.assertEqual(chunk['model'], 'fake-fast')
            self.assertEqual(len(chunk['choices']), 1)
            self.assertEqual(chunk['choices'][0]['index'], 0)
            self.assertLessEqual(set(chunk['choices'][0]['delta']), {'role', 'content'})
        self.assertEqual([chunk['choices'][0]['finish_reason'] for chunk in chunks],
                         [None] * (len(chunks) - 1) + ['stop'])
        self.assertEqual(chunks[-1]['choices'][0]['delta'], {})
        text = ''.join(chunk['choices'][0]['delta'].get('content', '') for chunk in chunks)
        self.assertEqual(text, REPLY)
        self.assertLess(max(len(event.encode()) for event in events), 16 * 1024)

    async def test_slow_model_streams_same_reply_with_requested_model_id(self):
        response = await self.stream('fake-slow')
        chunks = [json.loads(event) for event in sse_events(response.text)[:-1]]
        self.assertEqual({chunk['model'] for chunk in chunks}, {'fake-slow'})
        self.assertEqual(''.join(chunk['choices'][0]['delta'].get('content', '') for chunk in chunks), REPLY)

    async def test_invalid_requests_are_rejected_without_streaming(self):
        self.make()
        client = self.client()
        headers = {'Authorization': 'Bearer ' + KEY}
        cases = (('not json', 400), (json.dumps(chat(stream=False)), 400),
                 (json.dumps({'messages': MESSAGES, 'stream': True}), 400),
                 (json.dumps(chat('fake-unknown')), 404))
        for content, status in cases:
            with self.subTest(content=content):
                response = await client.post('/v1/chat/completions', content=content,
                    headers={**headers, 'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, status)
                self.assertNotIn('text/event-stream', response.headers['content-type'])


class BindTests(unittest.TestCase):
    def test_non_loopback_or_non_numeric_hosts_refuse_to_start(self):
        for host in ('0.0.0.0', '::', '192.168.1.5', '10.0.0.1', 'example.com', 'localhost', ''):
            with self.subTest(host=host), self.assertRaises(ValueError):
                FakeGatewayConfiguration(keys=(KEY,), host=host)

    def test_numeric_loopback_hosts_are_accepted(self):
        for host in ('127.0.0.1', '::1', '127.0.0.2'):
            with self.subTest(host=host):
                self.assertEqual(FakeGatewayConfiguration(keys=(KEY,), host=host).host, host)

    def test_invalid_keys_and_ports_are_refused(self):
        for options in (dict(keys=()), dict(keys=('',)), dict(keys=('has space',)), dict(keys=('é',)),
                        dict(keys=KEY), dict(keys=(KEY,), port=0), dict(keys=(KEY,), port=65536),
                        dict(keys=(KEY,), slow_delay_seconds=-1), dict(keys=(KEY,), slow_delay_seconds=5.1)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                FakeGatewayConfiguration(**options)

    def test_defaults_use_the_reserved_mvp_port_on_loopback(self):
        configuration = FakeGatewayConfiguration(keys=(KEY,))
        self.assertEqual((configuration.host, configuration.port), ('127.0.0.1', 3413))


class AuthorizationTests(GatewayCase):
    async def test_missing_or_wrong_key_is_401_and_recorded(self):
        self.make()
        client = self.client()
        attempts = ({}, {'Authorization': 'Bearer ' + OTHER}, {'Authorization': KEY},
                    {'Authorization': 'bearer ' + KEY}, {'Authorization': 'Bearer ' + KEY + ' '})
        for index, headers in enumerate(attempts):
            with self.subTest(headers=headers):
                models = await client.get('/v1/models', headers=headers)
                completion = await client.post('/v1/chat/completions', json=chat(), headers=headers)
                for response in (models, completion):
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers['www-authenticate'], 'Bearer')
                    self.assertNoSecret(response.text)
        self.assertEqual(len(self.gateway.records), len(attempts) * 2)
        self.assertEqual([record.authorization for record in self.gateway.records[::2]],
                         [None, 'Bearer ' + OTHER, KEY, 'bearer ' + KEY, 'Bearer ' + KEY + ' '])

    async def test_custody_proof_records_only_each_orgs_own_key(self):
        self.make(keys=(KEY, OTHER))
        client = self.client()
        for key in (KEY, KEY, OTHER):
            response = await client.post('/v1/chat/completions', json=chat(),
                                         headers={'Authorization': 'Bearer ' + key})
            self.assertEqual(response.status_code, 200)
        self.assertEqual([(record.method, record.path, record.model, record.authorization)
                          for record in self.gateway.records],
                         [('POST', '/v1/chat/completions', 'fake-fast', 'Bearer ' + KEY)] * 2
                         + [('POST', '/v1/chat/completions', 'fake-fast', 'Bearer ' + OTHER)])

    async def test_control_endpoint_returns_digests_never_the_key(self):
        self.make()
        client = self.client()
        await client.get('/v1/models', headers={'Authorization': 'Bearer ' + KEY})
        await client.get('/v1/models')
        control = await client.get('/__fake/requests')
        self.assertEqual(control.status_code, 200)
        self.assertNoSecret(control.text)
        self.assertEqual(control.json(), {'requests': [
            {'method': 'GET', 'path': '/v1/models', 'model': None,
             'authorization_sha256': hashlib.sha256(('Bearer ' + KEY).encode()).hexdigest()},
            {'method': 'GET', 'path': '/v1/models', 'model': None, 'authorization_sha256': None}]})
        self.assertEqual(len(self.gateway.records), 2, 'control requests are not recorded')


class NoEchoTests(GatewayCase):
    async def test_no_response_contains_any_part_of_the_bearer_value(self):
        self.make()
        client = self.client()
        headers = {'Authorization': 'Bearer ' + KEY}
        responses = [await client.get('/v1/models', headers=headers)]
        for model in ('fake-fast', 'fake-slow', 'fake-error', 'fake-malformed'):
            responses.append(await client.post('/v1/chat/completions', json=chat(model), headers=headers))
        responses.append(await client.post('/v1/chat/completions', content='not json', headers=headers))
        responses.append(await client.post('/v1/chat/completions', json=chat('fake-unknown'), headers=headers))
        responses.append(await client.get('/__fake/requests'))
        self.assertEqual([response.status_code for response in responses],
                         [200, 200, 200, 500, 200, 400, 404, 200])
        for response in responses:
            self.assertNoSecret(response.text)
            self.assertNoSecret(str(dict(response.headers)))


class FaultInjectionTests(GatewayCase):
    async def test_fake_error_is_a_redacted_500(self):
        self.make()
        response = await self.client().post('/v1/chat/completions', json=chat('fake-error'),
                                            headers={'Authorization': 'Bearer ' + KEY})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'error': {'message': 'Fake gateway failure.', 'type': 'server_error'}})

    async def test_fake_malformed_adds_a_forbidden_delta_key_after_the_role_chunk(self):
        self.make()
        response = await self.client().post('/v1/chat/completions', json=chat('fake-malformed'),
                                            headers={'Authorization': 'Bearer ' + KEY})
        chunks = [json.loads(event) for event in sse_events(response.text)[:-1]]
        self.assertEqual(chunks[0]['choices'][0]['delta'], {'role': 'assistant', 'content': ''})
        self.assertEqual(set(chunks[1]['choices'][0]['delta']) - {'role', 'content'}, {'function_call'})

    async def test_fake_slow_pauses_between_every_content_delta_and_fast_never_does(self):
        self.make(slow_delay_seconds=0.25)
        client = self.client()
        headers = {'Authorization': 'Bearer ' + KEY}
        await client.post('/v1/chat/completions', json=chat('fake-fast'), headers=headers)
        self.assertEqual(self.sleeps, [])
        await client.post('/v1/chat/completions', json=chat('fake-slow'), headers=headers)
        self.assertEqual(self.sleeps, [0.25] * len(REPLY.split()))

    async def test_reset_clears_records_and_isolates_the_next_test(self):
        self.make()
        client = self.client()
        await client.get('/v1/models', headers={'Authorization': 'Bearer ' + KEY})
        await client.get('/v1/models')
        self.assertEqual(len(self.gateway.records), 2)
        response = await client.post('/__fake/reset')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.gateway.records, ())
        self.assertEqual((await client.get('/__fake/requests')).json(), {'requests': []})
        await client.get('/v1/models', headers={'Authorization': 'Bearer ' + OTHER})
        self.assertEqual([record.authorization for record in self.gateway.records], ['Bearer ' + OTHER])
        self.gateway.reset()
        self.assertEqual(self.gateway.records, ())


class AdapterCompatibilityTests(GatewayCase):
    def transport(self):
        return httpx.ASGITransport(app=self.gateway.app)

    async def test_catalog_adapter_accepts_fake_models(self):
        self.make()
        ids = await HttpxModelsAdapter(transport=self.transport()).discover_async(KEY)
        self.assertEqual(ids, ('fake-error', 'fake-fast', 'fake-malformed', 'fake-slow'))
        self.assertEqual([(record.path, record.authorization) for record in self.gateway.records],
                         [('/v1/models', 'Bearer ' + KEY)])

    async def test_catalog_adapter_fails_closed_on_a_rejected_key(self):
        self.make(keys=(OTHER,))
        with self.assertRaises(GatewayUnavailable):
            await HttpxModelsAdapter(transport=self.transport()).discover_async(KEY)

    async def collect(self, model, key=KEY):
        adapter = HttpxTextAdapter(transport=self.transport())
        request = TextRequest('assistant', (('user', 'Hello'),))
        items = []
        try:
            async for item in adapter.events(key, model, request):
                items.append(item)
        except GatewayUnavailable:
            return items, True
        return items, False

    async def test_inference_adapter_normalizes_fake_stream(self):
        self.make()
        items, failed = await self.collect('fake-fast')
        self.assertFalse(failed)
        self.assertEqual(items[-1], ('finish', 'stop'))
        self.assertEqual(''.join(text for kind, text in items[:-1] if kind == 'text'), REPLY)
        self.assertEqual({kind for kind, _ in items[:-1]}, {'text'})
        self.assertEqual(self.gateway.records[0].model, 'fake-fast')

    async def test_inference_adapter_rejects_malformed_stream_without_leaking_text(self):
        self.make()
        items, failed = await self.collect('fake-malformed')
        self.assertTrue(failed)
        self.assertEqual(items, [])

    async def test_inference_adapter_rejects_error_and_bad_key(self):
        self.make()
        self.assertEqual(await self.collect('fake-error'), ([], True))
        self.assertEqual(await self.collect('fake-fast', key=OTHER), ([], True))


if __name__ == '__main__':
    unittest.main()
