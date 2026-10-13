"""Owned PostgreSQL: the real mvp_local composition (readiness F25, allow-list, directory, mailbox, guard)."""
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from forge import contract
from forge.mvp_local import MVP_PORTS, compose, load_config, load_secrets
from forge.mvp_profile import MVP_PROFILE
from forge.provisioning import SEED, provision
from mvp_support import LOGIN_ROLES, mvp_database

CLIENT = 'http://127.0.0.1:3411'
ADMIN = 'http://127.0.0.1:%d' % MVP_PORTS['control_plane']
GATEWAY = 'http://127.0.0.1:%d' % MVP_PORTS['fake_gateway']


@contextmanager
def stack(environment=None):
    """A composed control plane over a provisioned two-organization database."""
    with mvp_database() as db, tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
        # Only the application sees the hostile environment, never the harness' own admin connections.
        cleanup.enter_context(patch.dict(os.environ, environment or {}))
        root = Path(directory)
        (root/'mailbox').mkdir()
        (root/'admin').mkdir()
        (root/'admin'/'index.html').write_text('<title>Forge admin</title>', 'utf-8')
        secrets = {'roles': dict(db.passwords), 'delivery_key': Fernet.generate_key().decode(),
                   'gateway_key': Fernet.generate_key().decode(), 'platform_key': Fernet.generate_key().decode()}
        (root/'secrets.json').write_text(json.dumps(secrets), 'utf-8')
        values = db.connection_settings()
        config_path = root/'config.json'
        config_path.write_text(json.dumps({
            'version': 1, 'profile': MVP_PROFILE,
            'database': {'host': values['host'], 'port': values['port'], 'dbname': values['dbname']},
            'secrets_file': str(root/'secrets.json'), 'mailbox_dir': str(root/'mailbox'),
            'admin_dir': str(root/'admin'), 'require_admin_build': True,
            'control_plane_port': MVP_PORTS['control_plane'], 'client_origin': CLIENT, 'cors_origins': [CLIENT],
            'gateway_allowed_endpoints': [GATEWAY]}), 'utf-8')
        results = provision(db.admin, SEED, lambda created: None)
        pools = []
        cleanup.callback(lambda: [pool.close(timeout=5) for pool in reversed(pools)])
        config = load_config(str(config_path))
        app = compose(config, load_secrets(config.secrets_file), pools)
        client = cleanup.enter_context(TestClient(app, base_url=ADMIN, raise_server_exceptions=False))
        yield db, client, results, root, secrets


def login(client, account):
    response = client.post('/forge/v1/accounts/login', json={'email': account.email, 'password': account.password})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


class PostgresMvpLocalTests(unittest.TestCase):
    def test_status_is_ready_on_the_pinned_profile_and_the_contract_is_served(self):
        with stack() as (db, client, results, root, secrets):
            status = client.get('/status')
            self.assertEqual((status.status_code, status.json()), (200, {'status': 'ready', 'profile': MVP_PROFILE, 'admin': 'ready'}))
            served = client.get('/forge/v1/contract').json()
            self.assertEqual(served['contract_version'], 'forge-mvp/1')
            self.assertEqual(served['schema_sha256'], contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            self.assertIn('Forge admin', client.get('/admin/').text)

    def test_status_turns_not_ready_when_the_schema_drifts(self):
        with stack() as (db, client, results, root, secrets):
            self.assertEqual(client.get('/status').status_code, 200)
            db.admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
            self.assertEqual((client.get('/status').status_code, client.get('/status').json()['status']), (503, 'not_ready'))

    def test_environment_variables_cannot_redirect_the_database(self):
        environment = {'PGDATABASE': 'elsewhere', 'PGHOST': '203.0.113.9', 'PGPORT': '1', 'PGUSER': 'root',
                       'PGPASSWORD': 'wrong'}
        with stack(environment) as (db, client, results, root, secrets):
            self.assertEqual(client.get('/status').status_code, 200)
            admin = results[0].accounts[0]
            me = client.get('/forge/v1/accounts/me', headers=login(client, admin))
            self.assertEqual([o['display_name'] for o in me.json()['organizations']], ['Organization A'])

    def test_an_invitation_is_written_to_the_mailbox_with_the_client_origin_and_no_other_secret(self):
        with stack() as (db, client, results, root, secrets):
            first = results[0]
            admin = first.accounts[0]
            headers = login(client, admin)
            invited = client.post('/forge/v1/accounts/invitations', headers={**headers, 'Origin': ADMIN}, json={
                'organization_id': str(first.organization_id), 'department_id': str(first.department_id),
                'email': 'newcomer@example.com', 'name': 'New Comer'})
            self.assertEqual((invited.status_code, invited.json()['delivery_channel']), (201, 'local_test_mailbox'))
            (message,) = sorted((root/'mailbox').glob('*.eml'))
            text = message.read_text('utf-8')
            self.assertRegex(text, r'To: newcomer@example\.com')
            self.assertEqual(set(re.findall(r'http://[0-9.:]+/[a-z]+', text)), {CLIENT + '/onboarding'})
            private = [admin.password, headers['Authorization'].split(' ')[1], results[0].gateway_key, results[1].gateway_key,
                       secrets['delivery_key'], secrets['gateway_key'], *db.passwords.values(), *(a.password for r in results for a in r.accounts)]
            self.assertFalse([value for value in private if value in text])

    def test_the_gateway_is_read_only_for_the_admin_and_the_origin_and_host_guards_are_wired_end_to_end(self):
        with stack() as (db, client, results, root, secrets):
            first = results[0]
            headers = login(client, first.accounts[0])
            url = '/forge/v1/orgs/%s/gateway' % first.organization_id
            status = client.get(url, headers=headers).json()
            self.assertEqual((status['status'], status['allowed_endpoints']), ('NOT_CONFIGURED', []), 'no origin details reach the admin')
            saved = client.put(url, headers=headers, json={'expected_revision': 0, 'api_key': first.gateway_key, 'endpoint': GATEWAY})
            self.assertEqual((saved.status_code, saved.json()['error']['code']), (403, 'GATEWAY_MANAGED_BY_PLATFORM'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.organization_gateways').fetchone(), (0,), 'nothing is stored')
            foreign = client.put(url, headers={**headers, 'Origin': 'http://evil.test'},
                                 json={'expected_revision': 0, 'api_key': first.gateway_key, 'endpoint': GATEWAY})
            self.assertEqual((foreign.status_code, foreign.json()['error']['code']), (403, 'FORBIDDEN_ORIGIN'))
            self.assertNotIn(first.gateway_key, saved.text + client.get(url, headers=headers).text)
            self.assertEqual(client.get(url, headers={**headers, 'Host': 'evil.test:3410'}).status_code, 403)

    def test_directory_and_member_listing_work_through_the_composed_app(self):
        with stack() as (db, client, results, root, secrets):
            first = results[0]
            headers = login(client, first.accounts[0])
            members = client.get('/forge/v1/orgs/%s/members' % first.organization_id, headers=headers)
            self.assertEqual(sorted(m['email'] for m in members.json()['members']),
                             ['admin-a@forge.local.test', 'member-a@forge.local.test'])
            other = client.get('/forge/v1/orgs/%s/members' % results[1].organization_id, headers=headers)
            self.assertEqual(other.status_code, 404)
            self.assertEqual(len(LOGIN_ROLES), 6)


if __name__ == '__main__':
    unittest.main()
