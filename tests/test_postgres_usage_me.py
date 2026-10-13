"""Owned PostgreSQL 0042 member own usage: a member (or administrator) reads only the own counters of an active company, never
another person's, and the denial for strangers, stale sessions, suspended members and inactive companies is one uniform code."""
from datetime import timedelta
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F41, F42, MVP_ADDITIONS, MVP_CHECKPOINTS, USAGE_ME_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_schema import drop_platform_roles
from test_postgres_usage_reads import LAST_WEEK, ReadsWorld, TODAY
from test_postgres_usage_reports_http import RANGE, record

ME = 'SELECT * FROM forge.usage_member_me(%s,%s,%s,%s)'


class UsageMeProfileTests(unittest.TestCase):
    def test_0042_follows_0041_with_its_own_pinned_checkpoint(self):
        self.assertEqual(USAGE_ME_MIGRATION, '0042_usage_me.sql')
        self.assertEqual(MVP_ADDITIONS[at(USAGE_ME_MIGRATION) - 1], '0041_connector_secrets.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(USAGE_ME_MIGRATION):at(USAGE_ME_MIGRATION) + 2], (F41, F42))
        self.assertRegex(F42 or '', r'^[0-9a-f]{64}$', 'F42 must be pinned')
        self.assertNotEqual(F42, F41)


class UsageMeFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0041_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(USAGE_ME_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, USAGE_ME_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F41)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(USAGE_ME_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0042 member usage checkpoint F42:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0041 must be identical')
        self.assertEqual(fresh, F42, 'F42 must be pinned to the reviewed value')


class MemberUsageTests(ReadsWorld):
    def mine(self, digest, org, *arguments):
        return call(self.db, ME, (digest, org, *arguments), role='forge_gateway_service')

    def test_each_person_reads_only_the_own_counters(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin, member = self.results[0].accounts
            _, member_digest = sign_in(db, member.email, member.password)
            _, admin_digest = sign_in(db, admin.email, admin.password)
            # (requests, prompt, completion, estimated, errors, cost, unpriced): the member's own row only
            self.assertEqual(self.mine(member_digest, self.org_a, LAST_WEEK, TODAY), [(1, 2000, 1000, 0, 0, 4000, 0)])
            self.assertEqual(self.mine(admin_digest, self.org_a, LAST_WEEK, TODAY), [(6, 5010, 2510, 0, 0, 10000, 1)])
            self.assertEqual(self.mine(member_digest, self.org_a, TODAY, TODAY), [(1, 2000, 1000, 0, 0, 4000, 0)])
            quiet = TODAY + timedelta(days=30)
            self.assertEqual(self.mine(member_digest, self.org_a, quiet, quiet), [(0, 0, 0, 0, 0, 0, 0)])

    def test_strangers_stale_sessions_suspended_members_and_inactive_companies_are_one_denial(self):
        with mvp_database() as db:
            self.build_reads(db)
            admin, member = self.results[0].accounts
            _, member_digest = sign_in(db, member.email, member.password)
            _, other_digest = sign_in(db, self.results[1].accounts[0].email, self.results[1].accounts[0].password)
            for digest, org in ((member_digest, self.org_b), (other_digest, self.org_a), ('0' * 64, self.org_a), (member_digest, None)):
                self.assertEqual(refusal(self, lambda: self.mine(digest, org, LAST_WEEK, TODAY)), 'DIRECTORY_DENIED')
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org_a,))
            self.assertEqual(refusal(self, lambda: self.mine(member_digest, self.org_a, LAST_WEEK, TODAY)), 'DIRECTORY_DENIED')
            db.admin.execute('UPDATE forge.organizations SET active=true WHERE id=%s', (self.org_a,))
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (self.second_a,))
            self.assertEqual(refusal(self, lambda: self.mine(member_digest, self.org_a, LAST_WEEK, TODAY)), 'DIRECTORY_DENIED')

    def test_ranges_are_bounded(self):
        with mvp_database() as db:
            self.build_reads(db)
            _, digest = sign_in(db, self.results[0].accounts[1].email, self.results[0].accounts[1].password)
            for arguments in ((TODAY, LAST_WEEK), (LAST_WEEK - timedelta(days=400), TODAY), (None, TODAY), (LAST_WEEK, None)):
                with self.subTest(arguments=str(arguments)[:40]):
                    self.assertEqual(refusal(self, lambda: self.mine(digest, self.org_a, *arguments)), 'DIRECTORY_INVALID')
            self.assertEqual(len(self.mine(digest, self.org_a, TODAY - timedelta(days=365), TODAY)), 1)

    def test_only_the_gateway_service_pool_may_execute_it_and_it_gained_no_table_privilege(self):
        with mvp_database() as db:
            signature = 'forge.usage_member_me(text,uuid,date,date)'
            for role, expected in (('forge_gateway_service', True), ('forge_platform_service', False), ('forge_capability_service', False),
                                   ('forge_account_service', False), ('public', False)):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(), (expected,), role)
            for role in ('forge_gateway_service', 'forge_platform_service'):
                self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.usage_daily','SELECT')", (role,)).fetchone(), (False,))


class MemberUsageHttpTests(unittest.TestCase):
    def test_a_member_reads_own_usage_over_http_and_others_are_refused(self):
        with stack() as (db, client, results, root, secrets):
            org_a, org_b = results[0].organization_id, results[1].organization_id
            ids = [row[0] for row in db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id '
                                                      'WHERE m.organization_id=%s ORDER BY a.canonical_email', (org_a,))]
            record(db, org_a, ids[0], 'up/model-a', 1000, 500)
            record(db, org_a, ids[1], 'up/model-a', 20, 10)
            record(db, org_a, ids[1], 'up/model-b', 5, 5)
            admin, member = results[0].accounts
            path = '/forge/v1/orgs/%s/usage/me' % org_a
            headers = login(client, member)
            mine = client.get(path, headers=headers, params=RANGE)
            self.assertEqual(mine.status_code, 200, mine.text)
            self.assertEqual({key: mine.json()[key] for key in ('requests', 'prompt_tokens', 'completion_tokens')}, {'requests': 2, 'prompt_tokens': 25, 'completion_tokens': 15})
            self.assertEqual(client.get(path, headers=login(client, admin), params=RANGE).json()['prompt_tokens'], 1000, 'an administrator reads the own row too')
            denied = (client.get(path.replace(str(org_a), str(org_b)), headers=login(client, member), params=RANGE),
                      client.get(path, headers=login(client, results[1].accounts[0]), params=RANGE), client.get(path, params=RANGE))
            self.assertEqual([response.status_code for response in denied], [404, 404, 401])
            self.assertNotIn(str(ids[0]), mine.text)
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (ids[1],))
            self.assertEqual(client.get(path, headers=headers, params=RANGE).status_code, 404, 'a suspended member loses the route')


if __name__ == '__main__':
    unittest.main()
