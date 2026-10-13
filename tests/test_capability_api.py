"""Capability governance routes over a fake service: hidden from the contract, bearer-authenticated, bounded, finite errors, no existence leak."""
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
from forge.capability_api import mount_company_capabilities
from forge.capability_model import (AuditRecord, CapabilityConflict, CapabilityDenied, CapabilityInvalid, CapabilityLocked, CapabilityNotFound,
                                    CapabilityUnavailable, CatalogRecord, CompanyPolicyRow)
from forge.capability_policy import CatalogEntry, Layer
from forge.capability_service import AdminItem
from forge.foundation import AuthenticatedIdentity
from forge.platform import MfaRequired, PlatformDenied
from forge.platform_api import mount_platform
from datetime import datetime, timezone

ORG, ACCOUNT = uuid4(), uuid4()
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
PLATFORM = '/forge/v1/platform'
COMPANY = '/forge/v1/orgs/%s' % ORG
SKILL = CatalogEntry('skill:pdf', 'skill', '1.0.0', 'low', True, 'on', 0, None)
ENTRY = {'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0}
AT = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
AUDIT = AuditRecord(7, 'org', ORG, ACCOUNT, 'org.setting_set', 'skill:pdf', None, 'off', AT)


class Ready:
    def check(self):
        return True


class Sessions:
    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == TOKEN else None


class FakeCapabilities:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _do(self, name, *args):
        self.calls.append((name, args))
        if self.fail:
            raise self.fail
        return {'catalog': [CatalogRecord(SKILL, 1, Layer('off', 'forced_off'))], 'put_entry': CatalogRecord(SKILL, 2, Layer()),
                'set_platform_policy': True, 'set_company_override': False, 'set_enabled': True,
                'company_policy': [CompanyPolicyRow('skill:pdf', Layer(None, 'forced_off'), False)], 'platform_audit': [AUDIT],
                'org_audit': [AUDIT], 'company_view': [AdminItem('skill:pdf', 'skill', 'low', True, 0, 'forced_off', True, None)]}[name]

    def catalog(self, token): return self._do('catalog', token)
    def put_entry(self, token, identifier, expected, document): return self._do('put_entry', token, identifier, expected, document)
    def set_platform_policy(self, token, identifier, state, lock): return self._do('set_platform_policy', token, identifier, state, lock)
    def company_policy(self, token, org): return self._do('company_policy', token, org)
    def set_company_override(self, token, org, identifier, state, lock): return self._do('set_company_override', token, org, identifier, state, lock)
    def platform_audit(self, token, before, page): return self._do('platform_audit', token, before, page)
    def company_view(self, token, org): return self._do('company_view', token, org)
    def set_enabled(self, token, org, identifier, want): return self._do('set_enabled', token, org, identifier, want)
    def org_audit(self, token, org, before, page): return self._do('org_audit', token, org, before, page)


def client(capabilities=None):
    capabilities = capabilities or FakeCapabilities()
    app = create_account_app(sessions=None)
    mount_platform(app, service=object(), sessions=Sessions(), readiness=Ready(), capabilities=capabilities)
    mount_company_capabilities(app, capabilities=capabilities, sessions=Sessions(), readiness=Ready())
    return TestClient(app, raise_server_exceptions=False), app, capabilities


class HiddenTests(unittest.TestCase):
    def test_every_route_is_hidden_so_the_contract_pin_is_unchanged(self):
        http, app, _ = client()
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        paths = {route.path for route in app.routes}
        for expected in (PLATFORM + '/capabilities', PLATFORM + '/capabilities/{identifier}', PLATFORM + '/capabilities/{identifier}/policy',
                         PLATFORM + '/capability-audit', PLATFORM + '/companies/{organization_id}/capabilities',
                         PLATFORM + '/companies/{organization_id}/capabilities/{identifier}', '/forge/v1/orgs/{organization_id}/capabilities',
                         '/forge/v1/orgs/{organization_id}/capabilities/{identifier}', '/forge/v1/orgs/{organization_id}/capability-audit'):
            self.assertIn(expected, paths)
        self.assertEqual([route['path'] for route in contract.build(app)['routes'] if 'capabilities' in route['path'] or 'capability-audit' in route['path']], [])


class AuthenticationTests(unittest.TestCase):
    def test_no_session_is_401_everywhere(self):
        http, _, capabilities = client()
        for method, path in (('get', PLATFORM + '/capabilities'), ('put', PLATFORM + '/capabilities/skill:pdf/policy'), ('get', COMPANY + '/capabilities'),
                             ('put', COMPANY + '/capabilities/skill:pdf'), ('get', COMPANY + '/capability-audit')):
            for headers in ({}, {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}, {'Authorization': 'Basic abc'}):
                with self.subTest(path=path, headers=bool(headers)):
                    self.assertEqual(getattr(http, method)(path, headers=headers).status_code, 401)
        self.assertEqual(capabilities.calls, [])


class PlatformRouteTests(unittest.TestCase):
    def test_catalog_listing_and_entry_write(self):
        http, _, capabilities = client()
        listing = http.get(PLATFORM + '/capabilities', headers=HEADERS)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['capabilities'][0], {
            'id': 'skill:pdf', 'kind': 'skill', 'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0,
            'manifest_sha256': None, 'credential_locus': 'server', 'declared_permissions': [], 'granted_permissions': [], 'revision': 1,
            'platform': {'state': 'off', 'lock': 'forced_off'}})
        written = http.put(PLATFORM + '/capabilities/skill:pdf', headers=HEADERS, json={'expected_revision': 1, 'entry': ENTRY})
        self.assertEqual((written.status_code, written.json()['revision']), (200, 2))
        self.assertEqual(capabilities.calls[-1], ('put_entry', (TOKEN, 'skill:pdf', 1, ENTRY)))

    def test_policy_and_company_override_bodies_are_exact(self):
        http, _, capabilities = client()
        ok = http.put(PLATFORM + '/capabilities/skill:pdf/policy', headers=HEADERS, json={'state': None, 'lock': 'forced_off'})
        self.assertEqual((ok.status_code, ok.json()), (200, {'changed': True}))
        self.assertEqual(capabilities.calls[-1], ('set_platform_policy', (TOKEN, 'skill:pdf', None, 'forced_off')))
        override = http.put(PLATFORM + '/companies/%s/capabilities/skill:pdf' % ORG, headers=HEADERS, json={'state': 'off', 'lock': 'none'})
        self.assertEqual((override.status_code, override.json()), (200, {'changed': False}))
        for body in ({}, {'state': 'on'}, {'state': 'on', 'lock': 'none', 'x': 1}, {'state': 1, 'lock': 'none'}, [], {'state': 'on', 'lock': 5}):
            with self.subTest(body=body):
                self.assertEqual(http.put(PLATFORM + '/capabilities/skill:pdf/policy', headers=HEADERS, json=body).status_code, 422)
        self.assertEqual(http.put(PLATFORM + '/capabilities/skill:pdf', headers=HEADERS, json={'expected_revision': 'one', 'entry': ENTRY}).status_code, 422)
        self.assertEqual(http.put(PLATFORM + '/capabilities/skill:pdf', headers=HEADERS, json={'entry': ENTRY}).status_code, 422)

    def test_company_policy_view_and_audit(self):
        http, _, capabilities = client()
        view = http.get(PLATFORM + '/companies/%s/capabilities' % ORG, headers=HEADERS)
        self.assertEqual(view.json(), {'capabilities': [{'id': 'skill:pdf', 'state': None, 'lock': 'forced_off', 'org_enabled': False}]})
        audit = http.get(PLATFORM + '/capability-audit?before=9&page=5', headers=HEADERS)
        self.assertEqual(audit.json(), {'entries': [{'id': 7, 'scope': 'org', 'organization_id': str(ORG), 'actor_id': str(ACCOUNT), 'action': 'org.setting_set',
                                                      'target': 'skill:pdf', 'before': None, 'after': 'off', 'at': AT.isoformat()}], 'next_before': None})
        self.assertEqual(capabilities.calls[-1], ('platform_audit', (TOKEN, 9, 5)))
        for query in ('page=0', 'page=101', 'before=abc', 'x=1', 'page=1&page=2'):
            self.assertEqual(http.get(PLATFORM + '/capability-audit?' + query, headers=HEADERS).status_code, 422, query)

    def test_platform_refusals_keep_the_platform_codes_and_capability_errors_are_finite(self):
        for failure, status, code in ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (MfaRequired(), 403, 'MFA_REQUIRED'), (CapabilityInvalid(), 422, 'INVALID_REQUEST'),
                                      (CapabilityNotFound(), 404, 'NOT_FOUND'), (CapabilityConflict(), 409, 'REVISION_CONFLICT'),
                                      (CapabilityUnavailable(), 503, 'SERVICE_UNAVAILABLE'), (RuntimeError('secret detail'), 503, 'SERVICE_UNAVAILABLE')):
            with self.subTest(code=code):
                http, _, _ = client(FakeCapabilities(failure))
                response = http.get(PLATFORM + '/capabilities', headers=HEADERS)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
                self.assertNotIn('secret detail', response.text)


class CompanyRouteTests(unittest.TestCase):
    def test_the_administrator_view_and_the_enable_disable_write(self):
        http, _, capabilities = client()
        view = http.get(COMPANY + '/capabilities', headers=HEADERS)
        self.assertEqual(view.json(), {'capabilities': [{'id': 'skill:pdf', 'kind': 'skill', 'risk': 'low', 'is_base': True, 'min_sandbox_level': 0,
                                                         'state': 'forced_off', 'locked': True, 'setting': None}]})
        for value in (True, False, None):
            changed = http.put(COMPANY + '/capabilities/skill:pdf', headers=HEADERS, json={'enabled': value})
            self.assertEqual((changed.status_code, changed.json()), (200, {'changed': True}))
            self.assertEqual(capabilities.calls[-1], ('set_enabled', (TOKEN, ORG, 'skill:pdf', value)))
        for body in ({}, {'enabled': 'yes'}, {'enabled': True, 'x': 1}, {'enabled': 1}):
            self.assertEqual(http.put(COMPANY + '/capabilities/skill:pdf', headers=HEADERS, json=body).status_code, 422, body)

    def test_a_locked_capability_is_409_locked_and_a_denied_caller_gets_the_same_not_found_as_a_missing_company(self):
        http, _, _ = client(FakeCapabilities(CapabilityLocked()))
        locked = http.put(COMPANY + '/capabilities/skill:pdf', headers=HEADERS, json={'enabled': True})
        self.assertEqual((locked.status_code, locked.json()['error']['code']), (409, 'LOCKED'))
        http, _, _ = client(FakeCapabilities(CapabilityDenied()))
        for method, path, body in (('get', COMPANY + '/capabilities', None), ('put', COMPANY + '/capabilities/skill:pdf', {'enabled': True}),
                                   ('get', COMPANY + '/capability-audit', None)):
            response = http.request(method, path, headers=HEADERS, json=body)
            self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'), path)
        http, _, _ = client(FakeCapabilities(CapabilityUnavailable()))
        self.assertEqual(http.get(COMPANY + '/capabilities', headers=HEADERS).status_code, 503)

    def test_the_company_audit_pages_with_a_cursor(self):
        http, _, capabilities = client()
        body = http.get(COMPANY + '/capability-audit?page=1', headers=HEADERS).json()
        self.assertEqual((len(body['entries']), body['next_before']), (1, 7))
        self.assertEqual(capabilities.calls[-1], ('org_audit', (TOKEN, ORG, None, 1)))

    def test_a_malformed_company_id_or_oversized_body_is_refused_before_the_service(self):
        http, _, capabilities = client()
        self.assertEqual(http.get('/forge/v1/orgs/not-a-uuid/capabilities', headers=HEADERS).status_code, 422)
        big = http.put(COMPANY + '/capabilities/skill:pdf', headers={**HEADERS, 'content-type': 'application/json'}, content=b'{"enabled":' + b' ' * 3000 + b'true}')
        self.assertEqual(big.status_code, 413)
        self.assertEqual(http.put(COMPANY + '/capabilities/skill:pdf', headers={**HEADERS, 'content-type': 'text/plain'}, content=b'{}').status_code, 415)
        self.assertEqual(capabilities.calls, [])


if __name__ == '__main__':
    unittest.main()
