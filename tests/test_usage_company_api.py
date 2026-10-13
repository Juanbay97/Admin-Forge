"""Company per-person usage route over fakes: hidden from the contract, administrator-only, own company only, bounded and finite."""
from datetime import date
import json
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import MagicMock
from uuid import UUID, uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from dataclasses import replace
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.authorization import AuthorizationSnapshot
from forge.directory import DirectoryDenied, DirectoryUnavailable
from forge.foundation import AuthenticatedIdentity, MembershipStatus
from forge.usage_api import mount_company_usage
from forge.usage_company import CompanyUsage, MemberUsage
from forge.usage_platform import Counters

ORG = UUID('11111111-1111-4111-8111-111111111111')
MEMBER = uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PATH = '/forge/v1/orgs/%s/usage/members' % ORG
RANGE = {'from': '2026-10-01', 'to': '2026-10-12'}
COUNTERS = Counters(6, 5010, 2510, 1, 0, 10000, 1)


class Store:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def members(self, digest, org, first, last, after, page):
        self.calls.append((digest, org, first, last, after, page))
        if self.fail:
            raise self.fail
        return [MemberUsage(MEMBER, 'pat@example.com', 'Pat Member', 'suspended', COUNTERS)]

    def mine(self, digest, org, first, last):
        self.calls.append((digest, org, first, last))
        if self.fail:
            raise self.fail
        return COUNTERS


def client(*, roles=('organization_admin',), store=None, snapshot_org=ORG, valid=True):
    identity = AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4()))
    sessions, readiness, authorization = MagicMock(), MagicMock(), MagicMock()
    sessions.validate.side_effect = lambda token: identity if token == TOKEN else None
    readiness.check.return_value = True
    authorization.read.return_value = AuthorizationSnapshot(identity, snapshot_org, uuid4(), 1, frozenset(roles), MembershipStatus.ACTIVE, True)
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_company_usage(app, usage=CompanyUsage(store), sessions=sessions, authorization_reader=authorization, readiness=readiness)
    return TestClient(app, raise_server_exceptions=False), app, store, authorization


class CompanyUsageRouteTests(unittest.TestCase):
    def test_hidden_from_the_contract_and_shaped_as_names_and_counters(self):
        http, app, store, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        body = http.get(PATH, headers=HEADERS, params=RANGE).json()
        self.assertEqual(body, {'members': [{'member_id': str(MEMBER), 'email': 'pat@example.com', 'name': 'Pat Member', 'state': 'suspended',
                                             'requests': 6, 'prompt_tokens': 5010, 'completion_tokens': 2510, 'estimated_requests': 1,
                                             'error_requests': 0, 'cost_micros': 10000, 'unpriced_requests': 1}], 'next_after': None})
        self.assertEqual(store.calls[0][1:], (ORG, date(2026, 10, 1), date(2026, 10, 12), None, 50))
        self.assertNotEqual(store.calls[0][0], TOKEN)

    def test_members_other_companies_and_missing_authority_are_not_found_and_never_reach_the_store(self):
        for options in ({'roles': ('member',)}, {'roles': ()}, {'snapshot_org': uuid4()}):
            http, _, store, _ = client(**options)
            self.assertEqual(http.get(PATH, headers=HEADERS, params=RANGE).status_code, 404, options)
            self.assertEqual(store.calls, [])
        http, _, store, authorization = client()
        authorization.read.return_value = replace(authorization.read.return_value, membership_status=MembershipStatus.SUSPENDED)
        self.assertEqual(http.get(PATH, headers=HEADERS, params=RANGE).status_code, 404)
        self.assertEqual(store.calls, [])

    def test_the_database_denial_is_the_same_not_found_and_other_failures_are_finite(self):
        for failure, status, code in ((DirectoryDenied(), 404, 'NOT_FOUND'), (DirectoryUnavailable(), 503, 'SERVICE_UNAVAILABLE'),
                                      (RuntimeError('boom'), 503, 'SERVICE_UNAVAILABLE'), (ValueError('x'), 422, 'INVALID_REQUEST')):
            http, _, _, _ = client(store=Store(failure))
            response = http.get(PATH, headers=HEADERS, params=RANGE)
            self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))

    def test_bad_queries_and_credentials_are_refused_before_anything_else(self):
        http, _, store, authorization = client()
        for params in ({}, {'from': '2026-10-01'}, {**RANGE, 'page': '0'}, {**RANGE, 'page': 'x'}, {**RANGE, 'extra': '1'},
                       {'from': '2026-10-12', 'to': '2026-10-01'}, {**RANGE, 'after': 'nope'}, {'from': '2020-01-01', 'to': '2026-10-01'}):
            with self.subTest(params=str(params)):
                self.assertEqual(http.get(PATH, headers=HEADERS, params=params).status_code, 422)
        self.assertEqual(store.calls, [])
        self.assertEqual(http.get(PATH, params=RANGE).status_code, 401)
        self.assertEqual(http.get(PATH, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, params=RANGE).status_code, 401)
        self.assertEqual(http.get('/forge/v1/orgs/not-a-uuid/usage/members', headers=HEADERS, params=RANGE).status_code, 422)

    def test_pagination_cursor_is_the_last_member_when_the_page_is_full(self):
        http, _, store, _ = client()
        body = http.get(PATH, headers=HEADERS, params={**RANGE, 'page': '1'}).json()
        self.assertEqual(body['next_after'], str(MEMBER))
        again = http.get(PATH, headers=HEADERS, params={**RANGE, 'page': '1', 'after': str(MEMBER)})
        self.assertEqual((again.status_code, store.calls[-1][4]), (200, MEMBER))


ME = '/forge/v1/orgs/%s/usage/me' % ORG


class MyUsageRouteTests(unittest.TestCase):
    def test_hidden_from_the_contract_and_one_flat_counters_object(self):
        http, app, store, _ = client(roles=('member',))
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertIn(ME, {route.path.replace('{organization_id}', str(ORG)) for route in app.routes})
        response = http.get(ME, headers=HEADERS, params=RANGE)
        self.assertEqual((response.status_code, response.json()), (200, {'requests': 6, 'prompt_tokens': 5010, 'completion_tokens': 2510,
                                                                       'estimated_requests': 1, 'error_requests': 0, 'cost_micros': 10000,
                                                                       'unpriced_requests': 1}))
        self.assertEqual(store.calls[0][1:], (ORG, date(2026, 10, 1), date(2026, 10, 12)))
        self.assertNotEqual(store.calls[0][0], TOKEN, 'the store gets the digest, never the capability')

    def test_any_active_member_reads_own_usage_and_an_administrator_too(self):
        for roles in (('member',), ('organization_admin',), ('member', 'organization_admin')):
            http, _, store, _ = client(roles=roles)
            self.assertEqual(http.get(ME, headers=HEADERS, params=RANGE).status_code, 200, roles)

    def test_other_companies_inactive_and_suspended_memberships_are_not_found_and_never_reach_the_store(self):
        http, _, store, _ = client(snapshot_org=uuid4())
        self.assertEqual(http.get(ME, headers=HEADERS, params=RANGE).status_code, 404)
        http, _, store, authorization = client(roles=('member',))
        for change in ({'membership_status': MembershipStatus.SUSPENDED}, {'organization_active': False}):
            authorization.read.return_value = replace(authorization.read.return_value, **change)
            self.assertEqual(http.get(ME, headers=HEADERS, params=RANGE).status_code, 404, change)
        self.assertEqual(store.calls, [])

    def test_the_database_denial_is_the_same_not_found_and_other_failures_are_finite(self):
        for failure, status, code in ((DirectoryDenied(), 404, 'NOT_FOUND'), (DirectoryUnavailable(), 503, 'SERVICE_UNAVAILABLE'),
                                      (RuntimeError('boom'), 503, 'SERVICE_UNAVAILABLE'), (ValueError('x'), 422, 'INVALID_REQUEST')):
            http, _, _, _ = client(store=Store(failure))
            response = http.get(ME, headers=HEADERS, params=RANGE)
            self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))

    def test_only_from_and_to_are_accepted_and_credentials_come_first(self):
        http, _, store, _ = client()
        for params in ({}, {'from': '2026-10-01'}, {**RANGE, 'page': '1'}, {**RANGE, 'after': str(MEMBER)}, {**RANGE, 'extra': '1'},
                       {'from': '2026-10-12', 'to': '2026-10-01'}, {'from': '2020-01-01', 'to': '2026-10-01'}):
            with self.subTest(params=str(params)):
                self.assertEqual(http.get(ME, headers=HEADERS, params=params).status_code, 422)
        self.assertEqual(store.calls, [])
        self.assertEqual(http.get(ME, params=RANGE).status_code, 401)
        self.assertEqual(http.get(ME, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, params=RANGE).status_code, 401)
        self.assertEqual(http.get('/forge/v1/orgs/not-a-uuid/usage/me', headers=HEADERS, params=RANGE).status_code, 422)


if __name__ == '__main__':
    unittest.main()
