"""Owned PostgreSQL: suspending a company through the platform API denies its members and administrators at once, leaves the
other company and the sessions alone, and reactivation restores everything (the matrix over every member/admin path)."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from platform_support import OWNER_EMAIL, PASSWORD, add_owner
from test_postgres_platform_http import BASE, Person, code_for
from test_postgres_mvp_local import login, stack


class PostgresPlatformSuspensionTests(unittest.TestCase):
    def verified_owner(self, db, client):
        add_owner(db.admin)
        headers = login(client, Person(OWNER_EMAIL, PASSWORD))
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers).json()
        self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
        return headers

    def operations(self, org):
        """(who, method, path, json) for every kind of member and administrator call that touches a company."""
        o = '/forge/v1/orgs/%s' % org
        return (('member', 'GET', '/forge/v1/accounts/me', None), ('member', 'GET', o + '/branding', None),
                ('admin', 'GET', o + '/departments', None), ('admin', 'GET', o + '/members', None), ('admin', 'GET', o + '/gateway', None),
                ('admin', 'GET', o + '/gateway/catalogue/status', None), ('admin', 'GET', o + '/branding', None))

    def run_all(self, client, people, org):
        return {(who, path): client.request(method, path, headers=people[who], json=body).status_code
                for who, method, path, body in self.operations(org)}

    def test_a_suspended_company_denies_every_member_and_admin_path_while_the_other_company_and_the_sessions_are_untouched(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org_a, org_b = results
            a = {'admin': login(client, org_a.accounts[0]), 'member': login(client, org_a.accounts[1])}
            b = {'admin': login(client, org_b.accounts[0]), 'member': login(client, org_b.accounts[1])}
            before_a, before_b = self.run_all(client, a, org_a.organization_id), self.run_all(client, b, org_b.organization_id)
            self.assertEqual(set(before_a.values()), {200}, before_a)
            self.assertEqual(set(before_b.values()), {200}, before_b)
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}).status_code, 200)

            suspended = client.post(BASE + '/companies/%s/suspend' % org_a.organization_id, headers=owner)
            self.assertEqual((suspended.status_code, suspended.json()['active']), (200, False))
            during_a = self.run_all(client, a, org_a.organization_id)
            self.assertTrue(all(status in (401, 403, 404) for status in during_a.values()), during_a)
            self.assertEqual(self.run_all(client, b, org_b.organization_id), before_b, 'the other company is unaffected')
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}).status_code, 404,
                             'the company code stops resolving')
            self.assertEqual(login(client, org_a.accounts[1]).keys(), {'Authorization'}, 'sessions are untouched: only authority is denied')

            repeated = client.post(BASE + '/companies/%s/suspend' % org_a.organization_id, headers=owner)
            self.assertEqual((repeated.status_code, repeated.json()['active']), (200, False))
            restored = client.post(BASE + '/companies/%s/reactivate' % org_a.organization_id, headers=owner)
            self.assertEqual((restored.status_code, restored.json()['active']), (200, True))
            self.assertEqual(self.run_all(client, a, org_a.organization_id), before_a, 'reactivation restores access at once')
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}).status_code, 200)
            actions = [entry['action'] for entry in client.get(BASE + '/audit', headers=owner).json()['entries']]
            self.assertEqual(actions, ['company.reactivated', 'company.suspended', 'owner.mfa_enrolled'])

    def test_a_suspended_company_cannot_issue_invitations_and_its_inference_authority_resolves_to_nothing(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org_a = results[0]
            admin = login(client, org_a.accounts[0])
            member_id = db.admin.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (org_a.accounts[1].email,)).fetchone()[0]
            admin_id = db.admin.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (org_a.accounts[0].email,)).fetchone()[0]
            org = org_a.organization_id
            resolve = lambda who: db.admin.execute('SELECT forge.gateway_resolve_member(%s,%s)', (org, who)).fetchone()[0]
            self.assertIsNotNone(resolve(member_id))
            invite = {'organization_id': str(org), 'department_id': str(org_a.department_id), 'email': 'new.person@a.test', 'name': 'New Person'}
            self.assertEqual(client.post('/forge/v1/accounts/invitations', headers=admin, json=invite).status_code, 201)
            client.post(BASE + '/companies/%s/suspend' % org, headers=owner)
            self.assertIsNone(resolve(member_id), 'the member route that inference depends on')
            self.assertIsNone(resolve(admin_id))
            self.assertEqual(db.admin.execute('SELECT forge.gateway_resolve_admin(%s,%s)', (org, admin_id)).fetchone()[0], None)
            denied = client.post('/forge/v1/accounts/invitations', headers=admin, json={**invite, 'email': 'other.person@a.test'})
            self.assertIn(denied.status_code, (403, 404))
            client.post(BASE + '/companies/%s/reactivate' % org, headers=owner)
            self.assertIsNotNone(resolve(member_id))
            self.assertEqual(client.post('/forge/v1/accounts/invitations', headers=admin, json={**invite, 'email': 'third.person@a.test'}).status_code, 201)

    def test_a_company_admin_cannot_suspend_anything_and_an_unknown_company_is_404(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            admin = login(client, results[0].accounts[0])
            for path in ('suspend', 'reactivate'):
                response = client.post(BASE + '/companies/%s/%s' % (results[1].organization_id, path), headers=admin)
                self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
                missing = client.post(BASE + '/companies/00000000-0000-4000-8000-000000000000/%s' % path, headers=owner)
                self.assertEqual((missing.status_code, missing.json()['error']['code']), (404, 'NOT_FOUND'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organizations WHERE active').fetchone(), (2,))


class PostgresPlatformBrandingHttpTests(unittest.TestCase):
    DOC = {'name': 'Acme Labs', 'loginCopy': 'Welcome.', 'assets': {},
           'theme': {'primary': '#0B1D26', 'accent': '#B45309', 'tint': '#E8DCC1', 'heading': 'inter', 'body': 'inter'}}

    def test_the_owner_edits_one_company_branding_and_the_other_companys_public_branding_is_unchanged(self):
        with stack() as (db, client, results, root, secrets):
            suspension = PostgresPlatformSuspensionTests()
            owner = suspension.verified_owner(db, client)
            org_a, org_b = results
            url = BASE + '/companies/%s/branding' % org_a.organization_id
            self.assertEqual(client.get(url, headers=owner).json()['revision'], 0)
            saved = client.put(url, headers=owner, json={'expectedRevision': 0, 'branding': self.DOC})
            self.assertEqual((saved.status_code, saved.json()['name'], saved.json()['revision']), (200, 'Acme Labs', 1))
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}).json()['name'], 'Acme Labs')
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-b'}).json()['revision'], 0)
            stale = client.put(url, headers=owner, json={'expectedRevision': 0, 'branding': self.DOC})
            self.assertEqual((stale.status_code, stale.json()['error']['code']), (409, 'REVISION_CONFLICT'))
            bad = client.put(url, headers=owner, json={'expectedRevision': 1, 'branding': {**self.DOC, 'name': '<b>'}})
            self.assertEqual(bad.status_code, 422)
            admin = login(client, org_a.accounts[0])
            member_view = client.get('/forge/v1/orgs/%s/branding' % org_a.organization_id, headers=admin)
            self.assertEqual((member_view.status_code, member_view.json()['name'], member_view.json()['revision']), (200, 'Acme Labs', 1))
            own = client.put('/forge/v1/orgs/%s/branding' % org_a.organization_id, headers=admin,
                             json={'expectedRevision': 1, 'branding': {**self.DOC, 'name': 'Admin Edit'}})
            self.assertEqual((own.status_code, own.json()['revision']), (200, 2), 'the company admin keeps editing its own')
            reset = client.post(url + '/reset', headers=owner, json={'expectedRevision': 2})
            self.assertEqual((reset.status_code, reset.json()['revision']), (200, 3))
            denied = client.put('/forge/v1/platform/companies/%s/branding' % org_b.organization_id, headers=admin,
                                json={'expectedRevision': 0, 'branding': self.DOC})
            self.assertEqual((denied.status_code, denied.json()['error']['code']), (403, 'PLATFORM_DENIED'))


if __name__ == '__main__':
    unittest.main()
