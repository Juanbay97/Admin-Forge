"""Real RSA and owned PostgreSQL proof through the HTTP designation boundary."""
from pathlib import Path
import sys
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from forge.api import create_app
from forge.administration import DesignationConfiguration, InitialAdministratorService
from forge.administration_store import PostgresInitialAdministratorStore
from postgres_support import DatabaseFixture, connect, ORG_A, MEMBER_A, ALICE, CAROL
import test_administration as crypto_tests
import test_administration_api as http_tests
from test_entra import TENANT, NOW, issuer


class PostgresAdministrationHttpTests(http_tests.HttpAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()
        cls.crypto = crypto_tests.AdministrationTests()
        cls.crypto.setUpClass()

    def setUp(self):
        self.db.reset()
        self.crypto.setUp()
        with connect() as conn:
            conn.execute(
                "UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                (issuer(), str(UUID(int=800)), UUID(TENANT), UUID(int=800), ALICE),
            )
        self.pool = self.db.pool(user="forge_designator")
        self.addCleanup(self.pool.close, timeout=5)
        self.store = PostgresInitialAdministratorStore(self.pool)
        self.service = InitialAdministratorService(
            self.crypto.validator, self.store, self.crypto.configuration,
        )
        self.client = TestClient(create_app(initial_administrator_service=self.service))
        self.addCleanup(self.client.close)
        self.payload = http_tests.body()
        self.token = self.crypto.token()

    def signed_post(self, payload=None, token=None, client=None):
        return self.post(payload or self.payload, client=client,
                         headers={"Authorization": "Bearer " + (token or self.token)})

    def state(self):
        with connect() as conn:
            return (
                conn.execute("SELECT * FROM forge.membership_roles ORDER BY 1,2,3").fetchall(),
                conn.execute("SELECT * FROM forge.initial_admin_designations ORDER BY 1").fetchall(),
                conn.execute("SELECT * FROM forge.initial_admin_outbox ORDER BY 1").fetchall(),
                conn.execute("SELECT id,status,revision FROM forge.memberships ORDER BY id").fetchall(),
                conn.execute("SELECT id,active FROM forge.organizations ORDER BY id").fetchall(),
            )

    def test_http_success_and_exact_replay_commit_only_once(self):
        with patch.object(self.service, "designate", wraps=self.service.designate) as designate:
            first = self.signed_post()
            self.assertEqual(first.status_code, 200, first.text)
            state = self.state()
            replay = self.signed_post()
            self.assertEqual(first.json(), replay.json())
            self.assertEqual(designate.call_count, 2)
        self.assertEqual(state, self.state())
        roles, markers, events, members, _ = state
        self.assertEqual(roles, [(ORG_A, MEMBER_A, "organization_admin")])
        self.assertEqual(len(markers), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(next(row for row in members if row[0] == MEMBER_A)[2], 2)
        with connect() as conn:
            event = conn.execute(
                "SELECT event_id,request_id,resource_id,actor_id,revision FROM forge.initial_admin_outbox"
            ).fetchone()
        self.assertEqual(event, (UUID(first.json()["event_id"]), UUID(self.payload["operation_id"]),
                                 MEMBER_A, crypto_tests.ACTOR, 2))
        self.assertEqual(first.json()["audit_publication"], "pending")

    def test_changed_payload_and_new_operation_conflict_without_writes(self):
        # A different coherent target reaches the replay-conflict check, not binding denial.
        with connect() as conn:
            conn.execute(
                "UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                (issuer(), str(UUID(int=801)), UUID(TENANT), UUID(int=801), CAROL),
            )
        self.assertEqual(self.signed_post().status_code, 200)
        before = self.state()
        for changes in ({"expected_revision": 2}, {"membership_id": str(UUID(int=23))},
                        {"operation_id": str(uuid4())}):
            self.assert_error(self.signed_post(self.payload | changes), 409, "DESIGNATION_CONFLICT")
            self.assertEqual(self.state(), before)

    def test_stale_revision_conflict_is_atomic(self):
        before = self.state()
        self.assert_error(self.signed_post(self.payload | {"expected_revision": 2}),
                          409, "DESIGNATION_CONFLICT")
        self.assertEqual(self.state(), before)

    def test_invalid_and_unprivileged_tokens_never_reach_store(self):
        before = self.state()
        tokens = ["invalid-token", self.crypto.token(oid=str(uuid4()), roles=["organization_admin"]),
                  self.crypto.token(exp=NOW-90, nbf=NOW-200, iat=NOW-200)]
        with patch.object(self.store, "_designate", wraps=self.store._designate) as store_call:
            for token in tokens:
                self.assert_error(self.signed_post(token=token), 403, "DESIGNATION_DENIED")
            store_call.assert_not_called()
        self.assertEqual(self.state(), before)

    def test_replay_with_expired_token_or_revoked_operator_does_not_mutate(self):
        self.assertEqual(self.signed_post().status_code, 200)
        before = self.state()
        self.assert_error(self.signed_post(token=self.crypto.token(exp=NOW-90, nbf=NOW-200, iat=NOW-200)),
                          403, "DESIGNATION_DENIED")
        revoked = InitialAdministratorService(
            self.crypto.validator, self.store,
            DesignationConfiguration((), self.crypto.configuration.organization_tenants),
        )
        with TestClient(create_app(initial_administrator_service=revoked)) as client:
            self.assert_error(self.signed_post(client=client), 403, "DESIGNATION_DENIED")
        self.assertEqual(self.state(), before)

    def test_absent_injection_and_validator_outage_leave_database_unchanged(self):
        before = self.state()
        with TestClient(create_app()) as client:
            self.assert_error(self.signed_post(client=client), 503, "SERVICE_UNAVAILABLE")
        self.crypto.fetcher.error = RuntimeError(http_tests.SECRET)
        self.assert_error(self.signed_post(), 503, "SERVICE_UNAVAILABLE")
        self.assertEqual(self.state(), before)

    def test_outbox_sql_failure_rolls_back_claim_grant_and_revision(self):
        import psycopg
        observed = []

        class Cursor(psycopg.Cursor):
            def execute(cursor, query, params=None, **kwargs):
                if str(query).startswith("INSERT INTO forge.initial_admin_outbox"):
                    super().execute(
                        "SELECT (SELECT count(*) FROM forge.membership_roles),"
                        "(SELECT revision FROM forge.memberships LIMIT 1),"
                        "(SELECT count(*) FROM forge.initial_admin_designations)"
                    )
                    observed.append(cursor.fetchone())
                    return super().execute("SELECT 1/0")
                return super().execute(query, params, **kwargs)

        class Connection(psycopg.Connection):
            def cursor(connection, *args, **kwargs):
                return Cursor(connection, row_factory=kwargs.get("row_factory"))

        pool = self.db.pool(user="forge_designator", connection_class=Connection)
        self.addCleanup(pool.close, timeout=5)
        service = InitialAdministratorService(
            self.crypto.validator, PostgresInitialAdministratorStore(pool), self.crypto.configuration,
        )
        before = self.state()
        with TestClient(create_app(initial_administrator_service=service)) as client:
            self.assert_error(self.signed_post(client=client), 503, "SERVICE_UNAVAILABLE")
        self.assertEqual(observed, [(1, 2, 1)])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.signed_post().status_code, 200)

    def test_inactive_organization_designation_does_not_activate_it(self):
        with connect() as conn:
            conn.execute("UPDATE forge.organizations SET active=false WHERE id=%s", (ORG_A,))
        self.assertEqual(self.signed_post().status_code, 200)
        with connect() as conn:
            self.assertIs(conn.execute("SELECT active FROM forge.organizations WHERE id=%s",
                                       (ORG_A,)).fetchone()[0], False)

    def test_closed_pool_is_redacted_service_unavailable(self):
        before = self.state()
        self.pool.close(timeout=5)
        self.assert_error(self.signed_post(), 503, "SERVICE_UNAVAILABLE")
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
