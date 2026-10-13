"""Owned PostgreSQL: the governance API through the real composed control plane (owner catalog and locks, company administrator, hidden routes)."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge import contract
from forge.invitations import capability_digest
from platform_support import OWNER_EMAIL, PASSWORD, add_owner, verify_directly
from test_postgres_mvp_local import login, stack

PLATFORM = '/forge/v1/platform'
ENTRY = {'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0}


class Person:
    def __init__(self, email, password=PASSWORD):
        self.email, self.password = email, password


def owner(db, client):
    add_owner(db.admin)
    headers = login(client, Person(OWNER_EMAIL))
    verify_directly(db.admin, OWNER_EMAIL, capability_digest(headers['Authorization'].split()[1]))
    return headers


class PostgresCapabilityHttpTests(unittest.TestCase):
    def test_the_owner_governs_the_catalog_and_a_company_administrator_toggles_what_is_not_locked(self):
        with stack() as (db, client, results, root, secrets):
            org_a, org_b = results[0].organization_id, results[1].organization_id
            boss = owner(db, client)
            admin_a, member_a = login(client, results[0].accounts[0]), login(client, results[0].accounts[1])
            admin_b = login(client, results[1].accounts[0])
            for identifier in ('skill:pdf', 'connector:github'):
                created = client.put(PLATFORM + '/capabilities/' + identifier, headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
                self.assertEqual((created.status_code, created.json()['revision']), (200, 1), created.text)
            self.assertEqual([item['id'] for item in client.get(PLATFORM + '/capabilities', headers=boss).json()['capabilities']], ['connector:github', 'skill:pdf'])
            duplicate = client.put(PLATFORM + '/capabilities/skill:pdf', headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
            self.assertEqual((duplicate.status_code, duplicate.json()['error']['code']), (409, 'REVISION_CONFLICT'))
            base = 'orgs/%s/capabilities' % org_a
            view = client.get('/forge/v1/' + base, headers=admin_a).json()['capabilities']
            self.assertEqual({item['id']: (item['state'], item['locked'], item['setting']) for item in view},
                             {'skill:pdf': ('on', False, None), 'connector:github': ('on', False, None)}, 'a new company has the base set on with zero rows')
            self.assertEqual(client.put('/forge/v1/%s/skill:pdf' % base, headers=admin_a, json={'enabled': False}).json(), {'changed': True})
            lock = client.put(PLATFORM + '/companies/%s/capabilities/connector:github' % org_a, headers=boss, json={'state': None, 'lock': 'forced_off'})
            self.assertEqual((lock.status_code, lock.json()), (200, {'changed': True}))
            locked = client.put('/forge/v1/%s/connector:github' % base, headers=admin_a, json={'enabled': True})
            self.assertEqual((locked.status_code, locked.json()['error']['code']), (409, 'LOCKED'))
            view = {item['id']: item for item in client.get('/forge/v1/' + base, headers=admin_a).json()['capabilities']}
            self.assertEqual((view['skill:pdf']['state'], view['skill:pdf']['setting'], view['connector:github']['state'], view['connector:github']['locked']),
                             ('off', False, 'forced_off', True))
            self.assertEqual(client.get('/forge/v1/orgs/%s/capabilities' % org_b, headers=admin_b).json()['capabilities'][0]['state'], 'on', 'the other company is untouched')
            audit = client.get('/forge/v1/orgs/%s/capability-audit' % org_a, headers=admin_a).json()
            self.assertEqual([entry['action'] for entry in audit['entries']], ['company.policy_set', 'org.setting_set'])
            everything = client.get(PLATFORM + '/capability-audit', headers=boss).json()['entries']
            self.assertEqual(len(everything), 4)

    def test_denials_look_the_same_and_members_cannot_write(self):
        with stack() as (db, client, results, root, secrets):
            org_a, org_b = results[0].organization_id, results[1].organization_id
            boss = owner(db, client)
            client.put(PLATFORM + '/capabilities/skill:pdf', headers=boss, json={'expected_revision': 0, 'entry': ENTRY})
            admin_a, member_a, admin_b = login(client, results[0].accounts[0]), login(client, results[0].accounts[1]), login(client, results[1].accounts[0])
            for headers, org in ((member_a, org_a), (admin_a, org_b), (admin_b, org_a)):
                for response in (client.get('/forge/v1/orgs/%s/capabilities' % org, headers=headers),
                                 client.put('/forge/v1/orgs/%s/capabilities/skill:pdf' % org, headers=headers, json={'enabled': False}),
                                 client.get('/forge/v1/orgs/%s/capability-audit' % org, headers=headers)):
                    self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))
            for response in (client.get(PLATFORM + '/capabilities', headers=admin_a),
                             client.put(PLATFORM + '/capabilities/skill:pdf/policy', headers=admin_a, json={'state': 'off', 'lock': 'none'}),
                             client.put(PLATFORM + '/companies/%s/capabilities/skill:pdf' % org_a, headers=admin_a, json={'state': 'off', 'lock': 'none'})):
                self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(client.get('/forge/v1/orgs/%s/capabilities' % org_a).status_code, 401)

    def test_a_password_only_owner_session_cannot_write_and_the_contract_pin_is_unchanged(self):
        with stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            headers = login(client, Person(OWNER_EMAIL))
            blocked = client.put(PLATFORM + '/capabilities/skill:pdf', headers=headers, json={'expected_revision': 0, 'entry': ENTRY})
            self.assertEqual((blocked.status_code, blocked.json()['error']['code']), (403, 'MFA_REQUIRED'))
            served = client.get('/forge/v1/contract').json()
            self.assertEqual(served['schema_sha256'], contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            self.assertNotIn('capabilities', json.dumps(client.get('/openapi.json').json()) if client.get('/openapi.json').status_code == 200 else '')


if __name__ == '__main__':
    unittest.main()
