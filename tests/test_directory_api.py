"""Directory HTTP surface over mocked ports; session/readiness fixtures only."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.directory import (Account, Department, DirectoryConflict, DirectoryDenied, DirectorySuspended,
    Membership, Me)
from forge.foundation import AuthenticatedIdentity

ORG = '11111111-1111-4111-8111-111111111111'
ACCOUNT = uuid4()
HEADERS = {'Authorization': 'Bearer ' + 'A' * 43}


def sample_me():
    return Me(Account(ACCOUNT, 'admin@example.com', 'Admin'), (
        Membership(UUID(ORG), 'Org A', 'active', ('organization_admin',), (Department(uuid4(), 'Legal'),)),
        Membership(uuid4(), 'Org B', 'active', ('member',), ())))


class DirectoryApiTests(unittest.TestCase):
    def fixture(self, directory=True):
        sessions = MagicMock()
        sessions.validate.return_value = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
        readiness = MagicMock()
        readiness.check.return_value = True
        service = MagicMock()
        service.me.return_value = sample_me()
        service.departments.return_value = [Department(uuid4(), 'Legal')]
        service.create_department.side_effect = lambda token, org, name: Department(uuid4(), name)
        app = create_account_app(sessions=sessions, readiness=readiness,
                                 directory=service if directory else None)
        return TestClient(app, raise_server_exceptions=False), sessions, service

    def test_me_returns_identity_and_memberships_without_secrets(self):
        client, _, service = self.fixture()
        with client:
            response = client.get('/forge/v1/accounts/me', headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['account'], {'id': str(ACCOUNT), 'email': 'admin@example.com', 'display_name': 'Admin'})
            self.assertEqual([o['display_name'] for o in body['organizations']], ['Org A', 'Org B'])
            self.assertEqual(body['organizations'][0]['roles'], ['organization_admin'])
            self.assertEqual(body['organizations'][0]['departments'][0]['name'], 'Legal')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            for secret in ('password', 'token', 'gateway', 'api_key', 'encrypted'):
                self.assertNotIn(secret, response.text)
            self.assertEqual(service.me.call_args.args, ('A' * 43,))

    def test_me_has_no_caller_supplied_organization(self):
        client, _, service = self.fixture()
        with client:
            client.get('/forge/v1/accounts/me?organization_id=' + ORG, headers=HEADERS)
            self.assertEqual(service.me.call_args.args, ('A' * 43,))
            self.assertEqual(len(service.me.call_args.args), 1)

    def test_missing_malformed_and_revoked_sessions_are_401_and_never_reach_the_service(self):
        client, sessions, service = self.fixture()
        with client:
            for headers in ({}, {'Authorization': 'Bearer short'}, {'Authorization': 'Basic ' + 'A' * 43}):
                with self.subTest(headers=headers):
                    self.assertEqual(client.get('/forge/v1/accounts/me', headers=headers).status_code, 401)
            sessions.validate.return_value = None
            response = client.get('/forge/v1/accounts/me', headers=HEADERS)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()['error']['code'], 'UNAUTHENTICATED')
        service.me.assert_not_called()

    def test_no_active_membership_is_403_membership_suspended(self):
        client, _, service = self.fixture()
        service.me.side_effect = DirectorySuspended()
        with client:
            response = client.get('/forge/v1/accounts/me', headers=HEADERS)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['error']['code'], 'MEMBERSHIP_SUSPENDED')

    def test_unknown_account_and_unconfigured_directory(self):
        client, _, service = self.fixture()
        service.me.side_effect = DirectoryDenied()
        with client:
            self.assertEqual(client.get('/forge/v1/accounts/me', headers=HEADERS).status_code, 404)
        client, _, _ = self.fixture(directory=False)
        with client:
            self.assertEqual(client.get('/forge/v1/accounts/me', headers=HEADERS).status_code, 503)

    def test_store_failure_is_redacted_503(self):
        client, _, service = self.fixture()
        service.me.side_effect = RuntimeError('PRIVATE_SECRET_MARKER')
        with client:
            response = client.get('/forge/v1/accounts/me', headers=HEADERS)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('PRIVATE_SECRET_MARKER', response.text)

    url = '/forge/v1/orgs/' + ORG + '/departments'

    def test_list_and_create_departments(self):
        client, _, service = self.fixture()
        with client:
            listing = client.get(self.url, headers=HEADERS)
            self.assertEqual(listing.status_code, 200)
            self.assertEqual([d['name'] for d in listing.json()['departments']], ['Legal'])
            created = client.post(self.url, headers=HEADERS, json={'name': 'Finance'})
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()['name'], 'Finance')
            self.assertEqual(service.create_department.call_args.args, ('A' * 43, UUID(ORG), 'Finance'))

    def test_duplicate_name_is_a_redacted_409(self):
        client, _, service = self.fixture()
        service.create_department.side_effect = DirectoryConflict()
        with client:
            response = client.post(self.url, headers=HEADERS, json={'name': 'Legal'})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['error']['code'], 'DEPARTMENT_EXISTS')

    def test_cross_org_and_non_admin_are_uniform_404(self):
        client, _, service = self.fixture()
        service.departments.side_effect = DirectoryDenied()
        service.create_department.side_effect = DirectoryDenied()
        with client:
            self.assertEqual(client.get(self.url, headers=HEADERS).status_code, 404)
            self.assertEqual(client.post(self.url, headers=HEADERS, json={'name': 'X'}).status_code, 404)

    def test_invalid_input_is_422_before_the_service(self):
        client, _, service = self.fixture()
        with client:
            for body in ({}, {'name': ''}, {'name': 'x' * 121}, {'name': 5}, {'name': 'ok', 'org': ORG}):
                with self.subTest(body=body):
                    self.assertEqual(client.post(self.url, headers=HEADERS, json=body).status_code, 422)
            self.assertEqual(client.post(self.url, headers=HEADERS, content=b'x' * 8193).status_code, 422)
            self.assertEqual(client.get('/forge/v1/orgs/not-a-uuid/departments', headers=HEADERS).status_code, 422)
        service.create_department.assert_not_called()

    def test_service_rejects_value_error_as_422(self):
        client, _, service = self.fixture()
        service.create_department.side_effect = ValueError('bad')
        with client:
            self.assertEqual(client.post(self.url, headers=HEADERS, json={'name': 'Fine'}).status_code, 422)

    def test_unauthenticated_requests_precede_validation(self):
        client, _, service = self.fixture()
        with client:
            self.assertEqual(client.post(self.url, json={}).status_code, 401)
            self.assertEqual(client.get(self.url).status_code, 401)
        service.departments.assert_not_called()

    def test_openapi_declares_bearer_security(self):
        client, _, _ = self.fixture()
        with client:
            paths = client.get('/openapi.json').json()['paths']
            for path, method in (('/forge/v1/accounts/me', 'get'), ('/forge/v1/orgs/{organization_id}/departments', 'get'),
                                 ('/forge/v1/orgs/{organization_id}/departments', 'post')):
                self.assertEqual(paths[path][method]['security'], [{'ForgeBearer': []}])


if __name__ == '__main__':
    unittest.main()
