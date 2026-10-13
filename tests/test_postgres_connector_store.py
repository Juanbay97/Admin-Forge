"""Owned PostgreSQL: the connector store adapter on the 8th pool with the real cipher (typed errors, fresh policy state, sealed round trips)."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.connector_cipher import Binding, ConnectorCipher, ConnectorCipherError, hint
from forge.connector_model import (BrokerConflict, BrokerDenied, BrokerInvalid, BrokerLimit, BrokerNotFound, BrokerUnavailable)
from forge.connector_store import PostgresConnectorStore
from forge.platform import PlatformDenied
from capability_support import GovernanceWorld
from mvp_support import mvp_database

CONNECTOR = 'connector:fixture'
ATTRIBUTES = {'name': 'Fixture', 'transport': 'mcp_http', 'auth': 'oauth', 'mcp_url': 'https://mcp.fixture.test/mcp', 'egress_hosts': ['mcp.fixture.test']}


def digest_of(text):
    return hashlib.sha256(text.encode()).hexdigest()


class StoreWorld(GovernanceWorld):
    def build(self, db):
        super().build(db)
        self.put(CONNECTOR, attributes=ATTRIBUTES, credential_locus='server', risk='medium')
        self.store = PostgresConnectorStore(db.pool('forge_broker_service'))
        self.cipher = ConnectorCipher(Fernet.generate_key())


class StoreTests(StoreWorld, unittest.TestCase):
    def test_a_sealed_credential_round_trips_bound_to_its_revision_and_the_status_never_shows_it(self):
        with mvp_database() as db:
            self.build(db)
            admin, member = self.digest['admin_a'], self.digest['member_a']
            secret = {'client_id': 'cid-123', 'client_secret': 'csecret-0123456789'}
            sealed = self.cipher.seal(Binding(self.org_a, 'org', '', CONNECTOR, 1), secret)
            info = self.store.credential_save(admin, self.org_a, CONNECTOR, 'oauth_client', 0, sealed, hint(secret['client_secret']))
            self.assertEqual((info.revision, info.hint, info.kind), (1, '6789', 'oauth_client'))
            context = self.store.context(member, self.org_a, CONNECTOR)
            self.assertEqual((context.credential_scope, context.credential_kind, context.credential_revision, context.state, context.attributes),
                             ('org', 'oauth_client', 1, 'on', ATTRIBUTES))
            self.assertEqual(self.cipher.open(Binding(self.org_a, 'org', '', CONNECTOR, context.credential_revision), context.credential_sealed), secret)
            with self.assertRaises(ConnectorCipherError):
                self.cipher.open(Binding(self.org_a, 'org', '', CONNECTOR, 2), context.credential_sealed)
            status = self.store.credential_status(admin, self.org_a)
            self.assertEqual([(row.capability_id, row.org_kind, row.org_revision, row.org_hint) for row in status], [(CONNECTOR, 'oauth_client', 1, '6789')])
            self.assertNotIn('csecret', repr(status) + repr(self.store.status(member, self.org_a)))
            self.assertEqual(self.store.credential_revision(admin, self.org_a, CONNECTOR), 1)
            self.assertTrue(self.store.credential_clear(admin, self.org_a, CONNECTOR, 1))
            self.assertFalse(self.store.credential_clear(admin, self.org_a, CONNECTOR, 1))

    def test_the_policy_state_is_resolved_fresh_on_every_read(self):
        with mvp_database() as db:
            self.build(db)
            member = self.digest['member_a']
            self.assertEqual(self.store.status(member, self.org_a)[0].state, 'on')
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, None, 'forced_off'))
            self.assertEqual(self.store.status(member, self.org_a)[0].state, 'forced_off')
            self.assertEqual(self.store.context(member, self.org_a, CONNECTOR).state, 'forced_off')
            self.assertEqual(self.store.status(self.digest['member_b'], self.org_b)[0].state, 'on')
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, None, 'none'))
            self.role.call('SELECT forge.cap_org_set(%s,%s,%s,false)', (self.digest['admin_a'], self.org_a, CONNECTOR))
            self.assertEqual(self.store.context(member, self.org_a, CONNECTOR).state, 'off')

    def test_the_oauth_flow_through_the_store_with_sealed_verifier_and_grant(self):
        with mvp_database() as db:
            self.build(db)
            member = self.digest['member_a']
            state = uuid4().hex
            verifier = self.cipher.seal(Binding(self.org_a, 'user', str(self.membership_of('member_a')), CONNECTOR, 1), {'verifier': 'v' * 43})
            self.store.oauth_start(member, self.org_a, CONNECTOR, digest_of(state), verifier, 300)
            taken = self.store.oauth_take(digest_of(state))
            self.assertEqual((taken.organization_id, taken.capability_id, taken.grant_revision), (self.org_a, CONNECTOR, 0))
            self.assertEqual(self.cipher.open(Binding(taken.organization_id, 'user', str(taken.membership_id), CONNECTOR, 1), taken.sealed_verifier), {'verifier': 'v' * 43})
            bundle = self.cipher.seal(Binding(taken.organization_id, 'user', str(taken.membership_id), CONNECTOR, 1), {'access_token': 'a' * 30, 'refresh_token': 'r' * 30})
            self.assertEqual(self.store.oauth_complete(digest_of(state), 0, bundle, '2030-01-01T00:00:00+00:00'), 1)
            with self.assertRaises(BrokerDenied):
                self.store.oauth_take(digest_of(state))
            context = self.store.context(member, self.org_a, CONNECTOR)
            self.assertEqual((context.grant_status, context.grant_revision), ('connected', 1))
            opened = self.cipher.open(Binding(self.org_a, 'user', str(context.membership_id), CONNECTOR, context.grant_revision), context.grant_sealed)
            self.assertEqual(opened['refresh_token'], 'r' * 30)
            refreshed = self.cipher.seal(Binding(self.org_a, 'user', str(context.membership_id), CONNECTOR, 2), {'access_token': 'b' * 30, 'refresh_token': 'r' * 30})
            self.assertEqual(self.store.grant_update(member, self.org_a, CONNECTOR, 1, refreshed, '2030-01-01T00:00:00+00:00', 'connected'), 2)
            with self.assertRaises(BrokerConflict):
                self.store.grant_update(member, self.org_a, CONNECTOR, 1, refreshed, '2030-01-01T00:00:00+00:00', 'connected')
            removed = self.store.grant_delete(member, self.org_a, CONNECTOR)
            self.assertEqual((removed.revision, removed.sealed), (2, refreshed))
            self.assertIsNone(self.store.grant_delete(member, self.org_a, CONNECTOR))

    def membership_of(self, name):
        return self.db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s', (getattr(self, name).email,)).fetchone()[0]

    def test_every_refusal_is_a_typed_error(self):
        with mvp_database() as db:
            self.build(db)
            member, admin = self.digest['member_a'], self.digest['admin_a']
            with self.assertRaises(BrokerDenied):
                self.store.context(member, self.org_b, CONNECTOR)
            with self.assertRaises(BrokerDenied):
                self.store.credential_save(member, self.org_a, CONNECTOR, 'api_key', 0, 'S' * 100, 'abcd')
            with self.assertRaises(BrokerNotFound):
                self.store.context(member, self.org_a, 'connector:ghost')
            with self.assertRaises(BrokerInvalid):
                self.store.credential_save(admin, self.org_a, CONNECTOR, 'password', 0, 'S' * 100, 'abcd')
            with self.assertRaises(BrokerConflict):
                self.store.credential_save(admin, self.org_a, CONNECTOR, 'api_key', 3, 'S' * 100, 'abcd')
            with self.assertRaises(PlatformDenied):
                self.store.platform_credential_save(admin, CONNECTOR, 'oauth_client', 0, 'S' * 100, 'abcd')
            for index in range(5):
                self.store.oauth_start(member, self.org_a, CONNECTOR, digest_of('s%d' % index), 'S' * 100, 300)
            with self.assertRaises(BrokerLimit):
                self.store.oauth_start(member, self.org_a, CONNECTOR, digest_of('s9'), 'S' * 100, 300)
            with self.assertRaises(BrokerDenied):
                self.store.oauth_take(digest_of('never'))

    def test_a_pool_that_is_not_the_broker_role_is_unavailable(self):
        with mvp_database() as db:
            self.build(db)
            with self.assertRaises(BrokerUnavailable):
                PostgresConnectorStore(db.pool('forge_capability_service')).status(self.digest['member_a'], self.org_a)

    def test_the_readiness_probe_attests_the_broker_role_and_composition_fails_closed_without_it(self):
        with mvp_database() as db:
            self.build(db)
            self.assertIs(self.store.ready(), True)
            self.assertIs(PostgresConnectorStore(db.pool('forge_capability_service')).ready(), False)
            db.admin.execute('ALTER ROLE forge_broker_service LOGIN SUPERUSER')
            try:
                self.assertIs(PostgresConnectorStore(db.pool('forge_broker_service')).ready(), False, 'a privileged login role is not the reviewed role')
            finally:
                db.admin.execute('ALTER ROLE forge_broker_service NOSUPERUSER')

    def test_the_call_log_is_metadata_only(self):
        with mvp_database() as db:
            self.build(db)
            member = self.membership_of('member_a')
            self.assertTrue(self.store.log_call(self.org_a, member, uuid4(), CONNECTOR, 'ok', 12, 'tools/list', None, 80, 900, 200))
            self.assertEqual(db.admin.execute('SELECT source,method,tool_name FROM forge.tool_invocation_log').fetchall(), [('broker', 'tools/list', None)])


if __name__ == '__main__':
    unittest.main()
