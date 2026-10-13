"""Platform usage service and routes over fakes: price edits are validated integers, hidden from the contract, bearer-authenticated,
bounded and finite."""
from datetime import date, datetime, timezone
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
from forge.platform import MfaRequired, PlatformDenied, PlatformInvalid
from forge.platform_api import mount_platform
from forge.usage_platform import Counters, ModelPrice, ModelUsage, CompanyUsageRow, PlatformUsage, UsageTotals

TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
BASE = '/forge/v1/platform'
WHEN = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
ORG = uuid4()
COUNTERS = Counters(7, 7010, 3510, 1, 0, 14000, 2)
PRICE = ModelPrice(7, 'up/model-a', 2, 3_000_000, 9_000_000, 'USD', WHEN, uuid4())


class Store:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def set_price(self, digest, upstream_id, input_micros, output_micros, effective_from):
        self.calls.append(('set_price', digest, upstream_id, input_micros, output_micros, effective_from))
        if self.fail:
            raise self.fail
        return PRICE

    def prices(self, digest, upstream_id):
        self.calls.append(('prices', digest, upstream_id))
        if self.fail:
            raise self.fail
        return [PRICE]

    def by_company(self, digest, first, last, after, page):
        self.calls.append(('by_company', digest, first, last, after, page))
        if self.fail:
            raise self.fail
        return [CompanyUsageRow(ORG, 'org-a', 'Organization A', COUNTERS)]

    def by_model(self, digest, first, last, after, page):
        self.calls.append(('by_model', digest, first, last, after, page))
        return [ModelUsage('up/model-a', COUNTERS)]

    def totals(self, digest, first, last):
        self.calls.append(('totals', digest, first, last))
        return UsageTotals(2, COUNTERS)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.service = PlatformUsage(self.store)

    def test_a_valid_price_reaches_the_store_with_the_digest_and_never_the_capability(self):
        self.assertEqual(self.service.set_price(TOKEN, 'up/model-a', 3_000_000, 9_000_000, WHEN), PRICE)
        (_, digest, upstream, inp, out, starts), = self.store.calls
        self.assertEqual((upstream, inp, out, starts), ('up/model-a', 3_000_000, 9_000_000, WHEN))
        self.assertNotEqual(digest, TOKEN)
        self.service.set_price(TOKEN, 'up/model-b', 0, 0)
        self.assertEqual(self.store.calls[-1][-1], None)

    def test_invalid_values_are_refused_before_the_store(self):
        for arguments in (('bad id', 1, 1, None), ('', 1, 1, None), (None, 1, 1, None), ('up/m', -1, 1, None), ('up/m', 1, 10 ** 9 + 1, None),
                          ('up/m', True, 1, None), ('up/m', 1.5, 1, None), ('up/m', '1', 1, None),
                          ('up/m', 1, 1, datetime(2026, 1, 1)), ('up/m', 1, 1, '2026-01-01'), ('x' * 256, 1, 1, None)):
            with self.subTest(arguments=repr(arguments)[:40]), self.assertRaises(PlatformInvalid):
                self.service.set_price(TOKEN, *arguments)
        self.assertEqual(self.store.calls, [])

    def test_the_list_filters_by_model_and_validates_the_filter(self):
        self.assertEqual(self.service.prices(TOKEN, 'up/model-a'), [PRICE])
        self.assertEqual(self.store.calls[-1][2], 'up/model-a')
        self.service.prices(TOKEN)
        self.assertIsNone(self.store.calls[-1][2])
        with self.assertRaises(PlatformInvalid):
            self.service.prices(TOKEN, 'bad id')


class ReportServiceTests(unittest.TestCase):
    def test_reports_pass_a_bounded_range_and_page_to_the_store(self):
        store = Store()
        service = PlatformUsage(store)
        first, last = date(2026, 10, 1), date(2026, 10, 12)
        self.assertEqual(service.by_company(TOKEN, first, last)[0].counters, COUNTERS)
        self.assertEqual(store.calls[-1][2:], (first, last, None, 50))
        service.by_company(TOKEN, first, last, after=ORG, page=100)
        self.assertEqual(store.calls[-1][2:], (first, last, ORG, 100))
        service.by_model(TOKEN, first, last, after='up/a', page=1)
        self.assertEqual(store.calls[-1][2:], (first, last, 'up/a', 1))
        self.assertEqual(service.totals(TOKEN, first, last), UsageTotals(2, COUNTERS))

    def test_invalid_ranges_pages_and_cursors_never_reach_the_store(self):
        store = Store()
        service = PlatformUsage(store)
        ok = (date(2026, 10, 1), date(2026, 10, 12))
        for arguments in (((ok[1], ok[0]),), ((date(2025, 1, 1), ok[1]),), ((None, ok[1]),), (('2026-10-01', ok[1]),), ((datetime(2026, 10, 1), ok[1]),)):
            with self.subTest(arguments=repr(arguments)[:40]), self.assertRaises(PlatformInvalid):
                service.totals(TOKEN, *arguments[0])
        for page in (0, 101, True, '5'):
            with self.subTest(page=page), self.assertRaises(PlatformInvalid):
                service.by_company(TOKEN, *ok, page=page)
        for after in ('x', 5):
            with self.subTest(after=after), self.assertRaises(PlatformInvalid):
                service.by_company(TOKEN, *ok, after=after)
        with self.assertRaises(PlatformInvalid):
            service.by_model(TOKEN, *ok, after='bad id')
        self.assertEqual(store.calls, [])


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(uuid4())) if token == TOKEN else None


def client(store=None):
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), usage=PlatformUsage(store))
    return TestClient(app, raise_server_exceptions=False), app, store


class ReportRouteTests(unittest.TestCase):
    RANGE = {'from': '2026-10-01', 'to': '2026-10-12'}

    def test_reports_are_hidden_and_shaped_as_counters_and_integer_micro_usd(self):
        http, app, store = client()
        self.assertFalse([path for path in app.openapi()['paths'] if 'usage' in path])
        companies = http.get(BASE + '/usage/companies', headers=HEADERS, params=self.RANGE).json()
        self.assertEqual(companies, {'companies': [{'organization_id': str(ORG), 'slug': 'org-a', 'display_name': 'Organization A', 'requests': 7,
                                                    'prompt_tokens': 7010, 'completion_tokens': 3510, 'estimated_requests': 1, 'error_requests': 0,
                                                    'cost_micros': 14000, 'unpriced_requests': 2}], 'next_after': None})
        self.assertEqual(store.calls[-1][2:], (date(2026, 10, 1), date(2026, 10, 12), None, 50))
        models = http.get(BASE + '/usage/models', headers=HEADERS, params={**self.RANGE, 'page': '1'}).json()
        self.assertEqual((models['models'][0]['upstream_id'], models['models'][0]['cost_micros'], models['next_after']), ('up/model-a', 14000, 'up/model-a'))
        totals = http.get(BASE + '/usage/totals', headers=HEADERS, params=self.RANGE).json()
        self.assertEqual((totals['companies'], totals['requests'], totals['cost_micros']), (2, 7, 14000))

    def test_bad_queries_are_refused_before_the_service_and_the_routes_need_a_bearer(self):
        http, _, store = client()
        for params in ({}, {'from': '2026-10-01'}, {'from': 'yesterday', 'to': '2026-10-12'}, {**self.RANGE, 'page': '0'}, {**self.RANGE, 'page': 'x'},
                       {**self.RANGE, 'extra': '1'}, {'from': '2026-10-12', 'to': '2026-10-01'}, {**self.RANGE, 'after': 'not-a-uuid'}):
            with self.subTest(params=str(params)):
                self.assertEqual(http.get(BASE + '/usage/companies', headers=HEADERS, params=params).status_code, 422)
        self.assertEqual(http.get(BASE + '/usage/totals', headers=HEADERS, params={**self.RANGE, 'page': '1'}).status_code, 422)
        self.assertEqual(store.calls, [])
        self.assertEqual(http.get(BASE + '/usage/totals', params=self.RANGE).status_code, 401)


class RouteTests(unittest.TestCase):
    def test_hidden_from_the_contract(self):
        http, app, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path == BASE + '/prices' for route in app.routes))

    def test_post_sets_a_price_and_get_lists_versions(self):
        http, _, store = client()
        created = http.post(BASE + '/prices', headers=HEADERS, json={'upstream_id': 'up/model-a', 'input_micros': 3_000_000,
                                                                      'output_micros': 9_000_000, 'effective_from': '2026-10-12T09:00:00+00:00'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json(), {'id': 7, 'upstream_id': 'up/model-a', 'version': 2, 'input_micros': 3_000_000, 'output_micros': 9_000_000,
                                          'currency': 'USD', 'effective_from': '2026-10-12T09:00:00+00:00', 'set_by': str(PRICE.set_by)})
        self.assertEqual(store.calls[0][-1], WHEN)
        listed = http.get(BASE + '/prices', headers=HEADERS, params={'upstream_id': 'up/model-a'})
        self.assertEqual((listed.status_code, [item['version'] for item in listed.json()['prices']]), (200, [2]))
        self.assertEqual(http.get(BASE + '/prices', headers=HEADERS).status_code, 200)

    def test_malformed_requests_and_failures_are_finite(self):
        http, _, store = client()
        bad = [{}, {'upstream_id': 'up/m', 'input_micros': '1', 'output_micros': 1}, {'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1.5},
               {'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1, 'extra': 1}, {'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1, 'effective_from': 'tomorrow'},
               {'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1, 'effective_from': '2026-10-12T09:00:00'}, {'upstream_id': 5, 'input_micros': 1, 'output_micros': 1}]
        for body in bad:
            with self.subTest(body=str(body)[:40]):
                self.assertEqual(http.post(BASE + '/prices', headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(store.calls, [])
        self.assertEqual(http.post(BASE + '/prices', json={}).status_code, 401)
        self.assertEqual(http.get(BASE + '/prices?upstream_id=a&upstream_id=b', headers=HEADERS).status_code, 422)
        for failure, status, code in ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (MfaRequired(), 403, 'MFA_REQUIRED'), (RuntimeError('x'), 503, 'SERVICE_UNAVAILABLE')):
            failing, _, _ = client(Store(failure))
            response = failing.post(BASE + '/prices', headers=HEADERS, json={'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1})
            self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))


if __name__ == '__main__':
    unittest.main()
