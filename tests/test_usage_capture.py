"""Metering at the inference seam: one event per inference that reached the gateway, recorded in a shielded finally, with
estimated counts when the gateway gave none, the serving key on failover, and a recording failure that never touches the stream."""
import asyncio
import dataclasses
from pathlib import Path
import sys
import unittest
from uuid import UUID, uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher, GatewayDenied, GatewayRecord, GatewayUnavailable, RetryableUpstream
from forge.gateway_inference import GatewayInference, RouteContext, TextRequest
from forge.usage import AllowAll, UsageEvent, estimate_tokens

ORG, MEMBER = uuid4(), uuid4()
TOKEN = 'A' * 43
REQUEST = TextRequest('assistant', (('system', 'be brief'), ('user', 'hello there friend')))  # 8 + 18 = 26 characters
ENDPOINT = 'https://ia.prometheonlab.com'


class Recorder:
    def __init__(self, *, fail=None, delay=0):
        self.events, self.fail, self.delay = [], fail, delay

    def record(self, event):
        import time
        time.sleep(self.delay)
        if self.fail:
            raise self.fail
        self.events.append(event)
        return True


class Pool:
    def __init__(self, cipher, keys):
        binding = uuid4()
        self.key_ids = [uuid4() for _ in keys]
        records = [GatewayRecord(1, binding, ENDPOINT, cipher.seal_pooled(key_id, 1, key, ENDPOINT), key_id, 1)
                   for key_id, key in zip(self.key_ids, keys)]
        self.route = RouteContext(ORG, 'assistant', 1, 'private/route', records[0], tuple(records[1:]), MEMBER)
        self.denied = False

    def resolve(self, digest, org, alias):
        if self.denied:
            raise GatewayDenied()
        return self.route


class Script:
    """Per bearer key: a list of items to yield, or 'retry' to fail before any byte, or an exception to raise after the items."""
    def __init__(self, scripts, hold=None):
        self.scripts, self.hold, self.seen = scripts, hold, []

    async def events(self, key, route, request):
        self.seen.append(str(key))
        script = self.scripts[str(key)]
        if script == 'retry':
            raise RetryableUpstream()
        items, ending = script
        for item in items:
            yield item
            await asyncio.sleep(0.005)
        if self.hold is not None:
            await self.hold.wait()
        if ending is not None:
            raise ending


def usage(prompt, completion):
    return ('usage', {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion})


OK = [('text', 'hello '), ('text', 'world'), ('finish', 'stop')]


class MeteringTests(unittest.IsolatedAsyncioTestCase):
    def build(self, keys, scripts, *, recorder=None, quota=None, hold=None):
        self.cipher = GatewayCipher(Fernet.generate_key())
        self.pool = Pool(self.cipher, keys)
        self.recorder = recorder or Recorder()
        self.adapter = Script(scripts, hold)
        options = {} if quota is None else {'quota': quota}
        self.service = GatewayInference(self.pool, self.cipher, self.adapter, usage=self.recorder, **options)

    async def drain(self, disconnected=None):
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        return b''.join([part async for part in self.service.stream(prepared, disconnected=disconnected)])

    async def test_a_gateway_reported_success_records_one_event_with_the_serving_key_and_gateway_tokens(self):
        self.build(['key-one-K1'], {'key-one-K1': ([*OK, usage(21, 4)], None)})
        output = await self.drain()
        self.assertIn(b'[DONE]', output)
        self.assertNotIn(b'prompt_tokens', output, 'usage is recorded, never relayed to the member')
        (event,) = self.recorder.events
        self.assertEqual((event.organization_id, event.membership_id, event.alias, event.upstream_id, event.key_id),
                         (ORG, MEMBER, 'assistant', 'private/route', self.pool.key_ids[0]))
        self.assertEqual((event.prompt_tokens, event.completion_tokens, event.source, event.status, event.error_code), (21, 4, 'gateway', 'ok', None))
        self.assertTrue(event.latency_ms >= 0 and event.ttfb_ms is not None and 0 <= event.ttfb_ms <= event.latency_ms)
        self.assertIsInstance(event.event_id, UUID)

    async def test_a_gateway_that_omits_usage_is_estimated_from_characters(self):
        self.build(['key-one-K1'], {'key-one-K1': (OK, None)})
        await self.drain()
        (event,) = self.recorder.events
        # prompt: 26 characters -> 7 tokens; completion: 'hello world' = 11 characters -> 3 tokens
        self.assertEqual((event.prompt_tokens, event.completion_tokens, event.source, event.status), (7, 3, 'estimated', 'ok'))
        self.assertEqual([estimate_tokens(0), estimate_tokens(1), estimate_tokens(4), estimate_tokens(5)], [0, 1, 1, 2])

    async def test_a_client_that_closes_early_still_records_an_estimated_cancelled_event(self):
        self.build(['key-one-K1'], {'key-one-K1': ([('text', 'hello '), ('text', 'world'), ('finish', 'stop')], None)}, hold=asyncio.Event())
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        stream = self.service.stream(prepared)
        self.assertIn(b'hello', await anext(stream))
        await stream.aclose()
        (event,) = self.recorder.events
        self.assertEqual((event.status, event.source, event.prompt_tokens, event.completion_tokens), ('cancelled', 'estimated', 7, 2))

    async def test_a_cancelled_consumer_task_still_records_through_the_shield(self):
        self.build(['key-one-K1'], {'key-one-K1': ([('text', 'hello ')], None)}, recorder=Recorder(delay=0.05), hold=asyncio.Event())
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        stream = self.service.stream(prepared)
        await anext(stream)
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.2)
        self.assertEqual([event.status for event in self.recorder.events], ['cancelled'])

    async def test_a_failure_after_output_records_an_error_event_with_a_finite_code(self):
        self.build(['key-one-K1'], {'key-one-K1': ([('text', 'hello ')], GatewayUnavailable())})
        output = await self.drain()
        self.assertIn(b'INFERENCE_UNAVAILABLE', output)
        (event,) = self.recorder.events
        self.assertEqual((event.status, event.error_code, event.source), ('error', 'INFERENCE_UNAVAILABLE', 'estimated'))

    async def test_failover_records_one_event_for_the_key_that_served(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'retry', 'key-two-K2': ([*OK, usage(5, 2)], None)})
        await self.drain()
        (event,) = self.recorder.events
        self.assertEqual((event.key_id, event.status, event.prompt_tokens), (self.pool.key_ids[1], 'ok', 5))

    async def test_when_every_key_is_down_one_error_event_is_recorded_for_the_last_key_tried(self):
        self.build(['key-one-K1', 'key-two-K2'], {'key-one-K1': 'retry', 'key-two-K2': 'retry'})
        output = await self.drain()
        self.assertIn(b'INFERENCE_UNAVAILABLE', output)
        (event,) = self.recorder.events
        self.assertEqual((event.key_id, event.status, event.error_code, event.completion_tokens), (self.pool.key_ids[1], 'error', 'INFERENCE_UNAVAILABLE', 0))

    async def test_a_request_denied_before_any_outbound_call_records_nothing(self):
        self.build(['key-one-K1'], {'key-one-K1': (OK, None)})
        prepared = await self.service.prepare(TOKEN, ORG, REQUEST)
        self.pool.denied = True
        output = b''.join([part async for part in self.service.stream(prepared)])
        self.assertIn(b'INFERENCE_UNAVAILABLE', output)
        self.assertEqual((self.adapter.seen, self.recorder.events), ([], []))

    async def test_a_recording_failure_never_changes_the_stream_and_is_counted(self):
        self.build(['key-one-K1'], {'key-one-K1': ([*OK, usage(5, 2)], None)}, recorder=Recorder(fail=RuntimeError('store down')))
        output = await self.drain()
        self.assertEqual((output.count(b'[DONE]'), output.count(b'INFERENCE_UNAVAILABLE'), self.service.usage_failures), (1, 0, 1))
        self.assertIn(b'hello', output)

    async def test_without_a_recorder_or_a_member_nothing_is_recorded_and_nothing_breaks(self):
        self.build(['key-one-K1'], {'key-one-K1': (OK, None)})
        self.service = GatewayInference(self.pool, self.cipher, self.adapter)
        self.assertIn(b'[DONE]', await self.drain())
        self.pool.route = dataclasses.replace(self.pool.route, membership_id=None)
        self.service = GatewayInference(self.pool, self.cipher, self.adapter, usage=self.recorder)
        self.assertIn(b'[DONE]', await self.drain())
        self.assertEqual(self.recorder.events, [])

    async def test_the_event_carries_counters_and_identifiers_only(self):
        names = {field.name for field in dataclasses.fields(UsageEvent)}
        self.assertEqual(names, {'event_id', 'organization_id', 'membership_id', 'alias', 'upstream_id', 'key_id', 'prompt_tokens',
                                 'completion_tokens', 'latency_ms', 'ttfb_ms', 'status', 'error_code', 'source'})


class QuotaTests(unittest.IsolatedAsyncioTestCase):
    def build(self, quota=None):
        cipher = GatewayCipher(Fernet.generate_key())
        self.pool = Pool(cipher, ['key-one-K1'])
        self.adapter = Script({'key-one-K1': (OK, None)})
        options = {} if quota is None else {'quota': quota}
        return GatewayInference(self.pool, cipher, self.adapter, **options)

    async def test_the_default_quota_never_denies(self):
        service = self.build()
        self.assertIsNone(AllowAll().check(ORG, MEMBER))
        self.assertTrue(await service.prepare(TOKEN, ORG, REQUEST))

    async def test_prepare_calls_the_quota_with_the_company_and_member_and_a_denial_stops_before_outbound(self):
        calls = []

        class Refuse:
            def check(self, org, member):
                calls.append((org, member))
                raise GatewayDenied()
        service = self.build(Refuse())
        with self.assertRaises(GatewayDenied):
            await service.prepare(TOKEN, ORG, REQUEST)
        self.assertEqual((calls, self.adapter.seen), ([(ORG, MEMBER)], []))


if __name__ == '__main__':
    unittest.main()
