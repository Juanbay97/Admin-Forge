"""Owned PostgreSQL + loopback fixtures: the per-member OAuth flow (start, callback, replay, expiry, refresh single-flight, reauth, disconnect)."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import unittest
from urllib.parse import parse_qs, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
import httpx
from cryptography.fernet import Fernet
from forge.connector_cipher import Binding, ConnectorCipher
from forge.connector_model import BrokerDenied, BrokerDisabled, BrokerNotConfigured, BrokerReauth, BrokerUpstream
from forge.connector_oauth import CALLBACK_PATH, ConnectorOAuth
from forge.connector_store import PostgresConnectorStore
from forge.egress_guard import EgressGuard, Fixture, GuardedClient
from fixtures.fake_oauth_provider import PROVIDER_CLIENT_ID, PROVIDER_CLIENT_SECRET
from fixtures.fake_mcp_server import FakeConnectors
from capability_support import GovernanceWorld
from mvp_support import mvp_database

CONNECTOR, STDIO = 'connector:fixture', 'connector:stdio'
ORIGIN = 'https://forge.example.test'


def attributes(**change):
    values = {'name': 'Fixture', 'transport': 'mcp_http', 'auth': 'oauth', 'mcp_url': 'http://mcp.fixture.test/mcp', 'egress_hosts': ['oauth.fixture.test', 'mcp.fixture.test'],
              'oauth': {'authorize_url': 'http://oauth.fixture.test/authorize', 'token_url': 'http://oauth.fixture.test/token', 'scopes': ['read', 'write'],
                        'revocation_url': 'http://oauth.fixture.test/revoke'}}
    values.update(change)
    return values


class OAuthWorld(GovernanceWorld):
    def build(self, db, **provider):
        super().build(db)
        self.put(CONNECTOR, attributes=attributes(), credential_locus='server', risk='medium')
        self.put(STDIO, attributes={'transport': 'stdio', 'auth': 'none'}, credential_locus='client', risk='medium')
        self.fixtures = FakeConnectors(**provider).start()
        self.addCleanup(self.fixtures.stop)
        self.provider, self.mcp = self.fixtures.oauth, self.fixtures.mcp
        self.store = PostgresConnectorStore(db.pool('forge_broker_service'))
        self.cipher = ConnectorCipher(Fernet.generate_key())
        guard = EgressGuard(fixtures={'oauth.fixture.test': Fixture('127.0.0.1', self.provider.port), 'mcp.fixture.test': Fixture('127.0.0.1', self.mcp.bound_port)})
        self.client = GuardedClient(guard)
        self.addCleanup(self.client.close)
        self.now = time.time()
        self.offset = 0
        self.oauth = ConnectorOAuth(self.store, self.cipher, self.client, public_origin=ORIGIN, clock=lambda: time.time() + self.offset)
        self.token = {name: self.token_for(name) for name in ('admin_a', 'member_a', 'admin_b', 'member_b')}

    def token_for(self, name):
        from platform_support import sign_in
        return sign_in(self.db, getattr(self, name).email, getattr(self, name).password)[0]

    def configure(self, org=None, who='admin_a'):
        org = org or self.org_a
        secret = {'client_id': PROVIDER_CLIENT_ID, 'client_secret': PROVIDER_CLIENT_SECRET}
        from forge.invitations import capability_digest
        self.store.credential_save(capability_digest(self.token[who]), org, CONNECTOR, 'oauth_client', 0,
                                   self.cipher.seal(Binding(org, 'org', '', CONNECTOR, 1), secret), 'cret')

    def consent(self, url):
        """The browser step: follow the authorize URL at the fixture and return the code and state it redirects back with."""
        parts = urlsplit(url)
        response = httpx.get('http://127.0.0.1:%d%s?%s' % (self.provider.port, parts.path, parts.query), follow_redirects=False)
        self.assertEqual(response.status_code, 302, response.text)
        location = urlsplit(response.headers['location'])
        self.assertEqual('%s://%s%s' % (location.scheme, location.netloc, location.path), ORIGIN + CALLBACK_PATH)
        query = {key: values[0] for key, values in parse_qs(location.query).items()}
        return query

    def connect(self, who='member_a', org=None):
        org = org or self.org_a
        query = self.consent(self.oauth.start(self.token[who], org, CONNECTOR))
        return self.oauth.complete(query['state'], query['code']), query

    def grant(self, who='member_a'):
        from forge.invitations import capability_digest
        return self.store.context(capability_digest(self.token[who]), self.org_a, CONNECTOR)


class FlowTests(OAuthWorld, unittest.TestCase):
    def test_the_member_connects_and_the_tokens_stay_server_side(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            url = self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR)
            query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
            self.assertEqual((query['response_type'], query['client_id'], query['redirect_uri'], query['code_challenge_method'], query['scope']),
                             ('code', PROVIDER_CLIENT_ID, ORIGIN + CALLBACK_PATH, 'S256', 'read write'))
            self.assertNotIn(PROVIDER_CLIENT_SECRET, url)
            redirected = self.consent(url)
            self.assertEqual(self.oauth.complete(redirected['state'], redirected['code']), CONNECTOR)
            self.assertEqual((self.provider.exchanges, self.provider.token_requests[0]['redirect_uri']), (1, ORIGIN + CALLBACK_PATH))
            context = self.grant()
            self.assertEqual((context.grant_status, context.grant_revision), ('connected', 1))
            token = self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, context)
            self.assertIn(token, self.provider.issued)
            row = db.admin.execute('SELECT sealed,status FROM forge.connector_grants').fetchone()
            self.assertNotIn(token, row[0], 'the token is sealed in storage')
            statuses = {item.id: item for item in self.store.status(__import__('forge.invitations', fromlist=['x']).capability_digest(self.token['member_a']), self.org_a)}
            self.assertEqual(statuses[CONNECTOR].grant_status, 'connected')
            self.assertNotIn(token, repr(statuses))
            self.assertEqual(db.admin.execute("SELECT count(*) FROM forge.capability_change_audit WHERE action='connector.connected'").fetchone(), (1,))

    def test_a_replayed_callback_is_refused_and_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            _, query = self.connect()
            with self.assertRaises(BrokerDenied):
                self.oauth.complete(query['state'], query['code'])
            self.assertEqual((self.provider.exchanges, self.grant().grant_revision), (1, 1))

    def test_unknown_malformed_and_expired_states_are_the_same_refusal(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            for state in ('x' * 43, 'short', '', None, 'é' * 30):
                with self.assertRaises(BrokerDenied):
                    self.oauth.complete(state, 'code')
            query = self.consent(self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR))
            db.admin.execute("UPDATE forge.connector_oauth_states SET expires_at=clock_timestamp()-interval '1 second'")
            with self.assertRaises(BrokerDenied):
                self.oauth.complete(query['state'], query['code'])
            self.assertEqual(self.provider.exchanges, 0, 'an expired state never reaches the provider')

    def test_a_denied_consent_and_a_failed_exchange_burn_the_state(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            self.provider.fail_exchange = True
            query = self.consent(self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR))
            with self.assertRaises(BrokerUpstream):
                self.oauth.complete(query['state'], query['code'])
            with self.assertRaises(BrokerDenied):
                self.oauth.complete(query['state'], query['code'])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,))
            self.provider.fail_exchange = False
            self.provider.deny_consent = True
            denied = self.consent(self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR))
            self.assertEqual(denied.get('error'), 'access_denied')
            self.oauth.abort(denied['state'])
            with self.assertRaises(BrokerDenied):
                self.oauth.complete(denied['state'], 'any-code')

    def test_a_disabled_or_unconfigured_connector_cannot_start_and_a_lock_after_start_blocks_the_callback(self):
        with mvp_database() as db:
            self.build(db)
            with self.assertRaises(BrokerNotConfigured):
                self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR)
            self.configure()
            with self.assertRaises(BrokerNotConfigured):
                self.oauth.start(self.token['member_a'], self.org_a, STDIO)
            query = self.consent(self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR))
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, None, 'forced_off'))
            with self.assertRaises(BrokerDisabled):
                self.oauth.complete(query['state'], query['code'])
            with self.assertRaises(BrokerDisabled):
                self.oauth.start(self.token['member_a'], self.org_a, CONNECTOR)
            self.assertEqual(self.provider.exchanges, 0)

    def test_the_redirect_origin_is_configuration_only(self):
        for bad in ('', None, 'not a url', 'https://forge.example.test/path', 'https://forge.example.test/?x=1', 'ftp://forge.example.test', 'https://'):
            with self.subTest(origin=bad), self.assertRaises(ValueError):
                ConnectorOAuth(object(), object(), object(), public_origin=bad)
        self.assertEqual(ConnectorOAuth(object(), object(), object(), public_origin='https://forge.example.test:8443/').redirect_uri, 'https://forge.example.test:8443' + CALLBACK_PATH)


class RefreshTests(OAuthWorld, unittest.TestCase):
    def test_an_expired_token_is_refreshed_once_and_the_new_token_works(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            self.connect()
            first = self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant())
            self.offset = 4000  # past the one-hour lifetime
            second = self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant())
            self.assertNotEqual(first, second)
            self.assertEqual(self.provider.refreshes, 1)
            self.assertIn(second, self.provider.issued)
            self.assertEqual(self.grant().grant_revision, 2)
            self.assertEqual(self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant()), second, 'a fresh token is not refreshed again')

    def test_five_concurrent_calls_reach_the_provider_with_one_refresh(self):
        with mvp_database() as db:
            self.build(db, refresh_delay=0.4)
            self.configure()
            self.connect()
            self.offset = 4000
            context = self.grant()
            with ThreadPoolExecutor(5) as pool:
                tokens = list(pool.map(lambda _: self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, context), range(5)))
            self.assertEqual(self.provider.refreshes, 1)
            self.assertEqual(len(set(tokens)), 1)
            self.assertIn(tokens[0], self.provider.issued)

    def test_a_refused_refresh_marks_reauth_required_and_stops_brokering(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            self.connect()
            self.offset = 4000
            self.provider.fail_refresh = True
            with self.assertRaises(BrokerReauth):
                self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant())
            context = self.grant()
            self.assertEqual(context.grant_status, 'reauth_required')
            with self.assertRaises(BrokerReauth):
                self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, context)
            self.provider.fail_refresh = False
            self.connect()  # connecting again restores the grant
            self.assertEqual(self.grant().grant_status, 'connected')

    def test_a_provider_outage_during_refresh_is_an_upstream_error_not_a_reauth(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            self.connect()
            self.offset = 4000
            self.provider.stop()
            with self.assertRaises(BrokerUpstream):
                self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant())
            self.assertEqual(self.grant().grant_status, 'connected')
            self.provider = type('Stopped', (), {'stop': lambda self: None})()
            self.fixtures.oauth = self.provider


class DisconnectTests(OAuthWorld, unittest.TestCase):
    def test_disconnect_destroys_the_grant_and_revokes_upstream(self):
        with mvp_database() as db:
            self.build(db)
            self.configure()
            self.connect()
            refresh = self.cipher.open(Binding(self.org_a, 'user', str(self.grant().membership_id), CONNECTOR, 1), self.grant().grant_sealed)['refresh_token']
            self.assertTrue(self.oauth.disconnect(self.token['member_a'], self.org_a, CONNECTOR))
            self.assertEqual(self.provider.revoked, [refresh])
            self.assertIsNone(self.grant().grant_status)
            self.assertFalse(self.oauth.disconnect(self.token['member_a'], self.org_a, CONNECTOR))
            with self.assertRaises(BrokerReauth):
                self.oauth.access_token(self.token['member_a'], self.org_a, CONNECTOR, self.grant())
            self.assertEqual(db.admin.execute("SELECT count(*) FROM forge.capability_change_audit WHERE action='connector.disconnected'").fetchone(), (1,))


if __name__ == '__main__':
    unittest.main()
