"""Loopback fixtures for the connector broker: a fake OAuth 2.0 provider (authorization code + PKCE, rotating refresh tokens, revocation)
and a fake MCP server (JSON-RPC over HTTP, with tools that echo request headers, set cookies, stream and stall).

Only for tests and the local/dev compose overlay; nothing here is imported by the production composition. Standard library only
(``http.server``), one thread per request. ``python -m forge.fake_connectors serve`` runs both for the deploy smoke.
"""
import argparse
import base64
from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import sys
from threading import Event, Lock, Thread
import time
from urllib.parse import parse_qs, urlencode, urlsplit

PROVIDER_CLIENT_ID = 'fixture-client'
PROVIDER_CLIENT_SECRET = 'fixture-client-secret-0001'


def _pkce(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


class _Server:
    """A ThreadingHTTPServer on a daemon thread; ``handler_class`` closes over the owner."""

    def __init__(self, handler_class, host, port):
        self._httpd = ThreadingHTTPServer((host, port), handler_class)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()


class FakeOAuthProvider:
    def __init__(self, *, client_id=PROVIDER_CLIENT_ID, client_secret=PROVIDER_CLIENT_SECRET, access_ttl=3600, refresh_delay=0.0,
                 host='127.0.0.1', port=0):
        self.client_id, self.client_secret, self.access_ttl, self.refresh_delay = client_id, client_secret, access_ttl, refresh_delay
        self.deny_consent = self.fail_refresh = self.fail_exchange = False
        self.codes, self.refresh_tokens, self.issued, self.revoked = {}, {}, set(), []
        self.exchanges = self.refreshes = 0
        self.token_requests = []
        self._lock = Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, body=b'', *, content_type='application/json', headers=()):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                for name, value in headers:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parts = urlsplit(self.path)
                if parts.path != '/authorize':
                    return self._reply(404)
                query = {key: values[0] for key, values in parse_qs(parts.query).items()}
                owner._authorize(self, query)

            def do_POST(self):
                parts = urlsplit(self.path)
                length = int(self.headers.get('Content-Length') or 0)
                form = {key: values[0] for key, values in parse_qs(self.rfile.read(length).decode()).items()}
                if parts.path == '/token':
                    owner._token(self, form)
                elif parts.path == '/revoke':
                    owner.revoked.append(form.get('token'))
                    self._reply(200, b'{}')
                else:
                    self._reply(404)
        self._server = _Server(Handler, host, port)

    @property
    def port(self):
        return self._server.port

    def start(self):
        self._server.start()
        return self

    def stop(self):
        self._server.stop()

    def _authorize(self, handler, query):
        if (query.get('response_type') != 'code' or query.get('client_id') != self.client_id or query.get('code_challenge_method') != 'S256'
                or not query.get('code_challenge') or not query.get('redirect_uri') or not query.get('state')):
            return handler._reply(400, b'bad authorization request', content_type='text/plain')
        if self.deny_consent:
            target = query['redirect_uri'] + '?' + urlencode({'error': 'access_denied', 'state': query['state']})
        else:
            code = secrets.token_urlsafe(24)
            with self._lock:
                self.codes[code] = {'challenge': query['code_challenge'], 'redirect_uri': query['redirect_uri'], 'scope': query.get('scope', '')}
            target = query['redirect_uri'] + '?' + urlencode({'code': code, 'state': query['state']})
        handler._reply(302, headers=[('Location', target)])

    def _client_ok(self, handler, form):
        if form.get('client_id') == self.client_id and form.get('client_secret') == self.client_secret:
            return True
        header = handler.headers.get('Authorization', '')
        if header.startswith('Basic '):
            return base64.b64decode(header[6:]).decode() == '%s:%s' % (self.client_id, self.client_secret)
        return False

    def _issue(self, scope):
        access, refresh = 'at-' + secrets.token_urlsafe(24), 'rt-' + secrets.token_urlsafe(24)
        with self._lock:
            self.issued.add(access)
            self.refresh_tokens[refresh] = scope
        return {'access_token': access, 'token_type': 'Bearer', 'expires_in': self.access_ttl, 'refresh_token': refresh, 'scope': scope}

    def _token(self, handler, form):
        self.token_requests.append(dict(form))
        if not self._client_ok(handler, form):
            return handler._reply(401, b'{"error":"invalid_client"}')
        grant = form.get('grant_type')
        if grant == 'authorization_code':
            with self._lock:
                self.exchanges += 1
                record = self.codes.pop(form.get('code'), None)
            if (self.fail_exchange or record is None or record['redirect_uri'] != form.get('redirect_uri')
                    or _pkce(form.get('code_verifier', '')) != record['challenge']):
                return handler._reply(400, b'{"error":"invalid_grant"}')
            return handler._reply(200, json.dumps(self._issue(record['scope'])).encode())
        if grant == 'refresh_token':
            with self._lock:
                self.refreshes += 1
            if self.refresh_delay:
                time.sleep(self.refresh_delay)
            with self._lock:
                scope = None if self.fail_refresh else self.refresh_tokens.pop(form.get('refresh_token'), None)
            if scope is None:
                return handler._reply(400, b'{"error":"invalid_grant"}')
            return handler._reply(200, json.dumps(self._issue(scope)).encode())
        handler._reply(400, b'{"error":"unsupported_grant_type"}')


@dataclass
class Seen:
    headers: dict
    body: bytes
    path: str


@dataclass
class FakeMcpServer:
    """A fake MCP endpoint at ``/mcp``. ``accept(token)`` authorizes a Bearer token; ``api_keys`` authorizes a raw header value."""
    host: str = '127.0.0.1'
    port: int = 0
    valid_tokens: set = field(default_factory=set)
    api_key_header: str | None = None
    api_keys: set = field(default_factory=set)
    requests: list = field(default_factory=list)

    def __post_init__(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body=b'', *, content_type='application/json', headers=()):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                for name, value in headers:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length)
                headers = {name.lower(): value for name, value in self.headers.items()}
                owner.requests.append(Seen(headers, body, self.path))
                if self.path != '/mcp':
                    return self._send(404)
                if not owner._authorized(headers):
                    return self._send(401, b'{"error":"unauthorized"}', headers=[('WWW-Authenticate', 'Bearer realm="fixture"')])
                try:
                    message = json.loads(body)
                    method, identifier, params = message['method'], message.get('id'), message.get('params') or {}
                except Exception:
                    return self._send(400, b'{"error":"bad request"}')
                owner._dispatch(self, method, identifier, params, headers)

            def do_GET(self):
                self._send(405)
        self._server = _Server(Handler, self.host, self.port)

    @property
    def bound_port(self):
        return self._server.port

    def start(self):
        self._server.start()
        return self

    def stop(self):
        self._server.stop()

    def accept(self, token):
        self.valid_tokens.add(token)

    def _authorized(self, headers):
        header = headers.get('authorization', '')
        if header.startswith('Bearer ') and header[7:] in self.valid_tokens:
            return True
        return self.api_key_header is not None and headers.get(self.api_key_header.lower()) in self.api_keys

    def _dispatch(self, handler, method, identifier, params, headers):
        def result(value, extra=()):
            body = json.dumps({'jsonrpc': '2.0', 'id': identifier, 'result': value}).encode()
            handler._send(200, body, headers=list(extra))
        if method == 'initialize':
            return result({'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'fixture', 'version': '1'}},
                          [('Mcp-Session-Id', 'fixture-session')])
        if method.startswith('notifications/'):
            return handler._send(202)
        if method == 'ping':
            return result({})
        if method == 'tools/list':
            return result({'tools': [{'name': name, 'inputSchema': {'type': 'object'}} for name in ('echo', 'headers', 'cookie', 'big', 'slow', 'stream', 'redirect')]})
        if method == 'tools/call':
            name, arguments = params.get('name'), params.get('arguments') or {}
            if name == 'echo':
                return result({'content': [{'type': 'text', 'text': str(arguments.get('text', ''))}]})
            if name == 'headers':
                return result({'content': [{'type': 'text', 'text': json.dumps(headers)}]})
            if name == 'cookie':
                return result({'content': [{'type': 'text', 'text': 'cookie set'}]}, [('Set-Cookie', 'sid=upstream-session-secret'), ('X-Upstream-Auth', 'Bearer upstream-secret')])
            if name == 'big':
                return result({'content': [{'type': 'text', 'text': 'x' * int(arguments.get('size', 1000))}]})
            if name == 'slow':
                time.sleep(float(arguments.get('seconds', 1)))
                return result({'content': [{'type': 'text', 'text': 'late'}]})
            if name == 'redirect':
                return handler._send(302, headers=[('Location', 'https://evil.example.test/')])
            if name == 'stream' and 'text/event-stream' in headers.get('accept', ''):
                events = ''.join('event: message\ndata: %s\n\n' % json.dumps({'jsonrpc': '2.0', 'id': identifier, 'result': {'part': index}}) for index in range(3))
                return handler._send(200, events.encode(), content_type='text/event-stream')
            return result({'content': [{'type': 'text', 'text': 'unknown tool'}], 'isError': True})
        handler._send(200, json.dumps({'jsonrpc': '2.0', 'id': identifier, 'error': {'code': -32601, 'message': 'Method not found'}}).encode())


class FakeConnectors:
    """The pair the smoke runs: an MCP server that accepts exactly the access tokens its OAuth provider issued."""

    def __init__(self, *, host='127.0.0.1', oauth_port=0, mcp_port=0, **oauth_options):
        self.oauth = FakeOAuthProvider(host=host, port=oauth_port, **oauth_options)
        self.mcp = FakeMcpServer(host=host, port=mcp_port, valid_tokens=self.oauth.issued)

    def start(self):
        self.oauth.start()
        self.mcp.start()
        return self

    def stop(self):
        self.oauth.stop()
        self.mcp.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge.fake_connectors', description='Fake OAuth provider and MCP server; tests and dev overlay only.')
    commands = parser.add_subparsers(dest='command', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--bind', default='127.0.0.1')
    serve.add_argument('--oauth-port', type=int, required=True)
    serve.add_argument('--mcp-port', type=int, required=True)
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    fixtures = FakeConnectors(host=arguments.bind, oauth_port=arguments.oauth_port, mcp_port=arguments.mcp_port).start()
    print(json.dumps({'status': 'ready', 'oauth_port': fixtures.oauth.port, 'mcp_port': fixtures.mcp.bound_port}), flush=True)
    try:
        Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        fixtures.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
