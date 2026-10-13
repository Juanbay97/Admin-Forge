"""Owned PostgreSQL 0041 connector storage: write-only org credentials, revision CAS, single-use OAuth states, per-member grants,
the revoke hook and tenant isolation. The functions take opaque sealed text: sealing itself is tested in test_connector_cipher."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import CONNECTOR_SECRETS_MIGRATION, F40, F41, MVP_ADDITIONS, MVP_CHECKPOINTS
from capability_support import GovernanceWorld, entry
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

CONNECTOR, OTHER = 'connector:fixture', 'connector:stdio'
SEALED = 'S' * 120
ATTRIBUTES = {'name': 'Fixture', 'transport': 'mcp_http', 'auth': 'oauth', 'mcp_url': 'https://mcp.fixture.test/mcp', 'egress_hosts': ['mcp.fixture.test']}
FUNCTIONS = ('broker_status(text,uuid)', 'broker_context(text,uuid,text)', 'broker_credential_save(text,uuid,text,text,bigint,text,text)',
             'broker_credential_clear(text,uuid,text,bigint)', 'broker_credential_status(text,uuid)', 'broker_platform_credential_save(text,text,text,bigint,text,text)',
             'broker_platform_credential_revision(text,text)', 'broker_credential_revision(text,uuid,text)', 'broker_oauth_start(text,uuid,text,text,text,integer)',
             'broker_oauth_take(text)', 'broker_oauth_complete(text,bigint,text,timestamptz)', 'broker_grant_update(text,uuid,text,bigint,text,timestamptz,text)',
             'broker_grant_delete(text,uuid,text)', 'broker_log_call(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer)')


def digest_of(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ConnectorProfileTests(unittest.TestCase):
    def test_0041_follows_0040_with_its_own_pinned_checkpoint(self):
        self.assertEqual(CONNECTOR_SECRETS_MIGRATION, '0041_connector_secrets.sql')
        self.assertEqual(MVP_ADDITIONS[at(CONNECTOR_SECRETS_MIGRATION) - 1], '0040_tool_invocation_log.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(CONNECTOR_SECRETS_MIGRATION):at(CONNECTOR_SECRETS_MIGRATION) + 2], (F40, F41))
        self.assertRegex(F41 or '', r'^[0-9a-f]{64}$', 'F41 must be pinned')
        self.assertNotEqual(F41, F40)


class ConnectorFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0040_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(CONNECTOR_SECRETS_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, CONNECTOR_SECRETS_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F40)
            conn.execute(migration_text(CONNECTOR_SECRETS_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0041 connector secrets checkpoint F41:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0040 must be identical')
        self.assertEqual(fresh, F41, 'F41 must be pinned to the reviewed value')


class BrokerWorld(GovernanceWorld):
    def build(self, db):
        super().build(db)
        self.put(CONNECTOR, attributes=ATTRIBUTES, credential_locus='server', risk='medium')
        self.put(OTHER, attributes={'transport': 'stdio', 'auth': 'none'}, credential_locus='client', risk='medium')
        self.membership = {name: db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s',
                                                  (getattr(self, name).email,)).fetchone()[0] for name in ('admin_a', 'member_a', 'admin_b', 'member_b')}

    def call(self, text, params=()):
        return self.broker.call(text, params)

    def refusal(self, text, params=()):
        return self.broker.refusal(text, params)

    def save_credential(self, who='admin_a', org=None, expected=0, kind='oauth_client', sealed=SEALED, hint='abcd'):
        return self.call('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)', (self.digest[who], org or self.org_a, CONNECTOR, kind, expected, sealed, hint))

    def start(self, state, who='member_a', org=None, ttl=300):
        return self.call('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (self.digest[who], org or self.org_a, CONNECTOR, digest_of(state), SEALED, ttl))

    def connect(self, who='member_a', state=None):
        state = state or uuid4().hex
        self.start(state, who)
        taken = self.call('SELECT * FROM forge.broker_oauth_take(%s)', (digest_of(state),))[0]
        self.call('SELECT forge.broker_oauth_complete(%s,%s,%s,now()+%s::interval)', (digest_of(state), taken[4], 'G' * 120, '1 hour'))
        return state


class CredentialTests(BrokerWorld, unittest.TestCase):
    def test_an_administrator_saves_write_only_and_a_stale_revision_is_a_conflict(self):
        with mvp_database() as db:
            self.build(db)
            self.assertEqual(self.save_credential(), [(1, 'abcd', 'oauth_client')])
            self.assertEqual(self.save_credential(expected=1, kind='api_key', hint='wxyz'), [(2, 'wxyz', 'api_key')])
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, CONNECTOR, 'api_key', 1, SEALED, 'abcd')), 'BROKER_CONFLICT')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, CONNECTOR, 'api_key', 0, SEALED, 'abcd')), 'BROKER_CONFLICT', 'a create over an existing row')
            self.assertEqual(db.admin.execute('SELECT revision,kind FROM forge.connector_credentials').fetchall(), [(2, 'api_key')])
            status = self.call('SELECT * FROM forge.broker_credential_status(%s,%s)', (self.digest['admin_a'], self.org_a))
            self.assertEqual(status, [(CONNECTOR, 'api_key', 2, 'wxyz', None)])
            self.assertNotIn(SEALED, json.dumps(status, default=str))
            self.assertEqual(self.call('SELECT forge.broker_credential_revision(%s,%s,%s)', (self.digest['admin_a'], self.org_a, CONNECTOR)), [(2,)])
            self.assertEqual(self.call('SELECT forge.broker_credential_clear(%s,%s,%s,%s)', (self.digest['admin_a'], self.org_a, CONNECTOR, 2)), [(True,)])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_credentials').fetchone(), (0,))

    def test_members_other_companies_unknown_and_client_side_connectors_are_refused(self):
        with mvp_database() as db:
            self.build(db)
            for who, org in (('member_a', self.org_a), ('admin_b', self.org_a), ('admin_a', self.org_b)):
                self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                              (self.digest[who], org, CONNECTOR, 'api_key', 0, SEALED, 'abcd')), 'CAP_DENIED', (who, org))
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, 'connector:ghost', 'api_key', 0, SEALED, 'abcd')), 'BROKER_NOT_FOUND')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, OTHER, 'api_key', 0, SEALED, 'abcd')), 'BROKER_NOT_FOUND', 'stdio connectors keep their credentials on the client')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, CONNECTOR, 'password', 0, SEALED, 'abcd')), 'BROKER_INVALID')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)',
                                          (self.digest['admin_a'], self.org_a, CONNECTOR, 'api_key', 0, 'short', 'abcd')), 'BROKER_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_credentials').fetchone(), (0,))

    def test_the_platform_default_is_written_by_the_owner_only_and_a_company_credential_overrides_it(self):
        with mvp_database() as db:
            self.build(db)
            self.assertEqual(self.call('SELECT * FROM forge.broker_platform_credential_save(%s,%s,%s,%s,%s,%s)', (self.owner, CONNECTOR, 'oauth_client', 0, 'P' * 120, 'plat')),
                             [(1, 'plat', 'oauth_client')])
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_platform_credential_save(%s,%s,%s,%s,%s,%s)', (self.digest['admin_a'], CONNECTOR, 'oauth_client', 1, SEALED, 'x')), 'PLATFORM_DENIED')
            self.assertEqual(self.call('SELECT forge.broker_platform_credential_revision(%s,%s)', (self.owner, CONNECTOR)), [(1,)])
            context = self.call('SELECT credential_scope,credential_kind,credential_sealed,credential_revision FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR))
            self.assertEqual(context, [('platform', 'oauth_client', 'P' * 120, 1)])
            self.save_credential()
            context = self.call('SELECT credential_scope,credential_sealed FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR))
            self.assertEqual(context, [('org', SEALED)])
            other = self.call('SELECT credential_scope FROM forge.broker_context(%s,%s,%s)', (self.digest['member_b'], self.org_b, CONNECTOR))
            self.assertEqual(other, [('platform',)], 'the other company still inherits the platform default')

    def test_credential_changes_are_audited_without_any_secret_text(self):
        with mvp_database() as db:
            self.build(db)
            self.save_credential()
            self.call('SELECT forge.broker_credential_clear(%s,%s,%s,%s)', (self.digest['admin_a'], self.org_a, CONNECTOR, 1))
            rows = self.role.call('SELECT action,target,before_state,after_state FROM forge.cap_org_audit_page(%s,%s,NULL,10)', (self.digest['admin_a'], self.org_a))
            self.assertEqual(rows, [('connector.credential_cleared', CONNECTOR, 'r1', None), ('connector.credential_set', CONNECTOR, None, 'r1')])
            self.assertNotIn(SEALED, json.dumps(db.admin.execute('SELECT * FROM forge.capability_change_audit').fetchall(), default=str))


class OAuthTests(BrokerWorld, unittest.TestCase):
    def test_start_take_complete_stores_a_grant_and_the_state_is_single_use(self):
        with mvp_database() as db:
            self.build(db)
            state = uuid4().hex
            self.start(state)
            self.assertEqual(db.admin.execute('SELECT length(state_hash),taken_at IS NULL,completed_at IS NULL FROM forge.connector_oauth_states').fetchone(), (64, True, True),
                             'only the hash is stored')
            taken = self.call('SELECT * FROM forge.broker_oauth_take(%s)', (digest_of(state),))[0]
            self.assertEqual(taken, (self.org_a, self.membership['member_a'], CONNECTOR, SEALED, 0))
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_oauth_take(%s)', (digest_of(state),)), 'BROKER_DENIED', 'a replay is refused')
            self.assertEqual(self.call('SELECT forge.broker_oauth_complete(%s,%s,%s,now()+%s::interval)', (digest_of(state), 0, 'G' * 120, '1 hour')), [(1,)])
            self.assertEqual(self.refusal('SELECT forge.broker_oauth_complete(%s,%s,%s,now())', (digest_of(state), 1, 'G' * 120)), 'BROKER_DENIED', 'completion is single-use too')
            self.assertEqual(db.admin.execute('SELECT status,revision FROM forge.connector_grants').fetchall(), [('connected', 1)])
            status = {row[0]: row for row in self.call('SELECT capability_id,grant_status FROM forge.broker_status(%s,%s)', (self.digest['member_a'], self.org_a))}
            self.assertEqual(status[CONNECTOR][1], 'connected')
            self.assertEqual(self.call('SELECT grant_status FROM forge.broker_status(%s,%s) WHERE capability_id=%s', (self.digest['admin_a'], self.org_a, CONNECTOR)), [(None,)],
                             'another member of the same company is not connected')
            audit = self.role.call('SELECT action FROM forge.cap_org_audit_page(%s,%s,NULL,10)', (self.digest['admin_a'], self.org_a))
            self.assertEqual(audit, [('connector.connected',)])

    def test_unknown_malformed_expired_and_untaken_states_are_the_same_refusal(self):
        with mvp_database() as db:
            self.build(db)
            state = uuid4().hex
            self.start(state)
            for bad in (digest_of('never issued'), 'not-hex', '', 'A' * 64, None):
                self.assertEqual(self.refusal('SELECT * FROM forge.broker_oauth_take(%s)', (bad,)), 'BROKER_DENIED', str(bad)[:20])
            self.assertEqual(self.refusal('SELECT forge.broker_oauth_complete(%s,%s,%s,now())', (digest_of(state), 0, 'G' * 120)), 'BROKER_DENIED', 'not taken yet')
            db.admin.execute("UPDATE forge.connector_oauth_states SET expires_at=clock_timestamp()-interval '1 second'")
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_oauth_take(%s)', (digest_of(state),)), 'BROKER_DENIED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,))

    def test_start_is_limited_validated_and_member_bound(self):
        with mvp_database() as db:
            self.build(db)
            for index in range(5):
                self.start('state-%d' % index)
            self.assertEqual(self.refusal('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR, digest_of('sixth'), SEALED, 300)), 'BROKER_LIMIT')
            self.start('other member', who='admin_a')
            for ttl in (0, 59, 601):
                self.assertEqual(self.refusal('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (self.digest['admin_a'], self.org_a, CONNECTOR, digest_of('t%d' % ttl), SEALED, ttl)), 'BROKER_INVALID')
            for who, org in (('member_a', self.org_b), ('member_b', self.org_a)):
                self.assertEqual(self.refusal('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (self.digest[who], org, CONNECTOR, digest_of('x'), SEALED, 300)), 'CAP_DENIED')
            self.assertEqual(self.refusal('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (self.digest['member_b'], self.org_b, 'connector:ghost', digest_of('y'), SEALED, 300)), 'BROKER_NOT_FOUND')

    def test_a_grant_write_is_compare_and_swap_and_a_refresh_moves_the_revision(self):
        with mvp_database() as db:
            self.build(db)
            self.connect()
            member = self.digest['member_a']
            self.assertEqual(self.call('SELECT forge.broker_grant_update(%s,%s,%s,%s,%s,now()+%s::interval,%s)', (member, self.org_a, CONNECTOR, 1, 'R' * 120, '2 hours', 'connected')), [(2,)])
            self.assertEqual(self.refusal('SELECT forge.broker_grant_update(%s,%s,%s,%s,%s,now(),%s)', (member, self.org_a, CONNECTOR, 1, 'R' * 120, 'connected')), 'BROKER_CONFLICT',
                             'a second refresher that read revision 1 loses')
            self.assertEqual(self.call('SELECT forge.broker_grant_update(%s,%s,%s,%s,NULL,NULL,%s)', (member, self.org_a, CONNECTOR, 2, 'reauth_required')), [(2,)], 'flagging keeps the revision')
            self.assertEqual(db.admin.execute('SELECT status,revision,sealed FROM forge.connector_grants').fetchone(), ('reauth_required', 2, 'R' * 120))
            self.assertEqual(self.refusal('SELECT forge.broker_grant_update(%s,%s,%s,%s,%s,now(),%s)', (member, self.org_a, CONNECTOR, 2, 'R' * 120, 'exploded')), 'BROKER_INVALID')
            self.assertEqual(self.refusal('SELECT forge.broker_grant_update(%s,%s,%s,%s,%s,now(),%s)', (self.digest['admin_a'], self.org_a, CONNECTOR, 1, 'R' * 120, 'connected')), 'BROKER_NOT_FOUND',
                             "one member cannot touch another member's grant")

    def test_disconnect_destroys_the_grant_returns_it_once_and_is_audited(self):
        with mvp_database() as db:
            self.build(db)
            self.connect()
            deleted = self.call('SELECT * FROM forge.broker_grant_delete(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR))
            self.assertEqual(deleted, [(1, 'G' * 120)])
            self.assertEqual(self.call('SELECT * FROM forge.broker_grant_delete(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR)), [])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,))
            self.assertEqual(db.admin.execute("SELECT count(*) FROM forge.capability_change_audit WHERE action='connector.disconnected'").fetchone(), (1,))

    def test_a_membership_that_leaves_active_loses_its_grants_and_pending_states_at_once(self):
        with mvp_database() as db:
            self.build(db)
            self.connect('member_a')
            self.connect('admin_a')
            self.start('pending')
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (self.membership['member_a'],))
            self.assertEqual(db.admin.execute('SELECT membership_id FROM forge.connector_grants').fetchall(), [(self.membership['admin_a'],)])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_oauth_states WHERE membership_id=%s', (self.membership['member_a'],)).fetchone(), (0,))
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR)), 'CAP_DENIED', 'a suspended member is denied')
            db.admin.execute("UPDATE forge.memberships SET status='active' WHERE id=%s", (self.membership['member_a'],))
            self.assertEqual(self.call('SELECT grant_status FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR)), [(None,)], 'reactivation does not resurrect the grant')


class ContextTests(BrokerWorld, unittest.TestCase):
    def test_the_context_carries_layers_attributes_and_the_grant_and_denies_strangers(self):
        with mvp_database() as db:
            self.build(db)
            self.connect()
            row = self.call('SELECT membership_id,attributes,credential_locus,default_state,company_lock,grant_status,grant_sealed,grant_revision FROM forge.broker_context(%s,%s,%s)',
                            (self.digest['member_a'], self.org_a, CONNECTOR))[0]
            self.assertEqual(row, (self.membership['member_a'], ATTRIBUTES, 'server', 'on', 'none', 'connected', 'G' * 120, 1))
            self.role.call('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (self.owner, self.org_a, CONNECTOR, None, 'forced_off'))
            self.assertEqual(self.call('SELECT company_lock FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, CONNECTOR)), [('forced_off',)],
                             'the layers are read fresh on every call')
            for digest, org in ((self.digest['member_a'], self.org_b), (self.digest['member_b'], self.org_a), ('0' * 64, self.org_a), (self.digest['member_a'], uuid4())):
                self.assertEqual(self.refusal('SELECT * FROM forge.broker_context(%s,%s,%s)', (digest, org, CONNECTOR)), 'CAP_DENIED')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, 'connector:ghost')), 'BROKER_NOT_FOUND')
            self.assertEqual(self.refusal('SELECT * FROM forge.broker_context(%s,%s,%s)', (self.digest['member_a'], self.org_a, 'skill:pdf')), 'BROKER_NOT_FOUND')

    def test_the_status_lists_connectors_with_public_attributes_and_no_secret(self):
        with mvp_database() as db:
            self.build(db)
            self.save_credential()
            rows = self.call('SELECT * FROM forge.broker_status(%s,%s)', (self.digest['member_a'], self.org_a))
            self.assertEqual([row[0] for row in rows], [CONNECTOR, OTHER])
            fixture = rows[0]
            self.assertEqual((fixture[1], fixture[10], fixture[11], fixture[12]), (ATTRIBUTES, 'org', 'oauth_client', None))
            self.assertNotIn(SEALED, json.dumps(rows, default=str))

    def test_a_brokered_call_is_logged_as_metadata_through_the_governance_log(self):
        with mvp_database() as db:
            self.build(db)
            event = uuid4()
            logged = self.call('SELECT forge.broker_log_call(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                               (self.org_a, self.membership['member_a'], event, CONNECTOR, 'ok', 31, 'tools/call', 'echo', 120, 480, 200))
            self.assertEqual(logged, [(True,)])
            self.assertEqual(self.call('SELECT forge.broker_log_call(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                       (self.org_a, self.membership['member_a'], event, CONNECTOR, 'ok', 31, 'tools/call', 'echo', 120, 480, 200)), [(False,)])
            self.assertEqual(db.admin.execute('SELECT source,capability_id,method,tool_name,status_code,bytes_in,bytes_out FROM forge.tool_invocation_log').fetchall(),
                             [('broker', CONNECTOR, 'tools/call', 'echo', 200, 120, 480)])
            self.assertEqual(self.refusal('SELECT forge.broker_log_call(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                          (self.org_a, self.membership['member_a'], uuid4(), CONNECTOR, 'exploded', 1, None, None, None, None, None)), 'CAP_INVALID')


class IsolationTests(BrokerWorld, unittest.TestCase):
    def test_the_service_role_executes_only_the_broker_functions_and_holds_no_table_privilege(self):
        with mvp_database() as db:
            for name in FUNCTIONS:
                self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_broker_service',%s::regprocedure,'EXECUTE')", ('forge.' + name,)).fetchone(), (True,), name)
                for role in ('forge_capability_service', 'forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'public'):
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')", (role, 'forge.' + name)).fetchone(), (False,), (role, name))
                self.assertEqual(db.admin.execute('SELECT pg_get_userbyid(proowner),proconfig FROM pg_proc WHERE oid=%s::regprocedure', ('forge.' + name,)).fetchone(),
                                 ('forge_broker_authority', ['search_path=pg_catalog']), name)
            for table in ('connector_credentials', 'connector_grants', 'connector_oauth_states'):
                self.assertEqual(db.admin.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', ('forge.' + table,)).fetchone(), (True, True))
                for role in ('forge_broker_service', 'forge_capability_service', 'forge_capability_authority', 'forge_platform_service', 'forge_platform_authority', 'forge_gateway_service',
                             'forge_gateway_authority', 'forge_account_service', 'forge_runtime', 'public'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, 'forge.' + table)).fetchone(), (False,), (role, table))
            self.assertEqual(db.admin.execute("SELECT has_schema_privilege('forge_broker_service','forge','CREATE'),has_schema_privilege('forge_broker_authority','forge','CREATE')").fetchone(), (False, False))
            self.build(db)
            with self.assertRaises(errors.InsufficientPrivilege):
                self.broker.call('SELECT * FROM forge.connector_grants')

    def test_the_authority_sees_no_company_without_a_context(self):
        with mvp_database() as db:
            self.build(db)
            self.connect('member_a')
            db.admin.execute('SET ROLE forge_broker_authority')
            try:
                self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,))
                db.admin.execute("SELECT set_config('forge.organization',%s,false)", (str(self.org_b),))
                self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (0,), 'company B has no grants')
                db.admin.execute("SELECT set_config('forge.organization',%s,false)", (str(self.org_a),))
                self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.connector_grants').fetchone(), (1,))
            finally:
                db.admin.execute('RESET ROLE')
                db.admin.execute("SELECT set_config('forge.organization','',false)")


if __name__ == '__main__':
    unittest.main()
