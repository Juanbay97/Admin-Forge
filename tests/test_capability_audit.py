"""Invocation metadata ingestion: strict allow-list validation before the store, and the hidden member route."""
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
from forge.capability_api import mount_invocation_audit
from forge.capability_audit import InvocationLog, MAX_BATCH
from forge.capability_model import CapabilityDenied, CapabilityInvalid
from forge.foundation import AuthenticatedIdentity

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PATH = '/forge/v1/capabilities/audit'


def event(**change):
    item = {'event_id': str(uuid4()), 'capability_id': 'tool:code_execute', 'at': '2026-10-12T12:00:00Z', 'outcome': 'ok', 'duration_ms': 120, 'sandbox_level': 3}
    item.update(change)
    return item


class Store:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def ingest(self, digest, org, events):
        self.calls.append((org, events))
        if self.fail:
            raise self.fail
        return len(events) - 1


class ValidationTests(unittest.TestCase):
    def test_a_valid_batch_reaches_the_store_normalized(self):
        store = Store()
        item = event(event_id=str(uuid4()).upper(), sandbox_level=None)
        del item['sandbox_level']
        self.assertEqual(InvocationLog(store).record(TOKEN, ORG, [item, event(at='2026-10-12T12:00:00.123Z')]), 1)
        ((org, events),) = store.calls
        self.assertEqual(events[0]['event_id'], item['event_id'].lower())
        self.assertNotIn('sandbox_level', events[0])

    def test_content_fields_unknown_keys_and_malformed_values_never_reach_the_store(self):
        store = Store()
        log = InvocationLog(store)
        bad = [{**event(), 'arguments': {'path': 'C:\\secret'}}, {**event(), 'output': 'text'}, {**event(), 'prompt': 'x'}, {**event(), 'error': 'boom'},
               {k: v for k, v in event().items() if k != 'capability_id'}, event(outcome='exploded'), event(outcome=None), event(duration_ms=-1),
               event(duration_ms=86_400_001), event(duration_ms=1.5), event(duration_ms=True), event(duration_ms='12'), event(sandbox_level=5), event(sandbox_level=-1),
               event(sandbox_level=False), event(capability_id='Bad Id'), event(capability_id='x' * 200), event(capability_id=''), event(event_id='not-a-uuid'),
               event(event_id=5), event(at='yesterday'), event(at='2026-10-12 12:00:00'), event(at='2026-10-12T12:00:00+00:00'), 'text', 5, None, []]
        for item in bad:
            with self.subTest(item=str(item)[:70]), self.assertRaises(CapabilityInvalid):
                log.record(TOKEN, ORG, [event(), item])
        for events in ([], [event() for _ in range(MAX_BATCH + 1)], {}, 'x', None, (event(),)):
            with self.subTest(events=str(events)[:30]), self.assertRaises(CapabilityInvalid):
                log.record(TOKEN, ORG, events)
        with self.assertRaises(CapabilityInvalid):
            log.record(TOKEN, 'not-uuid', [event()])
        self.assertEqual(store.calls, [])
        self.assertEqual(log.record(TOKEN, ORG, [event() for _ in range(MAX_BATCH)]), MAX_BATCH - 1)


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class Ready:
    def check(self):
        return True


def client(store=None, organizations=None):
    store = store or Store()
    app = create_account_app(sessions=None)
    mount_invocation_audit(app, log=InvocationLog(store), sessions=Sessions(), readiness=Ready(), organizations=organizations or (lambda token: [ORG]))
    return TestClient(app, raise_server_exceptions=False), app, store


class RouteTests(unittest.TestCase):
    def test_hidden_and_the_contract_pin_is_unchanged(self):
        _, app, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)), contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertIn(PATH, {route.path for route in app.routes})

    def test_a_member_batch_is_accepted_with_a_count_and_a_stranger_gets_401(self):
        http, _, store = client()
        accepted = http.post(PATH, headers=HEADERS, json={'events': [event(), event()]})
        self.assertEqual((accepted.status_code, accepted.json()), (202, {'received': 2, 'stored': 1}))
        self.assertEqual(store.calls[0][0], ORG)
        self.assertEqual(http.post(PATH, json={'events': [event()]}).status_code, 401)
        self.assertEqual(http.post(PATH, headers={'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, json={'events': [event()]}).status_code, 401)

    def test_content_fields_are_422_and_nothing_is_stored(self):
        http, _, store = client()
        for item in ({**event(), 'arguments': {'a': 1}}, {**event(), 'output': 'x'}, event(outcome='boom')):
            response = http.post(PATH, headers=HEADERS, json={'events': [item]})
            self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
        for body in ({}, {'events': []}, {'events': 'x'}, {'events': [event()], 'extra': 1}, [], {'events': [event() for _ in range(MAX_BATCH + 1)]}):
            self.assertEqual(http.post(PATH, headers=HEADERS, json=body).status_code, 422, str(body)[:40])
        self.assertEqual(store.calls, [])

    def test_oversized_and_wrongly_typed_bodies_are_refused_first(self):
        http, _, store = client()
        self.assertEqual(http.post(PATH, headers={**HEADERS, 'content-type': 'application/json'}, content=b'{"events":[' + b' ' * 70000 + b']}').status_code, 413)
        self.assertEqual(http.post(PATH, headers={**HEADERS, 'content-type': 'text/plain'}, content=b'{}').status_code, 415)
        self.assertEqual(store.calls, [])

    def test_company_selection_and_denial_follow_the_effective_route(self):
        other = uuid4()
        http, _, _ = client(organizations=lambda token: [ORG, other])
        self.assertEqual(http.post(PATH, headers=HEADERS, json={'events': [event()]}).status_code, 422)
        self.assertEqual(http.post(PATH + '?org=%s' % other, headers=HEADERS, json={'events': [event()]}).status_code, 202)
        self.assertEqual(http.post(PATH + '?org=%s' % uuid4(), headers=HEADERS, json={'events': [event()]}).status_code, 404)
        denied, _, _ = client(Store(CapabilityDenied()))
        response = denied.post(PATH, headers=HEADERS, json={'events': [event()]})
        self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))


if __name__ == '__main__':
    unittest.main()
