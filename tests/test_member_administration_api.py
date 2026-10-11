"""Member list HTTP surface over mocked ports; session/readiness fixtures only."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.directory import Department, DirectoryDenied, Member
from forge.foundation import AuthenticatedIdentity

ORG = '11111111-1111-4111-8111-111111111111'
MEMBER = '22222222-2222-4222-8222-222222222222'
HEADERS = {'Authorization': 'Bearer ' + 'A' * 43}
FIELDS = {'id', 'email', 'display_name', 'roles', 'status', 'departments'}


def sample(status='active', ident=MEMBER, roles=('member',)):
    return Member(UUID(ident), 'pat@example.com', 'Pat', status, roles, (Department(uuid4(), 'Legal'),))


class MemberApiTests(unittest.TestCase):
    members_url = '/forge/v1/orgs/' + ORG + '/members'

    def fixture(self, directory=True):
        sessions = MagicMock()
        sessions.validate.return_value = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
        readiness = MagicMock()
        readiness.check.return_value = True
        service = MagicMock()
        service.members.return_value = [sample('active', roles=('organization_admin',), ident=str(uuid4())),
                                        sample('active'), sample('suspended', ident=str(uuid4()))]
        app = create_account_app(sessions=sessions, readiness=readiness, directory=service if directory else None)
        return TestClient(app, raise_server_exceptions=False), sessions, service

    def test_admin_lists_members_with_exactly_the_public_fields(self):
        client, _, service = self.fixture()
        with client:
            response = client.get(self.members_url, headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            members = response.json()['members']
            self.assertEqual([m['status'] for m in members], ['active', 'active', 'suspended'])
            self.assertEqual(members[0]['roles'], ['organization_admin'])
            self.assertEqual(members[1]['departments'][0]['name'], 'Legal')
            for entry in members:
                self.assertEqual(set(entry), FIELDS)
            for secret in ('password', 'token', 'gateway', 'api_key', 'hash', 'encrypted'):
                self.assertNotIn(secret, response.text)
            self.assertEqual(service.members.call_args.args, ('A' * 43, UUID(ORG)))

    def test_cross_org_and_non_admin_are_the_same_redacted_404(self):
        client, _, service = self.fixture()
        service.members.side_effect = DirectoryDenied()
        with client:
            response = client.get(self.members_url, headers=HEADERS)
            self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))
            self.assertNotIn('pat@example.com', response.text)

    def test_invalid_organization_identifier_is_422_before_the_service(self):
        client, _, service = self.fixture()
        with client:
            self.assertEqual(client.get('/forge/v1/orgs/not-a-uuid/members', headers=HEADERS).status_code, 422)
        service.members.assert_not_called()

    def test_unauthenticated_requests_precede_everything(self):
        client, sessions, service = self.fixture()
        with client:
            self.assertEqual(client.get(self.members_url).status_code, 401)
            sessions.validate.return_value = None
            self.assertEqual(client.get(self.members_url, headers=HEADERS).status_code, 401)
        service.members.assert_not_called()

    def test_unconfigured_directory_and_store_failures_are_redacted_503(self):
        client, _, _ = self.fixture(directory=False)
        with client:
            self.assertEqual(client.get(self.members_url, headers=HEADERS).status_code, 503)
        client, _, service = self.fixture()
        service.members.side_effect = RuntimeError('PRIVATE_SECRET_MARKER')
        with client:
            response = client.get(self.members_url, headers=HEADERS)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('PRIVATE_SECRET_MARKER', response.text)

    def test_openapi_declares_bearer_security(self):
        client, _, _ = self.fixture()
        with client:
            paths = client.get('/openapi.json').json()['paths']
            self.assertEqual(paths['/forge/v1/orgs/{organization_id}/members']['get']['security'], [{'ForgeBearer': []}])


if __name__ == '__main__':
    unittest.main()
