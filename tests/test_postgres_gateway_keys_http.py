"""Owned PostgreSQL through the composed app: the platform owner manages the key pool over HTTP; a company administrator and
a member are denied everywhere; key text is write-only and never appears in any response, row or audit entry."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from platform_support import OWNER_EMAIL, PASSWORD, add_owner
from test_postgres_mvp_local import GATEWAY, login, stack
from test_postgres_platform_http import BASE, Person, code_for

KEY, SECOND = 'pool-fixture-key-ABCD', 'pool-fixture-key-WXYZ'


class PostgresKeyPoolHttpTests(unittest.TestCase):
    def verified_owner(self, db, client):
        add_owner(db.admin)
        headers = login(client, Person(OWNER_EMAIL, PASSWORD))
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers).json()
        self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
        return headers

    def test_the_owner_creates_two_keys_assigns_them_by_priority_and_sets_the_ceiling_with_an_audit_trail(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            seen = []
            first = client.post(BASE + '/gateway-keys', headers=owner, json={'label': 'primary', 'origin': GATEWAY, 'key': KEY})
            second = client.post(BASE + '/gateway-keys', headers=owner, json={'label': 'backup', 'origin': GATEWAY, 'key': SECOND})
            self.assertEqual((first.status_code, second.status_code), (201, 201), first.text + second.text)
            seen += [first.text, second.text]
            ids = [first.json()['id'], second.json()['id']]
            listed = client.get(BASE + '/gateway-keys', headers=owner)
            self.assertEqual((sorted(item['label'] for item in listed.json()['keys']), listed.json()['allowed_origins']),
                             (['backup', 'primary'], [GATEWAY]))
            assigned = client.put(BASE + '/companies/%s/gateway-keys' % org, headers=owner, json={'keys': [
                {'key_id': ids[1], 'priority': 2, 'active': True}, {'key_id': ids[0], 'priority': 1, 'active': True}]})
            self.assertEqual([item['label'] for item in assigned.json()['keys']], ['primary', 'backup'])
            ceiling = client.put(BASE + '/companies/%s/model-access' % org, headers=owner, json={'models': ['fake-model']})
            self.assertEqual(ceiling.json(), {'models': ['fake-model']})
            seen += [listed.text, assigned.text, ceiling.text]
            actions = [entry['action'] for entry in client.get(BASE + '/audit', headers=owner).json()['entries']]
            self.assertEqual(actions, ['company.model_access_set', 'company.gateway_assigned', 'gateway_key.created',
                                       'gateway_key.created', 'owner.mfa_enrolled'])
            everything = ' '.join(seen) + repr(db.admin.execute('SELECT * FROM forge.platform_audit_log').fetchall())
            self.assertFalse([value for value in (KEY, SECOND) if value in everything])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys WHERE encrypted_key LIKE %s', ('%' + KEY + '%',)).fetchone(), (0,))
            duplicate = client.post(BASE + '/gateway-keys', headers=owner, json={'label': 'primary', 'origin': GATEWAY, 'key': KEY})
            self.assertEqual((duplicate.status_code, duplicate.json()['error']['code']), (409, 'KEY_CONFLICT'))
            refused = client.post(BASE + '/gateway-keys', headers=owner, json={'label': 'evil', 'origin': 'https://evil.example', 'key': KEY})
            self.assertEqual(refused.status_code, 422)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (2,))

    def test_company_administrators_and_members_are_denied_on_every_key_route_and_nothing_is_stored(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            created = client.post(BASE + '/gateway-keys', headers=owner, json={'label': 'primary', 'origin': GATEWAY, 'key': KEY}).json()['id']
            routes = (('GET', '/gateway-keys', None), ('POST', '/gateway-keys', {'label': 'x', 'origin': GATEWAY, 'key': KEY}),
                      ('POST', '/gateway-keys/%s/rotate' % created, {'expected_revision': 1, 'key': SECOND}),
                      ('POST', '/gateway-keys/%s/disable' % created, None),
                      ('GET', '/companies/%s/gateway-keys' % org, None),
                      ('PUT', '/companies/%s/gateway-keys' % org, {'keys': [{'key_id': created, 'priority': 1, 'active': True}]}),
                      ('GET', '/companies/%s/model-access' % org, None), ('PUT', '/companies/%s/model-access' % org, {'models': ['m']}))
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                headers = login(client, account)
                for method, path, body in routes:
                    with self.subTest(account=account.email, path=path):
                        response = client.request(method, BASE + path, headers=headers, json=body)
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(db.admin.execute('SELECT count(*),max(revision),min(status) FROM forge.gateway_keys').fetchone(), (1, 1, 'active'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_gateway_keys').fetchone(), (0,))

    def test_a_password_only_owner_session_cannot_change_the_pool(self):
        with stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            headers = login(client, Person(OWNER_EMAIL, PASSWORD))
            response = client.post(BASE + '/gateway-keys', headers=headers, json={'label': 'primary', 'origin': GATEWAY, 'key': KEY})
            self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'MFA_REQUIRED'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
