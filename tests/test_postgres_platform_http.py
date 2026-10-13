"""Owned PostgreSQL: the platform API through the real composed control plane (owner, mandatory TOTP, hidden routes, denial)."""
import base64
import json
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge import contract
from forge.platform_totp import totp
from platform_support import OWNER_EMAIL, PASSWORD, add_owner
from test_postgres_mvp_local import login, stack

BASE = '/forge/v1/platform'


class Person:
    def __init__(self, email, password=PASSWORD):
        self.email, self.password = email, password


def code_for(secret, offset=0):
    raw = base64.b32decode(secret + '=' * (-len(secret) % 8))
    return totp(raw, int(time.time()) // 30 + offset)


class PostgresPlatformHttpTests(unittest.TestCase):
    def owner(self, db, client):
        add_owner(db.admin)
        return login(client, Person(OWNER_EMAIL))

    def enrolled(self, client, headers):
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers)
        self.assertEqual(enrollment.status_code, 201, enrollment.text)
        return enrollment.json()

    def test_the_owner_enrolls_totp_verifies_the_session_and_reads_companies_and_audit(self):
        with stack() as (db, client, results, root, secrets):
            headers = self.owner(db, client)
            me = client.get(BASE + '/me', headers=headers).json()
            self.assertEqual((me['role'], me['mfa']), ('platform_owner', {'state': 'none', 'verified': False, 'fresh': False}))
            blocked = client.get(BASE + '/companies', headers=headers)
            self.assertEqual((blocked.status_code, blocked.json()['error']['code']), (403, 'MFA_REQUIRED'))
            enrollment = self.enrolled(client, headers)
            self.assertEqual(len(enrollment['recovery_codes']), 10)
            self.assertTrue(enrollment['otpauth_uri'].startswith('otpauth://totp/Prometheon%20Forge:'))
            self.assertEqual(client.get(BASE + '/me', headers=headers).json()['mfa']['state'], 'pending')
            verified = client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])})
            self.assertEqual((verified.status_code, verified.json()), (200, {'verified': True}))
            self.assertEqual(client.get(BASE + '/me', headers=headers).json()['mfa'], {'state': 'active', 'verified': True, 'fresh': True})
            listing = client.get(BASE + '/companies', headers=headers).json()
            self.assertEqual([c['slug'] for c in listing['companies']], ['org-a', 'org-b'])
            self.assertIsNone(listing['next_after'])
            one = client.get(BASE + '/companies/%s' % results[1].organization_id, headers=headers).json()
            self.assertEqual((one['slug'], one['active']), ('org-b', True))
            self.assertEqual(client.get(BASE + '/companies/00000000-0000-4000-8000-000000000000', headers=headers).status_code, 404)
            audit = client.get(BASE + '/audit', headers=headers).json()
            self.assertEqual([e['action'] for e in audit['entries']], ['owner.mfa_enrolled'])
            paged = client.get(BASE + '/companies', headers=headers, params={'page': 1}).json()
            self.assertEqual(([c['slug'] for c in paged['companies']], paged['next_after']), (['org-a'], 'org-a'))

    def test_a_new_session_needs_its_own_verification_and_a_used_code_is_rejected_by_the_replay_guard(self):
        with stack() as (db, client, results, root, secrets):
            first = self.owner(db, client)
            enrollment = self.enrolled(client, first)
            self.assertEqual(client.post(BASE + '/login/mfa', headers=first, json={'code': code_for(enrollment['secret'])}).status_code, 200)
            second = login(client, Person(OWNER_EMAIL))
            self.assertEqual(client.get(BASE + '/companies', headers=second).json()['error']['code'], 'MFA_REQUIRED')
            replay = client.post(BASE + '/login/mfa', headers=second, json={'code': code_for(enrollment['secret'])})
            self.assertEqual((replay.status_code, replay.json()['error']['code']), (403, 'MFA_INVALID'))
            self.assertEqual(client.post(BASE + '/login/mfa', headers=second, json={'code': code_for(enrollment['secret'], +1)}).status_code, 200)
            self.assertEqual(client.get(BASE + '/companies', headers=second).status_code, 200)

    def test_a_recovery_code_verifies_a_session_once(self):
        with stack() as (db, client, results, root, secrets):
            first = self.owner(db, client)
            enrollment = self.enrolled(client, first)
            client.post(BASE + '/login/mfa', headers=first, json={'code': code_for(enrollment['secret'])})
            code = enrollment['recovery_codes'][0]
            second, third = login(client, Person(OWNER_EMAIL)), login(client, Person(OWNER_EMAIL))
            self.assertEqual(client.post(BASE + '/login/mfa', headers=second, json={'recovery_code': code}).status_code, 200)
            self.assertEqual(client.get(BASE + '/companies', headers=second).status_code, 200)
            reused = client.post(BASE + '/login/mfa', headers=third, json={'recovery_code': code})
            self.assertEqual((reused.status_code, reused.json()['error']['code']), (403, 'MFA_INVALID'))

    def test_five_wrong_codes_lock_the_factor_with_a_retry_after_and_an_active_factor_cannot_be_enrolled_again(self):
        with stack() as (db, client, results, root, secrets):
            headers = self.owner(db, client)
            enrollment = self.enrolled(client, headers)
            for _ in range(5):
                self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': '000000'}).status_code, 403)
            locked = client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])})
            self.assertEqual((locked.status_code, locked.json()['error']['code'], locked.headers['retry-after']), (429, 'MFA_LOCKED', '900'))
            db.admin.execute("UPDATE forge.platform_totp SET attempt_window=clock_timestamp()-interval '16 minutes'")
            self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
            again = client.post(BASE + '/mfa/enroll', headers=headers)
            self.assertEqual((again.status_code, again.json()['error']['code']), (409, 'MFA_ENROLLED'))

    def test_company_administrators_and_members_are_denied_every_platform_route(self):
        with stack() as (db, client, results, root, secrets):
            self.owner(db, client)
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                headers = login(client, account)
                for method, path in (('GET', '/me'), ('GET', '/companies'), ('GET', '/audit'), ('POST', '/mfa/enroll'),
                                     ('GET', '/companies/%s' % results[0].organization_id)):
                    with self.subTest(account=account.role, path=path):
                        response = client.request(method, BASE + path, headers=headers)
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
                denied = client.post(BASE + '/login/mfa', headers=headers, json={'code': '123456'})
                self.assertEqual((denied.status_code, denied.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_totp').fetchone(), (0,))

    def verified_owner(self, db, client):
        headers = self.owner(db, client)
        enrollment = self.enrolled(client, headers)
        self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
        return headers

    def emailed_link(self, root):
        import email
        from email import policy
        from urllib.parse import parse_qs, urlsplit
        (path,) = sorted((root/'mailbox').glob('*.eml'))
        message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        link = next(line for line in message.get_body(('plain',)).get_content().splitlines() if line.startswith('http'))
        fragment = parse_qs(urlsplit(link).fragment)
        return link, fragment['invitation_id'][0], fragment['capability'][0]

    def test_a_company_created_by_the_owner_gets_its_first_admin_through_the_emailed_invitation(self):
        with stack() as (db, client, results, root, secrets):
            headers = self.verified_owner(db, client)
            body = {'slug': 'acme', 'display_name': 'Acme Corporation', 'department': 'Operations',
                    'admin_email': 'first.admin@acme.test', 'admin_name': 'First Admin'}
            created = client.post(BASE + '/companies', headers=headers, json=body)
            self.assertEqual(created.status_code, 201, created.text)
            document = created.json()
            self.assertEqual((document['slug'], document['active'], document['invitation']['delivery_state'],
                              document['invitation']['delivery_channel']), ('acme', True, 'delivered', 'local_test_mailbox'))
            link, invitation, capability = self.emailed_link(root)
            self.assertIn('c=acme', link)
            self.assertNotIn(capability, created.text + client.get(BASE + '/audit', headers=headers).text)
            self.assertEqual(client.post(BASE + '/companies', headers=headers, json=body).status_code, 409)
            self.assertEqual([c['slug'] for c in client.get(BASE + '/companies', headers=headers).json()['companies']], ['acme', 'org-a', 'org-b'])
            accepted = client.post('/forge/v1/accounts/invitations/accept',
                                   json={'invitation_id': invitation, 'capability': capability, 'password': 'first-admin-passphrase'})
            self.assertEqual(accepted.status_code, 201, accepted.text)
            admin = login(client, Person('first.admin@acme.test', 'first-admin-passphrase'))
            members = client.get('/forge/v1/orgs/%s/members' % document['id'], headers=admin)
            self.assertEqual(members.status_code, 200, members.text)
            (listed,) = members.json()['members']
            self.assertEqual((listed['roles'], listed['status']), (['organization_admin'], 'active'))
            self.assertEqual(client.get('/forge/v1/orgs/%s/members' % results[0].organization_id, headers=admin).status_code, 404)
            self.assertEqual(client.get(BASE + '/me', headers=admin).status_code, 403, 'a company admin is not a platform identity')
            actions = [e['action'] for e in client.get(BASE + '/audit', headers=headers).json()['entries']]
            self.assertEqual(actions, ['company.created', 'owner.mfa_enrolled'])

    def test_creating_a_company_needs_the_owner_a_verified_session_and_a_valid_body(self):
        with stack() as (db, client, results, root, secrets):
            headers = self.owner(db, client)
            body = {'slug': 'acme', 'display_name': 'Acme', 'department': 'Ops', 'admin_email': 'a@acme.test', 'admin_name': 'A'}
            self.assertEqual(client.post(BASE + '/companies', headers=headers, json=body).json()['error']['code'], 'MFA_REQUIRED')
            admin = login(client, results[0].accounts[0])
            self.assertEqual(client.post(BASE + '/companies', headers=admin, json=body).json()['error']['code'], 'PLATFORM_DENIED')
            verified = self.verified_owner_after(db, client, headers)
            for bad in ({**body, 'slug': 'BAD CODE'}, {**body, 'admin_email': 'nope'}, {**body, 'display_name': ''}):
                self.assertEqual(client.post(BASE + '/companies', headers=verified, json=bad).status_code, 422)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organizations').fetchone(), (2,), 'only the seeded companies exist')

    def verified_owner_after(self, db, client, headers):
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers).json()
        client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])})
        return headers

    def test_the_contract_pin_served_by_the_composed_app_is_unchanged_and_no_platform_path_is_published(self):
        with stack() as (db, client, results, root, secrets):
            served = client.get('/forge/v1/contract').json()
            self.assertEqual(served['schema_sha256'], contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            self.assertFalse([path for path in client.get('/openapi.json').json()['paths'] if 'platform' in path])
            self.assertEqual(client.get(BASE + '/me').status_code, 401)


if __name__ == '__main__':
    unittest.main()
