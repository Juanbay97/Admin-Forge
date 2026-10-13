"""Platform read routes over a fake service: the company members list, hidden from the contract, bearer-authenticated, bounded and
finite. No secret column exists to leak: only the directory fields an administrator already sees."""
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
from forge.directory import Department
from forge.foundation import AuthenticatedIdentity
from forge.platform import MfaRequired, PlatformDenied, PlatformInvalid, PlatformNotFound
from forge.platform_api import mount_platform
from forge.platform_reads import MAX_PAGE, PlatformMember, PlatformReads

ORG, MEMBER, ACCOUNT = uuid4(), uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
BASE = '/forge/v1/platform'
PATH = BASE + '/companies/%s/members' % ORG
DEPARTMENT = Department(uuid4(), 'Support')
ROW = PlatformMember(MEMBER, 'pat@example.com', 'Pat Member', 'active', ('member',), (DEPARTMENT,))


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class Store:
    def __init__(self, fail=None, rows=None):
        self.calls, self.fail, self.rows = [], fail, [ROW] if rows is None else rows

    def members(self, digest, org, after, page):
        self.calls.append((digest, org, after, page))
        if self.fail:
            raise self.fail
        return self.rows


def client(store=None):
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), reads=PlatformReads(store))
    return TestClient(app, raise_server_exceptions=False), app, store


class MembersRouteTests(unittest.TestCase):
    def test_hidden_from_the_contract_and_shaped_like_the_company_member_list(self):
        http, app, store = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path == BASE + '/companies/{organization_id}/members' for route in app.routes))
        response = http.get(PATH, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()), (200, {'members': [{
            'id': str(MEMBER), 'email': 'pat@example.com', 'display_name': 'Pat Member', 'status': 'active', 'roles': ['member'],
            'departments': [{'id': str(DEPARTMENT.id), 'name': 'Support'}]}], 'next_after': None}))
        self.assertEqual(store.calls[0][1:], (ORG, None, 50))
        self.assertNotEqual(store.calls[0][0], TOKEN, 'the store gets the digest, never the capability')

    def test_a_full_page_carries_the_cursor_and_the_cursor_is_accepted(self):
        http, _, store = client()
        body = http.get(PATH, headers=HEADERS, params={'page': '1'}).json()
        self.assertEqual(body['next_after'], str(MEMBER))
        self.assertEqual(http.get(PATH, headers=HEADERS, params={'page': '1', 'after': str(MEMBER)}).status_code, 200)
        self.assertEqual(store.calls[-1][2:], (MEMBER, 1))

    def test_bad_queries_are_refused_before_the_store(self):
        http, _, store = client()
        for params in ({'page': '0'}, {'page': str(MAX_PAGE + 1)}, {'page': 'x'}, {'after': 'nope'}, {'extra': '1'}):
            with self.subTest(params=str(params)):
                self.assertEqual(http.get(PATH, headers=HEADERS, params=params).status_code, 422)
        self.assertEqual(http.get(BASE + '/companies/not-a-uuid/members', headers=HEADERS).status_code, 422)
        self.assertEqual(store.calls, [])

    def test_credentials_and_authority_failures_are_finite(self):
        http, _, _ = client()
        self.assertEqual(http.get(PATH).status_code, 401)
        self.assertEqual(http.get(PATH, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}).status_code, 401)
        for failure, status, code in ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (MfaRequired(), 403, 'MFA_REQUIRED'),
                                      (PlatformNotFound(), 404, 'NOT_FOUND'), (PlatformInvalid(), 422, 'INVALID_REQUEST'),
                                      (RuntimeError('boom'), 503, 'SERVICE_UNAVAILABLE')):
            with self.subTest(code=code):
                denied, _, _ = client(Store(failure))
                response = denied.get(PATH, headers=HEADERS)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))


class ServiceTests(unittest.TestCase):
    def test_arguments_are_bounded_before_the_store(self):
        store = Store()
        reads = PlatformReads(store)
        for arguments in (('x', None, 10), (ORG, 'x', 10), (ORG, None, 0), (ORG, None, MAX_PAGE + 1), (ORG, None, True)):
            with self.subTest(arguments=str(arguments)), self.assertRaises(PlatformInvalid):
                reads.members(TOKEN, *arguments)
        self.assertEqual(store.calls, [])
        self.assertEqual(reads.members(TOKEN, ORG, None, MAX_PAGE), [ROW])


if __name__ == '__main__':
    unittest.main()
