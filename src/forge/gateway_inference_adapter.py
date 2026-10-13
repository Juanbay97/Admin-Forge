"""Labelled-transport-testable, allow-listed-origin cancellable text SSE adapter."""
import asyncio
import codecs
import json
import httpx
from forge.gateway_configuration import GatewayUnavailable, GatewayCipher, GATEWAY_ENDPOINT, RetryableUpstream
from forge.gateway_origins import DEFAULT_POLICY, OriginPolicy

PATH = '/v1/chat/completions'
URL = GATEWAY_ENDPOINT + PATH
TOTAL_SECONDS = 60.0
EVENT_SECONDS = 5.0
MAX_BYTES = 1048576
MAX_EVENT_BYTES = 16384
MAX_EVENTS = 1024
MAX_OUTPUT_CHARS = 32768
RETRYABLE_STATUS = frozenset({401, 429})  # plus every 5xx
MAX_TOKENS = 10 ** 9
USAGE_KEYS = frozenset({'prompt_tokens', 'completion_tokens', 'total_tokens'})


def parse_usage(value):
    """The one terminal usage chunk: empty ``choices`` and exactly the token counters, as plain bounded integers."""
    usage = value.get('usage') if type(value) is dict else None
    if (type(value) is not dict or value.get('choices') != [] or type(value.get('choices')) is not list
            or type(usage) is not dict or not {'prompt_tokens', 'completion_tokens'} <= set(usage)
            or set(usage) - USAGE_KEYS
            or any(type(count) is not int or not 0 <= count <= MAX_TOKENS for count in usage.values())):
        raise GatewayUnavailable()
    return dict(usage)


class PrivateEchoGuard:
    """Hold only a possible sensitive prefix across upstream text fragments."""
    def __init__(self, terms):
        self.terms = tuple(terms)
        self.pending = ''

    def feed(self, text, *, final=False):
        text = self.pending + text
        if any(term in text for term in self.terms):
            raise GatewayUnavailable()
        held = 0
        if not final:
            for term in self.terms:
                for size in range(1, min(len(text), len(term) - 1) + 1):
                    if text.endswith(term[:size]):
                        held = max(held, size)
        self.pending = text[-held:] if held else ''
        return text[:-held] if held else text


class HttpxTextAdapter:
    def __init__(self, *, transport=None, policy=DEFAULT_POLICY, verify=True):
        # Injection is for explicitly labelled test transports; never ambient URLs.
        if type(policy) is not OriginPolicy:
            raise ValueError('Explicit gateway origin policy required.')
        self._transport, self._policy, self._verify = transport, policy, verify  # verify: True or a private-CA SSLContext

    async def events(self, key, upstream_id, request):
        GatewayCipher.validate_key(key)
        guard = PrivateEchoGuard((key, upstream_id))
        started = False
        try:
            # An opened GatewayKey carries its bound origin; a plain key is the fixed default.
            url = self._policy.require(getattr(key, 'endpoint', GATEWAY_ENDPOINT)) + PATH
            async with asyncio.timeout(TOTAL_SECONDS):
                async with httpx.AsyncClient(transport=self._transport, trust_env=False, verify=self._verify,
                        follow_redirects=False,
                        timeout=httpx.Timeout(5.0, connect=3.0, pool=1.0)) as client:
                    async with client.stream('POST', url,
                            headers={'Authorization': 'Bearer ' + key, 'Accept': 'text/event-stream',
                                     'Accept-Encoding': 'identity'},
                            json={'model': upstream_id,
                                  'messages': [{'role': role, 'content': content}
                                               for role, content in request.messages],
                                  'max_tokens': request.max_output_tokens, 'stream': True,
                                  'stream_options': {'include_usage': True}}) as response:
                        started = True
                        if response.status_code in RETRYABLE_STATUS or response.status_code >= 500:
                            raise RetryableUpstream()
                        if (response.status_code != 200
                                or response.headers.get('content-type', '').split(';')[0].strip()
                                != 'text/event-stream'
                                or response.headers.get('content-encoding', 'identity') != 'identity'):
                            raise GatewayUnavailable()
                        decoder = codecs.getincrementaldecoder('utf-8')('strict')
                        buffer = ''
                        lines = []
                        total = events = output = 0
                        finish = usage = None
                        iterator = response.aiter_raw().__aiter__()
                        # No chunk_size: every received fragment reaches the deadline/size checks.
                        while True:
                            async with asyncio.timeout(EVENT_SECONDS):
                                try:
                                    raw = await anext(iterator)
                                except StopAsyncIteration:
                                    break
                            total += len(raw)
                            if total > MAX_BYTES:
                                raise GatewayUnavailable()
                            buffer += decoder.decode(raw)
                            if len(buffer.encode('utf-8')) > MAX_EVENT_BYTES and '\n' not in buffer:
                                raise GatewayUnavailable()
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                line = line.removesuffix('\r')
                                if len(line.encode('utf-8')) > MAX_EVENT_BYTES:
                                    raise GatewayUnavailable()
                                if line:
                                    lines.append(line)
                                    if sum(len(item.encode('utf-8')) for item in lines) > MAX_EVENT_BYTES:
                                        raise GatewayUnavailable()
                                    continue
                                events += 1
                                if events > MAX_EVENTS:
                                    raise GatewayUnavailable()
                                data = []
                                for item in lines:
                                    if item.startswith(':'):
                                        continue
                                    if not item.startswith('data:'):
                                        raise GatewayUnavailable()
                                    data.append(item[5:].lstrip(' '))
                                lines.clear()
                                if not data:
                                    continue
                                document = '\n'.join(data)
                                if document == '[DONE]':
                                    if finish is None:
                                        raise GatewayUnavailable()
                                    tail = guard.feed('', final=True)
                                    if tail:
                                        yield 'text', tail
                                    yield 'finish', finish
                                    if usage is not None:
                                        yield 'usage', usage
                                    return
                                value = json.loads(document)
                                if finish is not None:
                                    # After the finish chunk only one exact usage chunk may follow, then [DONE].
                                    if usage is not None:
                                        raise GatewayUnavailable()
                                    usage = parse_usage(value)
                                    continue
                                if type(value) is dict and 'usage' in value:
                                    raise GatewayUnavailable()
                                choices = value.get('choices') if type(value) is dict else None
                                if type(choices) is not list or len(choices) != 1:
                                    raise GatewayUnavailable()
                                choice = choices[0]
                                if (type(choice) is not dict or choice.get('index') != 0
                                        or type(choice.get('index')) is not int
                                        or set(choice) - {'index', 'delta', 'finish_reason'}):
                                    raise GatewayUnavailable()
                                delta, reason = choice.get('delta'), choice.get('finish_reason')
                                if (type(delta) is not dict or set(delta) - {'role', 'content'}
                                        or ('role' in delta and delta['role'] != 'assistant')
                                        or reason not in (None, 'stop', 'length')):
                                    raise GatewayUnavailable()
                                content = delta.get('content', '')
                                if type(content) is not str:
                                    raise GatewayUnavailable()
                                output += len(content)
                                if output > MAX_OUTPUT_CHARS:
                                    raise GatewayUnavailable()
                                safe = guard.feed(content)
                                if safe:
                                    yield 'text', safe
                                if reason is not None:
                                    finish = reason
                        decoder.decode(b'', final=True)
                        # EOF/truncated JSON without explicit finish+[DONE] is not success.
                        raise GatewayUnavailable()
        except asyncio.CancelledError:
            raise
        except RetryableUpstream:
            raise
        except httpx.TransportError:
            # Before response headers nothing reached anyone, so another key may be tried; afterwards it is final.
            raise (GatewayUnavailable() if started else RetryableUpstream()) from None
        except Exception:
            raise GatewayUnavailable() from None
