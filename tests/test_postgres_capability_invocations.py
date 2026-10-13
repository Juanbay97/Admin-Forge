"""Owned PostgreSQL 0040 tool-invocation log: strict allow-listed batches, replay dedupe, member-bound writes, no content column."""
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
from forge.mvp_profile import F39, F40, MVP_ADDITIONS, MVP_CHECKPOINTS, TOOL_INVOCATION_LOG_MIGRATION
from capability_support import GovernanceWorld
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

INGEST = 'SELECT forge.cap_invocation_ingest(%s,%s,%s::jsonb)'
BROKER = 'SELECT forge.cap_invocation_record_broker(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'


def event(**change):
    item = {'event_id': str(uuid4()), 'capability_id': 'tool:code_execute', 'at': '2026-10-12T12:00:00Z', 'outcome': 'ok', 'duration_ms': 120, 'sandbox_level': 3}
    item.update(change)
    return {key: value for key, value in item.items() if value is not None}


class InvocationProfileTests(unittest.TestCase):
    def test_0040_follows_0039_with_its_own_pinned_checkpoint(self):
        self.assertEqual(TOOL_INVOCATION_LOG_MIGRATION, '0040_tool_invocation_log.sql')
        self.assertEqual(MVP_ADDITIONS[at(TOOL_INVOCATION_LOG_MIGRATION) - 1], '0039_capability_policy.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(TOOL_INVOCATION_LOG_MIGRATION):at(TOOL_INVOCATION_LOG_MIGRATION) + 2], (F39, F40))
        self.assertRegex(F40 or '', r'^[0-9a-f]{64}$', 'F40 must be pinned')
        self.assertNotEqual(F40, F39)


class InvocationFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0039_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(TOOL_INVOCATION_LOG_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, TOOL_INVOCATION_LOG_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F39)
            conn.execute(migration_text(TOOL_INVOCATION_LOG_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0040 tool invocation log checkpoint F40:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0039 must be identical')
        self.assertEqual(fresh, F40, 'F40 must be pinned to the reviewed value')


class IngestTests(GovernanceWorld, unittest.TestCase):
    def ingest(self, who, org, events):
        return self.role.call(INGEST, (self.digest[who], org, json.dumps(events)))[0][0]

    def rows(self):
        return self.db.admin.execute('SELECT event_id,organization_id,capability_id,outcome,duration_ms,sandbox_level,source FROM forge.tool_invocation_log').fetchall()

    def test_a_batch_is_stored_once_and_a_replay_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            batch = [event(), event(capability_id='skill:pdf', sandbox_level=None, outcome='error')]
            self.assertEqual(self.ingest('member_a', self.org_a, batch), 2)
            self.assertEqual(self.ingest('member_a', self.org_a, batch), 0, 'the same event ids store nothing')
            self.assertEqual(self.ingest('member_a', self.org_a, [batch[0], event()]), 1)
            stored = {row[0]: row for row in self.rows()}
            self.assertEqual(len(stored), 3)
            first = stored[__import__('uuid').UUID(batch[0]['event_id'])]
            self.assertEqual(first[1:], (self.org_a, 'tool:code_execute', 'ok', 120, 3, 'client'))
            member = db.admin.execute('SELECT membership_id FROM forge.tool_invocation_log LIMIT 1').fetchone()[0]
            expected = db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s', (self.member_a.email,)).fetchone()[0]
            self.assertEqual(member, expected, 'the member comes from the session, never from the payload')

    def test_content_fields_and_unknown_keys_are_refused_and_the_whole_batch_is_rolled_back(self):
        with mvp_database() as db:
            self.build(db)
            good = event()
            bad = (event(arguments='{"path":"C:\\\\secret"}'), event(output='hello'), event(prompt='x'), {**event(), 'extra': 1},
                   {k: v for k, v in event().items() if k != 'outcome'}, event(outcome='exploded'), event(duration_ms=-1), event(duration_ms=10 ** 9),
                   event(sandbox_level=5), event(capability_id='Bad Id'), event(capability_id='x' * 200), event(event_id='not-a-uuid'),
                   event(at='yesterday'), event(at='now'), event(duration_ms='12x'), event(duration_ms=True), 'string', 5, None, [])
            for item in bad:
                with self.subTest(item=str(item)[:60]):
                    code = self.role.refusal(INGEST, (self.digest['member_a'], self.org_a, json.dumps([good, item])))
                    self.assertEqual(code, 'CAP_INVALID')
            self.assertEqual(self.rows(), [], 'a refused batch stores nothing, not even its valid events')
            for events in ([], [event() for _ in range(101)], {}, 'x', None):
                self.assertEqual(self.role.refusal(INGEST, (self.digest['member_a'], self.org_a, json.dumps(events))), 'CAP_INVALID')
            self.assertEqual(self.ingest('member_a', self.org_a, [event() for _ in range(100)]), 100)

    def test_a_stranger_another_company_and_a_suspended_company_are_denied_and_store_nothing(self):
        with mvp_database() as db:
            self.build(db)
            for digest, org in ((self.digest['member_a'], self.org_b), (self.digest['member_b'], self.org_a), ('0' * 64, self.org_a), (self.digest['member_a'], uuid4())):
                self.assertEqual(self.role.refusal(INGEST, (digest, org, json.dumps([event()]))), 'CAP_DENIED')
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org_a,))
            self.assertEqual(self.role.refusal(INGEST, (self.digest['member_a'], self.org_a, json.dumps([event()]))), 'CAP_DENIED')
            self.assertEqual(self.rows(), [])


class StorageTests(GovernanceWorld, unittest.TestCase):
    def test_the_broker_path_is_internal_records_metadata_and_dedupes(self):
        with mvp_database() as db:
            self.build(db)
            member = db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s', (self.member_a.email,)).fetchone()[0]
            for role in ('forge_capability_service', 'forge_platform_service', 'public'):
                self.assertEqual(db.admin.execute("SELECT has_function_privilege(%s,'forge.cap_invocation_record_broker(uuid,uuid,uuid,text,text,integer,text,text,bigint,bigint,integer)','EXECUTE')",
                                                  (role,)).fetchone(), (False,), role)
            self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_capability_service','forge.cap_invocation_ingest(text,uuid,jsonb)','EXECUTE')").fetchone(), (True,))
            db.admin.execute('SET ROLE forge_capability_authority')
            try:
                event_id = uuid4()
                arguments = (self.org_a, member, event_id, 'connector:github', 'ok', 42, 'tools/call', 'create_issue', 100, 2000, 200)
                self.assertTrue(db.admin.execute(BROKER, arguments).fetchone()[0])
                self.assertFalse(db.admin.execute(BROKER, arguments).fetchone()[0])
                with self.assertRaises(errors.RaiseException) as caught:
                    db.admin.execute(BROKER, (self.org_a, member, uuid4(), 'connector:github', 'exploded', 1, None, None, None, None, None))
                self.assertEqual(caught.exception.diag.message_primary, 'CAP_INVALID')
            finally:
                db.admin.execute('RESET ROLE')
            self.assertEqual(db.admin.execute('SELECT source,method,tool_name,status_code,bytes_in,bytes_out FROM forge.tool_invocation_log').fetchall(),
                             [('broker', 'tools/call', 'create_issue', 200, 100, 2000)])

    def test_no_column_holds_content_and_no_role_can_change_or_remove_a_row(self):
        with mvp_database() as db:
            columns = {row[0]: row[1] for row in db.admin.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='forge' AND table_name='tool_invocation_log'")}
            self.assertEqual({name for name, kind in columns.items() if kind == 'text'}, {'capability_id', 'outcome', 'source', 'method', 'tool_name'})
            self.assertFalse([name for name in columns if any(word in name for word in ('argument', 'output', 'prompt', 'content', 'body', 'path', 'message'))])
            for role in ('forge_capability_authority', 'forge_capability_service', 'forge_gateway_authority', 'forge_runtime'):
                for privilege in ('UPDATE', 'DELETE', 'TRUNCATE'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.tool_invocation_log',%s)", (role, privilege)).fetchone(), (False,), (role, privilege))
            for role in ('forge_capability_service', 'forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'public'):
                self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.tool_invocation_log','SELECT,INSERT')", (role,)).fetchone(), (False,), role)
            self.assertEqual(db.admin.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='forge.tool_invocation_log'::regclass").fetchone(), (True, True))


if __name__ == '__main__':
    unittest.main()
