"""The fake gateway's ``openai_realistic`` mode streams the extra fields real OpenAI-format gateways send."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.fake_gateway import FakeGatewayConfiguration, create_fake_gateway, main, REPLY
from forge.gateway_inference import TextRequest
from forge.gateway_inference_adapter import HttpxTextAdapter

KEY = 'sk-fake-7f3a9c1d'
BODY = {'model': 'fake-fast', 'messages': [{'role': 'user', 'content': 'Hello'}], 'stream': True,
        'stream_options': {'include_usage': True}}


class RealisticTests(unittest.IsolatedAsyncioTestCase):
    def make(self, **options):
        self.gateway = create_fake_gateway(FakeGatewayConfiguration(keys=(KEY,), **options))
        return httpx.ASGITransport(app=self.gateway.app)

    async def chunks(self, **options):
        transport = self.make(**options)
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:3413') as client:
            response = await client.post('/v1/chat/completions', json=BODY, headers={'Authorization': 'Bearer ' + KEY})
        blocks = [block[len('data: '):] for block in response.text.split('\n\n') if block]
        self.assertEqual(blocks[-1], '[DONE]')
        return [json.loads(block) for block in blocks[:-1]]

    async def test_the_default_mode_is_unchanged(self):
        chunks = await self.chunks()
        self.assertFalse(any({'system_fingerprint', 'service_tier', 'obfuscation'} & set(chunk) for chunk in chunks))
        self.assertEqual(set(chunks[-1]['usage']), {'prompt_tokens', 'completion_tokens', 'total_tokens'})

    async def test_the_realistic_stream_carries_the_openai_extras(self):
        chunks = await self.chunks(openai_realistic=True)
        content, usage = chunks[:-1], chunks[-1]
        self.assertEqual(content[0]['choices'][0]['delta'], {'role': 'assistant', 'content': '', 'refusal': None})
        for chunk in content:
            self.assertIsNone(chunk['usage'])
            self.assertIsNone(chunk['choices'][0]['logprobs'])
            self.assertEqual({'system_fingerprint', 'service_tier', 'obfuscation'} - set(chunk), set())
        self.assertEqual(content[-1]['choices'][0]['finish_reason'], 'stop')
        self.assertEqual(usage['choices'], [])
        self.assertEqual(usage['usage']['total_tokens'], usage['usage']['prompt_tokens'] + usage['usage']['completion_tokens'])
        self.assertEqual(set(usage['usage']), {'prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_tokens_details',
                                               'completion_tokens_details', 'cost'})
        self.assertIsInstance(usage['usage']['prompt_tokens_details']['cached_tokens'], int)
        self.assertIsInstance(usage['usage']['completion_tokens_details']['reasoning_tokens'], int)

    async def test_the_adapter_meters_the_realistic_stream_with_the_same_counters(self):
        for options in ({}, {'openai_realistic': True}):
            with self.subTest(options=options):
                transport = self.make(**options)
                items = [item async for item in HttpxTextAdapter(transport=transport).events(
                    KEY, 'fake-fast', TextRequest('assistant', (('user', 'Hello'),)))]
                self.assertEqual(items[-2:], [('finish', 'stop'),
                                              ('usage', {'prompt_tokens': 2, 'completion_tokens': 6, 'total_tokens': 8})])
                self.assertEqual(''.join(text for kind, text in items if kind == 'text'), REPLY)

    async def test_the_malformed_and_nousage_models_keep_their_faults_in_realistic_mode(self):
        transport = self.make(openai_realistic=True)
        adapter = HttpxTextAdapter(transport=transport)
        request = TextRequest('assistant', (('user', 'Hello'),))
        with self.assertRaises(Exception):
            [item async for item in adapter.events(KEY, 'fake-malformed', request)]
        items = [item async for item in adapter.events(KEY, 'fake-nousage', request)]
        self.assertNotIn('usage', {kind for kind, _ in items})

    def test_the_mode_is_a_strict_boolean_and_a_cli_flag(self):
        with self.assertRaises(ValueError):
            FakeGatewayConfiguration(keys=(KEY,), openai_realistic='yes')
        self.assertTrue(FakeGatewayConfiguration(keys=(KEY,), openai_realistic=True).openai_realistic)
        self.assertEqual(main(['--openai-realistic']), 2, 'the flag needs a keys file, like any run')


if __name__ == '__main__':
    unittest.main()
