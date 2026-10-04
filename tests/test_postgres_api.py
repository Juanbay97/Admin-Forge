"""HTTP tests inject synthetic validation only here, over a genuine DB reader."""
from pathlib import Path
import sys
from threading import get_ident
import unittest
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fastapi.testclient import TestClient
from forge.api import create_app
from forge.foundation import AuthenticatedIdentity
from forge.postgres import PostgresBootstrapReader
from postgres_support import (
    ORG_A, ORG_B, MEMBER_A, DatabaseFixture, ProbeConnection, SECRET_MARKER, connect,
)


class TestValidator:
    def validate(self, token):
        if token in ('alice', 'bob', 'suspended', 'archived'):
            return AuthenticatedIdentity('test', 'issuer', token)
        return None


class PostgresBootstrapHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()
        self.pool = self.db.pool(connection_class=ProbeConnection)
        self.addCleanup(self.pool.close, timeout=5)
        self.reader = PostgresBootstrapReader(self.pool, acquisition_timeout=0.2)
        self.client = TestClient(create_app(TestValidator(), self.reader))
        self.addCleanup(self.client.close)

    def get(self, *, token='alice', org=ORG_A, client=None, headers=None):
        return (client or self.client).get('/forge/v1/bootstrap',
            params={'organization_id': str(org)},
            headers=headers if headers is not None else {'Authorization': 'Bearer ' + token})

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {'error'})
        error = response.json()['error']
        self.assertEqual(set(error), {'code', 'message', 'request_id', 'retryable',
                                    'retry_after_seconds', 'reset_at'})
        self.assertEqual(error['code'], code)
        self.assertEqual(error['retryable'], status == 503)
        self.assertIsNone(error['retry_after_seconds'])
        self.assertIsNone(error['reset_at'])
        UUID(error['request_id'])
        for private in (SECRET_MARKER, 'forge_runtime', 'DivisionByZero', 'psycopg',
                        'password=', 'issuer', str(MEMBER_A)):
            self.assertNotIn(private, response.text)

    def test_entra_binding_gates_real_reader_without_automatic_access(self):
        from forge.entra import VerifiedPrincipal
        from forge.identity_store import PostgresIdentityBinder
        tid, oid = str(UUID(int=101)), str(UUID(int=102))
        principal = VerifiedPrincipal('synthetic-trusted-port', tid, oid,
            'https://login.microsoftonline.com/' + tid + '/v2.0')
        with connect() as conn:
            conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',
                         ('entra', principal.issuer, oid, UUID(int=11)))
        class EntraPort:
            # Test-only trusted identity port; JWT crypto is independently covered by F06.
            def validate(self, token):
                return principal.identity if token == 'synthetic' else None
        client = TestClient(create_app(EntraPort(), self.reader))
        self.addCleanup(client.close)
        self.assert_error(self.get(token='synthetic', client=client), 404, 'NOT_FOUND')
        binder_pool = self.db.pool(user='forge_identity_binder')
        self.addCleanup(binder_pool.close, timeout=5)
        self.assertIsNotNone(PostgresIdentityBinder(binder_pool).bind_existing(UUID(int=11), principal))
        response = self.get(token='synthetic', client=client)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['membership'], {'id': str(MEMBER_A)})
        for private in (tid, oid, principal.sub, principal.issuer, 'entra_tenant_id'):
            self.assertNotIn(private, response.text)
        self.assert_error(self.get(token='synthetic', org=ORG_B, client=client), 404, 'NOT_FOUND')
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
        self.assert_error(self.get(token='synthetic', client=client), 403, 'MEMBERSHIP_SUSPENDED')
        with connect() as conn:
            conn.execute('DELETE FROM forge.memberships WHERE id=%s', (MEMBER_A,))
        self.assert_error(self.get(token='synthetic', client=client), 404, 'NOT_FOUND')

    def test_real_bootstrap_exact_public_projection_for_two_organizations(self):
        for token, org, revision in (('alice', ORG_A, 1), ('bob', ORG_B, 2)):
            with self.subTest(token=token):
                response = self.get(token=token, org=org)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(set(body), {'schema_version', 'organization', 'membership',
                                            'config_revision'})
                self.assertEqual(body['schema_version'], '1.0')
                self.assertEqual(set(body['organization']), {'id', 'slug', 'display_name'})
                self.assertEqual(body['organization']['id'], str(org))
                self.assertEqual(set(body['membership']), {'id'})
                self.assertEqual(body['config_revision'], revision)

    def test_owned_suspension_403_foreign_and_archived_404(self):
        self.assert_error(self.get(token='suspended'), 403, 'MEMBERSHIP_SUSPENDED')
        for token, org in (('alice', ORG_B), ('bob', ORG_A), ('suspended', ORG_B),
                           ('archived', ORG_A), ('alice', UUID(int=999))):
            with self.subTest(token=token, org=org):
                self.assert_error(self.get(token=token, org=org), 404, 'NOT_FOUND')

    def test_live_suspension_revocation_and_configuration_are_reloaded(self):
        self.assertEqual(self.get().json()['config_revision'], 1)
        with connect() as conn, conn.transaction():
            conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,9)', (ORG_A,))
            conn.execute('UPDATE forge.organizations SET selected_config_revision=9 WHERE id=%s',
                         (ORG_A,))
        self.assertEqual(self.get().json()['config_revision'], 9)
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
        self.assert_error(self.get(), 403, 'MEMBERSHIP_SUSPENDED')
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='archived' WHERE id=%s", (MEMBER_A,))
        self.assert_error(self.get(), 404, 'NOT_FOUND')

    def test_inactive_organization_is_hidden_before_owned_suspension(self):
        with connect() as conn:
            conn.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (ORG_A,))
        for token in ('alice', 'suspended'):
            self.assert_error(self.get(token=token), 404, 'NOT_FOUND')

    def test_secret_rich_real_query_failure_redacted_and_next_request_recovers(self):
        with self.pool.connection() as conn:
            pid = conn.info.backend_pid
            conn.fail_data = 'secret'
        self.assert_error(self.get(), 503, 'SERVICE_UNAVAILABLE')
        self.assertEqual(self.get(token='bob', org=ORG_B).status_code, 200)
        with self.pool.connection() as conn:
            self.assertEqual(conn.info.backend_pid, pid)
            self.assertIn(conn.execute("SELECT current_setting('forge.subject',true)")
                          .fetchone()[0], (None, ''))

    def test_closed_exhausted_and_admin_pools_are_redacted_503(self):
        with self.pool.connection():
            self.assert_error(self.get(), 503, 'SERVICE_UNAVAILABLE')
        self.pool.close(timeout=5)
        self.assert_error(self.get(), 503, 'SERVICE_UNAVAILABLE')
        admin = self.db.pool(user='postgres')
        self.addCleanup(admin.close, timeout=5)
        client = TestClient(create_app(TestValidator(), PostgresBootstrapReader(admin)))
        self.addCleanup(client.close)
        self.assert_error(self.get(client=client), 503, 'SERVICE_UNAVAILABLE')

    def test_default_api_deny_all_auth_validation_and_spoofed_context(self):
        client = TestClient(create_app(bootstrap_reader=self.reader))
        self.addCleanup(client.close)
        self.assert_error(self.get(client=client), 401, 'UNAUTHENTICATED')
        self.assert_error(self.get(headers={}), 401, 'UNAUTHENTICATED')
        self.assert_error(self.get(token='invalid'), 401, 'UNAUTHENTICATED')
        self.assert_error(self.get(token='invalid', org='invalid'), 401, 'UNAUTHENTICATED')
        self.assert_error(self.get(org='invalid'), 422, 'INVALID_REQUEST')
        self.assert_error(self.get(org=ORG_B, headers={
            'Authorization': 'Bearer alice', 'X-Subject': 'bob', 'X-Organization-Id': str(ORG_B),
            'Cookie': 'subject=bob'}), 404, 'NOT_FOUND')

    def test_real_reader_runs_in_worker_thread_not_client_thread(self):
        calling_thread = get_ident()
        self.assertEqual(self.get().status_code, 200)
        with self.pool.connection() as conn:
            self.assertTrue(conn.data_threads)
            self.assertNotIn(calling_thread, conn.data_threads)


if __name__ == '__main__':
    unittest.main()
