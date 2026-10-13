"""Owned PostgreSQL 0035 usage storage: one idempotent event per inference and a same-transaction daily rollup; the service pool
can only record (it holds no table privilege) and no row carries prompt or response content."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F34, F35, MVP_ADDITIONS, MVP_CHECKPOINTS, USAGE_EVENTS_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

NIL = '00000000-0000-0000-0000-000000000000'
RECORD = 'SELECT forge.usage_record(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'


class UsageProfileTests(unittest.TestCase):
    def test_0035_follows_0034_with_its_own_pinned_checkpoint(self):
        self.assertEqual(USAGE_EVENTS_MIGRATION, '0035_usage_events.sql')
        self.assertEqual(MVP_ADDITIONS[at(USAGE_EVENTS_MIGRATION) - 1], '0034_gateway_admin_readonly.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(USAGE_EVENTS_MIGRATION):at(USAGE_EVENTS_MIGRATION) + 2], (F34, F35))
        self.assertRegex(F35 or '', r'^[0-9a-f]{64}$', 'F35 must be pinned')
        self.assertNotEqual(F35, F34)


class UsageFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0034_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(USAGE_EVENTS_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, USAGE_EVENTS_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F34)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(USAGE_EVENTS_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0035 usage events checkpoint F35:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0034 must be identical')
        self.assertEqual(fresh, F35, 'F35 must be pinned to the reviewed value')


class UsageWorld(unittest.TestCase):
    def build(self, db):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.org_a, self.org_b = results[0].organization_id, results[1].organization_id
        ids = {row[1]: row[0] for row in db.admin.execute('SELECT id,organization_id FROM forge.memberships ORDER BY id')}
        self.members = {org: [row[0] for row in db.admin.execute('SELECT id FROM forge.memberships WHERE organization_id=%s ORDER BY id', (org,))]
                        for org in (self.org_a, self.org_b)}

    def record(self, org, member, *, event=None, alias='assistant', upstream='up/model-a', key=None, prompt=10, completion=5, latency=120,
               first_byte=30, outcome='ok', failure=None, source='gateway'):
        event = event or uuid4()
        with self.db.pool('forge_gateway_service').connection() as connection:
            row = connection.execute(RECORD, (org, member, event, alias, upstream, key, prompt, completion, latency, first_byte, outcome,
                                              failure, source)).fetchone()
        return event, row[0]

    def daily(self):
        return self.db.admin.execute('SELECT organization_id,membership_id,upstream_id,key_id::text,requests,prompt_tokens,completion_tokens,'
                                     'estimated_requests,error_requests,unpriced_requests FROM forge.usage_daily ORDER BY 1,2,3,4').fetchall()


class RecordTests(UsageWorld):
    def test_an_event_is_stored_once_and_a_retry_with_the_same_id_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            member = self.members[self.org_a][0]
            event, written = self.record(self.org_a, member)
            self.assertTrue(written)
            self.assertEqual(self.record(self.org_a, member, event=event, prompt=999)[1], False)
            row = db.admin.execute('SELECT organization_id,membership_id,model_alias,upstream_id,prompt_tokens,completion_tokens,latency_ms,ttfb_ms,'
                                   'status,error_code,usage_source,price_id,cost_micros FROM forge.usage_events WHERE event_id=%s', (event,)).fetchone()
            self.assertEqual(row, (self.org_a, member, 'assistant', 'up/model-a', 10, 5, 120, 30, 'ok', None, 'gateway', None, None))
            self.assertEqual(self.daily(), [(self.org_a, member, 'up/model-a', NIL, 1, 10, 5, 0, 0, 1)])

    def test_the_daily_rollup_equals_the_sum_of_its_events_per_member_model_and_key(self):
        with mvp_database() as db:
            self.build(db)
            first, second = self.members[self.org_a]
            key = db.admin.execute("INSERT INTO forge.gateway_keys(id,label,origin) VALUES(gen_random_uuid(),'k','https://gw.example') RETURNING id").fetchone()[0]
            for member, upstream, kid, prompt, completion, outcome, source in (
                    (first, 'up/model-a', None, 10, 5, 'ok', 'gateway'), (first, 'up/model-a', None, 7, 3, 'cancelled', 'estimated'),
                    (first, 'up/model-a', key, 4, 2, 'ok', 'gateway'), (first, 'up/model-b', None, 1, 1, 'error', 'estimated'),
                    (second, 'up/model-a', None, 20, 8, 'ok', 'gateway')):
                self.record(self.org_a, member, upstream=upstream, key=kid, prompt=prompt, completion=completion, outcome=outcome,
                            failure='INFERENCE_UNAVAILABLE' if outcome == 'error' else None, source=source)
            self.record(self.org_b, self.members[self.org_b][0], prompt=100, completion=50)
            rolled = {(row[0], row[1], row[2], row[3]): row[4:] for row in self.daily()}
            self.assertEqual(rolled[(self.org_a, first, 'up/model-a', NIL)], (2, 17, 8, 1, 0, 2))
            self.assertEqual(rolled[(self.org_a, first, 'up/model-a', str(key))], (1, 4, 2, 0, 0, 1))
            self.assertEqual(rolled[(self.org_a, first, 'up/model-b', NIL)], (1, 1, 1, 1, 1, 1))
            self.assertEqual(rolled[(self.org_a, second, 'up/model-a', NIL)], (1, 20, 8, 0, 0, 1))
            self.assertEqual(rolled[(self.org_b, self.members[self.org_b][0], 'up/model-a', NIL)], (1, 100, 50, 0, 0, 1))
            events = db.admin.execute('SELECT count(*),sum(prompt_tokens),sum(completion_tokens) FROM forge.usage_events').fetchone()
            daily = db.admin.execute('SELECT sum(requests),sum(prompt_tokens),sum(completion_tokens) FROM forge.usage_daily').fetchone()
            self.assertEqual(events, tuple(daily))
            self.assertEqual(events, (6, 142, 69))

    def test_invalid_input_and_a_member_of_another_company_are_refused_and_write_nothing(self):
        with mvp_database() as db:
            self.build(db)
            member = self.members[self.org_a][0]
            bad = ({'prompt': -1}, {'completion': 10 ** 13}, {'outcome': 'exploded'}, {'source': 'guess'}, {'alias': 'Bad Alias'},
                   {'upstream': 'has space'}, {'failure': 'lower'}, {'latency': -5}, {'key': uuid4()})
            for change in bad:
                with self.subTest(change=str(change)[:30]):
                    with self.assertRaises(errors.RaiseException) as caught:
                        self.record(self.org_a, member, **change)
                    self.assertEqual(caught.exception.diag.message_primary, 'USAGE_INVALID')
            with self.assertRaises(errors.RaiseException) as caught:
                self.record(self.org_b, member)  # a member of A recorded under B
            self.assertEqual(caught.exception.diag.message_primary, 'USAGE_INVALID')
            self.assertEqual(db.admin.execute('SELECT (SELECT count(*) FROM forge.usage_events),(SELECT count(*) FROM forge.usage_daily)').fetchone(), (0, 0))


class IsolationTests(UsageWorld):
    def test_the_service_pool_can_only_execute_record_and_no_role_but_the_authority_holds_any_table_privilege(self):
        with mvp_database() as db:
            self.build(db)
            for table in ('usage_events', 'usage_daily'):
                self.assertEqual(db.admin.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass', ('forge.' + table,)).fetchone(),
                                 (True, True))
                for role in ('forge_gateway_service', 'forge_account_service', 'forge_platform_service', 'forge_runtime', 'forge_branding_service', 'forge_enrollment'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, 'forge.' + table)).fetchone(), (False,), (role, table))
                with db.pool('forge_gateway_service').connection() as connection:
                    with self.assertRaises(errors.InsufficientPrivilege):
                        connection.execute('SELECT * FROM forge.%s' % table)
            self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_gateway_service','forge.usage_record(uuid,uuid,uuid,text,text,uuid,bigint,bigint,integer,integer,text,text,text)','EXECUTE')").fetchone(), (True,))

    def test_no_column_can_hold_prompt_or_response_content(self):
        with mvp_database() as db:
            columns = [row[0] for row in db.admin.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='forge' AND table_name IN ('usage_events','usage_daily') ORDER BY 1")]
            self.assertFalse([name for name in columns if any(word in name for word in ('content', 'prompt_text', 'message', 'response', 'body', 'text'))], columns)
            freeform = db.admin.execute(
                "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='forge' AND table_name IN ('usage_events','usage_daily') "
                "AND data_type='text' ORDER BY 1,2").fetchall()
            self.assertEqual(freeform, [('usage_daily', 'upstream_id'), ('usage_events', 'error_code'), ('usage_events', 'model_alias'),
                                        ('usage_events', 'status'), ('usage_events', 'upstream_id'), ('usage_events', 'usage_source')])


if __name__ == '__main__':
    unittest.main()
