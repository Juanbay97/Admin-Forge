"""The MCP proxy: a member's JSON-RPC request is authorized per call, sent upstream with the connector's credential injected server-side, and
the answer is scrubbed before it reaches the member. The credential never reaches the device.

Per call, in order, and before any upstream traffic: the body is size-capped and must be one JSON-RPC object whose method is allow-listed;
the live session, active membership and the connector's effective state (resolved fresh: a force-off is immediate) are checked in the
database; the member's rate is checked; the credential is opened in memory (an OAuth grant is refreshed single-flight when it is about to
expire). Then the egress guard plans the connection (https/443, allow-listed host, public pinned IP, no redirect), the client's headers are
reduced to a short allow-list, the credential header is injected, and the response is relayed with a header allow-list, a size and time
cap, and every occurrence of the injected credential replaced (also when a connector echoes request headers, also across stream chunks).
One metadata row is logged per call: connector, method, tool name, status, latency and byte counts, never a body or a header.
"""
from collections import deque
from dataclasses import dataclass
import json
import re
from threading import Lock
import time
from typing import Iterator
from uuid import uuid4

from forge.connector_cipher import Binding, ConnectorCipherError
from forge.connector_model import (BrokerError, BrokerDisabled, BrokerInvalid, BrokerNotConfigured, BrokerRateLimited, BrokerReauth, BrokerTooLarge,
                                   BrokerUpstream, ConnectorContext)
from forge.connector_oauth import credential_binding
from forge.egress_guard import EgressDenied
from forge.invitations import capability_digest

REQUEST_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 8 * 1024 * 1024
DEADLINE_SECONDS = 30.0
RATE_PER_MINUTE = 60
ALLOWED_EXACT = frozenset({'initialize', 'ping', 'notifications/initialized', 'notifications/cancelled'})
ALLOWED_PREFIXES = ('tools/', 'resources/', 'prompts/')
FORWARD_REQUEST = ('content-type', 'accept', 'mcp-session-id', 'mcp-protocol-version', 'last-event-id')
RELAY_RESPONSE = ('content-type', 'mcp-session-id', 'mcp-protocol-version')
_METHOD = re.compile(r'[a-z][a-z/_]{0,63}')
_TOOL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
REDACTION = b'[redacted]'


class BrokerMethodBlocked(BrokerError):
    """The JSON-RPC method is not on the allow-list (server-to-client requests such as sampling are never relayed)."""


class Redactor:
    """Replaces every occurrence of the given secrets (raw and JSON-escaped) in a byte stream, even across chunk boundaries."""

    def __init__(self, secrets):
        patterns = set()
        for secret in secrets:
            if secret:
                patterns.add(secret.encode('utf-8'))
                patterns.add(json.dumps(secret)[1:-1].encode('utf-8'))
        self._patterns = sorted(patterns, key=len, reverse=True)
        self._hold = max((len(pattern) for pattern in patterns), default=1) - 1
        self._tail = b''

    def _scrub(self, data):
        for pattern in self._patterns:
            data = data.replace(pattern, REDACTION)
        return data

    def feed(self, chunk):
        data = self._tail + chunk
        cut = max(0, len(data) - self._hold)
        moved = True
        while moved:  # never emit up to a point that lies inside a match: it may still be completed by the next chunk
            moved = False
            for pattern in self._patterns:
                position = data.find(pattern)
                while position != -1:
                    if position < cut < position + len(pattern):
                        cut, moved = position, True
                    position = data.find(pattern, position + 1)
        head, self._tail = data[:cut], data[cut:]
        return self._scrub(head)

    def flush(self):
        data, self._tail = self._scrub(self._tail), b''
        return data


@dataclass
class McpResponse:
    status: int
    headers: dict
    body: Iterator[bytes]


class RateLimiter:
    def __init__(self, per_minute, clock=time.monotonic):
        self._limit, self._clock, self._seen, self._lock = per_minute, clock, {}, Lock()

    def check(self, key):
        now = self._clock()
        with self._lock:
            window = self._seen.setdefault(key, deque())
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self._limit:
                raise BrokerRateLimited()
            window.append(now)


def parse_request(body):
    """The JSON-RPC method and the tool name (for ``tools/call``) of an allow-listed single request, else a typed error."""
    if type(body) is not bytes or len(body) > REQUEST_LIMIT:
        raise BrokerTooLarge()
    try:
        message = json.loads(body)
    except ValueError:
        raise BrokerInvalid() from None
    if type(message) is not dict or message.get('jsonrpc') != '2.0' or type(message.get('method')) is not str:
        raise BrokerInvalid()  # batches and non-requests are not relayed
    method = message['method']
    if not _METHOD.fullmatch(method) or not (method in ALLOWED_EXACT or method.startswith(ALLOWED_PREFIXES)):
        raise BrokerMethodBlocked()
    tool = None
    params = message.get('params')
    if method == 'tools/call' and type(params) is dict and type(params.get('name')) is str and _TOOL.fullmatch(params['name']):
        tool = params['name']
    return method, tool


class McpBroker:
    def __init__(self, store, oauth, cipher, client, *, clock=time.time, rate_per_minute=RATE_PER_MINUTE, response_limit=RESPONSE_LIMIT,
                 deadline=DEADLINE_SECONDS):
        self._store, self._oauth, self._cipher, self._client = store, oauth, cipher, client
        self._response_limit, self._deadline, self._clock = response_limit, deadline, clock
        self._limiter = RateLimiter(rate_per_minute)

    def _credential(self, token, org, connector_id, context: ConnectorContext):
        """(header name, header value, secret to scrub) for this call."""
        auth = context.attributes.get('auth')
        if auth == 'oauth':
            access = self._oauth.access_token(token, org, connector_id, context)
            return 'Authorization', 'Bearer ' + access, [access]
        if auth == 'api_key':
            if context.credential_kind != 'api_key' or context.credential_sealed is None:
                raise BrokerNotConfigured()
            try:
                key = self._cipher.open(credential_binding(context.credential_scope, org, connector_id, context.credential_revision), context.credential_sealed)['api_key']
            except (ConnectorCipherError, KeyError):
                raise BrokerNotConfigured() from None
            name = context.attributes.get('auth_header', 'Authorization')
            scheme = context.attributes.get('auth_scheme', 'Bearer' if name.lower() == 'authorization' else '')
            return name, ('%s %s' % (scheme, key)).strip(), [key]
        raise BrokerNotConfigured()

    def call(self, token, org, connector_id, body: bytes, client_headers: dict) -> McpResponse:
        method, tool = parse_request(body)
        digest = capability_digest(token)
        context = self._store.context(digest, org, connector_id)  # session, active membership and the layers, fresh on every call
        started = time.monotonic()
        event = uuid4()

        def log(outcome, status=None, received=None):
            try:
                self._store.log_call(org, context.membership_id, event, connector_id, outcome, int((time.monotonic() - started) * 1000), method, tool,
                                     len(body), received, status)
            except Exception:
                pass  # metadata is best effort; it never decides the call

        try:
            if context.state != 'on':
                raise BrokerDisabled()
            if (context.credential_locus != 'server' or context.attributes.get('transport') != 'mcp_http'
                    or type(context.attributes.get('mcp_url')) is not str):
                raise BrokerNotConfigured()
            self._limiter.check((org, context.membership_id))
            name, value, secrets = self._credential(token, org, connector_id, context)
            headers = {key: value for key, value in ((k.lower(), v) for k, v in client_headers.items()) if key in FORWARD_REQUEST}
            headers[name] = value  # injected last: whatever the client sent under that name is gone
            try:
                upstream = self._client.request('POST', context.attributes['mcp_url'], context.attributes.get('egress_hosts', []), headers=headers, content=body,
                                                 timeout=self._deadline)
            except EgressDenied:
                raise BrokerUpstream() from None
        except BrokerError as error:
            log('denied' if not isinstance(error, BrokerUpstream) else 'error')
            raise
        if upstream.status in (401, 403) and context.attributes.get('auth') == 'oauth':
            upstream.close()
            self._flag(digest, org, connector_id, context)
            log('denied', upstream.status, 0)
            raise BrokerReauth()
        redactor = Redactor(secrets)
        relayed = {key: value for key, value in ((k.lower(), v) for k, v in upstream.headers.items()) if key in RELAY_RESPONSE}
        streaming = 'text/event-stream' in upstream.headers.get('content-type', '')

        def stream():
            total = 0
            outcome = 'ok' if upstream.status < 400 else 'error'
            try:
                limit_at = started + self._deadline  # the whole call, not just the body
                for chunk in upstream.iter_bytes(self._response_limit, deadline=limit_at):
                    out = redactor.feed(chunk)
                    total += len(out)
                    if out:
                        yield out
                out = redactor.flush()
                total += len(out)
                if out:
                    yield out
            except EgressDenied as error:
                outcome = 'timeout' if str(error) == 'timeout' else 'error'
                if str(error) == 'too_large':
                    raise BrokerTooLarge() from None
                raise BrokerUpstream() from None
            except GeneratorExit:
                outcome = 'cancelled'
                raise
            finally:
                upstream.close()
                log(outcome, upstream.status, total)

        if streaming:
            return McpResponse(upstream.status, relayed, stream())
        payload = b''.join(stream())  # a bounded, scrubbed body
        return McpResponse(upstream.status, relayed, iter((payload,)))

    def _flag(self, digest, org, connector_id, context):
        try:
            self._store.grant_update(digest, org, connector_id, context.grant_revision, None, None, 'reauth_required')
        except Exception:
            pass
