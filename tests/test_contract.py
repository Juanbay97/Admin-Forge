"""Control-plane contract pin: generated from the app routes, committed, and served with its hash."""
import json
from pathlib import Path
import re
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app

ROUTES = {(r['method'], r['path']): r for r in contract.build(create_account_app())['routes']}


class ContractDocumentTests(unittest.TestCase):
    def test_version_and_every_forge_route_are_listed_with_request_and_response_key_sets(self):
        document = contract.build(create_account_app())
        self.assertEqual(document['contract_version'], 'forge-mvp/1')
        self.assertEqual(contract.CONTRACT_VERSION, 'forge-mvp/1')
        self.assertTrue(all(path.startswith('/forge/v1/') for _, path in ROUTES))
        me = ROUTES[('GET', '/forge/v1/accounts/me')]
        self.assertEqual((me['auth'], me['request']), ('bearer', []))
        self.assertEqual(me['responses']['200'], [
            'account.display_name', 'account.email', 'account.id', 'organizations[].departments[].id',
            'organizations[].departments[].name', 'organizations[].display_name', 'organizations[].id',
            'organizations[].roles', 'organizations[].status'])
        self.assertIn(403, me['errors'])
        put = ROUTES[('PUT', '/forge/v1/orgs/{organization_id}/gateway')]
        self.assertEqual(put['request'], ['api_key', 'endpoint', 'expected_revision'])
        self.assertEqual(put['responses']['200'], ['endpoint', 'revision', 'status'])
        publish = ROUTES[('POST', '/forge/v1/orgs/{organization_id}/models/publish')]
        self.assertIn('aliases{}', publish['request'])
        self.assertEqual(publish['request'].count('operation_id'), 1)

    def test_the_login_route_is_public_and_the_stream_route_declares_its_media_type(self):
        login = ROUTES[('POST', '/forge/v1/accounts/login')]
        self.assertEqual((login['auth'], login['request']), ('none', ['email', 'password']))
        self.assertEqual(login['responses']['200'], ['access_token', 'expires_at', 'token_type'])
        chat = ROUTES[('POST', '/forge/v1/orgs/{organization_id}/chat/completions')]
        self.assertEqual(chat['responses']['200'], ['text/event-stream'])
        self.assertEqual(chat['request'], ['max_output_tokens', 'messages[].content', 'messages[].role',
                                           'model', 'stream'])
        logout = ROUTES[('POST', '/forge/v1/accounts/logout')]
        self.assertEqual(logout['responses']['204'], [])

    def test_error_envelope_and_codes_cover_every_code_the_api_can_raise(self):
        document = contract.build(create_account_app())
        self.assertEqual(document['error_envelope'], [
            'error.code', 'error.message', 'error.request_id', 'error.reset_at', 'error.retry_after_seconds',
            'error.retryable'])
        source = (ROOT/'src/forge/account_api.py').read_text('utf-8')
        raised = set(re.findall(r"(?:ApiFailure|AccountFailure)\(\d+,'([A-Z_]+)'", source))
        raised |= set(re.findall(r"code='([A-Z_]+)'", source))
        self.assertGreaterEqual(len(raised), 8)
        self.assertEqual(sorted(raised), document['error_codes'])

    def test_committed_file_equals_the_regenerated_document(self):
        committed = json.loads(contract.COMMITTED_PATH.read_text('utf-8'))
        self.assertEqual(committed, contract.build(create_account_app()),
                         'run: python -m forge.contract --write')
        self.assertEqual(contract.COMMITTED_PATH.name, 'forge-mvp.contract.json')

    def test_render_round_trips_and_is_stable(self):
        document = contract.build(create_account_app())
        text = contract.render(document)
        self.assertEqual(json.loads(text), document)
        self.assertEqual(contract.render(json.loads(text)), text)
        self.assertTrue(text.endswith('\n'))

    def test_hash_is_canonical_and_changes_with_any_route_or_key_drift(self):
        document = contract.build(create_account_app())
        digest = contract.canonical_sha256(document)
        self.assertRegex(digest, r'^[0-9a-f]{64}$')
        # Independent of key order and of the committed file's line endings.
        shuffled = {key: document[key] for key in reversed(list(document))}
        self.assertEqual(contract.canonical_sha256(shuffled), digest)
        self.assertEqual(contract.canonical_sha256(json.loads(contract.render(document).replace('\n', '\r\n'))), digest)
        app = create_account_app()

        @app.get('/forge/v1/drifted')
        def drifted():
            return {'ok': True}
        self.assertNotEqual(contract.canonical_sha256(contract.build(app)), digest)
        changed = json.loads(json.dumps(document))
        changed['routes'][0]['request'].append('extra')
        self.assertNotEqual(contract.canonical_sha256(changed), digest)


class ContractRouteTests(unittest.TestCase):
    def test_serves_version_and_hash_of_the_committed_contract_without_authentication(self):
        committed = json.loads(contract.COMMITTED_PATH.read_text('utf-8'))
        with TestClient(create_account_app(), raise_server_exceptions=False) as client:
            response = client.get('/forge/v1/contract')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'contract_version': 'forge-mvp/1',
                                               'schema_sha256': contract.canonical_sha256(committed)})
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(client.get('/forge/v1/contract').json(), response.json())

    def test_the_served_hash_tracks_the_routes_of_the_serving_app(self):
        app = create_account_app()

        @app.get('/forge/v1/extra')
        def extra():
            return {'ok': True}
        with TestClient(app, raise_server_exceptions=False) as client:
            served = client.get('/forge/v1/contract').json()['schema_sha256']
        self.assertEqual(served, contract.canonical_sha256(contract.build(app)))
        self.assertNotEqual(served, contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))

    def test_other_methods_are_refused(self):
        with TestClient(create_account_app(), raise_server_exceptions=False) as client:
            self.assertEqual(client.post('/forge/v1/contract').status_code, 405)


if __name__ == '__main__':
    unittest.main()
