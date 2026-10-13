"""Connector routes over fakes: hidden from the contract, authenticated, bounded, finite errors and a callback page that never echoes anything."""
import json
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.connector_api import mount_connectors, mount_platform_connectors
from forge.connector_model import (BrokerConflict, BrokerDenied, BrokerDisabled, BrokerInvalid, BrokerNotConfigured, BrokerRateLimited, BrokerReauth,
                                    BrokerTooLarge, BrokerUpstream, CredentialInfo, CredentialStatus)
from forge.connector_service import MemberConnector
from forge.foundation import AuthenticatedIdentity
from forge.mcp_broker import BrokerMethodBlocked, McpResponse
from forge.platform_api import mount_platform

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
CONNECTOR = 'connector:github'
STATE = secrets.token_urlsafe(32)


class Ready:
    def __init__(self, ok=True):
        self.ok = ok

    def check(self):
        return self.ok


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class Fake:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _do(self, name, result, *args):
        self.calls.append((name, args))
        if self.fail:
            raise self.fail
        return result

    # service
    def status(self, token, org): return self._do('status', [MemberConnector(CONNECTOR, 'GitHub', 'dev-tools', 'mcp_http', 'oauth', 'on', 'not_connected', True)], token, org)
    def credential_status(self, token, org): return self._do('credential_status', [CredentialStatus(CONNECTOR, 'oauth_client', 2, 'cret', None)], token, org)
    def credential_set(self, token, org, identifier, kind, fields, expected): return self._do('credential_set', CredentialInfo(expected + 1, 'cret', kind), token, org, identifier, kind, fields, expected)
    def credential_clear(self, token, org, identifier, expected): return self._do('credential_clear', True, token, org, identifier, expected)
    def platform_credential_set(self, token, identifier, kind, fields, expected): return self._do('platform_credential_set', CredentialInfo(expected + 1, None, kind), token, identifier, kind, fields, expected)
    # oauth
    def start(self, token, org, identifier): return self._do('start', 'https://provider.example/authorize?state=x', token, org, identifier)
    def disconnect(self, token, org, identifier): return self._do('disconnect', True, token, org, identifier)
    def complete(self, state, code): return self._do('complete', CONNECTOR, state, code)
    def abort(self, state): return self._do('abort', None, state)
    # broker
    def call(self, token, org, identifier, body, headers):
        self.calls.append(('call', (org, identifier, body, headers.get('authorization'))))
        if self.fail:
            raise self.fail
        return McpResponse(200, {'content-type': 'application/json', 'mcp-session-id': 's1'}, iter([b'{"jsonrpc":"2.0",', b'"id":1,"result":{}}']))


def client(fake=None, *, service=True, ready=True):
    fake = fake or Fake()
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), connectors=fake if service else None)
    mount_connectors(app, service=fake if service else None, oauth=fake, broker=fake, sessions=Sessions(), readiness=Ready(ready), organizations=lambda token: [ORG])
    return TestClient(app, raise_server_exceptions=False), app, fake


class HiddenTests(unittest.TestCase):
    def test_every_route_is_hidden_so_the_contract_pin_is_unchanged(self):
        _, app, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)), contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        paths = {route.path for route in app.routes}
        for expected in ('/forge/v1/connectors', '/forge/v1/connectors/credentials', '/forge/v1/connectors/{identifier}/credential', '/forge/v1/connectors/{identifier}/oauth/start',
                         '/forge/v1/connectors/{identifier}/grant', '/forge/v1/connectors/oauth/callback', '/forge/v1/mcp/{identifier}', '/forge/v1/platform/connectors/{identifier}/credential'):
            self.assertIn(expected, paths)
        self.assertEqual([route['path'] for route in contract.build(app)['routes'] if 'connectors' in route['path'] or '/mcp/' in route['path']], [])


class AuthenticationTests(unittest.TestCase):
    def test_every_authenticated_route_is_401_without_a_session_and_calls_nothing(self):
        http, _, fake = client()
        for method, path in (('get', '/forge/v1/connectors'), ('get', '/forge/v1/connectors/credentials'), ('put', '/forge/v1/connectors/connector:github/credential'),
                             ('post', '/forge/v1/connectors/connector:github/oauth/start'), ('delete', '/forge/v1/connectors/connector:github/grant'), ('post', '/forge/v1/mcp/connector:github')):
            for headers in ({}, {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}):
                with self.subTest(path=path, headers=bool(headers)):
                    self.assertEqual(getattr(http, method)(path, headers=headers).status_code, 401)
        self.assertEqual(fake.calls, [])

    def test_without_a_connector_key_every_route_is_503(self):
        http, _, _ = client(service=False)
        for method, path in (('get', '/forge/v1/connectors'), ('post', '/forge/v1/connectors/connector:github/oauth/start'), ('post', '/forge/v1/mcp/connector:github')):
            self.assertEqual(getattr(http, method)(path, headers=HEADERS).status_code, 503, path)
        self.assertEqual(http.get('/forge/v1/connectors/oauth/callback?state=%s&code=c' % STATE).status_code, 503)


class MemberRouteTests(unittest.TestCase):
    def test_status_lists_connectors_without_secrets_and_is_not_cacheable(self):
        http, _, fake = client()
        response = http.get('/forge/v1/connectors', headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json(), {'connectors': [{'id': CONNECTOR, 'name': 'GitHub', 'category': 'dev-tools', 'transport': 'mcp_http', 'auth': 'oauth',
                                                           'state': 'on', 'status': 'not_connected', 'configured': True}]})
        self.assertEqual(fake.calls[0], ('status', (TOKEN, ORG)))

    def test_start_returns_the_authorize_url_and_disconnect_reports_the_result(self):
        http, _, fake = client()
        self.assertEqual(http.post('/forge/v1/connectors/connector:github/oauth/start', headers=HEADERS).json(), {'authorize_url': 'https://provider.example/authorize?state=x'})
        self.assertEqual(http.delete('/forge/v1/connectors/connector:github/grant', headers=HEADERS).json(), {'disconnected': True})
        self.assertEqual([call[0] for call in fake.calls], ['start', 'disconnect'])
        self.assertEqual(http.get('/forge/v1/connectors?x=1', headers=HEADERS).status_code, 422)

    def test_failures_are_finite_codes_without_detail(self):
        cases = ((BrokerDenied(), 404, 'NOT_FOUND'), (BrokerInvalid(), 422, 'INVALID_REQUEST'), (BrokerDisabled(), 403, 'CONNECTOR_DISABLED'), (BrokerNotConfigured(), 409, 'NOT_CONFIGURED'),
                 (BrokerReauth(), 409, 'REAUTH_REQUIRED'), (BrokerConflict(), 409, 'REVISION_CONFLICT'), (BrokerMethodBlocked(), 403, 'METHOD_NOT_ALLOWED'),
                 (BrokerTooLarge(), 413, 'PAYLOAD_TOO_LARGE'), (BrokerRateLimited(), 429, 'RATE_LIMITED'), (BrokerUpstream(), 502, 'UPSTREAM_ERROR'),
                 (RuntimeError('secret internal detail'), 503, 'SERVICE_UNAVAILABLE'))
        for failure, status, code in cases:
            with self.subTest(code=code):
                http, _, _ = client(Fake(failure))
                response = http.get('/forge/v1/connectors', headers=HEADERS)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
                self.assertNotIn('secret internal detail', response.text)
        http, _, _ = client(Fake(BrokerRateLimited()))
        self.assertEqual(http.get('/forge/v1/connectors', headers=HEADERS).headers['retry-after'], '60')


class CredentialRouteTests(unittest.TestCase):
    def test_a_credential_is_written_once_and_the_response_is_status_only(self):
        http, _, fake = client()
        written = http.put('/forge/v1/connectors/connector:github/credential', headers=HEADERS,
                           json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': 'cid', 'client_secret': 'SUPER-SECRET-VALUE'})
        self.assertEqual((written.status_code, written.json()), (200, {'revision': 1, 'hint': 'cret', 'kind': 'oauth_client'}))
        self.assertNotIn('SUPER-SECRET', written.text)
        self.assertEqual(fake.calls[-1], ('credential_set', (TOKEN, ORG, 'connector:github', 'oauth_client', {'client_id': 'cid', 'client_secret': 'SUPER-SECRET-VALUE'}, 0)))
        listing = http.get('/forge/v1/connectors/credentials', headers=HEADERS)
        self.assertEqual(listing.json(), {'credentials': [{'id': CONNECTOR, 'kind': 'oauth_client', 'revision': 2, 'hint': 'cret', 'platform_default': False}]})
        self.assertEqual(http.delete('/forge/v1/connectors/connector:github/credential?expected_revision=2', headers=HEADERS).json(), {'cleared': True})

    def test_malformed_credential_bodies_are_refused_before_the_service(self):
        http, _, fake = client()
        for body in ({}, {'kind': 'api_key', 'api_key': 'k'}, {'expected_revision': '0', 'kind': 'api_key', 'api_key': 'k'}, {'expected_revision': 0, 'kind': 5},
                     {'expected_revision': 0, 'kind': 'api_key', 'api_key': 'k', 'extra': 1}, []):
            with self.subTest(body=str(body)[:40]):
                self.assertEqual(http.put('/forge/v1/connectors/connector:github/credential', headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(http.delete('/forge/v1/connectors/connector:github/credential?expected_revision=abc', headers=HEADERS).status_code, 422)
        self.assertEqual(http.delete('/forge/v1/connectors/connector:github/credential', headers=HEADERS).status_code, 422)
        self.assertEqual(http.put('/forge/v1/connectors/connector:github/credential', headers={**HEADERS, 'content-type': 'application/json'}, content=b'{"x":"' + b'a' * 9000 + b'"}').status_code, 413)
        self.assertEqual(fake.calls, [])

    def test_the_platform_default_route_is_a_platform_route(self):
        http, _, fake = client()
        response = http.put('/forge/v1/platform/connectors/connector:github/credential', headers=HEADERS,
                            json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': 'cid', 'client_secret': 'PLATFORM-SECRET-VALUE'})
        self.assertEqual((response.status_code, response.json()), (200, {'revision': 1, 'hint': None, 'kind': 'oauth_client'}))
        self.assertNotIn('PLATFORM-SECRET', response.text)


class CallbackTests(unittest.TestCase):
    def test_a_valid_callback_completes_once_and_renders_a_fixed_page_with_no_echo(self):
        http, _, fake = client()
        response = http.get('/forge/v1/connectors/oauth/callback?code=the-code&state=%s' % STATE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.calls, [('complete', (STATE, 'the-code'))])
        for header, value in (('cache-control', 'no-store'), ('referrer-policy', 'no-referrer')):
            self.assertEqual(response.headers[header], value)
        self.assertIn("default-src 'none'", response.headers['content-security-policy'])
        self.assertNotIn(STATE, response.text)
        self.assertNotIn('the-code', response.text)

    def test_a_provider_error_burns_the_state_and_never_completes(self):
        http, _, fake = client()
        response = http.get('/forge/v1/connectors/oauth/callback?error=access_denied&state=%s&error_description=%%3Cscript%%3E' % STATE)
        self.assertEqual(response.status_code, 400)
        self.assertEqual([call[0] for call in fake.calls], ['abort'])
        self.assertNotIn('script', response.text)

    def test_malformed_duplicate_and_unknown_parameters_are_refused_without_a_call(self):
        http, _, fake = client()
        for query in ('', 'code=c', 'state=short&code=c', 'state=%s&code=c&code=d' % STATE, 'state=%s&code=c&extra=1' % STATE,
                      'state=%s&code=%s' % (STATE, 'x' * 3000)):
            with self.subTest(query=query[:40]):
                self.assertEqual(http.get('/forge/v1/connectors/oauth/callback?' + query).status_code, 400)
        self.assertEqual(fake.calls, [])

    def test_every_broker_refusal_is_the_same_generic_page(self):
        pages = set()
        for failure in (BrokerDenied(), BrokerUpstream(), BrokerDisabled(), BrokerNotConfigured()):
            http, _, _ = client(Fake(failure))
            response = http.get('/forge/v1/connectors/oauth/callback?code=c&state=%s' % STATE)
            self.assertEqual(response.status_code, 400)
            pages.add(response.text)
        self.assertEqual(len(pages), 1)
        http, _, _ = client(ready=False)
        self.assertEqual(http.get('/forge/v1/connectors/oauth/callback?code=c&state=%s' % STATE).status_code, 503)


class ProxyRouteTests(unittest.TestCase):
    BODY = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'

    def test_the_proxy_streams_the_scrubbed_response_with_the_relayed_headers(self):
        http, _, fake = client()
        response = http.post('/forge/v1/mcp/connector:github', headers={**HEADERS, 'content-type': 'application/json'}, content=self.BODY)
        self.assertEqual((response.status_code, response.headers['content-type'], response.headers['mcp-session-id'], response.headers['cache-control']),
                         (200, 'application/json', 's1', 'no-store'))
        self.assertEqual(response.content, b'{"jsonrpc":"2.0","id":1,"result":{}}')
        org, identifier, body, authorization = fake.calls[-1][1]
        self.assertEqual((org, identifier, body, authorization), (ORG, 'connector:github', self.BODY, 'Bearer ' + TOKEN))

    def test_media_type_and_size_are_checked_before_the_broker(self):
        http, _, fake = client()
        self.assertEqual(http.post('/forge/v1/mcp/connector:github', headers={**HEADERS, 'content-type': 'text/plain'}, content=self.BODY).status_code, 415)
        self.assertEqual(http.post('/forge/v1/mcp/connector:github', headers={**HEADERS, 'content-type': 'application/json'}, content=b'x' * (1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(fake.calls, [])

    def test_broker_refusals_map_to_finite_codes(self):
        for failure, status, code in ((BrokerMethodBlocked(), 403, 'METHOD_NOT_ALLOWED'), (BrokerReauth(), 409, 'REAUTH_REQUIRED'), (BrokerDisabled(), 403, 'CONNECTOR_DISABLED'),
                                      (BrokerDenied(), 404, 'NOT_FOUND')):
            http, _, _ = client(Fake(failure))
            response = http.post('/forge/v1/mcp/connector:github', headers={**HEADERS, 'content-type': 'application/json'}, content=self.BODY)
            self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))


if __name__ == '__main__':
    unittest.main()
