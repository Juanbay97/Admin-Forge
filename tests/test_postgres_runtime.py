"""Owned PostgreSQL runtime proof; no existing DB, account or live Entra."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from forge.postgres import PostgresReadinessProbe
from postgres_support import DatabaseFixture, connect, ORG_A


class PostgresRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()
        self.pool = self.db.pool()
        self.addCleanup(self.pool.close, timeout=5)

    def test_role_and_migrated_schema_are_ready_without_organization_context(self):
        self.assertTrue(PostgresReadinessProbe(self.pool).check())
        with self.pool.connection() as conn:
            for key in ("organization", "provider", "issuer", "subject"):
                self.assertIn(conn.execute("SELECT current_setting(%s,true)",
                    ("forge."+key,)).fetchone()[0], (None, ""))

    def test_readiness_needs_no_business_rows_or_counts(self):
        with connect() as conn:
            conn.execute("TRUNCATE forge.organizations,forge.identities CASCADE")
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_admin_is_not_ready(self):
        pool = self.db.pool(user="postgres")
        self.addCleanup(pool.close, timeout=5)
        self.assertFalse(PostgresReadinessProbe(pool).check())

    def test_frozen_legacy_readiness_accepts_retained_destination(self):
        import hashlib
        import forge.postgres as p
        names = ('_ROLE_CHECK', '_EMPTY_CONTEXT', '_SCHEMA_CHECK', '_BINDING_CHECK',
                 '_AUTHORIZATION_SCHEMA', '_ROLE_VALUES_CHECK', '_ROLE_SCOPE_CHECK',
                 '_DESIGNATION_SCHEMA', '_DESIGNATION_FUNCTION_SOURCES')
        self.assertEqual(hashlib.sha256(repr(tuple(getattr(p, n) for n in names)).encode()).hexdigest(),
                         '4766b7f0fd206467971e6f2a51357b9ef3546f797fc945c8b7a3554248edfb3c')
        with self.pool.connection() as conn, conn.transaction():
            conn.execute('SET LOCAL search_path=pg_catalog')
            for query, params in ((p._EMPTY_CONTEXT, None), (p._ROLE_CHECK, None),
                    (p._SCHEMA_CHECK, (p._BINDING_CHECK,)),
                    (p._AUTHORIZATION_SCHEMA, (p._ROLE_VALUES_CHECK, p._ROLE_SCOPE_CHECK)),
                    (p._DESIGNATION_SCHEMA, p._DESIGNATION_FUNCTION_SOURCES)):
                self.assertTrue(conn.execute(query, params).fetchone()[0])

    def test_outbox_security_and_shape_tampering_fails_closed(self):
        mutations = (
            'ALTER TABLE forge.outbox_events DISABLE ROW LEVEL SECURITY',
            'ALTER TABLE forge.outbox_events NO FORCE ROW LEVEL SECURITY',
            'ALTER TABLE forge.outbox_events DISABLE TRIGGER ALL',
            'ALTER TABLE forge.outbox_events ALTER actor_id DROP NOT NULL',
            'ALTER TABLE forge.outbox_events DROP CONSTRAINT outbox_events_revision_check',
            "ALTER POLICY outbox_record ON forge.outbox_events WITH CHECK (true)",
            'GRANT SELECT ON forge.outbox_events TO forge_outbox_writer',
            'GRANT UPDATE(actor_id) ON forge.outbox_events TO forge_outbox_writer',
            'GRANT INSERT ON forge.outbox_events TO forge_runtime',
            'ALTER ROLE forge_outbox_writer BYPASSRLS',
            'GRANT forge_outbox_writer TO forge_runtime',
            'GRANT forge_runtime TO forge_outbox_writer',
            'ALTER TABLE forge.outbox_events OWNER TO forge_outbox_writer',
            'GRANT EXECUTE ON FUNCTION forge.designation_uuid(text) TO forge_outbox_writer',
            'REVOKE CONNECT ON DATABASE forge_test FROM forge_outbox_writer',
        )
        for query in mutations:
            with self.subTest(query=query), connect() as conn:
                conn.execute('BEGIN')
                conn.execute(query)
                # Use the same transaction so no tampering survives a failing assertion.
                from forge.postgres import _OUTBOX_SCHEMA
                try:
                    self.assertFalse(conn.execute(_OUTBOX_SCHEMA).fetchone()[0])
                finally:
                    conn.execute('ROLLBACK')
            self.assertTrue(PostgresReadinessProbe(self.pool).check())


    def test_probe_restores_timeouts_and_never_sets_business_context(self):
        with self.pool.connection() as conn:
            before = (conn.execute("SHOW statement_timeout").fetchone()[0],
                      conn.execute("SHOW lock_timeout").fetchone()[0],
                      conn.info.backend_pid)
        self.assertTrue(PostgresReadinessProbe(self.pool).check())
        with self.pool.connection() as conn:
            after = (conn.execute("SHOW statement_timeout").fetchone()[0],
                     conn.execute("SHOW lock_timeout").fetchone()[0],
                     conn.info.backend_pid)
        self.assertEqual(before, after)

    def test_column_mutations_and_elevated_role_cannot_report_ready(self):
        for privilege in ("UPDATE", "INSERT", "REFERENCES"):
            with self.subTest(privilege=privilege), connect() as conn:
                query = privilege + "(entra_tenant_id,entra_object_id)"
                conn.execute("GRANT " + query + " ON forge.identities TO forge_runtime")
                try:
                    self.assertFalse(PostgresReadinessProbe(self.pool).check())
                finally:
                    conn.execute("REVOKE " + query + " ON forge.identities FROM forge_runtime")
        with connect() as conn:
            conn.execute("ALTER ROLE forge_runtime BYPASSRLS")
            try:
                self.assertFalse(PostgresReadinessProbe(self.pool).check())
            finally:
                conn.execute("ALTER ROLE forge_runtime NOBYPASSRLS")
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_missing_pair_constraint_trigger_policy_or_invoker_never_ready(self):
        with connect() as conn:
            check = conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='forge.identities'::regclass AND conname='entra_binding_consistent'").fetchone()[0]
        cases = [
            ("ALTER TABLE forge.identities DROP CONSTRAINT entra_binding_consistent",
             "ALTER TABLE forge.identities ADD CONSTRAINT entra_binding_consistent " + check),
            ("ALTER TABLE forge.identities DROP CONSTRAINT entra_binding_unique",
             "ALTER TABLE forge.identities ADD CONSTRAINT entra_binding_unique UNIQUE(entra_tenant_id,entra_object_id)"),
            ("ALTER TABLE forge.identities DISABLE TRIGGER entra_binding_write_once",
             "ALTER TABLE forge.identities ENABLE TRIGGER entra_binding_write_once"),
            ("ALTER POLICY identity_binding_scope ON forge.identities RENAME TO hidden_binding_scope",
             "ALTER POLICY hidden_binding_scope ON forge.identities RENAME TO identity_binding_scope"),
            ("ALTER FUNCTION forge.guard_entra_binding() SECURITY DEFINER",
             "ALTER FUNCTION forge.guard_entra_binding() SECURITY INVOKER"),
            ("ALTER TABLE forge.organizations ALTER COLUMN slug TYPE varchar(200)",
             "ALTER TABLE forge.organizations ALTER COLUMN slug TYPE text"),
        ]
        for query, restore in cases:
            with self.subTest(query=query), connect() as conn:
                # Commit isolated harness DDL so the other connection sees it.
                # Uncommitted catalog writes are not a valid corruption fixture.
                conn.execute(query)
                try:
                    self.assertFalse(PostgresReadinessProbe(self.pool).check())
                finally:
                    conn.execute(restore)
            self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_weakened_same_named_pair_check_is_not_ready(self):
        with connect() as conn:
            check = conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='forge.identities'::regclass AND conname='entra_binding_consistent'").fetchone()[0]
            with conn.transaction():
                conn.execute("ALTER TABLE forge.identities DROP CONSTRAINT entra_binding_consistent")
                conn.execute("ALTER TABLE forge.identities ADD CONSTRAINT entra_binding_consistent CHECK(true)")
            try:
                self.assertFalse(PostgresReadinessProbe(self.pool).check())
            finally:
                with conn.transaction():
                    conn.execute("ALTER TABLE forge.identities DROP CONSTRAINT entra_binding_consistent")
                    conn.execute("ALTER TABLE forge.identities ADD CONSTRAINT entra_binding_consistent " + check)
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_dirty_context_or_transaction_is_not_ready(self):
        from contextlib import contextmanager
        from forge.postgres import PostgresReadinessProbe
        with self.pool.connection() as connection:
            class Borrow:
                @contextmanager
                def connection(self, **kwargs):
                    yield connection
            with connection.transaction():
                self.assertFalse(PostgresReadinessProbe(Borrow()).check())
            connection.execute("SELECT set_config('forge.organization',%s,false)", (str(ORG_A),))
            try:
                self.assertFalse(PostgresReadinessProbe(Borrow()).check())
            finally:
                connection.execute("RESET forge.organization")
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_closed_pool_never_ready_or_silently_reopened(self):
        self.pool.close(timeout=5)
        self.assertFalse(PostgresReadinessProbe(self.pool).check())
        self.assertTrue(self.pool.closed)

    def test_probe_queries_are_catalog_only(self):
        import psycopg
        from postgres_support import KEYS
        queries = []
        class Cursor(psycopg.Cursor):
            def execute(self, query, params=None, **kwargs):
                queries.append(str(query))
                return super().execute(query, params, **kwargs)
        class Connection(psycopg.Connection):
            def cursor(self, *args, **kwargs):
                return Cursor(self, row_factory=kwargs.get("row_factory"))
        pool = self.db.pool(connection_class=Connection)
        self.addCleanup(pool.close, timeout=5)
        self.assertTrue(PostgresReadinessProbe(pool).check())
        self.assertTrue(queries)
        for query in queries:
            self.assertNotIn("FROM forge.", query)
            self.assertNotIn("JOIN forge.", query)
            self.assertNotIn("set_config", query)
        self.assertTrue(any("pg_catalog.pg_attribute" in q for q in queries))

    def configuration(self):
        from forge.runtime import LocalDatabaseConfiguration, RuntimeConfiguration
        from postgres_support import settings
        from test_entra import config
        return RuntimeConfiguration(config(), LocalDatabaseConfiguration(
            host="127.0.0.1", port=settings()["port"], dbname="forge_test",
            password=self.db.runtime_password))

    def test_actual_runtime_crypto_storage_binding_and_membership_contract(self):
        import time
        from uuid import UUID
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from fastapi.testclient import TestClient
        from forge.entra import EntraTokenValidator
        from forge.runtime import create_runtime_app
        from test_entra import FakeFetcher, TENANT, OID, AUDIENCE, CLIENT, issuer
        from postgres_support import MEMBER_A, ORG_B
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        fetcher = FakeFetcher(key)
        def validator(configuration):
            return EntraTokenValidator(configuration, fetcher=fetcher)
        now = int(time.time())
        claims = dict(iss=issuer(), aud=AUDIENCE, tid=TENANT, oid=OID, sub="guest-sub",
                      ver="2.0", azp=CLIENT, scp="forge.read",
                      iat=now-100, nbf=now-100, exp=now+600)
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "key-1"})
        app = create_runtime_app(self.configuration(), _validator_factory=validator)
        with connect() as conn:
            conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s WHERE id=%s",
                         (issuer(), OID, UUID(int=11)))
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer " + token}
            def bootstrap(org=ORG_A, supplied=headers):
                return client.get("/forge/v1/bootstrap", params={"organization_id":str(org)},
                                  headers=supplied)
            state = client.get("/forge/v1/status").json()
            self.assertEqual(state["runtime"], "ready")
            self.assertEqual(state["identity_provider"], "configured_unverified")
            self.assertEqual(fetcher.calls, [])  # Readiness never fetches IDP.
            self.assertEqual(bootstrap(supplied={"Authorization":"Bearer invalid"}).status_code, 401)
            self.assertEqual(fetcher.calls, [])
            self.assertEqual(bootstrap().status_code, 404)  # Unbound denies.
            with connect() as conn:
                conn.execute("UPDATE forge.identities SET entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                             (UUID(TENANT), UUID(OID), UUID(int=11)))
            response = bootstrap()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["membership"]["id"], str(MEMBER_A))
            self.assertEqual(bootstrap(ORG_B).status_code, 404)
            with connect() as conn:
                conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
            self.assertEqual(bootstrap().status_code, 403)
            with connect() as conn:
                conn.execute("DELETE FROM forge.memberships WHERE id=%s", (MEMBER_A,))
            self.assertEqual(bootstrap().status_code, 404)
            self.assertEqual(client.get("/forge/v1/status").json()["user_access"], "not_evaluated")
            pool = app.state.runtime.pool
            with pool.connection() as conn:
                self.assertEqual(conn.execute("SHOW statement_timeout").fetchone()[0], "3s")
                self.assertEqual(conn.execute("SHOW lock_timeout").fetchone()[0], "1s")
                self.assertEqual(conn.execute("SELECT current_user,session_user").fetchone(),
                                 ("forge_runtime","forge_runtime"))
                self.assertNotIn(self.db.runtime_password, repr(conn))
        self.assertTrue(pool.closed)

    def test_real_expired_readiness_cache_detects_schema_outage_and_recovers(self):
        from fastapi.testclient import TestClient
        from forge.runtime import create_runtime_app
        clock = [100.0]
        app = create_runtime_app(self.configuration(), _clock=lambda:clock[0])
        with TestClient(app) as client:
            self.assertEqual(client.get("/forge/v1/status").json()["storage"], "ready")
            with connect() as conn:
                conn.execute("ALTER TABLE forge.identities DISABLE ROW LEVEL SECURITY")
                try:
                    # Finite positive cache deliberately remains valid until TTL.
                    self.assertEqual(client.get("/forge/v1/status").json()["storage"], "ready")
                    clock[0] += 5
                    self.assertEqual(client.get("/forge/v1/status").json()["storage"], "unavailable")
                finally:
                    conn.execute("ALTER TABLE forge.identities ENABLE ROW LEVEL SECURITY")
            clock[0] += 5
            self.assertEqual(client.get("/forge/v1/status").json()["storage"], "ready")
        self.assertTrue(app.state.runtime.pool.closed)

    def test_real_wrong_credentials_are_unavailable_and_logs_redacted(self):
        from dataclasses import replace
        from fastapi.testclient import TestClient
        from forge.runtime import create_runtime_app
        configuration = self.configuration()
        configuration = replace(configuration, database=replace(configuration.database,
                                password="PRIVATE_WRONG_PASSWORD_MARKER"))
        with self.assertLogs("psycopg.pool", level="WARNING") as logs:
            app = create_runtime_app(configuration)
            with TestClient(app) as client:
                response = client.get("/forge/v1/status")
                self.assertEqual(response.json()["storage"], "unavailable")
                self.assertNotIn("PRIVATE", response.text)
                self.assertEqual(client.get("/healthz").status_code, 200)
        output = "\\n".join(logs.output)
        for forbidden in ("PRIVATE", "127.0.0.1", "forge_test", "password authentication failed"):
            self.assertNotIn(forbidden, output)
        self.assertTrue(app.state.runtime.pool.closed)



    def test_new_role_table_rls_column_mutations_and_binder_grants_fail_readiness(self):
        for privilege in ("INSERT","UPDATE","REFERENCES"):
            with self.subTest(privilege=privilege),connect() as conn:
                conn.execute("GRANT "+privilege+"(role) ON forge.membership_roles TO forge_runtime")
                try:self.assertFalse(PostgresReadinessProbe(self.pool).check())
                finally:conn.execute("REVOKE "+privilege+"(role) ON forge.membership_roles FROM forge_runtime")
                self.assertTrue(PostgresReadinessProbe(self.pool).check())
        for privilege in ("INSERT","UPDATE","REFERENCES"):
            with self.subTest(column="revision",privilege=privilege),connect() as conn:
                conn.execute("GRANT "+privilege+"(revision) ON forge.memberships TO forge_runtime")
                try:self.assertFalse(PostgresReadinessProbe(self.pool).check())
                finally:conn.execute("REVOKE "+privilege+"(revision) ON forge.memberships FROM forge_runtime")
        with connect() as conn:
            conn.execute("ALTER TABLE forge.membership_roles DISABLE ROW LEVEL SECURITY")
            try:self.assertFalse(PostgresReadinessProbe(self.pool).check())
            finally:conn.execute("ALTER TABLE forge.membership_roles ENABLE ROW LEVEL SECURITY")
            conn.execute("GRANT SELECT ON forge.membership_roles TO forge_identity_binder")
            try:self.assertFalse(PostgresReadinessProbe(self.pool).check())
            finally:conn.execute("REVOKE SELECT ON forge.membership_roles FROM forge_identity_binder")
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_new_authorization_shapes_and_policy_cannot_be_weakened(self):
        cases=(
            ("ALTER TABLE forge.membership_roles RENAME TO hidden_roles",
             "ALTER TABLE forge.hidden_roles RENAME TO membership_roles"),
            ("ALTER TABLE forge.memberships ALTER COLUMN revision DROP DEFAULT",
             "ALTER TABLE forge.memberships ALTER COLUMN revision SET DEFAULT 1"),
            ("ALTER TABLE forge.memberships DROP CONSTRAINT membership_revision_positive",
             "ALTER TABLE forge.memberships ADD CONSTRAINT membership_revision_positive CHECK(revision>0)"),
            ("ALTER TABLE forge.membership_roles DROP CONSTRAINT membership_roles_membership",
             "ALTER TABLE forge.membership_roles ADD CONSTRAINT membership_roles_membership "
             "FOREIGN KEY(organization_id,membership_id) REFERENCES forge.memberships(organization_id,id)"),
            ("ALTER TABLE forge.membership_roles DROP CONSTRAINT membership_roles_known",
             "ALTER TABLE forge.membership_roles ADD CONSTRAINT membership_roles_known CHECK "
             "(role IN ('organization_admin','department_manager','skill_reviewer','member'))"),
            ("ALTER POLICY membership_role_scope ON forge.membership_roles USING(true)",None),
            ("ALTER POLICY membership_role_scope ON forge.membership_roles USING ("
             "organization_id=forge.context_organization() AND EXISTS (SELECT 1 FROM "
             "forge.memberships m JOIN forge.organizations o ON o.id=m.organization_id "
             "WHERE m.organization_id=membership_roles.organization_id "
             "AND m.id=membership_roles.membership_id AND m.status='active' AND o.active))", None),
            ("CREATE POLICY unwanted_role_visibility ON forge.membership_roles FOR SELECT "
             "TO forge_runtime USING(true)","DROP POLICY unwanted_role_visibility ON forge.membership_roles"),
        )
        with connect() as conn:
            original=conn.execute("SELECT pg_get_expr(polqual,polrelid) FROM pg_policy "
                "WHERE polrelid='forge.membership_roles'::regclass "
                "AND polname='membership_role_scope'").fetchone()[0]
            for corrupt,restore in cases:
                with self.subTest(change=corrupt):
                    conn.execute(corrupt)
                    try:self.assertFalse(PostgresReadinessProbe(self.pool).check())
                    finally:
                        conn.execute(restore or ("ALTER POLICY membership_role_scope ON "
                            "forge.membership_roles USING("+original+")"))
                    self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def test_readiness_restores_explicit_runtime_search_path_with_five_tables(self):
        with self.pool.connection() as conn:
            conn.execute("SET search_path=pg_catalog,forge")
            before=conn.execute("SHOW search_path").fetchone()
        self.assertTrue(PostgresReadinessProbe(self.pool).check())
        with self.pool.connection() as conn:
            self.assertEqual(conn.execute("SHOW search_path").fetchone(),before)
            conn.execute("RESET search_path")


    def test_operational_schema_attestation_is_separate_from_runtime_data_access(self):
        from fastapi.testclient import TestClient
        from forge.runtime import create_runtime_app
        clock=[100.0]
        app=create_runtime_app(self.configuration(),_clock=lambda:clock[0])
        with TestClient(app) as client:
            self.assertEqual(client.get("/forge/v1/status").json()["storage"],"ready")
            with connect() as admin:
                admin.execute("ALTER TABLE forge.initial_admin_outbox RENAME TO hidden_initial_outbox")
                try:
                    clock[0]+=5
                    body=client.get("/forge/v1/status").json()
                    self.assertEqual(body["storage"],"unavailable")
                    self.assertNotIn("outbox",str(body))
                finally:admin.execute("ALTER TABLE forge.hidden_initial_outbox RENAME TO initial_admin_outbox")
            clock[0]+=5
            self.assertEqual(client.get("/forge/v1/status").json()["storage"],"ready")
        self.assertTrue(app.state.runtime.pool.closed)

    def test_new_designation_context_is_rejected_by_ordinary_runtime_borrow(self):
        from forge.postgres import PostgresBootstrapReader
        from forge.foundation import AuthenticatedIdentity
        with self.pool.connection() as conn:
            conn.execute("SET forge.designation_actor='unexpected'")
        try:
            self.assertFalse(PostgresReadinessProbe(self.pool).check())
            with self.assertRaises(RuntimeError):
                PostgresBootstrapReader(self.pool).read(
                    AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
        finally:
            with self.pool.connection() as conn:conn.execute("RESET forge.designation_actor")
        self.assertTrue(PostgresReadinessProbe(self.pool).check())


if __name__ == "__main__":
    unittest.main()
