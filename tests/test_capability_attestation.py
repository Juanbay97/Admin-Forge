"""Client attestation reports: a strict allow-list validated before the store and again by the database, and the hidden member route
``POST /forge/v1/client/attestation``. The report is advisory telemetry (client-asserted): no path, environment or content field exists."""
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
from forge.capability_api import mount_client_attestation
from forge.capability_attestation import AttestationReports, MAX_CASES
from forge.capability_model import CapabilityDenied, CapabilityInvalid
from forge.foundation import AuthenticatedIdentity

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PATH = '/forge/v1/client/attestation'


def report(**change):
    item = {'level': 3, 'suite_version': '1.2.0', 'client_version': '0.9.1', 'os_build': '10.0.26200',
            'cases': [{'id': 'traversal', 'passed': True}, {'id': 'env_dump', 'passed': True}], 'at': '2026-10-12T12:00:00Z'}
    item.update(change)
    return item


class Store:
    def __init__(self, fail=None, stored=True):
        self.calls, self.fail, self.stored = [], fail, stored

    def attest(self, digest, org, document):
        self.calls.append((digest, org, document))
        if self.fail:
            raise self.fail
        return self.stored


class ValidationTests(unittest.TestCase):
    def test_a_valid_report_reaches_the_store_normalized(self):
        store = Store()
        reports = AttestationReports(store)
        self.assertIs(reports.record(TOKEN, ORG, report(at='2026-10-12T12:00:00.5Z')), True)
        ((digest, org, document),) = store.calls
        self.assertNotEqual(digest, TOKEN)
        self.assertEqual((org, document['level'], document['at'], document['cases'][0]), (ORG, 3, '2026-10-12T12:00:00.5Z', {'id': 'traversal', 'passed': True}))
        self.assertEqual(set(document), {'level', 'suite_version', 'client_version', 'os_build', 'cases', 'at'})
        self.assertIs(AttestationReports(Store(stored=False)).record(TOKEN, ORG, report(cases=[])), False)

    def test_content_fields_and_malformed_values_never_reach_the_store(self):
        store = Store()
        reports = AttestationReports(store)
        bad = [{**report(), 'paths': ['C:\\Users\\x']}, {**report(), 'env': {'PATH': 'x'}}, {**report(), 'user': 'pat'}, {**report(), 'extra': 1},
               {k: v for k, v in report().items() if k != 'level'}, {k: v for k, v in report().items() if k != 'cases'},
               report(level=5), report(level=-1), report(level=True), report(level='3'), report(level=3.0), report(level=None),
               report(suite_version=''), report(suite_version='x' * 33), report(suite_version='a b'), report(client_version='1.0;rm'), report(client_version=5),
               report(os_build='C:\\Windows'), report(os_build='x' * 65), report(os_build=''),
               report(at='yesterday'), report(at='2026-10-12 12:00:00'), report(at='2026-10-12T12:00:00+00:00'), report(at=5),
               report(cases='x'), report(cases=None), report(cases=[{'id': 'a'}]), report(cases=[{'id': 'a', 'passed': 'yes'}]),
               report(cases=[{'id': 'a', 'passed': True, 'detail': 'C:\\x'}]), report(cases=[{'id': 'Bad Id', 'passed': True}]),
               report(cases=[{'id': 'x' * 65, 'passed': True}]), report(cases=['a']), report(cases=[{'id': 'a', 'passed': 1}]),
               report(cases=[{'id': 'a', 'passed': True}] * (MAX_CASES + 1)), 'text', 5, None, [], ()]
        for item in bad:
            with self.subTest(item=str(item)[:70]), self.assertRaises(CapabilityInvalid):
                reports.record(TOKEN, ORG, item)
        with self.assertRaises(CapabilityInvalid):
            reports.record(TOKEN, 'not-uuid', report())
        self.assertEqual(store.calls, [])
        self.assertIs(reports.record(TOKEN, ORG, report(cases=[{'id': 'a', 'passed': False}] * MAX_CASES)), True)


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class Ready:
    def check(self):
        return True


def client(store=None, organizations=None):
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_client_attestation(app, reports=AttestationReports(store), sessions=Sessions(), readiness=Ready(), organizations=organizations or (lambda token: [ORG]))
    return TestClient(app, raise_server_exceptions=False), app, store


class RouteTests(unittest.TestCase):
    def test_hidden_and_the_contract_pin_is_unchanged(self):
        _, app, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)), contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertIn(PATH, {route.path for route in app.routes})

    def test_a_member_report_is_accepted_and_says_whether_it_was_stored(self):
        http, _, store = client()
        accepted = http.post(PATH, headers=HEADERS, json=report())
        self.assertEqual((accepted.status_code, accepted.json()), (202, {'level': 3, 'stored': True}))
        self.assertEqual(store.calls[0][1], ORG)
        again, _, _ = client(Store(stored=False))
        self.assertEqual(again.post(PATH, headers=HEADERS, json=report()).json(), {'level': 3, 'stored': False})
        self.assertEqual(http.post(PATH, json=report()).status_code, 401)
        self.assertEqual(http.post(PATH, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, json=report()).status_code, 401)

    def test_content_fields_and_bad_shapes_are_422_and_nothing_is_stored(self):
        http, _, store = client()
        for body in ({**report(), 'paths': ['C:\\x']}, report(level=9), report(cases=[{'id': 'a', 'passed': True, 'output': 'x'}]), [], {}, 'x'):
            response = http.post(PATH, headers=HEADERS, json=body)
            self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'), str(body)[:50])
        self.assertEqual(http.post(PATH + '?extra=1', headers=HEADERS, json=report()).status_code, 422)
        self.assertEqual(store.calls, [])

    def test_oversized_and_wrongly_typed_bodies_are_refused_first(self):
        http, _, store = client()
        self.assertEqual(http.post(PATH, headers={**HEADERS, 'content-type': 'application/json'}, content=b'{"cases":[' + b' ' * 10000 + b']}').status_code, 413)
        self.assertEqual(http.post(PATH, headers={**HEADERS, 'content-type': 'text/plain'}, content=b'{}').status_code, 415)
        self.assertEqual(store.calls, [])

    def test_company_selection_and_denial_follow_the_effective_route(self):
        other = uuid4()
        http, _, _ = client(organizations=lambda token: [ORG, other])
        self.assertEqual(http.post(PATH, headers=HEADERS, json=report()).status_code, 422)
        self.assertEqual(http.post(PATH + '?org=%s' % other, headers=HEADERS, json=report()).status_code, 202)
        self.assertEqual(http.post(PATH + '?org=%s' % uuid4(), headers=HEADERS, json=report()).status_code, 404)
        denied, _, _ = client(Store(CapabilityDenied()))
        response = denied.post(PATH, headers=HEADERS, json=report())
        self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))


if __name__ == '__main__':
    unittest.main()
