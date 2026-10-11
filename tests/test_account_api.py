"""Account transport and trusted session service tests."""
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from forge.accounts import ACCOUNT_ISSUER
from forge.foundation import AuthenticatedIdentity
from forge.account_sessions import AccountSession,LoginThrottled
from forge.account_api import create_account_app
from forge.account_sessions import SessionService, SessionDenied
from fastapi.testclient import TestClient

class AccountApiTests(unittest.TestCase):
    def test_default_account_app_fails_closed(self):
        with TestClient(create_account_app(),raise_server_exceptions=False) as client:
            response=client.post('/forge/v1/accounts/login',json={'email':'a@example.com','password':'a valid long password'})
            self.assertEqual(response.status_code,503)
            self.assertNotIn('password',response.text)
            self.assertEqual(client.get('/forge/v1/bootstrap?organization_id=bad').status_code,401)
    def test_malformed_session_token_rejected_before_store(self):
        store=MagicMock()
        service=SessionService(store,hasher=MagicMock())
        for token in ('bad','a'*1000,'Bearer x',None):
            with self.subTest(token=token):
                self.assertIsNone(service.validate(token))
        store.validate.assert_not_called()
    def test_failed_login_never_issues_session(self):
        store=MagicMock()
        store.begin_login.return_value=None
        hasher=MagicMock()
        hasher.hash.return_value='private-dummy-record'
        hasher.verify.return_value=False
        service=SessionService(store,hasher=hasher)
        with self.assertRaises(SessionDenied):
            service.login('a@example.com','a valid long password')
        store.finish_login.assert_not_called()

    def configured(self, sessions=None, readiness=None, **ports):
        sessions = sessions or MagicMock()
        readiness = readiness or MagicMock()
        readiness.check.return_value = True
        return TestClient(create_account_app(sessions=sessions, readiness=readiness, **ports),
                          raise_server_exceptions=False)

    def test_successful_login_is_ephemeral_and_strict(self):
        sessions = MagicMock()
        token = secrets.token_urlsafe(32)
        sessions.login.return_value = AccountSession(token, datetime.now(timezone.utc)+timedelta(hours=1))
        with self.configured(sessions) as client:
            result = client.post('/forge/v1/accounts/login', json={
                'email':'a@example.com','password':'a valid long password'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(set(result.json()),{'access_token','token_type','expires_at'})
            self.assertEqual(result.json()['access_token'],token)
            self.assertEqual(result.headers['cache-control'],'no-store')
            self.assertEqual(result.headers['referrer-policy'],'no-referrer')
            invalid = client.post('/forge/v1/accounts/login',json={
                'email':'a@example.com','password':'a valid long password','role':'organization_admin'})
            self.assertEqual(invalid.status_code,422)
            oversized = client.post('/forge/v1/accounts/login',content=b'x'*8193)
            self.assertEqual(oversized.status_code,422)
        self.assertEqual(sessions.login.call_count,1)

    def test_spoofed_actor_headers_and_duplicate_bearer_are_denied(self):
        sessions = MagicMock()
        with self.configured(sessions) as client:
            for headers in ({'X-Identity':str(uuid4()),'X-Role':'organization_admin'},
                            [('Authorization','Bearer '+secrets.token_urlsafe(32)),
                             ('Authorization','Bearer '+secrets.token_urlsafe(32))]):
                response = client.post('/forge/v1/accounts/logout',headers=headers)
                self.assertEqual(response.status_code,401)
                self.assertEqual(response.headers['www-authenticate'],'Bearer')
        sessions.validate.assert_not_called()
        sessions.logout.assert_not_called()

    def test_readiness_failure_precedes_login_or_session_lookup(self):
        sessions = MagicMock()
        ready = MagicMock()
        ready.check.return_value = False
        with TestClient(create_account_app(sessions=sessions,readiness=ready),raise_server_exceptions=False) as client:
            for path, body in (('login',{'email':'a@example.com','password':'a valid long password'}),('logout',{})):
                response=client.post('/forge/v1/accounts/'+path,json=body,
                    headers={'Authorization':'Bearer '+secrets.token_urlsafe(32)})
                self.assertEqual(response.status_code,503)
        sessions.login.assert_not_called()
        sessions.validate.assert_not_called()

    def test_secret_rich_failures_and_bad_port_outputs_are_redacted(self):
        sessions = MagicMock()
        sessions.login.side_effect = RuntimeError('PRIVATE-password-token-dsn@example.com')
        with self.configured(sessions) as client:
            first=client.post('/forge/v1/accounts/login',json={'email':'a@example.com','password':'a valid long password'})
            sessions.login.side_effect=None
            sessions.login.return_value={'password':'PRIVATE-marker'}
            second=client.post('/forge/v1/accounts/login',json={'email':'a@example.com','password':'a valid long password'})
            for response in (first,second):
                self.assertEqual(response.status_code,503)
                self.assertNotIn('PRIVATE',response.text)
                UUID(response.json()['error']['request_id'])
            self.assertNotEqual(first.json()['error']['request_id'],second.json()['error']['request_id'])

    def test_generic_denial_and_retry_information(self):
        sessions=MagicMock()
        with self.configured(sessions) as client:
            for error,status in ((SessionDenied(),401),(LoginThrottled(30),429)):
                sessions.login.side_effect=error
                response=client.post('/forge/v1/accounts/login',json={'email':'a@example.com','password':'a valid long password'})
                self.assertEqual(response.status_code,status)
                if status==429:
                    self.assertEqual(response.headers['retry-after'],'30')
                    self.assertEqual(response.json()['error']['retry_after_seconds'],30)
                self.assertNotIn('a@example.com',response.text)

    def test_logout_uses_only_verified_genuine_session(self):
        sessions=MagicMock()
        token=secrets.token_urlsafe(32)
        sessions.validate.return_value=AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(uuid4()))
        sessions.logout.return_value=True
        with self.configured(sessions) as client:
            self.assertEqual(client.post('/forge/v1/accounts/logout',headers={'Authorization':'Bearer '+token}).status_code,204)
            sessions.validate.return_value=AuthenticatedIdentity('entra','untrusted',str(uuid4()))
            self.assertEqual(client.post('/forge/v1/accounts/logout',headers={'Authorization':'Bearer '+token}).status_code,401)
        sessions.logout.assert_called_once_with(token)

    def test_reset_request_does_not_reveal_account_existence(self):
        sessions=MagicMock()
        sessions.request_reset.return_value=None
        delivery=MagicMock()
        with self.configured(sessions,delivery=delivery) as client:
            result=client.post('/forge/v1/accounts/password-reset/request',json={'email':'unknown@example.com'})
            self.assertEqual(result.status_code,202)
            self.assertEqual(result.json(),{'status':'accepted','delivery_channel':'local_test_mailbox'})
        delivery.queue_reset.assert_not_called()
