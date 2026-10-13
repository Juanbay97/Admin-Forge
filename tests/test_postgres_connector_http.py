"""Owned PostgreSQL + loopback fixtures: the connector broker through the real composed control plane (connect, call, revoke, isolation)."""
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
import httpx
from forge import contract
from forge.egress_guard import Fixture
from fixtures.fake_mcp_server import FakeConnectors
from fixtures.fake_oauth_provider import PROVIDER_CLIENT_ID, PROVIDER_CLIENT_SECRET
from test_postgres_capability_http import PLATFORM, owner
from test_postgres_connector_oauth import CONNECTOR, attributes
from test_postgres_mvp_local import ADMIN, login, stack

CALLBACK = '/forge/v1/connectors/oauth/callback'
ENTRY = {'version': '1.0.0', 'risk': 'medium', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0, 'credential_locus': 'server', 'attributes': attributes()}


def rpc(method, identifier=1, **params):
    return json.dumps({'jsonrpc': '2.0', 'id': identifier, 'method': method, **({'params': params} if params else {})})


class Harness:
    """A composed control plane with the fixtures wired in as explicit egress fixture hosts."""

    def __init__(self, test):
        self.test = test
        self.fixtures = FakeConnectors().start()
        test.addCleanup(self.fixtures.stop)
        self.hosts = {'oauth.fixture.test': Fixture('127.0.0.1', self.fixtures.oauth.port), 'mcp.fixture.test': Fixture('127.0.0.1', self.fixtures.mcp.bound_port)}

    def consent(self, authorize_url):
        parts = urlsplit(authorize_url)
        reply = httpx.get('http://127.0.0.1:%d%s?%s' % (self.fixtures.oauth.port, parts.path, parts.query), follow_redirects=False)
        assert reply.status_code == 302, reply.text
        location = urlsplit(reply.headers['location'])
        return location, {key: values[0] for key, values in parse_qs(location.query).items()}


class PostgresConnectorHttpTests(unittest.TestCase):
    def test_the_member_connects_calls_and_loses_access_when_the_platform_locks_the_connector(self):
        harness = Harness(self)
        with stack(connector_fixtures=harness.hosts) as (db, client, results, root, secrets):
            org = results[0].organization_id
            boss = owner(db, client)
            admin, member = login(client, results[0].accounts[0]), login(client, results[0].accounts[1])
            self.assertEqual(client.put(PLATFORM + '/capabilities/' + CONNECTOR, headers=boss, json={'expected_revision': 0, 'entry': ENTRY}).status_code, 200)
            listing = client.get('/forge/v1/connectors', headers=member).json()['connectors']
            self.assertEqual([(item['id'], item['status'], item['configured'], item['transport']) for item in listing], [(CONNECTOR, 'not_connected', False, 'mcp_http')])
            denied = client.put('/forge/v1/connectors/%s/credential' % CONNECTOR, headers=member, json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': 'x'})
            self.assertEqual((denied.status_code, denied.json()['error']['code']), (404, 'NOT_FOUND'), 'a member cannot write the credential')
            blocked = client.post('/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=member)
            self.assertEqual((blocked.status_code, blocked.json()['error']['code']), (409, 'NOT_CONFIGURED'))
            saved = client.put('/forge/v1/connectors/%s/credential' % CONNECTOR, headers=admin,
                               json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': PROVIDER_CLIENT_ID, 'client_secret': PROVIDER_CLIENT_SECRET})
            self.assertEqual((saved.status_code, saved.json()), (200, {'revision': 1, 'hint': PROVIDER_CLIENT_SECRET[-4:], 'kind': 'oauth_client'}))
            self.assertNotIn(PROVIDER_CLIENT_SECRET, saved.text)
            self.assertEqual(client.get('/forge/v1/connectors/credentials', headers=admin).json()['credentials'][0]['hint'], PROVIDER_CLIENT_SECRET[-4:])
            self.assertEqual(client.get('/forge/v1/connectors/credentials', headers=member).status_code, 404, 'only an administrator reads the credential status')
            start = client.post('/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=member)
            self.assertEqual(start.status_code, 200, start.text)
            location, query = harness.consent(start.json()['authorize_url'])
            self.assertEqual('%s://%s%s' % (location.scheme, location.netloc, location.path), ADMIN + CALLBACK, 'the redirect URI comes from configuration')
            page = client.get(CALLBACK, params={'code': query['code'], 'state': query['state']})
            self.assertEqual((page.status_code, 'Connected' in page.text), (200, True))
            replay = client.get(CALLBACK, params={'code': query['code'], 'state': query['state']})
            self.assertEqual(replay.status_code, 400)
            self.assertEqual(client.get('/forge/v1/connectors', headers=member).json()['connectors'][0]['status'], 'connected')
            self.assertEqual(client.get('/forge/v1/connectors', headers=admin).json()['connectors'][0]['status'], 'not_connected')
            mcp = '/forge/v1/mcp/' + CONNECTOR
            json_headers = {**member, 'content-type': 'application/json'}
            initialized = client.post(mcp, headers=json_headers, content=rpc('initialize', protocolVersion='2025-03-26'))
            self.assertEqual((initialized.status_code, initialized.headers['mcp-session-id']), (200, 'fixture-session'))
            echoed = client.post(mcp, headers=json_headers, content=rpc('tools/call', name='echo', arguments={'text': 'hi'}))
            self.assertEqual(echoed.json()['result']['content'][0]['text'], 'hi')
            token = harness.fixtures.mcp.requests[-1].headers['authorization'][7:]
            leaked = client.post(mcp, headers=json_headers, content=rpc('tools/call', name='headers'))
            self.assertEqual(leaked.status_code, 200)
            for text in (leaked.text, echoed.text, initialized.text, page.text, start.text):
                self.assertNotIn(token, text)
                self.assertNotIn(PROVIDER_CLIENT_SECRET, text)
            self.assertEqual(client.post(mcp, headers=json_headers, content=rpc('sampling/createMessage')).status_code, 403)
            before = len(harness.fixtures.mcp.requests)
            lock = client.put(PLATFORM + '/companies/%s/capabilities/%s' % (org, CONNECTOR), headers=boss, json={'state': None, 'lock': 'forced_off'})
            self.assertEqual(lock.status_code, 200, lock.text)
            off = client.post(mcp, headers=json_headers, content=rpc('ping'))
            self.assertEqual((off.status_code, off.json()['error']['code']), (403, 'CONNECTOR_DISABLED'))
            self.assertEqual(len(harness.fixtures.mcp.requests), before, 'a forced-off connector sends nothing upstream')
            self.assertEqual(client.get('/forge/v1/connectors', headers=member).json()['connectors'][0]['status'], 'disabled')
            audit = [entry['action'] for entry in client.get('/forge/v1/orgs/%s/capability-audit' % org, headers=admin).json()['entries']]
            self.assertEqual(audit, ['company.policy_set', 'connector.connected', 'connector.credential_set'])

    def test_disconnect_revokes_upstream_and_a_removed_member_is_denied_with_the_grant_destroyed(self):
        harness = Harness(self)
        with stack(connector_fixtures=harness.hosts) as (db, client, results, root, secrets):
            boss = owner(db, client)
            admin, member = login(client, results[0].accounts[0]), login(client, results[0].accounts[1])
            client.put(PLATFORM + '/capabilities/' + CONNECTOR, headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
            client.put('/forge/v1/connectors/%s/credential' % CONNECTOR, headers=admin,
                       json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': PROVIDER_CLIENT_ID, 'client_secret': PROVIDER_CLIENT_SECRET})

            def connect():
                start = client.post('/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=member)
                _, query = harness.consent(start.json()['authorize_url'])
                return client.get(CALLBACK, params={'code': query['code'], 'state': query['state']})
            self.assertEqual(connect().status_code, 200)
            gone = client.delete('/forge/v1/connectors/%s/grant' % CONNECTOR, headers=member)
            self.assertEqual((gone.status_code, gone.json()), (200, {'disconnected': True}))
            self.assertEqual(len(harness.fixtures.oauth.revoked), 1)
            self.assertEqual(client.delete('/forge/v1/connectors/%s/grant' % CONNECTOR, headers=member).json(), {'disconnected': False})
            mcp = '/forge/v1/mcp/' + CONNECTOR
            reauth = client.post(mcp, headers={**member, 'content-type': 'application/json'}, content=rpc('ping'))
            self.assertEqual((reauth.status_code, reauth.json()['error']['code']), (409, 'REAUTH_REQUIRED'))
            self.assertEqual(connect().status_code, 200)
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=(SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s)",
                             (results[0].accounts[1].email,))
            before = len(harness.fixtures.mcp.requests)
            removed = client.post(mcp, headers={**member, 'content-type': 'application/json'}, content=rpc('ping'))
            self.assertIn(removed.status_code, (401, 403, 404))
            self.assertEqual(len(harness.fixtures.mcp.requests), before)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,))

    def test_company_isolation_and_the_platform_default_credential(self):
        harness = Harness(self)
        with stack(connector_fixtures=harness.hosts) as (db, client, results, root, secrets):
            boss = owner(db, client)
            member_a, member_b = login(client, results[0].accounts[1]), login(client, results[1].accounts[1])
            admin_b = login(client, results[1].accounts[0])
            client.put(PLATFORM + '/capabilities/' + CONNECTOR, headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
            default = client.put(PLATFORM + '/connectors/%s/credential' % CONNECTOR, headers=boss,
                                 json={'expected_revision': 0, 'kind': 'oauth_client', 'client_id': PROVIDER_CLIENT_ID, 'client_secret': PROVIDER_CLIENT_SECRET})
            self.assertEqual((default.status_code, default.json()['revision']), (200, 1), default.text)
            self.assertNotIn(PROVIDER_CLIENT_SECRET, default.text)
            self.assertEqual(client.put(PLATFORM + '/connectors/%s/credential' % CONNECTOR, headers=admin_b,
                                        json={'expected_revision': 1, 'kind': 'oauth_client', 'client_id': 'x'}).status_code, 403)
            for headers in (member_a, member_b):
                self.assertEqual(client.post('/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=headers).status_code, 200, 'the platform default configures every company')
            self.assertEqual(client.get('/forge/v1/connectors/credentials', headers=admin_b).json()['credentials'][0]['platform_default'], True)
            _, query = harness.consent(client.post('/forge/v1/connectors/%s/oauth/start' % CONNECTOR, headers=member_a).json()['authorize_url'])
            self.assertEqual(client.get(CALLBACK, params={'code': query['code'], 'state': query['state']}).status_code, 200)
            self.assertEqual(client.get('/forge/v1/connectors', headers=member_b).json()['connectors'][0]['status'], 'not_connected', 'company B is not connected by A\'s member')
            foreign = client.post('/forge/v1/mcp/%s?org=%s' % (CONNECTOR, results[0].organization_id), headers={**member_b, 'content-type': 'application/json'}, content=rpc('ping'))
            self.assertEqual(foreign.status_code, 404)

    def test_the_routes_are_hidden_from_the_contract_pin(self):
        harness = Harness(self)
        with stack(connector_fixtures=harness.hosts) as (db, client, results, root, secrets):
            served = client.get('/forge/v1/contract').json()
            self.assertEqual(served['schema_sha256'], contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            if client.get('/openapi.json').status_code == 200:
                self.assertNotIn('/connectors', json.dumps(client.get('/openapi.json').json()))


if __name__ == '__main__':
    unittest.main()
