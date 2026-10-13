"""Labelled HTTPX fixture transport, never real provider inference."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.gateway_configuration import GatewayUnavailable, RetryableUpstream
from forge.gateway_inference import TextRequest
from forge.gateway_inference_adapter import HttpxTextAdapter, URL

KEY = 'fixture-private-key'
UPSTREAM = 'private/upstream'
REQUEST = TextRequest('assistant', (('user', 'Hello'),))


def event(content='', finish=None, **delta):
    return ('data: ' + json.dumps({'model': UPSTREAM, 'id': KEY,
        'choices': [{'index': 0, 'delta': {'content': content, **delta},
                     'finish_reason': finish}]}) + '\n\n').encode()


BODY = event('Hello') + event(finish='stop') + b'data: [DONE]\n\n'


class Body(httpx.AsyncByteStream):
    def __init__(self, parts, delay=0):
        self.parts, self.delay, self.closed = parts, delay, False

    async def __aiter__(self):
        for part in self.parts:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield part

    async def aclose(self):
        self.closed = True


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, body, status=200, headers=None):
        async def labelled(request):
            self.assertEqual(str(request.url), URL)
            self.assertEqual(request.headers['authorization'], 'Bearer ' + KEY)
            data = json.loads(request.content)
            self.assertEqual(data['model'], UPSTREAM)
            self.assertEqual(set(data), {'model','messages','max_tokens','stream','stream_options'})
            self.assertEqual(data['stream_options'], {'include_usage': True})
            return httpx.Response(status, headers=headers or {'content-type':'text/event-stream'},
                                  stream=body)
        return HttpxTextAdapter(transport=httpx.MockTransport(labelled))

    async def collect(self, adapter):
        return [item async for item in adapter.events(KEY, UPSTREAM, REQUEST)]

    async def test_real_fragmented_sse_normalizes_and_closes(self):
        body = Body([bytes([byte]) for byte in BODY])
        self.assertEqual(await self.collect(self.adapter(body)), [('text','Hello'),('finish','stop')])
        self.assertTrue(body.closed)

    async def test_cancel_inflight_body_closes(self):
        body = Body([BODY], delay=5)
        task = asyncio.create_task(self.collect(self.adapter(body)))
        await asyncio.sleep(.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(body.closed)

    async def test_early_consumer_close_closes_transport(self):
        body = Body([event('Hello'),event(finish='stop'),b'data: [DONE]\n\n'])
        stream = self.adapter(body).events(KEY, UPSTREAM, REQUEST)
        self.assertEqual(await anext(stream), ('text','Hello'))
        await stream.aclose()
        self.assertTrue(body.closed)

    async def test_whole_deadline_fragment_trickle(self):
        body = Body([b':' for _ in range(100)], delay=.01)
        with patch('forge.gateway_inference_adapter.TOTAL_SECONDS', .05):
            with self.assertRaises(GatewayUnavailable):
                await asyncio.wait_for(self.collect(self.adapter(body)), .3)
        self.assertTrue(body.closed)

    async def test_whole_deadline_slow_headers_is_cancelled(self):
        exited = asyncio.Event()
        async def slow(request):
            try:
                await asyncio.sleep(5)
            finally:
                exited.set()
        adapter = HttpxTextAdapter(transport=httpx.MockTransport(slow))
        with patch('forge.gateway_inference_adapter.TOTAL_SECONDS', .03):
            with self.assertRaises(GatewayUnavailable):
                await asyncio.wait_for(self.collect(adapter), .3)
        self.assertTrue(exited.is_set())

    async def test_idle_event_deadline(self):
        body = Body([BODY],delay=5)
        with patch('forge.gateway_inference_adapter.EVENT_SECONDS', .03):
            with self.assertRaises(GatewayUnavailable):
                await self.collect(self.adapter(body))
        self.assertTrue(body.closed)

    async def test_redirect_status_and_bad_media_never_relay(self):
        for status,headers in ((302,{'location':'https://evil.invalid'}),(401,None),
                               (500,None),(200,{'content-type':'application/json'}),
                               (200,{'content-type':'text/event-stream','content-encoding':'gzip'})):
            with self.subTest(status=status,headers=headers):
                body = Body([KEY.encode()])
                with self.assertRaises(GatewayUnavailable) as caught:
                    await self.collect(self.adapter(body,status,headers))
                self.assertNotIn(KEY,str(caught.exception))
                self.assertTrue(body.closed)

    async def test_tools_malformed_finish_eof_and_utf8_fail_closed(self):
        for value in (event(tool_calls=[]),event(finish='tool_calls'),b'data: bad\n\n',
                      b'data: [DONE]\n\n',event('text'),b'data: \xff\n\n',
                      b'event: error\ndata: secret\n\n'):
            with self.subTest(value=value[:20]):
                body = Body([value])
                with self.assertRaises(GatewayUnavailable):
                    await self.collect(self.adapter(body))
                self.assertTrue(body.closed)

    async def test_byte_event_and_output_limits(self):
        for name,limit,value in (('MAX_BYTES',10,BODY),('MAX_EVENT_BYTES',10,BODY),
                                 ('MAX_EVENTS',1,BODY),('MAX_OUTPUT_CHARS',2,BODY)):
            body = Body([value])
            with patch('forge.gateway_inference_adapter.'+name,limit):
                with self.assertRaises(GatewayUnavailable):
                    await self.collect(self.adapter(body))
            self.assertTrue(body.closed)

    async def test_private_echo_guard_across_fragments(self):
        for term in (KEY,UPSTREAM):
            body = Body([event(term[:3]),event(term[3:]),event(finish='stop'),
                         b'data: [DONE]\n\n'])
            emitted = []
            with self.assertRaises(GatewayUnavailable):
                async for kind,value in self.adapter(body).events(KEY,UPSTREAM,REQUEST):
                    emitted.append(value)
            self.assertNotIn(term,''.join(emitted))
            self.assertTrue(body.closed)


class FailingBody(Body):
    async def __aiter__(self):
        for part in self.parts:
            yield part
        raise httpx.ReadError('connection reset')


class RetryClassificationTests(unittest.IsolatedAsyncioTestCase):
    """Only a failure before the first byte (status or connect) may be retried on another key; the signal is typed."""
    adapter = AdapterTests.adapter
    collect = AdapterTests.collect

    async def test_a_rejected_key_rate_limit_or_server_failure_before_any_body_is_retryable(self):
        for status in (401, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                body = Body([KEY.encode()])
                with self.assertRaises(RetryableUpstream) as caught:
                    await self.collect(self.adapter(body, status, {'content-type': 'application/json'}))
                self.assertIsInstance(caught.exception, GatewayUnavailable)
                self.assertNotIn(KEY, str(caught.exception))
                self.assertTrue(body.closed)

    async def test_connect_failures_before_headers_are_retryable(self):
        for failure in (httpx.ConnectError('refused'), httpx.ConnectTimeout('slow'), httpx.PoolTimeout('busy')):
            with self.subTest(failure=type(failure).__name__):
                async def refuse(request, failure=failure):
                    raise failure
                with self.assertRaises(RetryableUpstream):
                    await self.collect(HttpxTextAdapter(transport=httpx.MockTransport(refuse)))

    async def test_other_statuses_bad_media_and_every_failure_after_the_first_byte_are_not_retryable(self):
        for status, headers in ((400, None), (403, None), (404, None), (302, {'location': 'https://evil.invalid'}),
                                (200, {'content-type': 'application/json'})):
            with self.subTest(status=status):
                with self.assertRaises(GatewayUnavailable) as caught:
                    await self.collect(self.adapter(Body([b'x']), status, headers))
                self.assertNotIsInstance(caught.exception, RetryableUpstream)
        for body in (FailingBody([event('Hello')]), Body([event('Hello')]), Body([event('Hello'), b'data: bad\n\n'])):
            with self.subTest(body=type(body).__name__):
                emitted = []
                with self.assertRaises(GatewayUnavailable) as caught:
                    async for item in self.adapter(body).events(KEY, UPSTREAM, REQUEST):
                        emitted.append(item)
                self.assertEqual(emitted[:1], [('text', 'Hello')], 'the failure happened after output was produced')
                self.assertNotIsInstance(caught.exception, RetryableUpstream)


def usage_chunk(usage, **extra):
    return ('data: ' + json.dumps({'id': 'chatcmpl-usage', 'object': 'chat.completion.chunk', 'model': UPSTREAM,
                                   'choices': [], 'usage': usage, **extra}) + '\n\n').encode()


STOP = event('Hello') + event(finish='stop')
DONE = b'data: [DONE]\n\n'


class UsageTests(unittest.IsolatedAsyncioTestCase):
    """The final usage chunk is accepted only in its exact shape: after the finish chunk, once, with plain integers."""
    adapter = AdapterTests.adapter
    collect = AdapterTests.collect

    async def test_a_valid_terminal_usage_chunk_is_emitted_after_the_finish_event(self):
        for usage, expected in (({'prompt_tokens': 12, 'completion_tokens': 5}, {'prompt_tokens': 12, 'completion_tokens': 5}),
                                ({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                                 {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}),
                                ({'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7},
                                 {'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7})):
            with self.subTest(usage=usage):
                body = Body([STOP + usage_chunk(usage) + DONE])
                self.assertEqual(await self.collect(self.adapter(body)), [('text', 'Hello'), ('finish', 'stop'), ('usage', expected)])
                self.assertTrue(body.closed)

    async def test_a_gateway_without_usage_still_succeeds_and_emits_no_usage_event(self):
        body = Body([STOP + DONE])
        self.assertEqual(await self.collect(self.adapter(body)), [('text', 'Hello'), ('finish', 'stop')])

    async def test_every_malformed_or_misplaced_usage_fails_closed(self):
        good = {'prompt_tokens': 1, 'completion_tokens': 2}
        cases = {
            'unknown usage key': STOP + usage_chunk({**good, 'bogus': 1}) + DONE,
            'negative': STOP + usage_chunk({'prompt_tokens': -1, 'completion_tokens': 2}) + DONE,
            'float': STOP + usage_chunk({'prompt_tokens': 1.0, 'completion_tokens': 2}) + DONE,
            'bool': STOP + usage_chunk({'prompt_tokens': True, 'completion_tokens': 2}) + DONE,
            'string': STOP + usage_chunk({'prompt_tokens': '1', 'completion_tokens': 2}) + DONE,
            'null': STOP + usage_chunk({'prompt_tokens': None, 'completion_tokens': 2}) + DONE,
            'huge': STOP + usage_chunk({'prompt_tokens': 10 ** 12, 'completion_tokens': 2}) + DONE,
            'missing completion': STOP + usage_chunk({'prompt_tokens': 1}) + DONE,
            'bad total': STOP + usage_chunk({**good, 'total_tokens': -3}) + DONE,
            'usage not an object': STOP + usage_chunk([1, 2]) + DONE,
            'usage null': STOP + usage_chunk(None) + DONE,
            'duplicate usage': STOP + usage_chunk(good) + usage_chunk(good) + DONE,
            'usage before finish (own chunk)': event('Hello') + usage_chunk(good) + event(finish='stop') + DONE,
            'usage riding a content chunk': (('data: ' + json.dumps({'id': 'x', 'choices': [{'index': 0, 'delta': {'content': 'a'}, 'finish_reason': None}],
                                                                      'usage': good}) + '\n\n').encode() + event(finish='stop') + DONE),
            'usage chunk with a choice': STOP + (('data: ' + json.dumps({'id': 'x', 'usage': good, 'choices': [
                {'index': 0, 'delta': {'content': 'x'}, 'finish_reason': None}]}) + '\n\n').encode()) + DONE,
            'empty choices without usage': STOP + (('data: ' + json.dumps({'id': 'x', 'choices': []}) + '\n\n').encode()) + DONE,
            'content after usage': STOP + usage_chunk(good) + event('late') + DONE,
            'usage then eof without done': STOP + usage_chunk(good),
        }
        for name, value in cases.items():
            with self.subTest(name):
                body = Body([value])
                with self.assertRaises(GatewayUnavailable) as caught:
                    await self.collect(self.adapter(body))
                self.assertNotIsInstance(caught.exception, RetryableUpstream)
                self.assertTrue(body.closed)

    async def test_a_seeded_fuzz_of_usage_shapes_accepts_exactly_the_specified_ones(self):
        import random
        rng = random.Random(20261012)
        scalars = [0, 1, 7, 2 ** 31, 10 ** 12, -1, -(10 ** 9), 1.0, 2.5, True, False, None, '3', [], {}, [1]]
        keys = ['prompt_tokens', 'completion_tokens', 'total_tokens', 'bogus', '']

        def expected(usage):
            if type(usage) is not dict or not {'prompt_tokens', 'completion_tokens'} <= set(usage) or set(usage) - {'prompt_tokens', 'completion_tokens', 'total_tokens'}:
                return False
            if not all(type(value) is int and 0 <= value <= 10 ** 9 for value in usage.values()):
                return False
            return 'total_tokens' not in usage or usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']

        accepted = rejected = 0
        for _ in range(240):
            usage = {key: rng.choice(scalars) for key in rng.sample(keys, rng.randint(0, 5))}
            if rng.random() < .5:
                usage.update(prompt_tokens=rng.choice([0, 5, 99]), completion_tokens=rng.choice([0, 3, 42]))
            body = Body([STOP + usage_chunk(usage) + DONE])
            if expected(usage):
                accepted += 1
                self.assertEqual((await self.collect(self.adapter(body)))[-1], ('usage', usage), usage)
            else:
                rejected += 1
                with self.assertRaises(GatewayUnavailable):
                    await self.collect(self.adapter(body))
        self.assertGreater(accepted, 20)
        self.assertGreater(rejected, 20)


class VerifyTests(unittest.IsolatedAsyncioTestCase):
    """A private gateway CA reaches the HTTP client of both adapters; without one the default trust store applies."""
    async def test_the_configured_verify_context_is_handed_to_the_http_client(self):
        import ssl
        from forge.gateway_catalog_adapter import HttpxModelsAdapter
        seen = []
        real = httpx.AsyncClient

        def capture(*args, **kwargs):
            seen.append(kwargs.get('verify'))
            return real(*args, **kwargs)
        context = ssl.create_default_context()
        for adapter, call in ((HttpxTextAdapter(verify=context), lambda a: a.events(KEY, UPSTREAM, REQUEST).__anext__()),
                              (HttpxModelsAdapter(verify=context), lambda a: a.discover_async(KEY)),
                              (HttpxTextAdapter(), lambda a: a.events(KEY, UPSTREAM, REQUEST).__anext__())):
            with patch('httpx.AsyncClient', capture):
                with self.assertRaises(GatewayUnavailable):  # nothing listens; only the client construction matters
                    await asyncio.wait_for(call(adapter), 5)
        self.assertEqual(seen, [context, context, True])
