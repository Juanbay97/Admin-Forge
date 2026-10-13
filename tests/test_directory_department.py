"""Member department assignment over a fake directory store: a hidden administrator route that sets exactly one department, bounded
and finite. Authority is the database; this layer validates shapes and redacts."""
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
from forge.directory import Department, DirectoryDenied, DirectoryService, DirectoryUnavailable, Member
from forge.directory_api import mount_member_department
from forge.foundation import AuthenticatedIdentity

ORG, MEMBER, DEPARTMENT = uuid4(), uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PATH = '/forge/v1/orgs/%s/members/%s/department' % (ORG, MEMBER)
RESULT = Member(MEMBER, 'pat@example.com', 'Pat Member', 'active', ('member',), (Department(DEPARTMENT, 'Support'),))


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(uuid4())) if token == TOKEN else None


class Store:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def assign_department(self, digest, org, member, department):
        self.calls.append((digest, org, member, department))
        if self.fail:
            raise self.fail
        return RESULT


def client(store=None):
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_member_department(app, directory=DirectoryService(store), sessions=Sessions(), readiness=Ready())
    return TestClient(app, raise_server_exceptions=False), app, store


class DepartmentRouteTests(unittest.TestCase):
    def test_hidden_from_the_contract_and_answers_with_the_member(self):
        http, app, store = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path == '/forge/v1/orgs/{organization_id}/members/{member_id}/department' for route in app.routes))
        response = http.put(PATH, headers=HEADERS, json={'department_id': str(DEPARTMENT)})
        self.assertEqual((response.status_code, response.json()), (200, {
            'id': str(MEMBER), 'email': 'pat@example.com', 'display_name': 'Pat Member', 'status': 'active', 'roles': ['member'],
            'departments': [{'id': str(DEPARTMENT), 'name': 'Support'}]}))
        self.assertEqual(store.calls[0][1:], (ORG, MEMBER, DEPARTMENT))
        self.assertNotEqual(store.calls[0][0], TOKEN, 'the store gets the digest, never the capability')

    def test_malformed_bodies_never_reach_the_store(self):
        http, _, store = client()
        for body in ({}, {'department_id': 'nope'}, {'department_id': 5}, {'department_id': None}, {'department_id': str(DEPARTMENT), 'extra': 1},
                     {'department': str(DEPARTMENT)}, [], 'x'):
            with self.subTest(body=str(body)[:50]):
                self.assertEqual(http.put(PATH, headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(http.put(PATH, headers={**HEADERS, 'content-type': 'text/plain'}, content=b'{}').status_code, 415)
        self.assertEqual(http.put(PATH, headers={**HEADERS, 'content-type': 'application/json'}, content=b'{"department_id":"' + b'x' * 2000 + b'"}').status_code, 413)
        self.assertEqual(http.put('/forge/v1/orgs/not-a-uuid/members/%s/department' % MEMBER, headers=HEADERS, json={'department_id': str(DEPARTMENT)}).status_code, 422)
        self.assertEqual(store.calls, [])

    def test_credentials_come_first_and_failures_are_finite(self):
        http, _, store = client()
        self.assertEqual(http.put(PATH, json={'department_id': str(DEPARTMENT)}).status_code, 401)
        self.assertEqual(http.put(PATH, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, json={'department_id': str(DEPARTMENT)}).status_code, 401)
        self.assertEqual(store.calls, [])
        for failure, status, code in ((DirectoryDenied(), 404, 'NOT_FOUND'), (DirectoryUnavailable(), 503, 'SERVICE_UNAVAILABLE'),
                                      (RuntimeError('boom'), 503, 'SERVICE_UNAVAILABLE'),
                                      (ValueError('x'), 422, 'INVALID_REQUEST')):
            with self.subTest(code=code):
                failing, _, _ = client(Store(failure))
                response = failing.put(PATH, headers=HEADERS, json={'department_id': str(DEPARTMENT)})
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))


class ServiceTests(unittest.TestCase):
    def test_identifiers_are_typed_before_the_store(self):
        store = Store()
        service = DirectoryService(store)
        for arguments in (('x', MEMBER, DEPARTMENT), (ORG, 'x', DEPARTMENT), (ORG, MEMBER, 'x'), (ORG, None, DEPARTMENT)):
            with self.subTest(arguments=str(arguments)[:40]), self.assertRaises(ValueError):
                service.assign_department(TOKEN, *arguments)
        self.assertEqual(store.calls, [])
        self.assertIs(service.assign_department(TOKEN, ORG, MEMBER, DEPARTMENT), RESULT)


if __name__ == '__main__':
    unittest.main()
