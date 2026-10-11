"""Labelled HTTPX fixture discovery: no live gateway credentials or connections."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.gateway_catalog_adapter import HttpxModelsAdapter, MAX_DISCOVERY_BYTES
from forge.gateway_configuration import GatewayUnavailable

KEY='labelled-fixture-not-live-key'

class AdapterTests(unittest.TestCase):
    def test_fixed_origin_auth_timeouts_and_ids_only(self):
        observed=[]
        def handler(request):
            observed.append(request)
            return httpx.Response(200,json={'data':[{'id':'private/z','tools':True},{'id':'private/a'}]})
        result=HttpxModelsAdapter(transport=httpx.MockTransport(handler)).discover(KEY)
        self.assertEqual(result,('private/a','private/z'))
        request=observed[0]
        self.assertEqual(str(request.url),'https://ia.prometheonlab.com/v1/models')
        self.assertEqual(request.headers['authorization'],'Bearer '+KEY)
        self.assertEqual(request.extensions['timeout'],{'connect':2,'read':5,'write':2,'pool':1})

    def test_redirect_and_provider_failures_are_redacted(self):
        for status in (302,401,429,500):
            count=[]
            def handler(request):
                count.append(1)
                return httpx.Response(status,headers={'location':'https://attacker.invalid'},text=KEY)
            with self.assertRaises(GatewayUnavailable) as error:
                HttpxModelsAdapter(transport=httpx.MockTransport(handler)).discover(KEY)
            self.assertEqual(len(count),1)
            self.assertNotIn(KEY,str(error.exception));self.assertIsNone(error.exception.__cause__)

    def test_total_deadline_is_finite(self):
        ticks=iter((0,11))
        with self.assertRaises(GatewayUnavailable):
            HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'data':[{'id':'x'}]})),
                clock=lambda:next(ticks)).discover(KEY)

    def test_byte_count_and_model_count_limits(self):
        for response in (httpx.Response(200,content=b' '* (MAX_DISCOVERY_BYTES+1)),
                         httpx.Response(200,json={'data':[{'id':str(i)} for i in range(501)]})):
            with self.assertRaises(GatewayUnavailable):
                HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:response)).discover(KEY)

    def test_empty_duplicate_malformed_and_unbounded_ids(self):
        for data in ([],[{'id':'x'},{'id':'x'}],[{}],[{'id':42}],[{'id':'x'*256}],
                     [{'id':'unsafe\n'}],[{'id':'unicode-\u2603'}]):
            with self.subTest(data=data),self.assertRaises(GatewayUnavailable):
                HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'data':data}))).discover(KEY)

    def test_secret_rich_transport_exception_is_not_relayed(self):
        def handler(request):raise RuntimeError(KEY)
        with self.assertRaises(GatewayUnavailable) as error:
            HttpxModelsAdapter(transport=httpx.MockTransport(handler)).discover(KEY)
        self.assertNotIn(KEY,str(error.exception));self.assertIsNone(error.exception.__cause__)

    def test_compressed_response_rejected_before_decoding(self):
        response=httpx.Response(200,headers={'content-encoding':'gzip'},stream=httpx.ByteStream(b'not-decoded'))
        with self.assertRaises(GatewayUnavailable):
            HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:response)).discover(KEY)

class DeadlineTests(unittest.TestCase):
    def test_fragmented_trickle_is_checked_before_large_buffer_fills(self):
        class Trickle(httpx.SyncByteStream,httpx.AsyncByteStream):
            def __init__(self):self.consumed=0
            def __iter__(self):
                for _ in range(100):
                    self.consumed+=1
                    yield b' '
            async def __aiter__(self):
                import asyncio
                for _ in range(100):
                    await asyncio.sleep(0)
                    self.consumed+=1
                    yield b' '
        stream=Trickle()
        with self.assertRaises(GatewayUnavailable):
            HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:httpx.Response(200,stream=stream)),
                clock=lambda:float(stream.consumed)).discover(KEY)
        self.assertLessEqual(stream.consumed,10,'Total deadline must not wait for a64KiB buffer')

    def test_actual_fragmented_trickle_is_cancelled_and_closed(self):
        import asyncio
        import threading
        from time import monotonic
        class SlowTrickle(httpx.AsyncByteStream):
            def __init__(self):
                self.consumed=0;self.cancelled=False;self.closed=False
            async def __aiter__(self):
                try:
                    for _ in range(100):
                        await asyncio.sleep(0.02)
                        self.consumed+=1
                        yield b' '
                finally:self.cancelled=True
            async def aclose(self):self.closed=True
        stream=SlowTrickle();before={thread.ident for thread in threading.enumerate()}
        started=monotonic()
        with self.assertRaises(GatewayUnavailable):
            HttpxModelsAdapter(transport=httpx.MockTransport(lambda _:httpx.Response(200,stream=stream)),
                deadline_seconds=0.06).discover(KEY)
        self.assertLess(monotonic()-started,0.6)
        self.assertLess(stream.consumed,100)
        self.assertTrue(stream.cancelled);self.assertTrue(stream.closed)
        self.assertEqual({thread.ident for thread in threading.enumerate()},before)

    def test_slow_send_headers_cancel_without_pending_request(self):
        import asyncio
        from time import monotonic
        for stage in ('send', 'headers'):
            class StageTransport(httpx.AsyncBaseTransport):
                """Labelled awaited send/header stages; no socket or real key."""
                def __init__(self):
                    self.reached=[];self.cancelled=False;self.closed=False
                async def handle_async_request(self,request):
                    try:
                        for current in ('send','headers'):
                            self.reached.append(current)
                            await asyncio.sleep(30 if current==stage else 0)
                        return httpx.Response(200,json={'data':[{'id':'private/a'}]})
                    finally:self.cancelled=True
                async def aclose(self):self.closed=True
            transport=StageTransport()
            async def scenario():
                adapter=HttpxModelsAdapter(transport=transport,deadline_seconds=0.03)
                started=monotonic()
                with self.assertRaises(GatewayUnavailable) as error:
                    await adapter.discover_async(KEY)
                self.assertLess(monotonic()-started,0.6)
                self.assertEqual(transport.reached,['send'] if stage=='send' else ['send','headers'])
                self.assertTrue(transport.cancelled);self.assertTrue(transport.closed)
                self.assertNotIn(KEY,str(error.exception))
                self.assertEqual([task for task in asyncio.all_tasks() if task is not asyncio.current_task()],[])
            with self.subTest(stage=stage):asyncio.run(scenario())

    def test_sync_facade_does_not_nest_loop_and_async_entry_remains_usable(self):
        import asyncio
        requests=[]
        def handler(request):
            requests.append(1)
            return httpx.Response(200,json={'data':[{'id':'private/a'}]})
        async def scenario():
            adapter=HttpxModelsAdapter(transport=httpx.MockTransport(handler))
            with self.assertRaises(GatewayUnavailable):adapter.discover(KEY)
            self.assertEqual(requests,[])
            self.assertEqual(await adapter.discover_async(KEY),('private/a',))
            self.assertEqual(requests,[1])
        asyncio.run(scenario())

    def test_deadline_configuration_cannot_relax_ceiling(self):
        for value in (True,0,-1,11,float('inf'),float('nan'),'10'):
            with self.assertRaises(ValueError):HttpxModelsAdapter(deadline_seconds=value)
