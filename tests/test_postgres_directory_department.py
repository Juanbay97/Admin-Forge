"""Owned PostgreSQL 0045 member department assignment: an administrator sets exactly one department of the own company for a member;
a member, another company's administrator, a foreign or unknown department or member and a stale session are one denial."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import DIRECTORY_DEPARTMENT_MIGRATION, F44, F45, MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_schema import drop_platform_roles

ASSIGN = 'SELECT * FROM forge.directory_member_department(%s,%s,%s,%s)'


class DepartmentProfileTests(unittest.TestCase):
    def test_0045_follows_0044_with_its_own_pinned_checkpoint(self):
        self.assertEqual(DIRECTORY_DEPARTMENT_MIGRATION, '0045_directory_member_department.sql')
        self.assertEqual(MVP_ADDITIONS[at(DIRECTORY_DEPARTMENT_MIGRATION) - 1], '0044_platform_overview.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(DIRECTORY_DEPARTMENT_MIGRATION):at(DIRECTORY_DEPARTMENT_MIGRATION) + 2], (F44, F45))
        self.assertRegex(F45 or '', r'^[0-9a-f]{64}$', 'F45 must be pinned')
        self.assertNotEqual(F45, F44)


class DepartmentFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0044_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(DIRECTORY_DEPARTMENT_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, DIRECTORY_DEPARTMENT_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F44)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(DIRECTORY_DEPARTMENT_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0045 member department checkpoint F45:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0044 must be identical')
        self.assertEqual(fresh, F45, 'F45 must be pinned to the reviewed value')


class AssignmentTests(unittest.TestCase):
    def world(self, db):
        self.db = db
        self.results = provision(db.admin, SEED, lambda created: None)
        self.org_a, self.org_b = self.results[0].organization_id, self.results[1].organization_id
        self.admin, self.member = self.results[0].accounts
        self.second = db.admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,gen_random_uuid(),'Support') RETURNING id", (self.org_a,)).fetchone()[0]
        self.first = self.results[0].department_id
        self.member_id = db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE m.organization_id=%s AND a.canonical_email=%s',
                                          (self.org_a, self.member.email)).fetchone()[0]
        self.admin_digest = sign_in(db, self.admin.email, self.admin.password)[1]

    def assign(self, digest, org, member, department):
        return call(self.db, ASSIGN, (digest, org, member, department), role='forge_gateway_service')

    def departments(self, member=None):
        return [row[0] for row in self.db.admin.execute('SELECT department_id FROM forge.membership_departments WHERE membership_id=%s ORDER BY 1', (member or self.member_id,))]

    def test_an_administrator_moves_a_member_to_another_department_and_the_member_sees_it(self):
        with mvp_database() as db:
            self.world(db)
            self.assertEqual(self.departments(), [self.first])
            (row,) = self.assign(self.admin_digest, self.org_a, self.member_id, self.second)
            self.assertEqual((row[0], row[1], row[3], row[4]), (self.member_id, self.member.email, 'active', ['member']))
            self.assertEqual([department['name'] for department in row[5]], ['Support'])
            self.assertEqual(self.departments(), [self.second], 'exactly one department: the previous one is replaced')
            _, member_digest = sign_in(db, self.member.email, self.member.password)
            me = call(db, 'SELECT * FROM forge.directory_me(%s)', (member_digest,), role='forge_gateway_service')
            self.assertEqual([department['name'] for department in me[0][7]], ['Support'])

    def test_assigning_the_current_department_again_changes_nothing(self):
        with mvp_database() as db:
            self.world(db)
            self.assign(self.admin_digest, self.org_a, self.member_id, self.first)
            self.assign(self.admin_digest, self.org_a, self.member_id, self.first)
            self.assertEqual(self.departments(), [self.first])

    def test_a_suspended_member_can_still_be_assigned_and_a_member_with_several_departments_ends_with_one(self):
        with mvp_database() as db:
            self.world(db)
            db.admin.execute('INSERT INTO forge.membership_departments(organization_id,membership_id,department_id) VALUES(%s,%s,%s)', (self.org_a, self.member_id, self.second))
            self.assertEqual(len(self.departments()), 2)
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (self.member_id,))
            (row,) = self.assign(self.admin_digest, self.org_a, self.member_id, self.first)
            self.assertEqual((row[3], [department['id'] for department in row[5]]), ('suspended', [str(self.first)]))
            self.assertEqual(self.departments(), [self.first])

    def test_every_other_caller_and_target_is_one_denial_and_nothing_changes(self):
        with mvp_database() as db:
            self.world(db)
            _, member_digest = sign_in(db, self.member.email, self.member.password)
            _, other_admin = sign_in(db, self.results[1].accounts[0].email, self.results[1].accounts[0].password)
            foreign_department = self.results[1].department_id
            foreign_member = db.admin.execute('SELECT id FROM forge.memberships WHERE organization_id=%s LIMIT 1', (self.org_b,)).fetchone()[0]
            db.admin.execute("INSERT INTO forge.departments(organization_id,id,name,active) VALUES(%s,gen_random_uuid(),'Closed',false)", (self.org_a,))
            closed = db.admin.execute("SELECT id FROM forge.departments WHERE organization_id=%s AND name='Closed'", (self.org_a,)).fetchone()[0]
            cases = ((member_digest, self.org_a, self.member_id, self.second), (other_admin, self.org_a, self.member_id, self.second),
                     ('0' * 64, self.org_a, self.member_id, self.second), (self.admin_digest, self.org_b, self.member_id, self.second),
                     (self.admin_digest, self.org_a, foreign_member, self.second), (self.admin_digest, self.org_a, uuid4(), self.second),
                     (self.admin_digest, self.org_a, self.member_id, foreign_department), (self.admin_digest, self.org_a, self.member_id, uuid4()),
                     (self.admin_digest, self.org_a, self.member_id, closed), (self.admin_digest, None, self.member_id, self.second))
            for arguments in cases:
                with self.subTest(arguments=str(arguments)[-60:]):
                    self.assertEqual(refusal(self, lambda: self.assign(*arguments)), 'DIRECTORY_DENIED')
            for arguments in ((self.admin_digest, self.org_a, None, self.second), (self.admin_digest, self.org_a, self.member_id, None)):
                self.assertEqual(refusal(self, lambda: self.assign(*arguments)), 'DIRECTORY_INVALID')
            self.assertEqual(self.departments(), [self.first])
            self.assertEqual(self.departments(foreign_member), [self.results[1].department_id])

    def test_only_the_gateway_service_pool_may_execute_it_and_gained_no_table_privilege(self):
        with mvp_database() as db:
            signature = 'forge.directory_member_department(text,uuid,uuid,uuid)'
            for role, expected in (('forge_gateway_service', True), ('forge_platform_service', False), ('forge_capability_service', False), ('public', False)):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(), (expected,), role)
            for role in ('forge_gateway_service', 'forge_platform_service'):
                for privilege in ('INSERT', 'DELETE'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.membership_departments',%s)", (role, privilege)).fetchone(), (False,))


class AssignmentHttpTests(unittest.TestCase):
    def test_an_administrator_assigns_over_http_and_the_member_list_and_the_member_follow(self):
        with stack() as (db, client, results, root, secrets):
            org = results[0].organization_id
            admin, member = results[0].accounts
            second = db.admin.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,gen_random_uuid(),'Support') RETURNING id", (org,)).fetchone()[0]
            headers = login(client, admin)
            listed = client.get('/forge/v1/orgs/%s/members' % org, headers=headers).json()['members']
            target = next(item for item in listed if item['email'] == member.email)
            path = '/forge/v1/orgs/%s/members/%s/department' % (org, target['id'])
            response = client.put(path, headers=headers, json={'department_id': str(second)})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([department['name'] for department in response.json()['departments']], ['Support'])
            again = client.get('/forge/v1/orgs/%s/members' % org, headers=headers).json()['members']
            self.assertEqual([department['name'] for item in again if item['email'] == member.email for department in item['departments']], ['Support'])
            seen = client.get('/forge/v1/accounts/me', headers=login(client, member)).json()
            self.assertEqual([department['name'] for department in seen['organizations'][0]['departments']], ['Support'])
            denied = (client.put(path, headers=login(client, member), json={'department_id': str(second)}),
                      client.put(path, headers=login(client, results[1].accounts[0]), json={'department_id': str(second)}),
                      client.put(path, json={'department_id': str(second)}),
                      client.put(path, headers=headers, json={'department_id': str(uuid4())}))
            self.assertEqual([response.status_code for response in denied], [404, 404, 401, 404])


if __name__ == '__main__':
    unittest.main()
