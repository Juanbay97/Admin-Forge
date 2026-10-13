"""Platform gateway-key routes over a fake service: hidden, bearer-authenticated, bounded and finite; key text is accepted
only on create/rotate and never appears in a response."""
import json
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.foundation import AuthenticatedIdentity
from forge.gateway_keys import GatewayKeyInfo, KeyAssignment
from forge.platform import KeyConflict, MfaRequired, PlatformDenied, PlatformInvalid, PlatformNotFound, RevisionConflict
from forge.platform_api import mount_platform

ORG, KEY_ID, ACCOUNT = uuid4(), uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
BASE = '/forge/v1/platform'
KEY = 'pool-fixture-key-ABCD'
INFO = GatewayKeyInfo(KEY_ID, 'primary', 'https://gateway.fixture.example', 1, 'active', True, 'ABCD', 0)
ASSIGNED = KeyAssignment(KEY_ID, 'primary', 'https://gateway.fixture.example', 1, True, 'active', True)


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class FakeKeys:
    allowed_origins = ('https://gateway.fixture.example',)

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _do(self, name, *args):
        self.calls.append((name, args))
        if self.fail:
            raise self.fail
        return {'create': INFO, 'rotate': INFO, 'set_status': INFO, 'keys': [INFO], 'assignments': [ASSIGNED], 'assign': [ASSIGNED],
                'ceiling': ['gpt-a'], 'set_ceiling': ['gpt-a']}[name]

    def create(self, token, label, origin, key): return self._do('create', token, label, origin, key)
    def keys(self, token): return self._do('keys', token)
    def rotate(self, token, key_id, expected, key): return self._do('rotate', token, key_id, expected, key)
    def set_status(self, token, key_id, active): return self._do('set_status', token, key_id, active)
    def assignments(self, token, org): return self._do('assignments', token, org)
    def assign(self, token, org, entries): return self._do('assign', token, org, entries)
    def ceiling(self, token, org): return self._do('ceiling', token, org)
    def set_ceiling(self, token, org, models): return self._do('set_ceiling', token, org, models)


def client(keys=None):
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), keys=keys or FakeKeys())
    return TestClient(app, raise_server_exceptions=False), app


class KeyRouteTests(unittest.TestCase):
    def test_the_routes_are_hidden_so_the_contract_pin_is_unchanged(self):
        http, app = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path == BASE + '/gateway-keys' for route in app.routes))

    def test_create_accepts_the_key_once_and_the_response_carries_metadata_only(self):
        keys = FakeKeys()
        http, _ = client(keys)
        response = http.post(BASE + '/gateway-keys', headers=HEADERS,
                             json={'label': 'primary', 'origin': 'https://gateway.fixture.example', 'key': KEY})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'id': str(KEY_ID), 'label': 'primary', 'origin': 'https://gateway.fixture.example',
                                           'revision': 1, 'status': 'active', 'has_key': True, 'hint': 'ABCD', 'companies': 0})
        self.assertNotIn(KEY, response.text)
        self.assertEqual(keys.calls[0][1][1:], ('primary', 'https://gateway.fixture.example', KEY))
        placeholder = http.post(BASE + '/gateway-keys', headers=HEADERS, json={'label': 'spare', 'origin': 'https://gateway.fixture.example'})
        self.assertEqual((placeholder.status_code, keys.calls[1][1][3]), (201, None))

    def test_list_shows_the_allow_listed_origins_and_never_key_text(self):
        http, _ = client()
        body = http.get(BASE + '/gateway-keys', headers=HEADERS).json()
        self.assertEqual((body['keys'][0]['label'], body['allowed_origins']), ('primary', ['https://gateway.fixture.example']))
        self.assertNotIn('"key"', json.dumps(body))

    def test_rotate_disable_and_enable(self):
        keys = FakeKeys()
        http, _ = client(keys)
        path = BASE + '/gateway-keys/%s' % KEY_ID
        self.assertEqual(http.post(path + '/rotate', headers=HEADERS, json={'expected_revision': 1, 'key': KEY}).status_code, 200)
        self.assertEqual(http.post(path + '/disable', headers=HEADERS).status_code, 200)
        self.assertEqual(http.post(path + '/enable', headers=HEADERS).status_code, 200)
        self.assertEqual([call[0] for call in keys.calls], ['rotate', 'set_status', 'set_status'])
        self.assertEqual([call[1][2] for call in keys.calls[1:]], [False, True])

    def test_assignment_and_model_access_routes_pass_validated_values(self):
        keys = FakeKeys()
        http, _ = client(keys)
        company = BASE + '/companies/%s' % ORG
        put = http.put(company + '/gateway-keys', headers=HEADERS, json={'keys': [{'key_id': str(KEY_ID), 'priority': 1, 'active': True}]})
        self.assertEqual((put.status_code, put.json()['keys'][0]['priority']), (200, 1))
        self.assertEqual(keys.calls[0][1][2], [(KEY_ID, 1, True)])
        self.assertEqual(http.get(company + '/gateway-keys', headers=HEADERS).json()['keys'][0]['key_id'], str(KEY_ID))
        self.assertEqual(http.put(company + '/model-access', headers=HEADERS, json={'models': ['gpt-a']}).json(), {'models': ['gpt-a']})
        self.assertEqual(http.get(company + '/model-access', headers=HEADERS).json(), {'models': ['gpt-a']})

    def test_malformed_bodies_are_refused_before_the_service(self):
        keys = FakeKeys()
        http, _ = client(keys)
        company = BASE + '/companies/%s' % ORG
        bad = [('POST', BASE + '/gateway-keys', {'label': 'x'}), ('POST', BASE + '/gateway-keys', {'label': 'x', 'origin': 'o', 'key': 5}),
               ('POST', BASE + '/gateway-keys', {'label': 'x', 'origin': 'o', 'extra': 'y'}),
               ('POST', BASE + '/gateway-keys/%s/rotate' % KEY_ID, {'expected_revision': '1', 'key': KEY}),
               ('POST', BASE + '/gateway-keys/%s/rotate' % KEY_ID, {'expected_revision': 1}),
               ('PUT', company + '/gateway-keys', {'keys': [{'key_id': 'not-a-uuid', 'priority': 1, 'active': True}]}),
               ('PUT', company + '/gateway-keys', {'keys': [{'key_id': str(KEY_ID), 'priority': True, 'active': True}]}),
               ('PUT', company + '/gateway-keys', {'keys': [{'key_id': str(KEY_ID), 'priority': 1}]}),
               ('PUT', company + '/gateway-keys', {'keys': 'x'}), ('PUT', company + '/model-access', {'models': 'gpt-a'}),
               ('PUT', company + '/model-access', {'models': [1]}), ('PUT', company + '/model-access', {})]
        for method, path, body in bad:
            with self.subTest(path=path, body=str(body)[:40]):
                self.assertEqual(http.request(method, path, headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(keys.calls, [])
        self.assertEqual(http.post(BASE + '/gateway-keys', headers=HEADERS | {'Content-Type': 'application/json'}, content=b'{"label":"' + b'x' * 9000 + b'"}').status_code, 413)

    def test_authentication_and_finite_error_mapping(self):
        keys = FakeKeys()
        http, _ = client(keys)
        self.assertEqual(http.get(BASE + '/gateway-keys').status_code, 401)
        self.assertEqual(http.get(BASE + '/gateway-keys', headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}).status_code, 401)
        self.assertEqual(keys.calls, [])
        for failure, status, code in ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (MfaRequired(), 403, 'MFA_REQUIRED'),
                                      (KeyConflict(), 409, 'KEY_CONFLICT'), (RevisionConflict(), 409, 'REVISION_CONFLICT'),
                                      (PlatformInvalid(), 422, 'INVALID_REQUEST'), (PlatformNotFound(), 404, 'NOT_FOUND'),
                                      (RuntimeError(KEY), 503, 'SERVICE_UNAVAILABLE')):
            with self.subTest(code=code):
                failing, _ = client(FakeKeys(failure))
                response = failing.get(BASE + '/gateway-keys', headers=HEADERS)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
                self.assertNotIn(KEY, response.text)

    def test_without_a_key_service_the_routes_do_not_exist(self):
        app = create_account_app(sessions=None)
        mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready())
        self.assertEqual(TestClient(app).get(BASE + '/gateway-keys', headers=HEADERS).status_code, 404)


if __name__ == '__main__':
    unittest.main()
