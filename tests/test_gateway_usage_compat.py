"""Real OpenAI-format streams: the adapter tolerates the documented optional extras and keeps exact validation of what it uses.

Golden fixtures are modeled on OpenAI's chat completion chunk stream (``stream_options.include_usage``) and on the shape
OpenAI-compatible gateways such as OmniRoute relay. Labelled fixture transport only, never a real provider.
"""
import copy
import json
from pathlib import Path
import random
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.gateway_configuration import GatewayUnavailable, RetryableUpstream
from test_gateway_inference_adapter import AdapterTests, Body, KEY, UPSTREAM

FIXTURES = Path(__file__).resolve().parent/'fixtures'/'gateway'


def sse(chunk):
    return ('data: ' + json.dumps(chunk) + '\n\n').encode()


def chunk(choices, **extra):
    return {'id': 'chatcmpl-x', 'object': 'chat.completion.chunk', 'created': 1760000000, 'model': UPSTREAM, 'choices': choices, **extra}


def content_chunk(delta=None, finish=None, top=None, **choice):
    return chunk([{'index': 0, 'delta': {'content': 'Hello'} if delta is None else delta, 'finish_reason': finish, **choice}], **(top or {}))


GOOD = {'prompt_tokens': 9, 'completion_tokens': 3, 'total_tokens': 12}
DONE = b'data: [DONE]\n\n'


def stream(first=None, last=None, usage=GOOD, **usage_extra):
    stop = content_chunk({}, 'stop') if last is None else last
    return (sse(content_chunk() if first is None else first) + sse(stop)
            + (b'' if usage is None else sse(chunk([], usage=usage, **usage_extra))) + DONE)


class Case(unittest.IsolatedAsyncioTestCase):
    adapter = AdapterTests.adapter
    collect = AdapterTests.collect

    async def events(self, payload, fragment=False):
        data = [bytes([byte]) for byte in payload] if fragment else [payload]
        body = Body(data)
        result = await self.collect(self.adapter(body))
        self.assertTrue(body.closed)
        return result

    async def refused(self, payload):
        body = Body([payload])
        with self.assertRaises(GatewayUnavailable) as caught:
            await self.collect(self.adapter(body))
        self.assertNotIsInstance(caught.exception, RetryableUpstream)
        self.assertTrue(body.closed)


class GoldenStreamTests(Case):
    async def test_the_official_openai_stream_with_usage_null_obfuscation_and_nested_details(self):
        payload = (FIXTURES/'openai_official_stream_with_usage.sse').read_bytes()
        expected = [('text', 'Hello'), ('text', ' there'), ('finish', 'stop'),
                    ('usage', {'prompt_tokens': 9, 'completion_tokens': 3, 'total_tokens': 12})]
        self.assertEqual(await self.events(payload), expected)
        self.assertEqual(await self.events(payload, fragment=True), expected)

    async def test_an_openai_compatible_gateway_stream_with_cost_null_content_and_length_finish(self):
        payload = (FIXTURES/'openai_compatible_gateway_stream_with_usage.sse').read_bytes()
        self.assertEqual(await self.events(payload), [
            ('text', 'Hi'), ('finish', 'length'), ('usage', {'prompt_tokens': 5, 'completion_tokens': 1, 'total_tokens': 6})])


class TolerantUsageTests(Case):
    async def test_known_optional_usage_extras_are_ignored_and_never_returned(self):
        details = {'cached_tokens': 3, 'audio_tokens': 0, 'note': None, 'ok': True, 'ratio': 0.5, 'nested': {'a': {'b': 1}}}
        for name, extra in (('prompt details', {'prompt_tokens_details': details}),
                            ('completion details', {'completion_tokens_details': {'reasoning_tokens': 4}}),
                            ('null details', {'prompt_tokens_details': None, 'completion_tokens_details': None}),
                            ('cost', {'cost': 0.00042}), ('integer cost', {'cost': 0}), ('null cost', {'cost': None}),
                            ('cost details', {'cost': 1.5, 'cost_details': {'upstream_inference_cost': 1.2}}),
                            ('byok', {'is_byok': False})):
            with self.subTest(name):
                items = await self.events(stream(usage={**GOOD, **extra}))
                self.assertEqual(items[-1], ('usage', GOOD))

    async def test_the_usage_chunk_may_carry_the_known_identity_extras(self):
        payload = (sse(content_chunk()) + sse(content_chunk({}, 'stop'))
                   + sse(chunk([], usage=GOOD, system_fingerprint='fp_1', service_tier='default', obfuscation='xyz')) + DONE)
        self.assertEqual((await self.events(payload))[-1], ('usage', GOOD))

    async def test_the_counters_alone_still_work_and_a_consistent_total_is_kept(self):
        for usage in ({'prompt_tokens': 1, 'completion_tokens': 2}, {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}):
            with self.subTest(usage=usage):
                self.assertEqual((await self.events(stream(usage=usage)))[-1], ('usage', usage))

    async def test_what_the_adapter_uses_is_still_exact(self):
        cases = {
            'inconsistent total': {**GOOD, 'total_tokens': 13},
            'negative cost': {**GOOD, 'cost': -0.1},
            'string cost': {**GOOD, 'cost': '0.1'},
            'bool cost': {**GOOD, 'cost': True},
            'infinite cost': {**GOOD, 'cost': 1e999},
            'details not an object': {**GOOD, 'prompt_tokens_details': [1]},
            'details a number': {**GOOD, 'completion_tokens_details': 5},
            'details too deep': {**GOOD, 'prompt_tokens_details': {'a': {'b': {'c': {'d': 1}}}}},
            'details too wide': {**GOOD, 'prompt_tokens_details': {str(n): n for n in range(40)}},
            'details long string': {**GOOD, 'prompt_tokens_details': {'a': 'x' * 1000}},
            'details long list': {**GOOD, 'prompt_tokens_details': {'a': list(range(40))}},
            'details long key': {**GOOD, 'prompt_tokens_details': {'a' * 300: 1}},
            'unknown usage key': {**GOOD, 'surprise': 1},
            'float counter': {**GOOD, 'prompt_tokens': 9.0},
            'missing counter': {'prompt_tokens': 1, 'total_tokens': 1},
        }
        for name, usage in cases.items():
            with self.subTest(name):
                await self.refused(stream(usage=usage))


class TolerantChunkTests(Case):
    async def test_openai_chunk_extras_are_ignored(self):
        first = content_chunk({'role': 'assistant', 'content': '', 'refusal': None}, logprobs=None,
                              top={'usage': None, 'system_fingerprint': 'fp_1', 'service_tier': 'default', 'obfuscation': 'abc'})
        later = content_chunk({'content': 'Hello', 'tool_calls': None}, logprobs=None, top={'usage': None, 'obfuscation': 'z'})
        later['service_tier'] = None
        payload = sse(first) + sse(later) + sse(content_chunk({}, 'stop', logprobs=None)) + sse(chunk([], usage=GOOD)) + DONE
        self.assertEqual(await self.events(payload), [('text', 'Hello'), ('finish', 'stop'), ('usage', GOOD)])

    async def test_null_content_is_an_empty_fragment_and_the_role_may_repeat(self):
        payload = sse(content_chunk({'role': 'assistant', 'content': None})) + sse(content_chunk({'role': 'assistant', 'content': 'A'})) \
            + sse(content_chunk({}, 'stop')) + DONE
        self.assertEqual(await self.events(payload), [('text', 'A'), ('finish', 'stop')])

    async def test_everything_that_could_carry_output_or_a_tool_stays_refused(self):
        bad = {
            'refusal text': content_chunk({'content': 'x', 'refusal': 'I cannot'}),
            'tool calls': content_chunk({'tool_calls': [{'index': 0}]}),
            'empty tool calls': content_chunk({'tool_calls': []}),
            'function call': content_chunk({'content': 'x', 'function_call': None}),
            'logprobs data': content_chunk(logprobs={'content': []}),
            'unknown choice key': content_chunk(message={'content': 'x'}),
            'unknown delta key': content_chunk({'content': 'x', 'reasoning_content': 'y'}),
            'user role': content_chunk({'role': 'user', 'content': 'x'}),
            'second choice index': chunk([{'index': 1, 'delta': {'content': 'x'}, 'finish_reason': None}]),
            'usage on a content chunk': content_chunk(top={'usage': GOOD}),
            'tool finish': content_chunk({}, 'tool_calls'),
            'filter finish': content_chunk({}, 'content_filter'),
            'non string content': content_chunk({'content': 5}),
        }
        for name, first in bad.items():
            with self.subTest(name):
                await self.refused(stream(first=first))

    async def test_an_empty_choices_chunk_without_usage_and_usage_riding_a_choice_stay_refused(self):
        await self.refused(sse(content_chunk()) + sse(content_chunk({}, 'stop')) + sse(chunk([])) + DONE)
        await self.refused(sse(content_chunk()) + sse(chunk([{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], usage=GOOD)) + DONE)


class FuzzTests(Case):
    """A seeded random mix of tolerated and refused mutations; one independent oracle: accepted iff every mutation is tolerated."""
    MUTATIONS = (
        # (name, tolerated, apply(first, stop, usage_chunk))
        ('usage null', True, lambda f, s, u: f['choices'] and f.update(usage=None)),
        ('fingerprint', True, lambda f, s, u: s.update(system_fingerprint='fp_9')),
        ('service tier null', True, lambda f, s, u: f.update(service_tier=None)),
        ('obfuscation', True, lambda f, s, u: u.update(obfuscation='o' * 8)),
        ('logprobs null', True, lambda f, s, u: f['choices'][0].update(logprobs=None)),
        ('refusal null', True, lambda f, s, u: f['choices'][0]['delta'].update(refusal=None)),
        ('content null on stop', True, lambda f, s, u: s['choices'][0]['delta'].update(content=None)),
        ('prompt details', True, lambda f, s, u: u['usage'].update(prompt_tokens_details={'cached_tokens': 1, 'x': {'y': 2}})),
        ('completion details', True, lambda f, s, u: u['usage'].update(completion_tokens_details={'reasoning_tokens': 0})),
        ('cost', True, lambda f, s, u: u['usage'].update(cost=0.25)),
        ('byok', True, lambda f, s, u: u['usage'].update(is_byok=True)),
        ('refusal text', False, lambda f, s, u: f['choices'][0]['delta'].update(refusal='no')),
        ('tool calls', False, lambda f, s, u: f['choices'][0]['delta'].update(tool_calls=[{}])),
        ('logprobs data', False, lambda f, s, u: f['choices'][0].update(logprobs={'content': []})),
        ('deep details', False, lambda f, s, u: u['usage'].update(prompt_tokens_details={'a': {'b': {'c': {'d': 1}}}})),
        ('bad total', False, lambda f, s, u: u['usage'].update(total_tokens=1)),
        ('negative cost', False, lambda f, s, u: u['usage'].update(cost=-1)),
        ('unknown usage key', False, lambda f, s, u: u['usage'].update(mystery=1)),
        ('unknown top-level key', True, lambda f, s, u: s.update(mystery={'any': ['thing']})),
    )

    async def test_a_seeded_fuzz_of_openai_stream_extras(self):
        rng = random.Random(20261013)
        accepted = rejected = 0
        for _ in range(160):
            first, stop = content_chunk({'role': 'assistant', 'content': 'Hi'}), content_chunk({}, 'stop')
            usage = chunk([], usage=dict(GOOD))
            # Refused mutations are applied last so they overwrite the tolerated twin touching the same key.
            picked = sorted(rng.sample(self.MUTATIONS, rng.randint(0, 5)), key=lambda mutation: not mutation[1])
            for _, _, apply in picked:
                apply(first, stop, usage)
            payload = sse(first) + sse(stop) + sse(usage) + DONE
            if all(tolerated for _, tolerated, _ in picked):
                accepted += 1
                self.assertEqual(await self.events(payload), [('text', 'Hi'), ('finish', 'stop'), ('usage', GOOD)],
                                 [name for name, _, _ in picked])
            else:
                rejected += 1
                await self.refused(payload)
        self.assertGreater(accepted, 20)
        self.assertGreater(rejected, 20)

    async def test_the_extras_never_reach_the_text_or_usage_events(self):
        usage = chunk([], usage={**GOOD, 'cost': 9.9, 'prompt_tokens_details': {'cached_tokens': 1}})
        items = await self.events(sse(content_chunk()) + sse(content_chunk({}, 'stop')) + sse(usage) + DONE)
        self.assertEqual(items, [('text', 'Hello'), ('finish', 'stop'), ('usage', GOOD)])
        self.assertNotIn('cost', json.dumps(items))
        self.assertEqual(copy.deepcopy(GOOD), GOOD)


if __name__ == '__main__':
    unittest.main()
