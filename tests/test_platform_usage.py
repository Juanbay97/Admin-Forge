"""Platform usage service and routes over fakes: price edits are validated integers, hidden from the contract, bearer-authenticated,
bounded and finite."""
from datetime import datetime, timezone
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
from forge.usage_platform import ModelPrice, PlatformUsage

TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
BASE = '/forge/v1/platform'
WHEN = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
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
