"""Real PostgreSQL service/store proof with explicit fixture principal, never live Entra."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import secrets
import hashlib
import json
import time
import unittest
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

from postgres_support import (
    DatabaseFixture, connect, settings, catalog_authority_schema, ORG_A, ORG_B,
    MEMBER_A, MEMBER_B, ALICE, BOB,
)
from test_postgres_catalog_publication_authority import seed_actor, TENANT, OBJECT
from test_postgres_model_catalog import snapshot
from test_catalog_publication import Verifier, PRINCIPAL
from test_authorization import snapshot as observation
from forge.authorization_store import PostgresAuthorizationReader
from forge.catalog_publication import (
    CatalogPublisher, PublicationRequest, PublicationDenied, PublicationConflict, PublicationUnavailable,
)
from forge.catalog_publication_store import PostgresCatalogPublisher
from forge.model_catalog_store import insert_catalog, encode_catalog


class FaultCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        result = super().execute(query, params, **kwargs)
        self.connection.seen.append(str(query))
        if self.connection.fail_phase and self.connection.fail_phase in str(query):
            self.connection.fail_phase = None
            raise RuntimeError("PRIVATE_FIXTURE_SQL_FAILURE")
        return result


class FaultConnection(psycopg.Connection):
    fail_phase = None
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen = []

    def cursor(self, *args, **kwargs):
        return FaultCursor(self, row_factory=kwargs.get("row_factory"))


class PublicationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    @contextmanager
    def fixture(self):
        with catalog_authority_schema() as admin:
            seed_actor(admin)
            password = secrets.token_urlsafe(32)
            admin.execute(sql.SQL("ALTER ROLE forge_config_publisher LOGIN PASSWORD {}").format(sql.Literal(password)))
            kwargs = settings() | dict(user="forge_config_publisher", password=password)
            with ConnectionPool("", kwargs=kwargs, min_size=1, max_size=3,
                                connection_class=FaultConnection, open=True) as pool, self.db.pool() as reads:
                pool.wait(5)
                verifier = Verifier()
                reader = PostgresAuthorizationReader(reads)
                service = CatalogPublisher(verifier, reader, PostgresCatalogPublisher(pool))
                yield admin, pool, reader, verifier, service

    def prepare(self, admin, revision=1, operation=UUID(int=980), org=ORG_A):
        value = replace(snapshot(), revision=revision)
        if org != ORG_A:
            alias = value.aliases[0]
            routes = tuple(replace(route, organization_id=org) for route in alias.routes)
            value = replace(value, organization_id=org, aliases=(replace(alias, routes=routes),))
        with admin.transaction():
            insert_catalog(admin, value)
        return PublicationRequest(org, value.router_binding_id, operation, revision-1, encode_catalog(value)[1])

    def counts(self, admin):
        return tuple(admin.execute("SELECT count(*) FROM forge." + table).fetchone()[0]
                     for table in ("outbox_events", "active_model_catalogs", "catalog_publication_operations"))

    def test_publish_replay_after_advance_and_fresh_verification(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            first = self.prepare(admin)
            result = service.publish("fixture-token", first)
            second = self.prepare(admin, 2, UUID(int=981))
            service.publish("fixture-token", second)
            self.assertEqual(service.publish("fixture-token", first), result)
            self.assertEqual(admin.execute("SELECT catalog_revision FROM forge.active_model_catalogs").fetchone(), (2,))
            self.assertEqual(self.counts(admin), (2, 1, 2))
            self.assertEqual(len(verifier.calls), 3)
            verifier.principal = None
            with self.assertRaises(PublicationDenied):
                service.publish("fixture-token", first)

    def test_stale_cas_changed_operation_payload_and_missing_snapshot_conflict(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            service.publish("fixture-token", request)
            for changed in (replace(request, operation_id=UUID(int=999)),
                            replace(request, payload_sha256="0"*64),
                            replace(request, expected_revision=1)):
                with self.assertRaises(PublicationConflict):
                    service.publish("fixture-token", changed)
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_changed_actor_and_cross_org_global_operation_conflict(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            service.publish("fixture-token", request)
            other_object = UUID(int=955)
            admin.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                (PRINCIPAL.issuer, str(other_object), TENANT, other_object, BOB))
            admin.execute("INSERT INTO forge.memberships(organization_id,id,identity_id,status) "
                          "VALUES(%s,%s,%s,'active')", (ORG_A, UUID(int=27), BOB))
            admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin'),"
                          "(%s,%s,'organization_admin')", (ORG_A, UUID(int=27), ORG_B, MEMBER_B))
            verifier.principal = replace(PRINCIPAL, oid=str(other_object))
            with self.assertRaises(PublicationConflict):
                service.publish("fixture-token", request)
            foreign = self.prepare(admin, org=ORG_B)
            with self.assertRaises(PublicationConflict) as caught:
                service.publish("fixture-token", foreign)
            self.assertNotIn(str(MEMBER_A), str(caught.exception))
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_permissive_stale_prelookup_never_authorizes_revoked_actor_or_replay(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            service.publish("fixture-token", request)
            stale = reader.read(PRINCIPAL.identity, str(ORG_A))
            class StaleReader:
                def read(self, *args):
                    return stale
            unsafe_observation = CatalogPublisher(verifier, StaleReader(), PostgresCatalogPublisher(pool))
            for mutation in ("DELETE FROM forge.membership_roles",
                             "UPDATE forge.memberships SET status='suspended'"):
                admin.execute(mutation)
                with self.assertRaises(PublicationDenied):
                    unsafe_observation.publish("fixture-token", request)
                if mutation.startswith("DELETE"):
                    admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (ORG_A, MEMBER_A))
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_revocation_between_real_prelookup_and_helper_denies(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            class RevokeAfterRead:
                def read(self, identity, org):
                    value = reader.read(identity, org)
                    admin.execute("DELETE FROM forge.membership_roles WHERE membership_id=%s", (MEMBER_A,))
                    return value
            blocked = CatalogPublisher(verifier, RevokeAfterRead(), PostgresCatalogPublisher(pool))
            with self.assertRaises(PublicationDenied):
                blocked.publish("fixture-token", request)
            self.assertEqual(self.counts(admin), (0, 0, 0))

    def test_concurrent_identical_requests_commit_one_original_result(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            with ThreadPoolExecutor(2) as workers:
                results = list(workers.map(lambda _: service.publish("fixture-token", request), range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_concurrent_distinct_operations_have_one_cas_winner(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            def publish(value):
                try:
                    return service.publish("fixture-token", value)
                except PublicationConflict:
                    return None
            with ThreadPoolExecutor(2) as workers:
                results = list(workers.map(publish, (request, replace(request, operation_id=UUID(int=999)))))
            self.assertEqual(sum(value is not None for value in results), 1)
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_failures_after_each_write_roll_back_and_same_connection_recovers(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            # Shrink only this fixture pool to ensure the same real connection is borrowed.
            pool.resize(1, 1)
            for table in ("outbox_events", "active_model_catalogs", "catalog_publication_operations"):
                with pool.connection() as connection:
                    connection.fail_phase = "INSERT INTO forge." + table
                    connection.seen.clear()
                    pid = connection.info.backend_pid
                with self.assertRaises(PublicationUnavailable) as caught:
                    service.publish("fixture-token", request)
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertEqual(self.counts(admin), (0, 0, 0))
                with pool.connection() as connection:
                    self.assertEqual(connection.info.backend_pid, pid)
                    self.assertEqual(connection.execute("SELECT coalesce(current_setting('forge.organization',true),'')").fetchone(), ("",))
                    self.assertLess(next(i for i,q in enumerate(connection.seen) if "lock_catalog_authority" in q),
                                    next(i for i,q in enumerate(connection.seen) if "INSERT INTO forge." in q))
            service.publish("fixture-token", request)
            self.assertEqual(self.counts(admin), (1, 1, 1))

    def test_response_loss_after_commit_replays_without_second_event(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            class LostResponse:
                lost = False
                @contextmanager
                def connection(self, **kwargs):
                    with pool.connection(**kwargs) as conn:
                        yield conn
                    if not self.lost:
                        self.lost = True
                        raise RuntimeError("fixture response loss")
            uncertain = CatalogPublisher(verifier, reader, PostgresCatalogPublisher(LostResponse()))
            with self.assertRaises(PublicationUnavailable):
                uncertain.publish("fixture-token", request)
            result = uncertain.publish("fixture-token", request)
            self.assertEqual(self.counts(admin), (1, 1, 1))
            self.assertEqual(admin.execute("SELECT event_id FROM forge.catalog_publication_operations").fetchone()[0], result.event_id)

    def test_dirty_nonidle_elevated_and_extra_privilege_borrows_deny(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            class Fixed:
                @contextmanager
                def connection(self, **kwargs):
                    yield held
            with connect() as held:
                denied = CatalogPublisher(verifier, reader, PostgresCatalogPublisher(Fixed()))
                with self.assertRaises(PublicationUnavailable):
                    denied.publish("fixture-token", request)
            with pool.connection() as held:
                denied = CatalogPublisher(verifier, reader, PostgresCatalogPublisher(Fixed()))
                with held.transaction(), self.assertRaises(PublicationUnavailable):
                    denied.publish("fixture-token", request)
                held.execute("SET forge.organization='dirty'")
                with self.assertRaises(PublicationUnavailable):
                    denied.publish("fixture-token", request)
                held.execute("RESET forge.organization")
                held.autocommit = False
                with self.assertRaises(PublicationUnavailable):
                    denied.publish("fixture-token", request)
                held.autocommit = True
            admin.execute("GRANT SELECT ON forge.identities TO forge_config_publisher")
            with self.assertRaises(PublicationUnavailable):
                service.publish("fixture-token", request)
            self.assertEqual(self.counts(admin), (0, 0, 0))

    def test_concurrent_revocation_waits_then_service_reloads_denial(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            observed = reader.read(PRINCIPAL.identity, str(ORG_A))
            class Stale:
                def read(self, *args):
                    return observed
            contender = CatalogPublisher(verifier, Stale(), PostgresCatalogPublisher(pool))
            with ThreadPoolExecutor(1) as workers:
                with admin.transaction():
                    admin.execute("DELETE FROM forge.membership_roles WHERE membership_id=%s", (MEMBER_A,))
                    future = workers.submit(contender.publish, "fixture-token", request)
                    deadline = time.monotonic()+0.8
                    while time.monotonic() < deadline:
                        blocked = admin.execute("SELECT count(*) FROM pg_stat_activity "
                            "WHERE usename='forge_config_publisher' AND %s=ANY(pg_blocking_pids(pid))",
                            (admin.info.backend_pid,)).fetchone()[0]
                        if blocked:
                            break
                        time.sleep(0.01)
                    self.assertTrue(blocked)
                with self.assertRaises(PublicationDenied):
                    future.result(3)
            self.assertEqual(self.counts(admin), (0, 0, 0))

    def test_corrupted_stored_domain_is_unavailable_before_any_write(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            payload = json.loads(encode_catalog(snapshot())[0])
            payload["aliases"][0]["routes"][0]["capabilities"]["tools"] = None
            malformed = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            checksum = hashlib.sha256(malformed.encode()).hexdigest()
            admin.execute("UPDATE forge.model_catalog_snapshots SET payload=%s,payload_sha256=%s",
                          (malformed, checksum))
            with self.assertRaises(PublicationUnavailable):
                service.publish("fixture-token", replace(request, payload_sha256=checksum))
            self.assertEqual(self.counts(admin), (0, 0, 0))

    def test_delegatable_privilege_is_not_a_restricted_publisher_borrow(self):
        with self.fixture() as (admin, pool, reader, verifier, service):
            request = self.prepare(admin)
            admin.execute("GRANT SELECT ON forge.model_catalog_snapshots TO forge_config_publisher WITH GRANT OPTION")
            with self.assertRaises(PublicationUnavailable):
                service.publish("fixture-token", request)
            self.assertEqual(self.counts(admin), (0, 0, 0))
