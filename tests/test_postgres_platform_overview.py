"""Owned PostgreSQL 0044 platform overview and per-day series: the verified owner reads company counts, active people, totals and the
previous period in one call, plus a zero-filled daily series; every other caller is denied and nothing leaks content."""
from datetime import timedelta
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F43, F44, MVP_ADDITIONS, MVP_CHECKPOINTS, PLATFORM_OVERVIEW_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import OWNER_EMAIL, PASSWORD, add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_http import BASE, Person, code_for
from test_postgres_platform_schema import drop_platform_roles
from test_postgres_usage_reads import LAST_WEEK, TODAY, YESTERDAY, ReadsWorld
from test_postgres_usage_reports_http import record

OVERVIEW = 'SELECT * FROM forge.platform_overview(%s,%s,%s)'
DAYS = 'SELECT * FROM forge.platform_usage_days(%s,%s,%s)'


class OverviewProfileTests(unittest.TestCase):
    def test_0044_follows_0043_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_OVERVIEW_MIGRATION, '0044_platform_overview.sql')
        self.assertEqual(MVP_ADDITIONS[at(PLATFORM_OVERVIEW_MIGRATION) - 1], '0043_platform_members.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(PLATFORM_OVERVIEW_MIGRATION):at(PLATFORM_OVERVIEW_MIGRATION) + 2], (F43, F44))
        self.assertRegex(F44 or '', r'^[0-9a-f]{64}$', 'F44 must be pinned')
        self.assertNotEqual(F44, F43)


class OverviewFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0043_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(PLATFORM_OVERVIEW_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_OVERVIEW_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F43)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(PLATFORM_OVERVIEW_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0044 platform overview checkpoint F44:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0043 must be identical')
        self.assertEqual(fresh, F44, 'F44 must be pinned to the reviewed value')


class OverviewTests(ReadsWorld):
    # row: (active companies, suspended, active people, requests, prompt, completion, estimated, errors, cost, unpriced, then the previous
    # period: active people, requests, prompt, completion, cost)
    def test_the_owner_reads_companies_people_totals_and_the_previous_period(self):
        with mvp_database() as db:
            self.build_reads(db)
            (row,) = call(db, OVERVIEW, (self.digest, LAST_WEEK, TODAY))
            self.assertEqual(row[:10], (2, 0, 3, 9, 7360, 3660, 0, 0, 14600, 1))
            self.assertEqual(row[10:], (0, 0, 0, 0, 0), 'nothing happened in the eight days before')
            (today,) = call(db, OVERVIEW, (self.digest, TODAY, TODAY))
            self.assertEqual(today[:3], (2, 0, 3))
            self.assertEqual(today[10:], (1, 1, 50, 50, 100), 'the previous period of one day is yesterday: one person, one request')

    def test_suspended_companies_are_counted_apart(self):
        with mvp_database() as db:
            self.build_reads(db)
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org_b,))
            (row,) = call(db, OVERVIEW, (self.digest, LAST_WEEK, TODAY))
            self.assertEqual(row[:2], (1, 1))

    def test_an_empty_range_is_one_row_of_zeros_and_ranges_are_bounded(self):
        with mvp_database() as db:
            self.build_reads(db)
            quiet = TODAY + timedelta(days=30)
            self.assertEqual(call(db, OVERVIEW, (self.digest, quiet, quiet))[0][2:], (0,) * 13)
            for arguments in ((TODAY, LAST_WEEK), (TODAY - timedelta(days=366), TODAY), (None, TODAY), (LAST_WEEK, None)):
                with self.subTest(arguments=str(arguments)[:40]):
                    self.assertEqual(refusal(self, lambda: call(db, OVERVIEW, (self.digest, *arguments))), 'PLATFORM_INVALID')
                    self.assertEqual(refusal(self, lambda: call(db, DAYS, (self.digest, *arguments))), 'PLATFORM_INVALID')
            self.assertEqual(len(call(db, OVERVIEW, (self.digest, TODAY - timedelta(days=365), TODAY))), 1)

    def test_a_company_administrator_a_stale_digest_and_an_unverified_session_are_denied(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin = self.results[0].accounts[0]
            _, admin_digest = sign_in(db, admin.email, admin.password)
            _, unverified = sign_in(db)
            for query in (OVERVIEW, DAYS):
                self.assertEqual(refusal(self, lambda: call(db, query, (admin_digest, LAST_WEEK, TODAY))), 'PLATFORM_DENIED')
                self.assertEqual(refusal(self, lambda: call(db, query, ('0' * 64, LAST_WEEK, TODAY))), 'PLATFORM_DENIED')
                self.assertEqual(refusal(self, lambda: call(db, query, (unverified, LAST_WEEK, TODAY))), 'MFA_REQUIRED')


class DaysTests(ReadsWorld):
    def test_every_day_is_present_in_order_and_the_sums_equal_the_totals(self):
        with mvp_database() as db:
            self.build_reads(db)
            rows = call(db, DAYS, (self.digest, LAST_WEEK, TODAY))
            self.assertEqual([row[0] for row in rows], [LAST_WEEK + timedelta(days=offset) for offset in range(8)])
            by_day = {row[0]: row[1:] for row in rows}
            # (requests, prompt, completion, estimated, errors, cost, unpriced, active people)
            self.assertEqual(by_day[LAST_WEEK], (4, 4000, 2000, 0, 0, 8000, 0, 1))
            self.assertEqual(by_day[YESTERDAY], (1, 50, 50, 0, 0, 100, 0, 1))
            self.assertEqual(by_day[TODAY], (4, 3310, 1610, 0, 0, 6500, 1, 3))
            self.assertEqual(by_day[LAST_WEEK + timedelta(days=2)], (0,) * 8)
            (total,) = call(db, 'SELECT * FROM forge.platform_usage_totals(%s,%s,%s)', (self.digest, LAST_WEEK, TODAY))
            self.assertEqual([sum(row[index] for row in rows) for index in (1, 2, 3, 6)], [total[1], total[2], total[3], total[6]])
            self.assertEqual(len(call(db, DAYS, (self.digest, TODAY, TODAY))), 1)

    def test_the_platform_pool_gained_no_table_privilege(self):
        with mvp_database() as db:
            for function in ('forge.platform_overview(text,date,date)', 'forge.platform_usage_days(text,date,date)'):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', ('forge_platform_service', function, 'EXECUTE')).fetchone(), (True,))
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', ('public', function, 'EXECUTE')).fetchone(), (False,))
            self.assertEqual(db.admin.execute("SELECT has_table_privilege('forge_platform_service','forge.usage_daily','SELECT')").fetchone(), (False,))


class OverviewHttpTests(unittest.TestCase):
    def test_the_owner_reads_the_overview_and_the_series_over_http_and_company_people_are_denied(self):
        with stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            owner = login(client, Person(OWNER_EMAIL, PASSWORD))
            enrollment = client.post(BASE + '/mfa/enroll', headers=owner).json()
            self.assertEqual(client.post(BASE + '/login/mfa', headers=owner, json={'code': code_for(enrollment['secret'])}).status_code, 200)
            ids = {r.slug: db.admin.execute('SELECT id FROM forge.memberships WHERE organization_id=%s ORDER BY id', (r.organization_id,)).fetchone()[0] for r in results}
            record(db, results[0].organization_id, ids['org-a'], 'up/model-a', 1000, 500)
            record(db, results[1].organization_id, ids['org-b'], 'up/model-a', 10, 10)
            window = {'from': TODAY.isoformat(), 'to': TODAY.isoformat()}
            overview = client.get(BASE + '/overview', headers=owner, params=window)
            self.assertEqual(overview.status_code, 200, overview.text)
            body = overview.json()
            self.assertEqual((body['companies'], body['active_users'], body['requests'], body['prompt_tokens']), ({'active': 2, 'suspended': 0}, 2, 2, 1010))
            self.assertEqual(set(body['previous']), {'active_users', 'requests', 'prompt_tokens', 'completion_tokens', 'cost_micros'})
            series = client.get(BASE + '/usage/days', headers=owner, params={'from': (TODAY - timedelta(days=2)).isoformat(), 'to': TODAY.isoformat()}).json()['days']
            self.assertEqual([item['day'] for item in series], [(TODAY - timedelta(days=offset)).isoformat() for offset in (2, 1, 0)])
            self.assertEqual((series[-1]['requests'], series[-1]['active_users'], series[0]['requests']), (2, 2, 0))
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                headers = login(client, account)
                for path in ('/overview', '/usage/days'):
                    response = client.get(BASE + path, headers=headers, params=window)
                    self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(client.get(BASE + '/overview', params=window).status_code, 401)
            self.assertEqual(client.get(BASE + '/overview', headers=owner, params={'from': '2020-01-01', 'to': TODAY.isoformat()}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
