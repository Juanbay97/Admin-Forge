"""Company administrators see only the gateway status; the key is the platform's. PUT is refused with nothing stored."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock
from uuid import UUID, uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from fastapi.testclient import TestClient
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.authorization import AuthorizationSnapshot
from forge.foundation import AuthenticatedIdentity, MembershipStatus
from forge.gateway_configuration import GatewayDenied, GatewayStatus
from forge.gateway_pool_store import GatewayManaged, PoolGatewayConfiguration

ORG = '11111111-1111-4111-8111-111111111111'
TOKEN = 'A' * 43


class StatusStore:
    def __init__(self, configured=True, active=2, fail=None):
        self.configured, self.active, self.fail, self.calls = configured, active, fail, []

    def status(self, digest, organization_id):
        self.calls.append((digest, organization_id))
        if self.fail:
            raise self.fail
        return self.configured, self.active


class PoolConfigurationTests(unittest.TestCase):
    def test_the_status_reports_configured_and_the_usable_key_count_and_never_an_origin(self):
        store = StatusStore(True, 2)
        status = PoolGatewayConfiguration(store).read(TOKEN, UUID(ORG))
        self.assertEqual(status, GatewayStatus('SAVED_UNVERIFIED', 2, ''))
        self.assertEqual(status.allowed_endpoints, ())
        self.assertNotEqual(store.calls[0][0], TOKEN, 'the store receives the digest, never the capability')
        self.assertEqual(PoolGatewayConfiguration(StatusStore(False, 0)).read(TOKEN, UUID(ORG)), GatewayStatus('NOT_CONFIGURED', 0, ''))

    def test_saving_is_refused_before_any_store_call(self):
        store = StatusStore()
        service = PoolGatewayConfiguration(store)
        for arguments in ((TOKEN, UUID(ORG), 0, 'a-new-key'), (TOKEN, UUID(ORG), 0, 'a-new-key', 'https://ia.prometheonlab.com')):
            with self.assertRaises(GatewayManaged):
                service.save(*arguments)
        self.assertEqual(store.calls, [])
        self.assertEqual(service.allowed_endpoints, frozenset())

    def test_a_store_denial_stays_a_denial(self):
        with self.assertRaises(GatewayDenied):
            PoolGatewayConfiguration(StatusStore(fail=GatewayDenied())).read(TOKEN, UUID(ORG))


class AdminGatewayApiTests(unittest.TestCase):
    def client(self, service=None, roles=('organization_admin',)):
        sessions, readiness, authorization = MagicMock(), MagicMock(), MagicMock()
        identity = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
        sessions.validate.return_value = identity
        readiness.check.return_value = True
        authorization.read.return_value = AuthorizationSnapshot(identity, UUID(ORG), uuid4(), 1, frozenset(roles), MembershipStatus.ACTIVE, True)
        self.store = StatusStore()
        app = create_account_app(sessions=sessions, readiness=readiness, authorization_reader=authorization,
                                 gateway_configuration=service or PoolGatewayConfiguration(self.store))
        return TestClient(app, raise_server_exceptions=False), {'Authorization': 'Bearer ' + TOKEN}

    def test_get_shows_the_status_in_the_pinned_shape_without_origin_or_key_data(self):
        http, headers = self.client()
        with http:
            body = http.get('/forge/v1/orgs/' + ORG + '/gateway', headers=headers).json()
        self.assertEqual(body, {'status': 'SAVED_UNVERIFIED', 'revision': 2, 'endpoint': '', 'allowed_endpoints': []})

    def test_put_is_forbidden_with_a_finite_code_and_stores_nothing(self):
        http, headers = self.client()
        with http:
            response = http.put('/forge/v1/orgs/' + ORG + '/gateway', headers=headers,
                                json={'expected_revision': 0, 'api_key': 'FIXTURE_SECRET_MARKER'})
        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'GATEWAY_MANAGED_BY_PLATFORM'))
        self.assertNotIn('FIXTURE_SECRET_MARKER', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.store.calls, [])

    def test_non_admins_and_foreign_companies_are_still_not_found_before_the_refusal(self):
        for roles in (('member',), ()):
            http, headers = self.client(roles=roles)
            with http:
                self.assertEqual(http.put('/forge/v1/orgs/' + ORG + '/gateway', headers=headers,
                                          json={'expected_revision': 0, 'api_key': 'k'}).status_code, 404)
                self.assertEqual(http.get('/forge/v1/orgs/' + ORG + '/gateway', headers=headers).status_code, 404)
        self.assertEqual(self.store.calls, [])


if __name__ == '__main__':
    unittest.main()
