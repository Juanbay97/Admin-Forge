"""Narrow member text inference, not a full OpenAI or capability contract."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import json
import re
from typing import Protocol
from uuid import UUID, uuid4
from anyio.to_thread import run_sync
from forge.gateway_configuration import GatewayRecord, GatewayDenied, GatewayUnavailable, RetryableUpstream
from forge.invitations import capability_digest

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
                or any(type(item) is not GatewayRecord for item in self.fallbacks)):
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


def sse(document):
    return ('data: ' + json.dumps(document, separators=(',', ':'), ensure_ascii=True)
            + '\n\n').encode('utf-8')


class GatewayInference:
    def __init__(self, store: InferenceStore, cipher, adapter):
        self._store, self._cipher, self._adapter = store, cipher, adapter

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
        opened = []
        for record in route.candidates:
            try:
                opened.append(self._cipher.open_key(organization_id, record))
            except GatewayUnavailable:
                continue  # an unreadable key is skipped; none readable is unavailable before any outbound call
        if not opened:
            raise GatewayUnavailable()
        return PreparedInference(digest, route, request, opened[0], tuple(opened))

    async def _failover(self, prepared):
        """Try each opened key once, in priority order; only a typed pre-first-byte failure moves on."""
        for key in prepared.keys or (prepared.key,):
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
            stream = self._failover(prepared)
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
                    yield chunk(value)
                elif kind == 'finish':
                    yield chunk(finish=value)
                else:
                    raise GatewayUnavailable()
            yield b'data: [DONE]\n\n'
        except asyncio.CancelledError:
            raise
        except Exception:
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
