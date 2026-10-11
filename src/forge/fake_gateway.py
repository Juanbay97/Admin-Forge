"""Fake OpenAI-compatible gateway for tests and local demos; never a real provider.

It proves the wire contract the strict adapters accept (models list and streamed
chat) and records Authorization headers so tests can prove key custody. It binds
to numeric loopback only, never echoes a bearer value, and proves nothing about
the real OmniRoute gateway's strictness.
"""
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
from ipaddress import ip_address
import json
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

MODELS = ('fake-fast', 'fake-slow', 'fake-error', 'fake-malformed')
REPLY = 'This is a fake gateway reply.'
DEFAULT_PORT = 3413
MAX_KEYS = 8
MAX_SLOW_DELAY = 5.0
MAX_MODEL_ID = 255
KEY_PATTERN = re.compile(r'[!-~]{1,4096}')


@dataclass(frozen=True, repr=False)
class FakeGatewayConfiguration:
    """Explicit trusted values; the accepted keys are never discovered."""
    keys: tuple[str, ...]
    host: str = '127.0.0.1'
    port: int = DEFAULT_PORT
    slow_delay_seconds: float = 0.5

    def __post_init__(self):
        if type(self.keys) is not tuple or not 1 <= len(self.keys) <= MAX_KEYS:
            raise ValueError('Invalid fake gateway keys.')
        if any(type(key) is not str or not KEY_PATTERN.fullmatch(key) for key in self.keys):
            raise ValueError('Invalid fake gateway keys.')
        try:
            loopback = type(self.host) is str and ip_address(self.host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError('The fake gateway binds to numeric loopback only.')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Invalid fake gateway port.')
        if (type(self.slow_delay_seconds) not in (int, float)
                or not 0 <= self.slow_delay_seconds <= MAX_SLOW_DELAY):
            raise ValueError('Invalid fake gateway delay.')

    def __repr__(self):
        return 'FakeGatewayConfiguration(host=%r, port=%r)' % (self.host, self.port)


@dataclass(frozen=True, repr=False)
class GatewayRecord:
    method: str
    path: str
    model: str | None
    authorization: str | None

    def __repr__(self):
        return 'GatewayRecord(method=%r, path=%r)' % (self.method, self.path)

    def digest(self):
        return None if self.authorization is None else hashlib.sha256(self.authorization.encode()).hexdigest()


def _event(model: str, delta: dict, finish_reason=None) -> str:
    chunk = {'id': 'chatcmpl-fake', 'object': 'chat.completion.chunk', 'created': 0, 'model': model,
             'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish_reason}]}
    return 'data: ' + json.dumps(chunk, separators=(',', ':')) + '\n\n'


class FakeGateway:
    def __init__(self, configuration: FakeGatewayConfiguration, sleep):
        self.configuration = configuration
        self._sleep = sleep
        self._records: list[GatewayRecord] = []
        self.app = self._build()

    @property
    def records(self) -> tuple[GatewayRecord, ...]:
        return tuple(self._records)

    def reset(self):
        self._records.clear()

    def _authorized(self, request: Request) -> bool:
        header = request.headers.get('authorization')
        return header is not None and any(
            hmac.compare_digest(header.encode(), ('Bearer ' + key).encode())
            for key in self.configuration.keys)

    def _record(self, request: Request, model=None):
        self._records.append(GatewayRecord(request.method, request.url.path, model,
                                           request.headers.get('authorization')))

    async def _stream(self, model: str):
        """Role chunk, word deltas, a stop chunk, then ``[DONE]``; faults are model-id driven."""
        yield _event(model, {'role': 'assistant', 'content': ''})
        words = REPLY.split(' ')
        for position, word in enumerate(words):
            if model == 'fake-slow':
                await self._sleep(self.configuration.slow_delay_seconds)
            delta = {'content': word if position == len(words) - 1 else word + ' '}
            if model == 'fake-malformed':
                delta['function_call'] = None
            yield _event(model, delta)
        yield _event(model, {}, 'stop')
        yield 'data: [DONE]\n\n'

    def _build(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        def unauthorized():
            return JSONResponse({'error': {'message': 'Invalid credentials.', 'type': 'invalid_request_error'}},
                                status_code=401, headers={'WWW-Authenticate': 'Bearer'})

        @app.get('/v1/models')
        async def models(request: Request):
            self._record(request)
            if not self._authorized(request):
                return unauthorized()
            return {'object': 'list', 'data': [
                {'id': model, 'object': 'model', 'created': 0, 'owned_by': 'fake-gateway'}
                for model in sorted(MODELS)]}

        def failure(status, message, kind='invalid_request_error'):
            return JSONResponse({'error': {'message': message, 'type': kind}}, status_code=status)

        @app.post('/v1/chat/completions')
        async def completions(request: Request):
            if not self._authorized(request):
                self._record(request)
                return unauthorized()
            try:
                body = await request.json()
            except ValueError:
                body = None
            model = body.get('model') if type(body) is dict else None
            if type(model) is not str or not 1 <= len(model) <= MAX_MODEL_ID:
                model = None
            self._record(request, model)
            if model is None or type(body.get('messages')) is not list or not body['messages']:
                return failure(400, 'Invalid request.')
            if body.get('stream') is not True:
                return failure(400, 'Only streamed completions are supported.')
            if model not in MODELS:
                return failure(404, 'Unknown model.')
            if model == 'fake-error':
                return failure(500, 'Fake gateway failure.', 'server_error')
            return StreamingResponse(self._stream(model), media_type='text/event-stream',
                                     headers={'Cache-Control': 'no-store'})

        @app.get('/__fake/requests')
        async def requests():
            return {'requests': [{'method': record.method, 'path': record.path, 'model': record.model,
                                  'authorization_sha256': record.digest()} for record in self._records]}

        @app.post('/__fake/reset')
        async def reset():
            self.reset()
            return Response(status_code=204)

        return app


def create_fake_gateway(configuration: FakeGatewayConfiguration, *, sleep=None) -> FakeGateway:
    """``sleep`` is an injectable coroutine function so tests never wait for real time."""
    if type(configuration) is not FakeGatewayConfiguration:
        raise TypeError('Explicit fake gateway configuration required.')
    return FakeGateway(configuration, asyncio.sleep if sleep is None else sleep)
