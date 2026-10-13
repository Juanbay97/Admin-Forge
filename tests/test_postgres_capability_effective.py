"""Owned PostgreSQL: the signed effective policy through the real composed control plane (defaults, locks, attestation, epochs, isolation)."""
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.capability_signing import DocumentRejected, verify_document
from test_postgres_capability_http import PLATFORM, owner
from test_postgres_mvp_local import login, stack

EFFECTIVE = '/forge/v1/capabilities/effective'
SKILL = {'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0, 'credential_locus': 'none'}
EXEC = {**SKILL, 'risk': 'high', 'is_base': False, 'min_sandbox_level': 3}
SHELL = {**EXEC, 'min_sandbox_level': 4}
PIN = 'b' * 64
APP = {'version': '1.0.0', 'risk': 'medium', 'is_base': False, 'default_state': 'off', 'min_sandbox_level': 0, 'manifest_sha256': PIN,
       'declared_permissions': ['ui.title', 'storage.local'], 'granted_permissions': ['ui.title']}


def seed(client, boss):
    for identifier, entry in (('skill:pdf', SKILL), ('connector:github', {**SKILL, 'credential_locus': 'server'}), ('tool:code_execute', EXEC),
                              ('tool:bash', SHELL), ('app:acme.hello', APP)):
        response = client.put(PLATFORM + '/capabilities/' + identifier, headers=boss, json={'expected_revision': 0, 'entry': entry})
        assert response.status_code == 200, response.text


def states(document):
    return {(item['kind'], item['id']): item['state'] for item in document['capabilities']}


class PostgresEffectivePolicyTests(unittest.TestCase):
    def test_a_member_gets_a_verifiable_document_with_defaults_the_attestation_gate_and_locks(self):
        with stack() as (db, client, results, root, secrets):
            boss = owner(db, client)
            seed(client, boss)
            member = login(client, results[0].accounts[1])
            keys = client.get('/forge/v1/capabilities/keys').json()
            first = client.get(EFFECTIVE + '?sandbox_level=2', headers=member)
            self.assertEqual(first.status_code, 200, first.text)
            document = first.json()
            verify_document(document, keys, now=time.time())
            self.assertEqual(document['org'], str(results[0].organization_id))
            self.assertEqual(states(document), {('skill', 'pdf'): 'on', ('connector', 'github'): 'on', ('tool', 'code_execute'): 'blocked_attestation',
                                                ('tool', 'bash'): 'blocked_attestation', ('app', 'acme.hello'): 'off'}, 'zero rows: the base set is on, exec is gated, apps are off')
            at_three = states(client.get(EFFECTIVE + '?sandbox_level=3', headers=member).json())
            self.assertEqual((at_three[('tool', 'code_execute')], at_three[('tool', 'bash')]), ('on', 'blocked_attestation'))
            at_four = states(client.get(EFFECTIVE + '?sandbox_level=4', headers=member).json())
            self.assertEqual((at_four[('tool', 'code_execute')], at_four[('tool', 'bash')]), ('on', 'on'))
            self.assertEqual(states(client.get(EFFECTIVE, headers=member).json())[('tool', 'code_execute')], 'blocked_attestation', 'no report = level 0')
            tampered = {**document, 'reported_level': 4}
            with self.assertRaises(DocumentRejected):
                verify_document(tampered, keys, now=time.time())

    def test_epochs_rise_with_changes_and_a_force_off_reaches_only_its_company(self):
        with stack() as (db, client, results, root, secrets):
            boss = owner(db, client)
            seed(client, boss)
            member_a, member_b = login(client, results[0].accounts[1]), login(client, results[1].accounts[1])
            admin_a = login(client, results[0].accounts[0])
            before = client.get(EFFECTIVE, headers=member_a).json()
            lock = client.put(PLATFORM + '/companies/%s/capabilities/connector:github' % results[0].organization_id, headers=boss, json={'state': None, 'lock': 'forced_off'})
            self.assertEqual(lock.json(), {'changed': True})
            after = client.get(EFFECTIVE, headers=member_a).json()
            self.assertEqual((after['platform_epoch'], after['org_epoch']), (before['platform_epoch'], before['org_epoch'] + 1))
            self.assertEqual((states(after)[('connector', 'github')], [item for item in after['capabilities'] if item['id'] == 'github'][0]['reason']), ('forced_off', 'forced_off'))
            self.assertEqual(client.put('/forge/v1/orgs/%s/capabilities/connector:github' % results[0].organization_id, headers=admin_a, json={'enabled': True}).status_code, 409)
            self.assertEqual(states(client.get(EFFECTIVE, headers=member_b).json())[('connector', 'github')], 'on')
            client.put(PLATFORM + '/capabilities/skill:pdf/policy', headers=boss, json={'state': 'off', 'lock': 'none'})
            platform_change = client.get(EFFECTIVE, headers=member_a).json()
            self.assertEqual(platform_change['platform_epoch'], after['platform_epoch'] + 1)
            self.assertEqual(states(platform_change)[('skill', 'pdf')], 'off')
            client.put('/forge/v1/orgs/%s/capabilities/skill:pdf' % results[0].organization_id, headers=admin_a, json={'enabled': True})
            self.assertEqual(states(client.get(EFFECTIVE, headers=member_a).json())[('skill', 'pdf')], 'on', 'the administrator beats the platform default')

    def test_an_enabled_app_lists_only_granted_permissions_with_its_pin_and_isolation_holds(self):
        with stack() as (db, client, results, root, secrets):
            boss = owner(db, client)
            seed(client, boss)
            admin_a, member_a = login(client, results[0].accounts[0]), login(client, results[0].accounts[1])
            client.put('/forge/v1/orgs/%s/capabilities/app:acme.hello' % results[0].organization_id, headers=admin_a, json={'enabled': True})
            app = next(item for item in client.get(EFFECTIVE, headers=member_a).json()['capabilities'] if item['kind'] == 'app')
            self.assertEqual((app['id'], app['enabled'], app['granted_permissions'], app['manifest_sha256']), ('acme.hello', True, ['ui.title'], PIN))
            member_b = login(client, results[1].accounts[1])
            other = next(item for item in client.get(EFFECTIVE, headers=member_b).json()['capabilities'] if item['kind'] == 'app')
            self.assertFalse(other['enabled'])
            foreign = client.get(EFFECTIVE + '?org=%s' % results[1].organization_id, headers=member_a)
            self.assertEqual((foreign.status_code, foreign.json()['error']['code']), (404, 'NOT_FOUND'))
            self.assertEqual(client.get(EFFECTIVE).status_code, 401)

    def test_the_key_set_is_served_and_the_document_is_not_cacheable(self):
        with stack() as (db, client, results, root, secrets):
            keys = client.get('/forge/v1/capabilities/keys')
            self.assertEqual((keys.status_code, keys.json()['keys'][0]['status']), (200, 'active'))
            member = login(client, results[0].accounts[1])
            self.assertEqual(client.get(EFFECTIVE, headers=member).headers['cache-control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
