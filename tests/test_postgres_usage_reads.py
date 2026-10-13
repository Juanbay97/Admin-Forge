"""Owned PostgreSQL 0037 usage reads: the verified owner reads per company, per model and totals over a bounded range; a company
administrator reads per-person usage of the own company only (suspended members included); nobody else reads anything."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from psycopg import errors
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.invitations import capability_digest
from forge.mvp_profile import F36, F37, MVP_ADDITIONS, MVP_CHECKPOINTS, USAGE_READS_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles
from test_postgres_usage_events import UsageWorld

TODAY = datetime.now(timezone.utc).date()  # the rollup day is the UTC day
YESTERDAY = TODAY - timedelta(days=1)
LAST_WEEK = TODAY - timedelta(days=7)
BY_COMPANY = 'SELECT * FROM forge.platform_usage_by_company(%s,%s,%s,%s,%s)'
BY_MODEL = 'SELECT * FROM forge.platform_usage_by_model(%s,%s,%s,%s,%s)'
TOTALS = 'SELECT * FROM forge.platform_usage_totals(%s,%s,%s)'
MEMBERS = 'SELECT * FROM forge.usage_company_members(%s,%s,%s,%s,%s,%s)'


class ReadsProfileTests(unittest.TestCase):
    def test_0037_follows_0036_with_its_own_pinned_checkpoint(self):
        self.assertEqual(USAGE_READS_MIGRATION, '0037_usage_reads.sql')
        self.assertEqual(MVP_ADDITIONS[at(USAGE_READS_MIGRATION) - 1], '0036_model_prices.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(USAGE_READS_MIGRATION):at(USAGE_READS_MIGRATION) + 2], (F36, F37))
        self.assertRegex(F37 or '', r'^[0-9a-f]{64}$', 'F37 must be pinned')
        self.assertNotEqual(F37, F36)


class ReadsFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0036_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(USAGE_READS_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, USAGE_READS_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F36)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(USAGE_READS_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0037 usage reads checkpoint F37:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0036 must be identical')
        self.assertEqual(fresh, F37, 'F37 must be pinned to the reviewed value')


class ReadsWorld(UsageWorld):
    def build_reads(self, db):
        self.build(db)
        add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=True)
        self.first_a, self.second_a = self.members[self.org_a]
        self.first_b = self.members[self.org_b][0]
        price = db.admin.execute("INSERT INTO forge.model_prices(upstream_id,version,input_micros,output_micros,effective_from,set_by) "
                                 "SELECT 'up/model-a',1,1000000,2000000,now()-interval '30 days',account_id FROM forge.platform_roles RETURNING id").fetchone()[0]
        for org, member, upstream, prompt, completion in ((self.org_a, self.first_a, 'up/model-a', 1000, 500), (self.org_a, self.first_a, 'up/model-b', 10, 10),
                                                          (self.org_a, self.second_a, 'up/model-a', 2000, 1000), (self.org_b, self.first_b, 'up/model-a', 300, 100)):
            self.record(org, member, upstream=upstream, prompt=prompt, completion=completion)
        # Older days are written directly (the record function stamps today).
        db.admin.execute("INSERT INTO forge.usage_daily(day,organization_id,membership_id,upstream_id,key_id,requests,prompt_tokens,completion_tokens,cost_micros) "
                         "VALUES(%s,%s,%s,'up/model-a','00000000-0000-0000-0000-000000000000',4,4000,2000,8000)", (LAST_WEEK, self.org_a, self.first_a))
        db.admin.execute("INSERT INTO forge.usage_daily(day,organization_id,membership_id,upstream_id,key_id,requests,prompt_tokens,completion_tokens,cost_micros) "
                         "VALUES(%s,%s,%s,'up/model-a','00000000-0000-0000-0000-000000000000',1,50,50,100)", (YESTERDAY, self.org_b, self.first_b))


class PlatformReportTests(ReadsWorld):
    def test_the_owner_reads_per_company_per_model_and_totals_over_a_bounded_range(self):
        with mvp_database() as db:
            self.build_reads(db)
            companies = {row[0]: row[3:] for row in call(db, BY_COMPANY, (self.digest, LAST_WEEK, TODAY, None, 50))}
            self.assertEqual(companies[self.org_a], (7, 7010, 3510, 0, 0, 14000, 1))  # (requests, prompt, completion, estimated, errors, cost, unpriced)
            self.assertEqual(companies[self.org_b], (2, 350, 150, 0, 0, 600, 0))
            self.assertEqual({row[1] for row in call(db, BY_COMPANY, (self.digest, LAST_WEEK, TODAY, None, 50))}, {'org-a', 'org-b'})
            models = {row[0]: row[1:] for row in call(db, BY_MODEL, (self.digest, LAST_WEEK, TODAY, None, 50))}
            self.assertEqual(models, {'up/model-a': (8, 7350, 3650, 0, 0, 14600, 0), 'up/model-b': (1, 10, 10, 0, 0, 0, 1)})
            self.assertEqual(call(db, TOTALS, (self.digest, LAST_WEEK, TODAY)), [(2, 9, 7360, 3660, 0, 0, 14600, 1)])

    def test_only_the_days_in_the_range_are_aggregated(self):
        with mvp_database() as db:
            self.build_reads(db)
            self.assertEqual(call(db, TOTALS, (self.digest, TODAY, TODAY))[0][:2], (2, 4))
            week = call(db, TOTALS, (self.digest, LAST_WEEK, YESTERDAY))[0]
            self.assertEqual((week[1], week[2]), (5, 4050))
            self.assertEqual(call(db, TOTALS, (self.digest, TODAY + timedelta(days=30), TODAY + timedelta(days=31)))[0], (0,) * 8)

    def test_pagination_is_keyset_and_bounds_are_enforced(self):
        with mvp_database() as db:
            self.build_reads(db)
            low, high = sorted([self.org_a, self.org_b])
            self.assertEqual([row[0] for row in call(db, BY_COMPANY, (self.digest, LAST_WEEK, TODAY, None, 1))], [low])
            self.assertEqual([row[0] for row in call(db, BY_COMPANY, (self.digest, LAST_WEEK, TODAY, low, 1))], [high])
            self.assertEqual(call(db, BY_COMPANY, (self.digest, LAST_WEEK, TODAY, high, 1)), [])
            self.assertEqual([row[0] for row in call(db, BY_MODEL, (self.digest, LAST_WEEK, TODAY, 'up/model-a', 5))], ['up/model-b'])
            for arguments in ((TODAY, LAST_WEEK, None, 10), (TODAY - timedelta(days=400), TODAY, None, 10), (LAST_WEEK, TODAY, None, 0),
                              (LAST_WEEK, TODAY, None, 101), (None, TODAY, None, 10)):
                with self.subTest(arguments=str(arguments)[:40]):
                    self.assertEqual(refusal(self, lambda: call(db, BY_COMPANY, (self.digest, *arguments))), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: call(db, TOTALS, (self.digest, TODAY - timedelta(days=366), TODAY))), 'PLATFORM_INVALID')
            self.assertEqual(len(call(db, TOTALS, (self.digest, TODAY - timedelta(days=365), TODAY))), 1)

    def test_a_company_administrator_a_stale_digest_and_an_unverified_session_are_denied(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin = self.results[0].accounts[0]
            _, admin_digest = sign_in(db, admin.email, admin.password)
            for query, arguments in ((BY_COMPANY, (LAST_WEEK, TODAY, None, 10)), (BY_MODEL, (LAST_WEEK, TODAY, None, 10)), (TOTALS, (LAST_WEEK, TODAY))):
                self.assertEqual(refusal(self, lambda: call(db, query, (admin_digest, *arguments))), 'PLATFORM_DENIED')
                self.assertEqual(refusal(self, lambda: call(db, query, ('0' * 64, *arguments))), 'PLATFORM_DENIED')
            _, unverified = sign_in(db)
            self.assertEqual(refusal(self, lambda: call(db, TOTALS, (unverified, LAST_WEEK, TODAY))), 'MFA_REQUIRED')


class CompanyReportTests(ReadsWorld):
    def report(self, digest, org, *arguments):
        return call(self.db, MEMBERS, (digest, org, *arguments), role='forge_gateway_service')

    def test_an_administrator_reads_per_person_usage_of_the_own_company_only_with_names(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin = self.results[0].accounts[0]
            _, digest = sign_in(db, admin.email, admin.password)
            rows = {row[0]: row for row in self.report(digest, self.org_a, LAST_WEEK, TODAY, None, 50)}
            self.assertEqual(set(rows), {self.first_a, self.second_a})
            self.assertEqual(rows[self.first_a][4:], (6, 5010, 2510, 0, 0, 10000, 1))  # (requests, prompt, completion, estimated, errors, cost, unpriced)
            self.assertEqual(rows[self.second_a][4:], (1, 2000, 1000, 0, 0, 4000, 0))
            self.assertEqual({(row[1], row[3]) for row in rows.values()}, {(self.results[0].accounts[0].email, 'active'), (self.results[0].accounts[1].email, 'active')})
            self.assertEqual(refusal(self, lambda: self.report(digest, self.org_b, LAST_WEEK, TODAY, None, 50)), 'DIRECTORY_DENIED')

    def test_suspended_members_history_stays_visible_and_members_and_stale_sessions_are_denied(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin, member = self.results[0].accounts
            _, digest = sign_in(db, admin.email, admin.password)
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (self.second_a,))
            rows = self.report(digest, self.org_a, LAST_WEEK, TODAY, None, 50)
            self.assertEqual({(row[0], row[3]) for row in rows}, {(self.first_a, 'active'), (self.second_a, 'suspended')})
            _, member_digest = sign_in(db, member.email, member.password)
            self.assertEqual(refusal(self, lambda: self.report(member_digest, self.org_a, LAST_WEEK, TODAY, None, 50)), 'DIRECTORY_DENIED')
            self.assertEqual(refusal(self, lambda: self.report('0' * 64, self.org_a, LAST_WEEK, TODAY, None, 50)), 'DIRECTORY_DENIED')
            for arguments in ((TODAY, LAST_WEEK, None, 10), (LAST_WEEK, TODAY, None, 0), (LAST_WEEK - timedelta(days=400), TODAY, None, 10)):
                self.assertEqual(refusal(self, lambda: self.report(digest, self.org_a, *arguments)), 'DIRECTORY_INVALID')
            low = min(self.first_a, self.second_a)
            self.assertEqual(len(self.report(digest, self.org_a, LAST_WEEK, TODAY, low, 50)), 1)

    def test_the_service_pool_still_holds_no_table_privilege_on_usage(self):
        with mvp_database() as db:
            for table in ('usage_daily', 'usage_events', 'model_prices'):
                for role in ('forge_gateway_service', 'forge_platform_service'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT')", (role, 'forge.' + table)).fetchone(), (False,))


if __name__ == '__main__':
    unittest.main()
