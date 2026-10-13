"""Narrow member text inference, not a full OpenAI or capability contract."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import json
import re
import time
from typing import Protocol
from uuid import UUID, uuid4
from anyio.to_thread import run_sync
from forge.gateway_configuration import GatewayRecord, GatewayDenied, GatewayUnavailable, RetryableUpstream
from forge.invitations import capability_digest
from forge.usage import AllowAll, UsageEvent, estimate_tokens

MAX_MESSAGES = 16
MAX_CONTENT = 4096
MAX_INPUT_BYTES = 16384
MAX_OUTPUT_TOKENS = 2048
MAX_CANDIDATES = 16
REVOCATION_INTERVAL = 0.5


@dataclass(frozen=True, repr=False)
class TextRequest:
    model: str
    messages: tuple[tuple[str, str], ...]
    max_output_tokens: int = 512

    def __post_init__(self):
        if type(self.model) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', self.model):
            raise ValueError('Invalid text request.')
        if (type(self.messages) is not tuple or not 1 <= len(self.messages) <= MAX_MESSAGES
                or type(self.max_output_tokens) is not int
                or not 1 <= self.max_output_tokens <= MAX_OUTPUT_TOKENS):
            raise ValueError('Invalid text request.')
        for message in self.messages:
            if (type(message) is not tuple or len(message) != 2
                    or message[0] not in ('system', 'user', 'assistant')
                    or type(message[1]) is not str or not 1 <= len(message[1]) <= MAX_CONTENT):
                raise ValueError('Invalid text request.')
        try:
            size = sum(len(content.encode('utf-8')) for _, content in self.messages)
        except UnicodeError:
            raise ValueError('Invalid text request.') from None
        if size > MAX_INPUT_BYTES or self.messages[-1][0] != 'user':
            raise ValueError('Invalid text request.')


@dataclass(frozen=True, repr=False)
class RouteContext:
    organization_id: UUID
    alias: str
    catalog_revision: int
    upstream_id: str
    gateway: GatewayRecord
    # Further keys of the company in priority order; ``gateway`` is the lowest-priority (primary) one.
    fallbacks: tuple = ()
    # The authorized member, for usage attribution; None where the store does not resolve it (retained demo profile).
    membership_id: UUID | None = None

    @property
    def candidates(self):
        return (self.gateway, *self.fallbacks)

    def same_route(self, other):
        """Authority identity: the key material may rotate or reorder mid-stream, the route and binding may not."""
        return (type(other) is RouteContext and self.organization_id == other.organization_id
                and self.alias == other.alias and self.catalog_revision == other.catalog_revision
                and self.upstream_id == other.upstream_id and self.gateway.binding_id == other.gateway.binding_id
                and self.gateway.revision == other.gateway.revision)

    def validate(self, organization_id, alias):
        if (type(self.organization_id) is not UUID or self.organization_id != organization_id
                or self.alias != alias or type(self.catalog_revision) is not int
                or self.catalog_revision < 1 or type(self.upstream_id) is not str
                or not re.fullmatch(r'[!-~]{1,255}', self.upstream_id)
                or type(self.gateway) is not GatewayRecord or type(self.fallbacks) is not tuple
                or len(self.fallbacks) >= MAX_CANDIDATES
                or any(type(item) is not GatewayRecord for item in self.fallbacks)
                or (self.membership_id is not None and type(self.membership_id) is not UUID)):
            raise GatewayUnavailable()


class InferenceStore(Protocol):
    def resolve(self, digest: str, organization_id: UUID, alias: str) -> RouteContext: ...


@dataclass(frozen=True, repr=False)
class PreparedInference:
    digest: str
    route: RouteContext
    request: TextRequest
    key: str
    # Opened keys in priority order (the first equals ``key``); empty means just ``key``.
    keys: tuple = ()
    key_ids: tuple = ()  # parallel to ``keys``: the pool key each was opened from (None for a legacy key)


def sse(document):
    return ('data: ' + json.dumps(document, separators=(',', ':'), ensure_ascii=True)
            + '\n\n').encode('utf-8')


class _Meter:
    """Timings and counters of one stream; the key and the first byte are those of the attempt that served."""
    def __init__(self, clock):
        self.clock, self.started = clock, clock()
        self.attempted, self.key_id, self.attempt, self.first_byte = False, None, None, None
        self.usage, self.characters = None, 0

    def begin(self, key_id):
        self.attempted, self.key_id, self.attempt, self.first_byte = True, key_id, self.clock(), None

    def text(self, value):
        if self.first_byte is None:
            self.first_byte = int((self.clock() - self.attempt) * 1000)
        self.characters += len(value)


class GatewayInference:
    def __init__(self, store: InferenceStore, cipher, adapter, *, usage=None, quota=None, clock=time.monotonic):
        self._store, self._cipher, self._adapter = store, cipher, adapter
        self._usage, self._quota, self._clock = usage, AllowAll() if quota is None else quota, clock
        self.usage_failures = 0  # finite counter: recording is best-effort and never alters a stream

    async def _resolve(self, digest, organization_id, alias):
        # Framework's bounded worker limiter, no abandoned thread or network-held lock.
        worker = asyncio.create_task(run_sync(self._store.resolve, digest, organization_id,
                                              alias, abandon_on_cancel=False))
        try:
            route = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # asyncio cancellation must also settle the bounded synchronous port;
            # do not release a thread still using its database transaction.
            with suppress(Exception):
                await worker
            raise
        if type(route) is not RouteContext:
            raise GatewayUnavailable()
        route.validate(organization_id, alias)
        return route

    async def prepare(self, token, organization_id, request):
        if type(organization_id) is not UUID or type(request) is not TextRequest:
            raise ValueError('Invalid text request.')
        digest = capability_digest(token)
        route = await self._resolve(digest, organization_id, request.model)
        self._quota.check(organization_id, route.membership_id)  # a refusal comes before any key handling
        opened, key_ids = [], []
        for record in route.candidates:
            try:
                opened.append(self._cipher.open_key(organization_id, record))
                key_ids.append(record.key_id)
            except GatewayUnavailable:
                continue  # an unreadable key is skipped; none readable is unavailable before any outbound call
        if not opened:
            raise GatewayUnavailable()
        return PreparedInference(digest, route, request, opened[0], tuple(opened), tuple(key_ids))

    async def _failover(self, prepared, meter):
        """Try each opened key once, in priority order; only a typed pre-first-byte failure moves on."""
        keys = prepared.keys or (prepared.key,)
        ids = prepared.key_ids or (prepared.route.gateway.key_id,) * len(keys)
        for key, key_id in zip(keys, ids):
            meter.begin(key_id)
            stream = self._adapter.events(key, prepared.route.upstream_id, prepared.request)
            try:
                async for event in stream:
                    yield event
                return
            except RetryableUpstream:
                continue
            finally:
                await stream.aclose()
        raise GatewayUnavailable()

    async def stream(self, prepared, *, disconnected=None):
        """Every response is freshly normalized; upstream documents never cross API.

        Revocation checks run every0.5s plus bounded database/scheduler latency.
        Output waits when an authorization check is pending. Already delivered
        text and incurred upstream work cannot be undone.
        """
        identifier = str(uuid4())
        def chunk(text=None, finish=None):
            delta = {} if text is None else {'content': text}
            return sse({'id': identifier, 'object': 'chat.completion.chunk',
                        'model': prepared.request.model,
                        'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]})

        stream = None
        pending = None
        authority = None
        producer = None
        meter = _Meter(self._clock)
        outcome, failure = 'cancelled', None  # a stream that ends any other way than below was cut by the client
        allowed = asyncio.Event()
        allowed.set()

        async def check():
            current = await self._resolve(prepared.digest, prepared.route.organization_id,
                                          prepared.request.model)
            if not current.same_route(prepared.route):
                raise GatewayDenied()

        async def watch():
            while True:
                await asyncio.sleep(REVOCATION_INTERVAL)
                allowed.clear()
                if disconnected is not None and await disconnected():
                    raise GatewayDenied()
                await check()
                allowed.set()

        try:
            # Revalidate after preparation and immediately before the outbound call.
            await check()
            if disconnected is not None and await disconnected():
                return
            authority = asyncio.create_task(watch())
            stream = self._failover(prepared, meter)
            queue = asyncio.Queue(maxsize=1)

            async def produce():
                # One task owns the adapter's whole-request timeout from headers
                # through every fragment; never resume its timeout on a new task.
                from forge.gateway_inference_adapter import TOTAL_SECONDS
                try:
                    # Include downstream backpressure, even while the adapter is
                    # suspended at yield rather than awaiting an HTTP fragment.
                    async with asyncio.timeout(TOTAL_SECONDS):
                        async for event in stream:
                            await queue.put(event)
                        await queue.put(None)
                finally:
                    await stream.aclose()

            producer = asyncio.create_task(produce())
            while True:
                pending = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait((pending, authority, producer),
                                             return_when=asyncio.FIRST_COMPLETED)
                if authority in done:
                    authority.result()
                    raise GatewayUnavailable()
                if producer in done:
                    # Only owned deadline tasks cancel the producer while the
                    # consumer remains active. Client cancellation is handled by
                    # the outer CancelledError path and settles all owned tasks.
                    if producer.cancelled():
                        raise GatewayUnavailable()
                    producer.result()
                # A successful producer enqueued its terminal sentinel already.
                item = await pending
                pending = None
                if item is None:
                    break
                kind, value = item
                # Check-completion gate also wakes on revocation while body is ready.
                gate = asyncio.create_task(allowed.wait())
                try:
                    done, _ = await asyncio.wait((gate, authority),
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if authority in done:
                        authority.result()
                    await gate
                finally:
                    gate.cancel()
                    with suppress(asyncio.CancelledError):
                        await gate
                if disconnected is not None and await disconnected():
                    return
                if kind == 'text':
                    meter.text(value)
                    yield chunk(value)
                elif kind == 'finish':
                    yield chunk(finish=value)
                elif kind == 'usage':
                    meter.usage = value  # recorded below; never relayed to the member
                else:
                    raise GatewayUnavailable()
            outcome = 'ok'
            yield b'data: [DONE]\n\n'
        except asyncio.CancelledError:
            raise
        except Exception:
            outcome, failure = 'error', 'INFERENCE_UNAVAILABLE'
            yield sse({'error': {'code': 'INFERENCE_UNAVAILABLE',
                'message': 'Text generation unavailable.', 'request_id': identifier,
                'retryable': False}})
            yield b'data: [DONE]\n\n'
        finally:
            for task in (pending, authority, producer):
                if task is not None:
                    task.cancel()
            for task in (pending, authority, producer):
                if task is not None:
                    with suppress(asyncio.CancelledError, Exception):
                        await task
            if stream is not None:
                await stream.aclose()
            await self._record(prepared, meter, identifier, outcome, failure)

    def _event(self, prepared, meter, identifier, outcome, failure):
        if meter.usage is not None:
            prompt, completion, source = meter.usage['prompt_tokens'], meter.usage['completion_tokens'], 'gateway'
        else:
            prompt = estimate_tokens(sum(len(content) for _, content in prepared.request.messages))
            completion, source = estimate_tokens(meter.characters), 'estimated'
        return UsageEvent(UUID(identifier), prepared.route.organization_id, prepared.route.membership_id,
                          prepared.request.model, prepared.route.upstream_id, meter.key_id, prompt, completion,
                          int((self._clock() - meter.started) * 1000), meter.first_byte, outcome, failure, source)

    def _settled(self, task):
        if task.cancelled() or task.exception() is not None:
            self.usage_failures += 1

    async def _record(self, prepared, meter, identifier, outcome, failure):
        """Once per inference that reached the gateway, shielded so a cancelled consumer cannot lose it."""
        if self._usage is None or prepared.route.membership_id is None or not meter.attempted:
            return
        task = asyncio.ensure_future(run_sync(self._usage.record, self._event(prepared, meter, identifier, outcome, failure),
                                              abandon_on_cancel=False))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            task.add_done_callback(self._settled)  # the write finishes detached; its failure is still counted
            raise
        except Exception:
            self.usage_failures += 1
