"""Owned PostgreSQL 0043 platform company members: the verified owner reads one company's members (names, roles, departments,
suspended included) with keyset pages; every other caller is denied and the platform pool gained no table privilege."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F42, F43, MVP_ADDITIONS, MVP_CHECKPOINTS, PLATFORM_MEMBERS_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import OWNER_EMAIL, PASSWORD, add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_http import BASE, Person, code_for
from test_postgres_platform_schema import drop_platform_roles

MEMBERS = 'SELECT * FROM forge.platform_company_members(%s,%s,%s,%s)'


class MembersProfileTests(unittest.TestCase):
    def test_0043_follows_0042_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_MEMBERS_MIGRATION, '0043_platform_members.sql')
        self.assertEqual(MVP_ADDITIONS[at(PLATFORM_MEMBERS_MIGRATION) - 1], '0042_usage_me.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(PLATFORM_MEMBERS_MIGRATION):at(PLATFORM_MEMBERS_MIGRATION) + 2], (F42, F43))
        self.assertRegex(F43 or '', r'^[0-9a-f]{64}$', 'F43 must be pinned')
        self.assertNotEqual(F43, F42)


class MembersFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0042_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(PLATFORM_MEMBERS_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_MEMBERS_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F42)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(PLATFORM_MEMBERS_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0043 platform members checkpoint F43:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0042 must be identical')
        self.assertEqual(fresh, F43, 'F43 must be pinned to the reviewed value')


class MembersFunctionTests(unittest.TestCase):
    def world(self, db):
        self.results = provision(db.admin, SEED, lambda created: None)
        self.org_a, self.org_b = self.results[0].organization_id, self.results[1].organization_id
        add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=True)

    def test_the_owner_reads_the_members_of_one_company_with_roles_and_departments(self):
        with mvp_database() as db:
            self.world(db)
            rows = call(db, MEMBERS, (self.digest, self.org_a, None, 50))
            by_email = {row[1]: row for row in rows}
            admin, member = self.results[0].accounts
            self.assertEqual(set(by_email), {admin.email, member.email})
            self.assertEqual(by_email[admin.email][3:5], ('active', ['organization_admin']))
            self.assertEqual(by_email[member.email][3:5], ('active', ['member']))
            self.assertEqual([department['name'] for department in by_email[member.email][5]], ['Operations'])
            self.assertEqual([row[0] for row in rows], sorted(row[0] for row in rows), 'ordered by id for the keyset')
            self.assertEqual({row[1] for row in call(db, MEMBERS, (self.digest, self.org_b, None, 50))}, {account.email for account in self.results[1].accounts})

    def test_suspended_members_are_listed_and_pages_are_keyset(self):
        with mvp_database() as db:
            self.world(db)
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=(SELECT id FROM forge.memberships WHERE organization_id=%s ORDER BY id DESC LIMIT 1)",
                             (self.org_a, self.org_a))
            rows = call(db, MEMBERS, (self.digest, self.org_a, None, 50))
            self.assertEqual({row[3] for row in rows}, {'active', 'suspended'})
            first = call(db, MEMBERS, (self.digest, self.org_a, None, 1))
            second = call(db, MEMBERS, (self.digest, self.org_a, first[0][0], 1))
            self.assertEqual([first[0][0], second[0][0]], [row[0] for row in rows])
            self.assertEqual(call(db, MEMBERS, (self.digest, self.org_a, second[0][0], 1)), [])

    def test_bounds_unknown_companies_and_every_other_caller(self):
        with mvp_database() as db:
            self.world(db)
            for page in (0, 101, None):
                self.assertEqual(refusal(self, lambda: call(db, MEMBERS, (self.digest, self.org_a, None, page))), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: call(db, MEMBERS, (self.digest, uuid4(), None, 10))), 'PLATFORM_NOT_FOUND')
            self.assertEqual(refusal(self, lambda: call(db, MEMBERS, (self.digest, None, None, 10))), 'PLATFORM_NOT_FOUND')
            admin = self.results[0].accounts[0]
            _, admin_digest = sign_in(db, admin.email, admin.password)
            _, unverified = sign_in(db)
            self.assertEqual(refusal(self, lambda: call(db, MEMBERS, (admin_digest, self.org_a, None, 10))), 'PLATFORM_DENIED')
            self.assertEqual(refusal(self, lambda: call(db, MEMBERS, ('0' * 64, self.org_a, None, 10))), 'PLATFORM_DENIED')
            self.assertEqual(refusal(self, lambda: call(db, MEMBERS, (unverified, self.org_a, None, 10))), 'MFA_REQUIRED')

    def test_the_platform_pools_gained_no_table_privilege_and_no_secret_column_is_readable(self):
        with mvp_database() as db:
            for table in ('memberships', 'membership_roles', 'membership_departments', 'departments', 'owned_accounts'):
                for role in ('forge_platform_service', 'forge_gateway_service', 'forge_capability_service'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT')", (role, 'forge.' + table)).fetchone(), (False,), (role, table))
            for column in ('password_hash',):
                self.assertEqual(db.admin.execute("SELECT has_column_privilege('forge_platform_authority','forge.owned_accounts',%s,'SELECT')", (column,)).fetchone(), (False,))
            self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_platform_service','forge.platform_company_members(text,uuid,uuid,integer)','EXECUTE')").fetchone(), (True,))
            self.assertEqual(db.admin.execute("SELECT has_function_privilege('public','forge.platform_company_members(text,uuid,uuid,integer)','EXECUTE')").fetchone(), (False,))


class MembersHttpTests(unittest.TestCase):
    def test_the_owner_lists_company_members_over_http_and_company_people_are_denied(self):
        with stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            owner = login(client, Person(OWNER_EMAIL, PASSWORD))
            enrollment = client.post(BASE + '/mfa/enroll', headers=owner).json()
            self.assertEqual(client.post(BASE + '/login/mfa', headers=owner, json={'code': code_for(enrollment['secret'])}).status_code, 200)
            path = BASE + '/companies/%s/members' % results[0].organization_id
            listed = client.get(path, headers=owner)
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual({item['email'] for item in listed.json()['members']}, {account.email for account in results[0].accounts})
            self.assertEqual(listed.json()['next_after'], None)
            self.assertNotIn('password', listed.text)
            one = client.get(path, headers=owner, params={'page': '1'}).json()
            self.assertEqual((len(one['members']), one['next_after'] is not None), (1, True))
            self.assertEqual(client.get(BASE + '/companies/%s/members' % uuid4(), headers=owner).status_code, 404)
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                response = client.get(path, headers=login(client, account))
                self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(client.get(path).status_code, 401)


if __name__ == '__main__':
    unittest.main()
