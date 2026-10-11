"""Member administration HTTP surface over mocked ports; session/readiness fixtures only."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.directory import Department, DirectoryDenied, DirectoryLastAdmin, Member
from forge.foundation import AuthenticatedIdentity

ORG = '11111111-1111-4111-8111-111111111111'
MEMBER = '22222222-2222-4222-8222-222222222222'
HEADERS = {'Authorization': 'Bearer ' + 'A' * 43}
FIELDS = {'id', 'email', 'display_name', 'roles', 'status', 'departments'}


def sample(status='active', ident=MEMBER, roles=('member',)):
    return Member(UUID(ident), 'pat@example.com', 'Pat', status, roles, (Department(uuid4(), 'Legal'),))


class MemberApiTests(unittest.TestCase):
    members_url = '/forge/v1/orgs/' + ORG + '/members'
    suspend_url = members_url + '/' + MEMBER + '/suspend'
    reactivate_url = members_url + '/' + MEMBER + '/reactivate'

    def fixture(self, directory=True):
        sessions = MagicMock()
        sessions.validate.return_value = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
        readiness = MagicMock()
        readiness.check.return_value = True
        service = MagicMock()
        service.members.return_value = [sample('active', roles=('organization_admin',), ident=str(uuid4())),
                                        sample('active'), sample('suspended', ident=str(uuid4()))]
        service.suspend_member.side_effect = lambda token, org, member: sample('suspended', str(member))
        service.reactivate_member.side_effect = lambda token, org, member: sample('active', str(member))
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

    def test_suspend_and_reactivate_return_the_member_with_the_new_status(self):
        client, _, service = self.fixture()
        with client:
            suspended = client.post(self.suspend_url, headers=HEADERS)
            self.assertEqual((suspended.status_code, suspended.json()['status']), (200, 'suspended'))
            self.assertEqual(set(suspended.json()), FIELDS)
            self.assertEqual(service.suspend_member.call_args.args, ('A' * 43, UUID(ORG), UUID(MEMBER)))
            reactivated = client.post(self.reactivate_url, headers=HEADERS)
            self.assertEqual((reactivated.status_code, reactivated.json()['status']), (200, 'active'))
            self.assertEqual(service.reactivate_member.call_args.args, ('A' * 43, UUID(ORG), UUID(MEMBER)))

    def test_last_admin_is_a_redacted_409(self):
        client, _, service = self.fixture()
        service.suspend_member.side_effect = DirectoryLastAdmin()
        with client:
            response = client.post(self.suspend_url, headers=HEADERS)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['error']['code'], 'LAST_ADMIN')
            self.assertNotIn(MEMBER, response.text)

    def test_cross_org_non_admin_and_unknown_member_are_the_same_404(self):
        client, _, service = self.fixture()
        service.members.side_effect = DirectoryDenied()
        service.suspend_member.side_effect = DirectoryDenied()
        service.reactivate_member.side_effect = DirectoryDenied()
        with client:
            responses = [client.get(self.members_url, headers=HEADERS), client.post(self.suspend_url, headers=HEADERS),
                         client.post(self.reactivate_url, headers=HEADERS)]
            self.assertEqual([r.status_code for r in responses], [404, 404, 404])
            self.assertEqual({r.json()['error']['code'] for r in responses}, {'NOT_FOUND'})

    def test_invalid_identifiers_and_oversized_bodies_are_422_before_the_service(self):
        client, _, service = self.fixture()
        with client:
            self.assertEqual(client.get('/forge/v1/orgs/not-a-uuid/members', headers=HEADERS).status_code, 422)
            self.assertEqual(client.post(self.members_url + '/not-a-uuid/suspend', headers=HEADERS).status_code, 422)
            self.assertEqual(client.post(self.suspend_url, headers=HEADERS, content=b'x' * 8193).status_code, 422)
            self.assertEqual(client.post(self.reactivate_url, headers=HEADERS, content=b'x' * 8193).status_code, 422)
        service.suspend_member.assert_not_called()
        service.reactivate_member.assert_not_called()

    def test_unauthenticated_requests_precede_everything(self):
        client, sessions, service = self.fixture()
        with client:
            self.assertEqual(client.get(self.members_url).status_code, 401)
            self.assertEqual(client.post(self.suspend_url).status_code, 401)
            self.assertEqual(client.post(self.reactivate_url).status_code, 401)
            sessions.validate.return_value = None
            self.assertEqual(client.get(self.members_url, headers=HEADERS).status_code, 401)
        service.members.assert_not_called()
        service.suspend_member.assert_not_called()

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
            for path, method in (('/forge/v1/orgs/{organization_id}/members', 'get'),
                                 ('/forge/v1/orgs/{organization_id}/members/{member_id}/suspend', 'post'),
                                 ('/forge/v1/orgs/{organization_id}/members/{member_id}/reactivate', 'post')):
                self.assertEqual(paths[path][method]['security'], [{'ForgeBearer': []}])


if __name__ == '__main__':
    unittest.main()
