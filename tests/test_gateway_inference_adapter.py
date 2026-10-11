"""Labelled HTTPX fixture transport, never real provider inference."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.gateway_configuration import GatewayUnavailable
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
            self.assertEqual(set(data), {'model','messages','max_tokens','stream'})
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
