"""Platform HTTP routes over a fake service: hidden from the contract, bearer-authenticated, bounded bodies and finite errors."""
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
from forge.branding import DEFAULT, Branding
from forge.platform import (AuditEntry, Company, CompanyConflict, CreatedCompany, MfaEnrolled, MfaEnrollment, MfaInvalid, MfaLocked,
                            MfaRequired, MfaStatus, PlatformDenied, PlatformIdentity, PlatformInvalid, PlatformNotFound,
                            PlatformUnavailable, RevisionConflict)
from forge.platform_api import mount_platform

ORG, ACCOUNT, INVITATION = uuid4(), uuid4(), uuid4()
WHEN = datetime(2026, 10, 12, 8, 30, tzinfo=timezone.utc)
TOKEN = secrets.token_urlsafe(32)
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
BASE = '/forge/v1/platform'


class Ready:
    def __init__(self, value=True):
        self.value = value

    def check(self):
        return self.value


class Sessions:
    def __init__(self, known=TOKEN):
        self.known = known

    def validate(self, token):
        return AuthenticatedIdentity('forge', 'urn:prometheon:forge:accounts:v1', str(ACCOUNT)) if token == self.known else None


class FakeService:
    """Records every call and either answers or raises the configured failure."""
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _do(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.fail:
            raise self.fail
        return getattr(self, '_' + name)(*args, **kwargs)

    def me(self, token):
        return self._do('me', token)

    def mfa_status(self, token):
        return self._do('mfa_status', token)

    def enroll_mfa(self, token):
        return self._do('enroll_mfa', token)

    def verify_mfa(self, token, code):
        return self._do('verify_mfa', token, code)

    def recover_mfa(self, token, code):
        return self._do('recover_mfa', token, code)

    def companies(self, token, *, after=None, page=50):
        return self._do('companies', token, after=after, page=page)

    def company(self, token, organization_id):
        return self._do('company', token, organization_id)

    def audit(self, token, *, before=None, page=50):
        return self._do('audit', token, before=before, page=page)

    def create_company(self, token, **details):
        return self._do('create_company', token, **details)

    def suspend_company(self, token, organization_id):
        return self._do('suspend_company', token, organization_id)

    def reactivate_company(self, token, organization_id):
        return self._do('reactivate_company', token, organization_id)

    def company_branding(self, token, organization_id):
        return self._do('company_branding', token, organization_id)

    def save_company_branding(self, token, organization_id, expected, value):
        return self._do('save_company_branding', token, organization_id, expected, value)

    def reset_company_branding(self, token, organization_id, expected):
        return self._do('reset_company_branding', token, organization_id, expected)

    _me = lambda self, token: PlatformIdentity(ACCOUNT, 'platform_owner')
    _mfa_status = lambda self, token: MfaStatus('active', True, False)
    _enroll_mfa = lambda self, token: MfaEnrollment('JBSWY3DPEHPK3PXP', 'otpauth://totp/x?secret=JBSWY3DPEHPK3PXP', ('AAAA-BBBB-CCCC-DDDD',))
    _verify_mfa = lambda self, token, code: None
    _recover_mfa = lambda self, token, code: None
    _companies = lambda self, token, after=None, page=50: [Company(ORG, 'acme', 'Acme', True), Company(uuid4(), 'zeta', 'Zeta', False)]
    _company = lambda self, token, organization_id: Company(organization_id, 'acme', 'Acme', True)
    _create_company = lambda self, token, **details: CreatedCompany(Company(ORG, details['slug'], details['display_name'], True), INVITATION,
                                                                    WHEN, 'delivered', 'smtp')
    _suspend_company = lambda self, token, organization_id: Company(organization_id, 'acme', 'Acme', False)
    _reactivate_company = lambda self, token, organization_id: Company(organization_id, 'acme', 'Acme', True)
    _company_branding = lambda self, token, organization_id: DEFAULT
    _save_company_branding = lambda self, token, organization_id, expected, value: Branding(expected + 1, value.name, value.login_copy, value.primary,
                                                                                             value.accent, value.tint, value.heading, value.body, {})
    _reset_company_branding = lambda self, token, organization_id, expected: Branding(expected + 1, 'Prometheon Forge', '', '#0B1D26', '#E07A2D',
                                                                                       '#E8DCC1', 'montserrat', 'inter', {})
    _audit = lambda self, token, before=None, page=50: [AuditEntry(7, ACCOUNT, 'company.created', ORG, WHEN),
                                                      AuditEntry(5, ACCOUNT, 'company.suspended', None, WHEN)]


def client(service=None, *, ready=True, sessions=None):
    app = create_account_app(sessions=None)
    mount_platform(app, service=service or FakeService(), sessions=sessions or Sessions(), readiness=Ready(ready))
    return TestClient(app, raise_server_exceptions=False), app


class HiddenRouteTests(unittest.TestCase):
    def test_no_platform_route_is_in_the_schema_so_the_contract_pin_is_unchanged(self):
        plain = create_account_app(sessions=None)
        http, app = client()
        self.assertFalse([path for path in app.openapi()['paths'] if 'platform' in path])
        self.assertEqual(contract.build(app), contract.build(plain))
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
        self.assertTrue(any(route.path.startswith('/forge/v1/platform/') for route in app.routes))

    def test_every_platform_response_is_private(self):
        http, _ = client()
        for method, path in (('GET', '/forge/v1/platform/me'), ('GET', '/forge/v1/platform/companies'),
                             ('GET', '/forge/v1/platform/audit'), ('GET', '/forge/v1/platform/me')):
            response = http.request(method, path, headers=HEADERS)
            self.assertEqual(response.headers['cache-control'], 'no-store', path)
        denied = http.get('/forge/v1/platform/me')
        self.assertEqual(denied.headers['cache-control'], 'no-store')


class AuthenticationTests(unittest.TestCase):
    def test_a_missing_malformed_or_unknown_bearer_is_401_and_never_reaches_the_service(self):
        service = FakeService()
        http, _ = client(service)
        for headers in ({}, {'Authorization': 'Basic abc'}, {'Authorization': 'Bearer short'}, {'Authorization': 'Bearer ' + 'x' * 44},
                        {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}):
            with self.subTest(headers=headers):
                response = http.get('/forge/v1/platform/me', headers=headers)
                self.assertEqual((response.status_code, response.json()['error']['code']), (401, 'UNAUTHENTICATED'))
                self.assertEqual(response.headers['www-authenticate'], 'Bearer')
        self.assertEqual(service.calls, [])

    def test_a_service_that_is_not_ready_is_503_for_everyone(self):
        service = FakeService()
        http, _ = client(service, ready=False)
        response = http.get('/forge/v1/platform/me', headers=HEADERS)
        self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'))
        self.assertEqual(service.calls, [])


class ReadRouteTests(unittest.TestCase):
    def test_me_reports_identity_and_the_second_factor_state_without_widening_the_account_me(self):
        http, _ = client()
        body = http.get('/forge/v1/platform/me', headers=HEADERS).json()
        self.assertEqual(body, {'account_id': str(ACCOUNT), 'role': 'platform_owner',
                                'mfa': {'state': 'active', 'verified': True, 'fresh': False}})

    def test_companies_page_with_a_cursor_and_report_the_next_one_only_when_the_page_is_full(self):
        service = FakeService()
        http, _ = client(service)
        body = http.get('/forge/v1/platform/companies', headers=HEADERS, params={'page': 2, 'after': 'abc'}).json()
        self.assertEqual(service.calls[-1][2], {'after': 'abc', 'page': 2})
        self.assertEqual([c['slug'] for c in body['companies']], ['acme', 'zeta'])
        self.assertEqual(body['companies'][0], {'id': str(ORG), 'slug': 'acme', 'display_name': 'Acme', 'active': True})
        self.assertEqual(body['next_after'], 'zeta')
        short = http.get('/forge/v1/platform/companies', headers=HEADERS, params={'page': 5}).json()
        self.assertIsNone(short['next_after'], 'two rows of five: nothing more to fetch')
        http.get('/forge/v1/platform/companies', headers=HEADERS)
        self.assertEqual(service.calls[-1][2], {'after': None, 'page': 50})

    def test_invalid_query_values_are_422_before_the_service(self):
        service = FakeService()
        http, _ = client(service)
        for params in ({'page': 'x'}, {'page': '0'}, {'page': '101'}, {'page': '1.5'}, {'after': 'BAD CODE'}, {'after': 'a' * 64},
                       {'page': '1', 'page2': '2'}, {'after': ['a', 'b']}):
            with self.subTest(params=params):
                response = http.get('/forge/v1/platform/companies', headers=HEADERS, params=params)
                self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
        self.assertEqual(service.calls, [])

    def test_one_company_and_the_audit_page(self):
        service = FakeService()
        http, _ = client(service)
        response = http.get('/forge/v1/platform/companies/%s' % ORG, headers=HEADERS)
        self.assertEqual(response.json(), {'id': str(ORG), 'slug': 'acme', 'display_name': 'Acme', 'active': True})
        self.assertEqual(http.get('/forge/v1/platform/companies/not-a-uuid', headers=HEADERS).status_code, 422)
        audit = http.get('/forge/v1/platform/audit', headers=HEADERS, params={'before': 9, 'page': 2}).json()
        self.assertEqual(service.calls[-1][2], {'before': 9, 'page': 2})
        self.assertEqual(audit['entries'][0], {'id': 7, 'actor_id': str(ACCOUNT), 'action': 'company.created',
                                               'organization_id': str(ORG), 'recorded_at': '2026-10-12T08:30:00+00:00'})
        self.assertEqual(audit['next_before'], 5)
        self.assertEqual(http.get('/forge/v1/platform/audit', headers=HEADERS, params={'before': 'x'}).status_code, 422)
        self.assertEqual(http.get('/forge/v1/platform/audit', headers=HEADERS, params={'before': '0'}).status_code, 422)


class FactorRouteTests(unittest.TestCase):
    def post(self, http, path, body, **kw):
        return http.post('/forge/v1/platform/' + path, headers={**HEADERS, 'Content-Type': 'application/json'},
                         content=body if isinstance(body, (bytes, str)) else json.dumps(body), **kw)

    def test_enrollment_returns_the_one_time_material_with_201(self):
        service = FakeService()
        http, _ = client(service)
        response = http.post('/forge/v1/platform/mfa/enroll', headers=HEADERS)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'secret': 'JBSWY3DPEHPK3PXP', 'otpauth_uri': 'otpauth://totp/x?secret=JBSWY3DPEHPK3PXP',
                                           'recovery_codes': ['AAAA-BBBB-CCCC-DDDD']})
        self.assertEqual(service.calls[-1][0], 'enroll_mfa')

    def test_a_code_or_a_recovery_code_verifies_the_session_and_nothing_else_is_accepted(self):
        service = FakeService()
        http, _ = client(service)
        ok = self.post(http, 'login/mfa', {'code': '123456'})
        self.assertEqual((ok.status_code, ok.json()), (200, {'verified': True}))
        self.assertEqual(service.calls[-1], ('verify_mfa', (TOKEN, '123456'), {}))
        ok = self.post(http, 'login/mfa', {'recovery_code': 'AAAA-BBBB-CCCC-DDDD'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(service.calls[-1], ('recover_mfa', (TOKEN, 'AAAA-BBBB-CCCC-DDDD'), {}))
        before = len(service.calls)
        for body in ({}, {'code': '123456', 'recovery_code': 'x'}, {'code': 123456}, {'code': '123456', 'extra': 1}, [], 'null',
                     {'code': None}, {'recovery_code': ['a']}, '{"code":"1","code":"2"}', '{bad json', b'\xff\xfe'):
            with self.subTest(body=body):
                response = self.post(http, 'login/mfa', body)
                self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
        self.assertEqual(len(service.calls), before)

    def test_the_body_must_be_json_and_small(self):
        service = FakeService()
        http, _ = client(service)
        wrong = http.post('/forge/v1/platform/login/mfa', headers={**HEADERS, 'Content-Type': 'text/plain'}, content='{"code":"123456"}')
        self.assertEqual((wrong.status_code, wrong.json()['error']['code']), (415, 'UNSUPPORTED_MEDIA_TYPE'))
        big = self.post(http, 'login/mfa', '{"code":"' + '1' * 5000 + '"}')
        self.assertEqual((big.status_code, big.json()['error']['code']), (413, 'PAYLOAD_TOO_LARGE'))
        self.assertEqual(service.calls, [])


class CreateCompanyRouteTests(unittest.TestCase):
    BODY = {'slug': 'acme', 'display_name': 'Acme Corporation', 'department': 'Operations',
            'admin_email': 'admin@acme.test', 'admin_name': 'Acme Admin'}

    def post(self, http, body, **kw):
        return http.post(BASE + '/companies', headers={**HEADERS, 'Content-Type': 'application/json'},
                         content=body if isinstance(body, (bytes, str)) else json.dumps(body), **kw)

    def test_a_valid_body_creates_the_company_and_reports_the_invitation_without_its_capability(self):
        service = FakeService()
        http, _ = client(service)
        response = self.post(http, self.BODY)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {'id': str(ORG), 'slug': 'acme', 'display_name': 'Acme Corporation', 'active': True,
                                           'invitation': {'id': str(INVITATION), 'expires_at': '2026-10-12T08:30:00+00:00',
                                                          'delivery_state': 'delivered', 'delivery_channel': 'smtp'}})
        self.assertEqual(service.calls[-1], ('create_company', (TOKEN,), self.BODY))
        self.assertNotIn('capability', response.text)

    def test_the_body_must_be_exactly_the_five_string_fields(self):
        service = FakeService()
        http, _ = client(service)
        cases = ({}, {**self.BODY, 'extra': 'x'}, {key: value for key, value in self.BODY.items() if key != 'department'},
                 {**self.BODY, 'slug': 5}, {**self.BODY, 'admin_email': None}, {**self.BODY, 'admin_name': ['x']}, [], 'null', '{bad')
        for body in cases:
            with self.subTest(body=body):
                response = self.post(http, body)
                self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
        self.assertEqual(service.calls, [])
        wrong = http.post(BASE + '/companies', headers={**HEADERS, 'Content-Type': 'text/plain'}, content=json.dumps(self.BODY))
        self.assertEqual(wrong.status_code, 415)
        big = self.post(http, json.dumps({**self.BODY, 'display_name': 'x' * 5000}))
        self.assertEqual(big.status_code, 413)

    def test_a_taken_code_is_409_and_every_other_failure_keeps_its_finite_code(self):
        for failure, status, code in ((CompanyConflict(), 409, 'COMPANY_CONFLICT'), (MfaRequired(), 403, 'MFA_REQUIRED'),
                                      (PlatformInvalid(), 422, 'INVALID_REQUEST'), (PlatformDenied(), 403, 'PLATFORM_DENIED')):
            with self.subTest(code=code):
                http, _ = client(FakeService(fail=failure))
                response = self.post(http, self.BODY)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))


class CompanyOperationRouteTests(unittest.TestCase):
    DOC = {'name': 'Acme Labs', 'loginCopy': 'Welcome.', 'assets': {},
           'theme': {'primary': '#0B1D26', 'accent': '#B45309', 'tint': '#E8DCC1', 'heading': 'inter', 'body': 'inter'}}

    def send(self, http, method, path, body=None, **kw):
        headers = {**HEADERS, 'Content-Type': 'application/json'}
        return http.request(method, BASE + path, headers=headers, content=None if body is None else json.dumps(body), **kw)

    def test_suspend_and_reactivate_answer_with_the_company_as_it_now_is(self):
        service = FakeService()
        http, _ = client(service)
        down = self.send(http, 'POST', '/companies/%s/suspend' % ORG)
        up = self.send(http, 'POST', '/companies/%s/reactivate' % ORG)
        self.assertEqual((down.status_code, down.json()['active'], up.status_code, up.json()['active']), (200, False, 200, True))
        self.assertEqual([call[0] for call in service.calls], ['suspend_company', 'reactivate_company'])
        self.assertEqual(self.send(http, 'POST', '/companies/not-a-uuid/suspend').status_code, 422)
        denied = client(FakeService(fail=MfaRequired()))[0]
        self.assertEqual(self.send(denied, 'POST', '/companies/%s/suspend' % ORG).json()['error']['code'], 'MFA_REQUIRED')

    def test_the_branding_is_read_and_saved_with_the_same_document_shape_as_the_company_admin_api(self):
        service = FakeService()
        http, _ = client(service)
        read = self.send(http, 'GET', '/companies/%s/branding' % ORG)
        self.assertEqual((read.status_code, read.json()['revision'], read.json()['name']), (200, 0, DEFAULT.name))
        saved = self.send(http, 'PUT', '/companies/%s/branding' % ORG, {'expectedRevision': 3, 'branding': self.DOC})
        self.assertEqual((saved.status_code, saved.json()['revision'], saved.json()['name']), (200, 4, 'Acme Labs'))
        self.assertEqual(service.calls[-1][1][1:3], (ORG, 3))
        reset = self.send(http, 'POST', '/companies/%s/branding/reset' % ORG, {'expectedRevision': 4})
        self.assertEqual((reset.status_code, reset.json()['revision'], service.calls[-1][0]), (200, 5, 'reset_company_branding'))

    def test_a_malformed_branding_request_is_422_before_the_service_and_a_stale_revision_is_409(self):
        service = FakeService()
        http, _ = client(service)
        bad_theme = {**self.DOC, 'theme': {**self.DOC['theme'], 'primary': 'red'}}
        for body in ({}, {'branding': self.DOC}, {'expectedRevision': -1, 'branding': self.DOC}, {'expectedRevision': True, 'branding': self.DOC},
                     {'expectedRevision': '1', 'branding': self.DOC}, {'expectedRevision': 1, 'branding': bad_theme},
                     {'expectedRevision': 1, 'branding': 'x'}, {'expectedRevision': 1, 'branding': self.DOC, 'extra': 1}):
            with self.subTest(body=body):
                response = self.send(http, 'PUT', '/companies/%s/branding' % ORG, body)
                self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
        self.assertEqual(self.send(http, 'POST', '/companies/%s/branding/reset' % ORG, {'expectedRevision': 'x'}).status_code, 422)
        self.assertEqual(service.calls, [])
        stale = client(FakeService(fail=RevisionConflict()))[0]
        conflict = self.send(stale, 'PUT', '/companies/%s/branding' % ORG, {'expectedRevision': 1, 'branding': self.DOC})
        self.assertEqual((conflict.status_code, conflict.json()['error']['code']), (409, 'REVISION_CONFLICT'))


class ErrorMappingTests(unittest.TestCase):
    def test_every_platform_failure_is_one_finite_status_and_code_without_detail(self):
        table = ((PlatformDenied(), 403, 'PLATFORM_DENIED'), (MfaRequired(), 403, 'MFA_REQUIRED'), (MfaInvalid(), 403, 'MFA_INVALID'),
                 (MfaLocked(), 429, 'MFA_LOCKED'), (MfaEnrolled(), 409, 'MFA_ENROLLED'), (PlatformInvalid(), 422, 'INVALID_REQUEST'),
                 (PlatformNotFound(), 404, 'NOT_FOUND'), (PlatformUnavailable(), 503, 'SERVICE_UNAVAILABLE'),
                 (RuntimeError('password=hunter2 host=10.0.0.5'), 503, 'SERVICE_UNAVAILABLE'))
        for failure, status, code in table:
            with self.subTest(code=code):
                http, _ = client(FakeService(fail=failure))
                response = http.get('/forge/v1/platform/companies', headers=HEADERS)
                self.assertEqual((response.status_code, response.json()['error']['code']), (status, code))
                self.assertNotIn('hunter2', response.text)
                self.assertNotIn('10.0.0.5', response.text)
        retry = client(FakeService(fail=MfaLocked()))[0].get('/forge/v1/platform/companies', headers=HEADERS)
        self.assertEqual(retry.headers['retry-after'], '900')
        self.assertEqual(retry.json()['error']['retry_after_seconds'], 900)


if __name__ == '__main__':
    unittest.main()
