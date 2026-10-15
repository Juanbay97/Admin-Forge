"""Platform catalog routes over a fake service: hidden (contract pin unchanged), bearer-authenticated, bounded and finite."""
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
from forge.platform import NoActiveMember, PlatformDenied, PlatformInvalid, RevisionConflict
from forge.platform_api import mount_platform

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PATH = '/forge/v1/platform/companies/%s/catalog' % ORG
DISCOVERY = {'keys': [{'key_id': str(uuid4()), 'label': 'primary', 'origin': 'https://gateway.fixture.example', 'priority': 1,
                       'state': 'ok', 'model_count': 1, 'model_ids': ['m-a']}], 'model_ids': ['m-a'], 'discovered_at': '2026-10-14T12:00:00+00:00'}
BODY = {'expected_catalogue_revision': 0, 'expected_gateway_revision': 1, 'aliases': {'fast': 'm-a'}, 'default_alias': 'fast'}


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class FakeCatalog:
    def __init__(self, fail=None, found=None):
        self.calls, self.fail, self.found = [], fail, found

    def _do(self, name, *args):
        self.calls.append((name, args))
        if self.fail:
            raise self.fail

    def read(self, token, org):
        self._do('read', token, org)
        return self.found

    async def discover(self, token, org):
        self._do('discover', token, org)
        return DISCOVERY

    def publish(self, token, org, operation, expected, gateway_revision, mapping, default):
        self._do('publish', token, org, expected, gateway_revision, mapping, default)
        return {'revision': expected + 1, 'default_model': default, 'models': sorted(mapping)}


def client(catalog=None):
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), catalog=catalog or FakeCatalog())
    return TestClient(app, raise_server_exceptions=False), app


class CatalogRouteTests(unittest.TestCase):
    def test_the_routes_are_hidden_so_the_contract_pin_is_unchanged(self):
        _, app = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path == '/forge/v1/platform/companies/{organization_id}/catalog' for route in app.routes))

    def test_every_route_needs_the_bearer(self):
        http, _ = client()
        for method, path, body in (('GET', PATH, None), ('POST', PATH + '/discover', {}), ('PUT', PATH, BODY)):
            with self.subTest(path=path, method=method):
                self.assertEqual(http.request(method, path, json=body).status_code, 401)
                self.assertEqual(http.request(method, path, json=body, headers={'Authorization': 'Bearer ' + 'x' * 43}).status_code, 401)

    def test_read_marks_an_unconfigured_company_and_passes_the_projection_otherwise(self):
        http, _ = client(FakeCatalog())
        self.assertEqual(http.get(PATH, headers=HEADERS).json(), {'configured': False})
        http, _ = client(FakeCatalog(found={'gateway_revision': 1, 'ceiling': [], 'discovered': None,
                                            'catalogue': {'revision': 0, 'default_model': None, 'state': 'UNPUBLISHED', 'aliases': {}}}))
        body = http.get(PATH, headers=HEADERS).json()
        self.assertEqual((body['configured'], body['gateway_revision'], body['catalogue']['state']), (True, 1, 'UNPUBLISHED'))

    def test_discover_runs_the_service_and_rejects_a_body_with_content(self):
        catalog = FakeCatalog()
        http, _ = client(catalog)
        response = http.post(PATH + '/discover', headers=HEADERS, json={})
        self.assertEqual((response.status_code, response.json()), (200, DISCOVERY))
        self.assertEqual(catalog.calls[0][1][1], ORG)
        self.assertEqual(http.post(PATH + '/discover', headers=HEADERS, json={'key': 'x'}).status_code, 422)
        self.assertEqual(http.post(PATH + '/discover', headers=HEADERS, content=b'{}', ).status_code, 415)
        self.assertEqual(len(catalog.calls), 1)

    def test_publish_passes_validated_values_and_returns_the_new_revision(self):
        catalog = FakeCatalog()
        http, _ = client(catalog)
        response = http.put(PATH, headers=HEADERS, json=BODY)
        self.assertEqual((response.status_code, response.json()), (200, {'revision': 1, 'default_model': 'fast', 'models': ['fast']}))
        self.assertEqual(catalog.calls[0][1][2:], (0, 1, {'fast': 'm-a'}, 'fast'))

    def test_publish_refuses_a_malformed_body_before_calling_the_service(self):
        catalog = FakeCatalog()
        http, _ = client(catalog)
        bad = (
            {**BODY, 'extra': 1}, {k: v for k, v in BODY.items() if k != 'default_alias'}, {**BODY, 'aliases': ['fast']},
            {**BODY, 'aliases': {'fast': 7}}, {**BODY, 'default_alias': 3}, {**BODY, 'expected_catalogue_revision': -1},
            {**BODY, 'expected_gateway_revision': 0}, {**BODY, 'expected_catalogue_revision': True}, {**BODY, 'expected_gateway_revision': '1'},
        )
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(http.put(PATH, headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(http.put(PATH, headers=HEADERS, content=b'x' * 40000, ).status_code, 415)
        oversized = http.put(PATH, headers={**HEADERS, 'Content-Type': 'application/json'}, content=b'{"a":"' + b'x' * 40000 + b'"}')
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(catalog.calls, [])

    def test_failures_are_finite_codes(self):
        for failure, status, code in ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (RevisionConflict(), 409, 'REVISION_CONFLICT'),
                                      (NoActiveMember(), 409, 'NO_ACTIVE_MEMBER'), (PlatformInvalid(), 422, 'INVALID_REQUEST'),
                                      (RuntimeError('boom with a secret'), 503, 'SERVICE_UNAVAILABLE')):
            with self.subTest(code=code):
                http, _ = client(FakeCatalog(fail=failure))
                response = http.put(PATH, headers=HEADERS, json=BODY)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
                self.assertNotIn('secret', response.text)


if __name__ == '__main__':
    unittest.main()
