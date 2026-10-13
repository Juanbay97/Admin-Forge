"""Owned PostgreSQL + loopback fixtures: the MCP proxy end to end (per-call authorization, credential injection and scrub, limits, metadata log)."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.connector_cipher import Binding
from forge.connector_model import BrokerDenied, BrokerDisabled, BrokerInvalid, BrokerNotConfigured, BrokerRateLimited, BrokerReauth, BrokerTooLarge, BrokerUpstream
from forge.invitations import capability_digest
from forge.mcp_broker import BrokerMethodBlocked, McpBroker
from mvp_support import mvp_database
from test_postgres_connector_oauth import CONNECTOR, OAuthWorld, attributes

API_KEY_CONNECTOR = 'connector:apikey'
CLIENT_HEADERS = {'Content-Type': 'application/json', 'Authorization': 'Bearer the-forge-session', 'Cookie': 'forge=session', 'X-Forwarded-For': '10.1.2.3',
                  'Accept': 'application/json'}


def rpc(method, identifier=1, **params):
    body = {'jsonrpc': '2.0', 'id': identifier, 'method': method}
    if params:
        body['params'] = params
    return json.dumps(body).encode()


class BrokerWorld(OAuthWorld):
    def build(self, db, **options):
        provider = {key: options.pop(key) for key in ('refresh_delay',) if key in options}
        super().build(db, **provider)
        self.broker_service = McpBroker(self.store, self.oauth, self.cipher, self.client, **options)

    def connected(self):
        self.configure()
        self.connect()

    def call(self, body, who='member_a', connector=CONNECTOR, headers=None):
        response = self.broker_service.call(self.token[who], self.org_a, connector, body, headers if headers is not None else CLIENT_HEADERS)
        return response, b''.join(response.body)

    def upstream_count(self):
        return len(self.mcp.requests)


class ProxyTests(BrokerWorld, unittest.TestCase):
    def test_a_connected_member_lists_and_calls_tools_through_the_broker(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            response, body = self.call(rpc('initialize', protocolVersion='2025-03-26'))
            self.assertEqual((response.status, response.headers.get('mcp-session-id')), (200, 'fixture-session'))
            self.assertEqual(json.loads(body)['result']['serverInfo']['name'], 'fixture')
            self.assertEqual(self.call(rpc('notifications/initialized').replace(b'"id": 1, ', b''))[0].status, 202)
            tools = json.loads(self.call(rpc('tools/list'))[1])['result']['tools']
            self.assertIn('echo', [tool['name'] for tool in tools])
            echoed = json.loads(self.call(rpc('tools/call', name='echo', arguments={'text': 'hello'}))[1])
            self.assertEqual(echoed['result']['content'][0]['text'], 'hello')

    def test_the_credential_is_injected_server_side_and_the_client_credentials_never_go_upstream(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            self.call(rpc('tools/call', name='echo', arguments={'text': 'x'}))
            seen = self.mcp.requests[-1]
            token = seen.headers['authorization']
            self.assertTrue(token.startswith('Bearer at-') and token[7:] in self.provider.issued)
            for forbidden in ('cookie', 'x-forwarded-for'):
                self.assertNotIn(forbidden, seen.headers)
            self.assertNotIn('the-forge-session', json.dumps(seen.headers))
            self.assertEqual(seen.headers['host'], 'mcp.fixture.test'.replace('mcp.fixture.test', seen.headers['host']), 'the original host is what the upstream sees')

    def test_a_connector_that_echoes_request_headers_never_hands_the_credential_back(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            response, body = self.call(rpc('tools/call', name='headers'))
            token = self.mcp.requests[-1].headers['authorization'][7:]
            self.assertIn(b'authorization', body.lower(), 'the fixture really did echo the header')
            self.assertNotIn(token.encode(), body)
            self.assertIn(b'[redacted]', body)
            self.assertNotIn(b'the-forge-session', body)

    def test_upstream_cookies_and_auth_headers_are_dropped_from_the_response(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            response, body = self.call(rpc('tools/call', name='cookie'))
            self.assertEqual(response.status, 200)
            self.assertEqual({name.lower() for name in response.headers} - {'content-type', 'mcp-session-id', 'mcp-protocol-version'}, set())
            self.assertNotIn(b'upstream-session-secret', body)

    def test_a_server_sent_event_stream_passes_through_scrubbed(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            response, body = self.call(rpc('tools/call', name='stream'), headers={**CLIENT_HEADERS, 'Accept': 'application/json, text/event-stream'})
            self.assertEqual(response.headers['content-type'], 'text/event-stream')
            self.assertEqual(body.count(b'event: message'), 3)

    def test_a_blocked_method_a_batch_and_an_oversized_body_make_no_upstream_request(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            before = self.upstream_count()
            with self.assertRaises(BrokerMethodBlocked):
                self.call(rpc('sampling/createMessage'))
            with self.assertRaises(BrokerInvalid):
                self.call(b'[' + rpc('ping') + b']')
            with self.assertRaises(BrokerTooLarge):
                self.call(rpc('tools/call', name='echo', arguments={'text': 'x' * (1024 * 1024)}))
            self.assertEqual(self.upstream_count(), before)

    def test_an_oversized_upstream_response_is_capped(self):
        with mvp_database() as db:
            self.build(db, response_limit=2000)
            self.connected()
            with self.assertRaises(BrokerTooLarge):
                self.call(rpc('tools/call', name='big', arguments={'size': 50000}))
            self.assertEqual(self.call(rpc('ping'))[0].status, 200)

    def test_a_slow_upstream_is_bounded_by_the_deadline(self):
        with mvp_database() as db:
            self.build(db, deadline=0.3)
            self.connected()
            with self.assertRaises((BrokerUpstream, BrokerTooLarge)):
                self.call(rpc('tools/call', name='slow', arguments={'seconds': 1.2}), headers={**CLIENT_HEADERS, 'Accept': 'application/json, text/event-stream'})

    def test_an_upstream_redirect_is_never_followed(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            with self.assertRaises(BrokerUpstream):
                self.call(rpc('tools/call', name='redirect'))

    def test_the_member_rate_is_capped_per_minute(self):
        with mvp_database() as db:
            self.build(db, rate_per_minute=3)
            self.connected()
            for _ in range(3):
                self.call(rpc('ping'))
            with self.assertRaises(BrokerRateLimited):
                self.call(rpc('ping'))
            self.assertEqual(self.upstream_count(), 3)


class AuthorizationTests(BrokerWorld, unittest.TestCase):
    def test_a_force_off_denies_at_once_with_no_upstream_traffic(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            self.call(rpc('ping'))
            before = self.upstream_count()
            self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, CONNECTOR, None, 'forced_off'))
            with self.assertRaises(BrokerDisabled):
                self.call(rpc('ping'))
            self.assertEqual(self.upstream_count(), before)
            self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, CONNECTOR, None, 'none'))
            self.call(rpc('ping'))  # lifting the lock restores it: nothing was cached

    def test_the_administrator_turning_it_off_denies_too(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,false)', (self.digest['admin_a'], self.org_a, CONNECTOR))
            with self.assertRaises(BrokerDisabled):
                self.call(rpc('ping'))

    def test_a_removed_member_a_stranger_and_another_company_are_denied_before_any_upstream_request(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            before = self.upstream_count()
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=(SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s)",
                             (self.member_a.email,))
            with self.assertRaises(BrokerDenied):
                self.call(rpc('ping'))
            with self.assertRaises(BrokerDenied):
                self.broker_service.call(self.token['member_b'], self.org_a, CONNECTOR, rpc('ping'), CLIENT_HEADERS)
            with self.assertRaises(BrokerDenied):
                self.broker_service.call('A' * 43, self.org_a, CONNECTOR, rpc('ping'), CLIENT_HEADERS)
            self.assertEqual(self.upstream_count(), before)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,), 'the revoke hook destroyed the grant')

    def test_not_connected_not_configured_and_client_side_connectors_are_refused_without_traffic(self):
        with mvp_database() as db:
            self.build(db)
            with self.assertRaises(BrokerReauth):
                self.configure()
                self.call(rpc('ping'))
            with self.assertRaises(BrokerNotConfigured):
                self.call(rpc('ping'), connector='connector:stdio')
            self.assertEqual(self.upstream_count(), 0)

    def test_an_expired_token_is_refreshed_and_a_revoked_one_marks_reauth(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            first = self.call(rpc('ping'))[0]
            self.offset = 4000
            self.assertEqual(self.call(rpc('ping'))[0].status, 200)
            self.assertEqual(self.provider.refreshes, 1)
            token = self.mcp.requests[-1].headers['authorization'][7:]
            self.provider.issued.discard(token)  # the provider revokes it: the upstream now answers 401
            with self.assertRaises(BrokerReauth):
                self.call(rpc('ping'))
            self.assertEqual(self.grant().grant_status, 'reauth_required')

    def test_the_upstream_host_must_be_in_the_connectors_allow_list(self):
        with mvp_database() as db:
            self.build(db)
            self.put(CONNECTOR, 1, attributes=attributes(egress_hosts=['oauth.fixture.test']), credential_locus='server', risk='medium')
            self.connected()
            before = self.upstream_count()
            with self.assertRaises(BrokerUpstream):
                self.call(rpc('ping'))
            self.assertEqual(self.upstream_count(), before)


class ApiKeyTests(BrokerWorld, unittest.TestCase):
    def test_an_org_api_key_is_injected_in_the_configured_header_and_scrubbed_from_echoes(self):
        with mvp_database() as db:
            self.build(db)
            self.put(API_KEY_CONNECTOR, attributes={'transport': 'mcp_http', 'auth': 'api_key', 'mcp_url': 'http://mcp.fixture.test/mcp', 'egress_hosts': ['mcp.fixture.test'],
                                                  'auth_header': 'x-api-key', 'auth_scheme': ''}, credential_locus='server', risk='medium')
            key = 'sk-live-0123456789abcdef'
            self.mcp.api_key_header, self.mcp.api_keys = 'x-api-key', {key}
            self.store.credential_save(capability_digest(self.token['admin_a']), self.org_a, API_KEY_CONNECTOR, 'api_key', 0,
                                       self.cipher.seal(Binding(self.org_a, 'org', '', API_KEY_CONNECTOR, 1), {'api_key': key}), key[-4:])
            response, body = self.call(rpc('tools/call', name='headers'), connector=API_KEY_CONNECTOR)
            self.assertEqual(response.status, 200)
            self.assertEqual(self.mcp.requests[-1].headers['x-api-key'], key)
            self.assertNotIn(key.encode(), body)
            with self.assertRaises(BrokerNotConfigured):
                self.broker_service.call(self.token['member_b'], self.org_b, API_KEY_CONNECTOR, rpc('ping'), CLIENT_HEADERS)


class MetadataTests(BrokerWorld, unittest.TestCase):
    def test_one_metadata_row_per_call_and_never_a_body_a_header_or_a_secret(self):
        with mvp_database() as db:
            self.build(db)
            self.connected()
            self.call(rpc('tools/call', name='echo', arguments={'text': 'PRIVATE-MEMBER-TEXT'}))
            self.call(rpc('tools/list'))
            self.role.call('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (self.owner, CONNECTOR, None, 'forced_off'))
            with self.assertRaises(BrokerDisabled):
                self.call(rpc('ping'))
            rows = db.admin.execute("SELECT source,capability_id,method,tool_name,status_code,outcome,bytes_in>0,bytes_out FROM forge.tool_invocation_log ORDER BY recorded_at").fetchall()
            self.assertEqual([(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows],
                             [('broker', CONNECTOR, 'tools/call', 'echo', 200, 'ok'), ('broker', CONNECTOR, 'tools/list', None, 200, 'ok'), ('broker', CONNECTOR, 'ping', None, None, 'denied')])
            self.assertTrue(rows[0][6] and rows[0][7] > 0)
            dump = json.dumps(db.admin.execute('SELECT * FROM forge.tool_invocation_log').fetchall(), default=str)
            token = self.mcp.requests[-1].headers.get('authorization', '')[7:] or 'at-'
            for forbidden in ('PRIVATE-MEMBER-TEXT', 'the-forge-session', token, 'fixture-client-secret'):
                self.assertNotIn(forbidden, dump)


if __name__ == '__main__':
    unittest.main()
