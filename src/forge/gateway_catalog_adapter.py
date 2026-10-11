"""Bounded allow-listed-origin ID discovery; IDs do not establish capabilities."""
import asyncio
import json
import math
import re
from time import monotonic
import httpx
from forge.gateway_configuration import GatewayCipher, GatewayUnavailable, GATEWAY_ENDPOINT
from forge.gateway_origins import DEFAULT_POLICY, OriginPolicy

MAX_MODELS = 500
MAX_MODEL_ID = 255
MAX_DISCOVERY_BYTES = 1024 * 1024


def validated_ids(values):
    if type(values) not in (list, tuple) or not 1 <= len(values) <= MAX_MODELS:
        raise GatewayUnavailable()
    if any(type(value) is not str or not re.fullmatch(r'[!-~]{1,255}', value) for value in values):
        raise GatewayUnavailable()
    if len(set(values)) != len(values):
        raise GatewayUnavailable()
    return tuple(sorted(values))


class HttpxModelsAdapter:
    """Cancellable whole-request deadline, with a worker-thread sync facade.

    The account factory invokes synchronous ports in FastAPI worker threads.
    Async callers must await discover_async instead of nesting an event loop.
    The optional smaller deadline is useful for labelled cancellation tests;
    no caller can increase the production ten-second ceiling.
    """
    def __init__(self, *, transport=None, clock=monotonic, deadline_seconds=10.0, policy=DEFAULT_POLICY):
        if type(policy) is not OriginPolicy:
            raise ValueError('Explicit gateway origin policy required.')
        self._policy = policy
        if (type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds)
                or not 0 < deadline_seconds <= 10.0):
            raise ValueError('Invalid discovery deadline.')
        self._transport, self._clock = transport, clock
        self._deadline_seconds = deadline_seconds

    def discover(self, key: str) -> tuple[str, ...]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # One owned loop executes the request itself; no background request
            # thread, future or executor remains running after timeout returns.
            return asyncio.run(self.discover_async(key))
        raise GatewayUnavailable() from None

    async def discover_async(self, key: str) -> tuple[str, ...]:
        GatewayCipher.validate_key(key)
        observed_deadline = self._clock() + self._deadline_seconds
        try:
            # An opened GatewayKey carries its bound origin; a plain key is the fixed default.
            # Re-checked here so a narrowed allow-list denies before any request leaves.
            endpoint = self._policy.require(getattr(key, 'endpoint', GATEWAY_ENDPOINT))
            # Unlike per-read timeouts or clock observations, this cancellation
            # surrounds send, response headers and every awaited body fragment.
            async with asyncio.timeout(self._deadline_seconds):
                async with httpx.AsyncClient(transport=self._transport, trust_env=False,
                        follow_redirects=False, timeout=httpx.Timeout(5, connect=2, write=2, pool=1)) as client:
                    async with client.stream('GET', endpoint + '/v1/models',
                            headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json',
                                     'Accept-Encoding': 'identity'}) as response:
                        if (response.status_code != 200 or self._clock() >= observed_deadline
                                or response.headers.get('content-encoding','identity').lower() != 'identity'):
                            raise GatewayUnavailable()
                        body = bytearray()
                        # No application-sized buffering: inspect each transport
                        # fragment, including a trickle that never fills64KiB.
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_DISCOVERY_BYTES or self._clock() >= observed_deadline:
                                raise GatewayUnavailable()
                            body.extend(chunk)
                        if self._clock() >= observed_deadline:
                            raise GatewayUnavailable()
                        document = json.loads(body)
                        if (type(document) is not dict or type(document.get('data')) is not list
                                or not 1 <= len(document['data']) <= MAX_MODELS
                                or not all(type(item) is dict and 'id' in item for item in document['data'])):
                            raise GatewayUnavailable()
                        ids = validated_ids([item['id'] for item in document['data']])
                        if self._clock() >= observed_deadline:
                            raise GatewayUnavailable()
                        return ids
        except Exception:
            raise GatewayUnavailable() from None
