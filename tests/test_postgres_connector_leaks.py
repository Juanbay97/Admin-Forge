"""Owned PostgreSQL + loopback fixtures: the leak scan. After a full connect, call, failure and revoke run, no secret appears in any response,
header, log record or database row (the sealed columns hold ciphertext only)."""
import json
import logging
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from fixtures.fake_oauth_provider import PROVIDER_CLIENT_ID, PROVIDER_CLIENT_SECRET
from test_postgres_capability_http import PLATFORM, owner
from test_postgres_connector_http import CALLBACK, ENTRY, Harness, rpc
from test_postgres_connector_oauth import CONNECTOR, attributes
from test_postgres_mvp_local import login, stack

API_KEY_CONNECTOR = 'connector:apikey'
API_KEY = 'sk-live-LEAKSCAN-0123456789abcdef'
API_ENTRY = {**ENTRY, 'attributes': {'name': 'Keyed', 'transport': 'mcp_http', 'auth': 'api_key', 'mcp_url': 'http://mcp.fixture.test/mcp', 'egress_hosts': ['mcp.fixture.test'],
                                     'auth_header': 'x-api-key', 'auth_scheme': ''}}


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))
        if record.exc_info:
            self.lines.append(logging.Formatter().formatException(record.exc_info))


class PostgresConnectorLeakTests(unittest.TestCase):
    def test_no_secret_appears_in_any_response_log_or_row(self):
        harness = Harness(self)
        capture = Capture()
        root = logging.getLogger()
        previous = root.level
        root.addHandler(capture)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(capture), root.setLevel(previous)))
        seen = []
        with stack(connector_fixtures=harness.hosts) as (db, client, results, workdir, secrets):
            def call(method, path, **keywords):
                response = client.request(method, path, **keywords)
                seen.append(response.status_code.__str__() + ' ' + str(dict(response.headers)) + ' ' + response.text)
                return response
            boss = owner(db, client)
            admin, member = login(client, results[0].accounts[0]), login(client, results[0].accounts[1])
            codes, states = [], []
            call('PUT', PLATFORM + '/capabilities/' + CONNECTOR, headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
            call('PUT', PLATFORM + '/capabilities/' + API_KEY_CONNECTOR, headers=boss, json={'expected_revision': 0, 'entry': API_ENTRY})
            call('PUT', '/forge/v1/connectors/%s/credential' % CONNECTOR, headers=admin,
                 json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': PROVIDER_CLIENT_ID, 'client_secret': PROVIDER_CLIENT_SECRET})
            call('PUT', '/forge/v1/connectors/%s/credential' % API_KEY_CONNECTOR, headers=admin, json={'expected_revision': 0, 'kind': 'api_key', 'api_key': API_KEY})
            harness.fixtures.mcp.api_key_header, harness.fixtures.mcp.api_keys = 'x-api-key', {API_KEY}
            call('GET', '/forge/v1/connectors', headers=member)
            call('GET', '/forge/v1/connectors/credentials', headers=admin)
            start = call('POST', '/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=member)
            _, query = harness.consent(start.json()['authorize_url'])
            codes.append(query['code'])
            states.append(query['state'])
            call('GET', CALLBACK, params={'code': query['code'], 'state': query['state']})
            call('GET', CALLBACK, params={'code': query['code'], 'state': query['state']})  # replay
            call('GET', CALLBACK, params={'code': 'bogus', 'state': 'x' * 43})
            call('GET', CALLBACK, params={'error': 'access_denied', 'state': 'y' * 43})
            json_headers = {**member, 'content-type': 'application/json'}
            for name, extra in (('echo', {'arguments': {'text': 'hello'}}), ('headers', {}), ('cookie', {}), ('redirect', {}), ('big', {'arguments': {'size': 100}})):
                for connector in (CONNECTOR, API_KEY_CONNECTOR):
                    call('POST', '/forge/v1/mcp/' + connector, headers=json_headers, content=rpc('tools/call', name=name, **extra))
            call('POST', '/forge/v1/mcp/' + CONNECTOR, headers=json_headers, content=rpc('sampling/createMessage'))
            call('POST', '/forge/v1/mcp/' + CONNECTOR, headers=json_headers, content='{not json')
            call('POST', '/forge/v1/mcp/connector:ghost', headers=json_headers, content=rpc('ping'))
            call('POST', '/forge/v1/mcp/' + CONNECTOR, headers={**member, 'content-type': 'text/plain'}, content=rpc('ping'))
            call('POST', '/forge/v1/mcp/' + CONNECTOR, content=rpc('ping'))
            harness.fixtures.mcp.stop()  # an unreachable upstream: its error must be generic
            call('POST', '/forge/v1/mcp/' + CONNECTOR, headers=json_headers, content=rpc('ping'))
            call('PUT', PLATFORM + '/companies/%s/capabilities/%s' % (results[0].organization_id, CONNECTOR), headers=boss, json={'state': None, 'lock': 'forced_off'})
            call('POST', '/forge/v1/mcp/' + CONNECTOR, headers=json_headers, content=rpc('ping'))
            call('DELETE', '/forge/v1/connectors/%s/grant' % CONNECTOR, headers=member)
            call('DELETE', '/forge/v1/connectors/%s/credential' % CONNECTOR, headers=admin, params={'expected_revision': 1})
            call('GET', '/forge/v1/orgs/%s/capability-audit' % results[0].organization_id, headers=admin)
            provider = harness.fixtures.oauth
            tokens = {value for value in (*provider.issued, *[request.get('refresh_token') for request in provider.token_requests],
                                         *[request.get('code_verifier') for request in provider.token_requests],
                                         *[request.get('code') for request in provider.token_requests]) if value}
            secrets_found = {PROVIDER_CLIENT_SECRET, API_KEY, *tokens, *codes, *states}
            self.assertGreaterEqual(len(tokens), 3, 'the scan only means something if real tokens, codes and verifiers existed')
            tables = [row[0] for row in db.admin.execute("SELECT tablename FROM pg_tables WHERE schemaname='forge' ORDER BY 1")]
            dump = '\n'.join(str(row[0]) for table in tables for row in db.admin.execute('SELECT row_to_json(t)::text FROM forge.%s t' % table))
            for label, haystack in (('responses', '\n'.join(seen)), ('logs', '\n'.join(capture.lines)), ('database', dump)):
                # The member's own OAuth state is, by design, part of the authorize URL the start route returns to them.
                for secret in secrets_found - (set(states) if label == 'responses' else set()):
                    self.assertNotIn(secret, haystack, '%s contain a secret (%s...)' % (label, secret[:6]))
            self.assertIn('connector_grants', tables)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.tool_invocation_log WHERE source=%s', ('broker',)).fetchone()[0] > 0, True)


if __name__ == '__main__':
    unittest.main()
