"""Real owned PostgreSQL authority locks and replay ledger, not bearer verification."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import time
import unittest
from uuid import UUID

import psycopg

from postgres_support import (
    ALICE, MEMBER_A, MEMBER_B, ORG_A, ORG_B, DatabaseFixture, connect,
    catalog_authority_schema, set_context, seed_outbox_migration_legacy,
)
from test_postgres_catalog_publication_schema import scope, event, pointer
from test_postgres_model_catalog import snapshot, legacy_state
from test_model_catalog import BINDING, OTHER
from forge.model_catalog_store import insert_catalog, encode_catalog
from forge.postgres import PostgresReadinessProbe

TENANT, OBJECT, OPERATION, EVENT = (UUID(int=n) for n in (950, 951, 952, 953))
FUNCTION = "forge.lock_catalog_authority(uuid,uuid,uuid,uuid)"
TABLE = "forge.catalog_publication_operations"
AUTHORITY = ("organizations", "memberships", "identities", "membership_roles")


def seed_actor(conn):
    conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                 "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                 ("https://login.microsoftonline.com/" + str(TENANT) + "/v2.0",
                  str(OBJECT), TENANT, OBJECT, ALICE))
    conn.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",
                 (ORG_A, MEMBER_A))


def publisher(conn, org=ORG_A):
    scope(conn, org=org)
    set_context(conn, org, "entra",
                "https://login.microsoftonline.com/" + str(TENANT) + "/v2.0", str(OBJECT))


def authorize(conn, org=ORG_A, member=MEMBER_A, tenant=TENANT, object_id=OBJECT):
    return conn.execute("SELECT forge.lock_catalog_authority(%s,%s,%s,%s)",
                        (org, member, tenant, object_id)).fetchone()[0]


def seed_publication(conn, org=ORG_A, member=MEMBER_A, operation=OPERATION, event_id=EVENT):
    catalog = replace(snapshot(), organization_id=org) if org == ORG_A else snapshot()
    # Alternate organization needs an equally correlated domain, not a forged blob.
    if org != ORG_A:
        alias = catalog.aliases[0]
        routes = tuple(replace(route, organization_id=org) for route in alias.routes)
        catalog = replace(catalog, organization_id=org, aliases=(replace(alias, routes=routes),))
    with conn.transaction():
        insert_catalog(conn, catalog)
        conn.execute("INSERT INTO forge.outbox_events "
                     "(event_id,organization_id,actor_id,request_id,resource_id,event_type,previous_revision,revision) "
                     "VALUES(%s,%s,%s,%s,%s,'model_catalog.published',0,1)",
                     (event_id, org, member, operation, BINDING))
        pointer(conn, org=org, event_id=event_id)
    return encode_catalog(catalog)[1]


def ledger(conn, checksum_value, **changes):
    values = dict(operation=OPERATION, org=ORG_A, actor=MEMBER_A, binding=BINDING,
                  expected=0, revision=1, checksum=checksum_value, event=EVENT)
    values.update(changes)
    conn.execute("INSERT INTO forge.catalog_publication_operations "
                 "(operation_id,organization_id,actor_id,router_binding_id,expected_revision,"
                 "catalog_revision,payload_sha256,event_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                 tuple(values.values()))


class CatalogAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    def test_authority_helper_is_installed_and_hardened(self):
        with catalog_authority_schema() as conn:
            row = conn.execute("SELECT prosecdef,proconfig,pg_get_userbyid(proowner),prosrc "
                               "FROM pg_proc WHERE oid=%s::regprocedure", (FUNCTION,)).fetchone()
            self.assertEqual(row[:3], (True, ["search_path=pg_catalog"], "forge_catalog_authority"))
            self.assertNotIn("EXECUTE", row[3])
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_proc, "
                "LATERAL aclexplode(coalesce(proacl,acldefault('f',proowner))) a "
                "WHERE oid=%s::regprocedure AND grantee=0", (FUNCTION,)).fetchone()[0], 0)
            for role in ("forge_runtime", "forge_identity_binder", "forge_designator",
                         "forge_outbox_writer", "forge_catalog_writer", "forge_config_publisher"):
                self.assertEqual(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE')",
                    (role, FUNCTION)).fetchone()[0], role == "forge_config_publisher")

    def test_owner_is_nonlogin_nonbypass_noninheriting_and_not_table_owner(self):
        with catalog_authority_schema() as conn:
            role = conn.execute("SELECT oid,rolcanlogin,rolinherit,rolsuper,rolbypassrls,"
                "rolcreatedb,rolcreaterole,rolreplication FROM pg_roles "
                "WHERE rolname='forge_catalog_authority'").fetchone()
            self.assertEqual(role[1:], (False,) * 7)
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_auth_members "
                "WHERE roleid=%s OR member=%s", (role[0], role[0])).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_class WHERE relowner=%s",
                                          (role[0],)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT has_database_privilege('forge_catalog_authority',"
                "current_database(),'CONNECT,CREATE,TEMP'),"
                "has_schema_privilege('forge_catalog_authority','forge','CREATE')").fetchone(),
                (False, False))
            for table, in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='forge'"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    self.assertEqual(conn.execute("SELECT has_table_privilege(%s,%s,%s)",
                        ("forge_catalog_authority", "forge." + table, privilege)).fetchone()[0],
                        table in AUTHORITY and privilege == "SELECT")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                publisher(conn)
                conn.execute("SET ROLE forge_catalog_authority")

    def test_publisher_has_no_authority_mutation_or_event_read_expansion(self):
        with catalog_authority_schema() as conn:
            for table in AUTHORITY:
                for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                    self.assertFalse(conn.execute("SELECT has_any_column_privilege(%s,%s,%s)",
                        ("forge_config_publisher", "forge." + table, privilege)).fetchone()[0])
            self.assertFalse(conn.execute("SELECT has_table_privilege("
                "'forge_config_publisher','forge.outbox_events','SELECT')").fetchone()[0])
            seed_actor(conn)
            for table, column in zip(AUTHORITY, ("id", "organization_id", "id", "organization_id")):
                with self.subTest(table=table), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute("SET LOCAL ROLE forge_catalog_authority")
                    set_context(conn, ORG_A, "entra",
                                "https://login.microsoftonline.com/" + str(TENANT) + "/v2.0", str(OBJECT))
                    conn.execute("UPDATE forge." + table + " SET " + column + "=" + column)

    def test_exact_active_entra_admin_only_with_no_ambient_or_spoofed_scope(self):
        with catalog_authority_schema() as conn:
            seed_actor(conn)
            with conn.transaction():
                publisher(conn)
                conn.execute("SET LOCAL search_path=public")
                self.assertEqual(authorize(conn), 1)
                for args in ((ORG_B, MEMBER_A, TENANT, OBJECT), (ORG_A, MEMBER_B, TENANT, OBJECT),
                             (ORG_A, MEMBER_A, OTHER, OBJECT), (ORG_A, MEMBER_A, TENANT, OTHER),
                             (None, MEMBER_A, TENANT, OBJECT)):
                    self.assertIsNone(authorize(conn, *args))
            for key, value in (("organization", str(ORG_B)), ("provider", "test"),
                               ("issuer", "wrong"), ("subject", "wrong")):
                with self.subTest(key=key), conn.transaction():
                    publisher(conn)
                    conn.execute("SELECT set_config(%s,%s,true)", ("forge." + key, value))
                    self.assertIsNone(authorize(conn))
            with conn.transaction():
                scope(conn)
                self.assertIsNone(authorize(conn))

    def test_inactive_suspended_archived_missing_and_nonadmin_deny(self):
        mutations = ("UPDATE forge.organizations SET active=false",
                     "UPDATE forge.memberships SET status='suspended'",
                     "UPDATE forge.memberships SET status='archived'",
                     "DELETE FROM forge.membership_roles",
                     "UPDATE forge.membership_roles SET role='member'")
        with catalog_authority_schema() as conn:
            seed_actor(conn)
            for mutation in mutations:
                with self.subTest(mutation=mutation), conn.transaction(force_rollback=True):
                    conn.execute(mutation)
                    publisher(conn)
                    self.assertIsNone(authorize(conn))
            with conn.transaction():
                publisher(conn)
                self.assertIsNone(authorize(conn, member=UUID(int=999)))

    def test_unbound_identity_cannot_authorize_even_with_admin_grant(self):
        with catalog_authority_schema() as conn:
            conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s WHERE id=%s",
                         ("https://login.microsoftonline.com/" + str(TENANT) + "/v2.0", str(OBJECT), ALICE))
            conn.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (ORG_A, MEMBER_A))
            with conn.transaction():
                publisher(conn)
                self.assertIsNone(authorize(conn))

    def test_ledger_exact_roundtrip_immutable_and_roles_private(self):
        with catalog_authority_schema() as conn:
            checksum = seed_publication(conn)
            with conn.transaction():
                publisher(conn)
                ledger(conn, checksum)
                self.assertEqual(conn.execute("SELECT operation_id,actor_id,payload_sha256,event_id FROM " + TABLE)
                                 .fetchall(), [(OPERATION, MEMBER_A, checksum, EVENT)])
            self.assertEqual(conn.execute("SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) "
                "FROM pg_class WHERE oid=%s::regclass", (TABLE,)).fetchone(), (True, True, "forge_migrator"))
            for action in ("UPDATE " + TABLE + " SET expected_revision=1", "DELETE FROM " + TABLE,
                           "TRUNCATE " + TABLE):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    publisher(conn)
                    conn.execute(action)
            for role in ("forge_runtime", "forge_designator", "forge_identity_binder",
                         "forge_catalog_writer", "forge_outbox_writer", "forge_catalog_authority"):
                self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')",
                                               (role, TABLE)).fetchone()[0])

    def test_ledger_rejects_changed_actor_hash_revision_binding_event_and_operation(self):
        with catalog_authority_schema() as conn:
            checksum = seed_publication(conn)
            for changes in (dict(actor=MEMBER_B), dict(binding=OTHER), dict(checksum="0"*64),
                            dict(event=OTHER), dict(operation=OTHER), dict(expected=1),
                            dict(revision=2), dict(checksum="bad")):
                with self.subTest(changes=changes), self.assertRaises(psycopg.IntegrityError), conn.transaction():
                    publisher(conn)
                    ledger(conn, checksum, **changes)
            self.assertEqual(conn.execute("SELECT count(*) FROM " + TABLE).fetchone()[0], 0)

    def test_global_operation_collision_hides_foreign_record(self):
        with catalog_authority_schema() as conn:
            checksum = seed_publication(conn)
            foreign_hash = seed_publication(conn, ORG_B, MEMBER_B, OPERATION, OTHER)
            with conn.transaction():
                publisher(conn)
                ledger(conn, checksum)
            with conn.transaction():
                publisher(conn, ORG_B)
                self.assertEqual(conn.execute("SELECT * FROM " + TABLE).fetchall(), [])
            with self.assertRaises(psycopg.errors.UniqueViolation) as caught, conn.transaction():
                publisher(conn, ORG_B)
                ledger(conn, foreign_hash, org=ORG_B, actor=MEMBER_B, event=OTHER)
            self.assertNotIn(str(MEMBER_A), str(caught.exception))
            self.assertNotIn(checksum, str(caught.exception))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                publisher(conn, ORG_B)
                ledger(conn, checksum)

    def wait_blocked(self, observer, waiter, blocker):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if blocker in observer.execute("SELECT pg_blocking_pids(%s)", (waiter,)).fetchone()[0]:
                return
            time.sleep(0.01)
        self.fail("Real PostgreSQL lock wait was not observed")

    def test_authority_locks_block_direct_revocation_until_transaction_end(self):
        mutations = ("UPDATE forge.organizations SET active=false WHERE id=%s",
                     "UPDATE forge.memberships SET status='suspended' WHERE id=%s",
                     "DELETE FROM forge.identities WHERE id=%s",
                     "DELETE FROM forge.membership_roles WHERE membership_id=%s")
        with catalog_authority_schema() as conn:
            seed_actor(conn)
            for query, key in zip(mutations, (ORG_A, MEMBER_A, ALICE, MEMBER_A)):
                with self.subTest(query=query), connect() as revoker, ThreadPoolExecutor(1) as pool:
                    def revoke():
                        with revoker.transaction(force_rollback=True):
                            return revoker.execute(query, (key,)).rowcount
                    with conn.transaction():
                        publisher(conn)
                        self.assertEqual(authorize(conn), 1)
                        future = pool.submit(revoke)
                        self.wait_blocked(conn, revoker.info.backend_pid, conn.info.backend_pid)
                        self.assertFalse(future.done())
                    if "identities" in query:
                        # Direct delete first blocks, then the existing membership FK denies it.
                        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                            future.result(timeout=3)
                    else:
                        self.assertEqual(future.result(timeout=3), 1)

    def test_preceding_revocation_is_reloaded_after_real_wait(self):
        for kind in ("organization", "membership", "identity", "grant"):
            self.db.reset()
            with self.subTest(kind=kind), catalog_authority_schema() as conn:
                seed_actor(conn)
                with connect() as requester, ThreadPoolExecutor(1) as pool:
                    def request():
                        with requester.transaction():
                            publisher(requester)
                            return authorize(requester)
                    with conn.transaction():
                        if kind == "organization":
                            conn.execute("UPDATE forge.organizations SET active=false WHERE id=%s", (ORG_A,))
                        elif kind == "membership":
                            conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
                        elif kind == "grant":
                            conn.execute("DELETE FROM forge.membership_roles WHERE membership_id=%s", (MEMBER_A,))
                        else:
                            conn.execute("DELETE FROM forge.membership_roles WHERE membership_id=%s", (MEMBER_A,))
                            conn.execute("DELETE FROM forge.memberships WHERE id=%s", (MEMBER_A,))
                            conn.execute("DELETE FROM forge.identities WHERE id=%s", (ALICE,))
                        future = pool.submit(request)
                        self.wait_blocked(conn, requester.info.backend_pid, conn.info.backend_pid)
                    self.assertIsNone(future.result(timeout=3))

    def test_lock_order_holds_each_predecessor_before_waiting_on_next(self):
        targets = (("organizations", "id", ORG_A), ("memberships", "id", MEMBER_A),
                   ("identities", "id", ALICE), ("membership_roles", "membership_id", MEMBER_A))
        with catalog_authority_schema() as conn:
            seed_actor(conn)
            for index in (1, 2, 3):
                table, column, key = targets[index]
                with self.subTest(waiting_on=table), connect() as requester, ThreadPoolExecutor(1) as pool:
                    def request():
                        with requester.transaction():
                            publisher(requester)
                            return authorize(requester)
                    with conn.transaction():
                        conn.execute("SELECT 1 FROM forge." + table + " WHERE " + column + "=%s FOR UPDATE", (key,))
                        future = pool.submit(request)
                        self.wait_blocked(conn, requester.info.backend_pid, conn.info.backend_pid)
                        for prior_table, prior_column, prior_key in targets[:index]:
                            with self.assertRaises(psycopg.errors.LockNotAvailable), conn.transaction():
                                conn.execute("SELECT 1 FROM forge." + prior_table + " WHERE " +
                                             prior_column + "=%s FOR UPDATE NOWAIT", (prior_key,))
                    self.assertEqual(future.result(timeout=3), 1)

    def test_populated_upgrade_rollback_and_old_readiness(self):
        for failure in (True, False):
            self.db.reset()
            with connect() as initial:
                seed_outbox_migration_legacy(initial)
            captured = {}
            def prepare(conn):
                event(conn, event_id=UUID(int=977), binding=MEMBER_A, kind="membership.updated")
                seed_publication(conn)
                captured["legacy"] = legacy_state(conn)
                for table in ("model_catalog_snapshots", "active_model_catalogs"):
                    captured[table] = conn.execute("SELECT * FROM forge." + table).fetchall()
                    self.assertTrue(captured[table])
                self.assertTrue(captured["legacy"][0]["outbox_events"])
            with self.db.pool() as pool:
                self.assertTrue(PostgresReadinessProbe(pool).check())
                with catalog_authority_schema(fail_migration=failure, before_migration=prepare) as conn:
                    self.assertFalse(PostgresReadinessProbe(pool).check())
                    after = legacy_state(conn)
                    self.assertEqual(after[0], captured["legacy"][0])
                    retained = [p for p in after[1] if not p[0].startswith("catalog_authority_")]
                    self.assertEqual(retained, captured["legacy"][1])
                    for table in ("model_catalog_snapshots", "active_model_catalogs"):
                        self.assertEqual(conn.execute("SELECT * FROM forge." + table).fetchall(), captured[table])
                    self.assertEqual(conn.execute("SELECT to_regclass(%s) IS NOT NULL", (TABLE,)).fetchone()[0], not failure)
                    self.assertEqual(conn.execute("SELECT to_regprocedure(%s) IS NOT NULL", (FUNCTION,)).fetchone()[0], not failure)
                    self.assertEqual(conn.execute("SELECT count(*) FROM pg_roles "
                        "WHERE rolname='forge_catalog_authority'").fetchone()[0], 0 if failure else 1)
                self.assertTrue(PostgresReadinessProbe(pool).check())

    def test_caller_rollback_leaves_no_ledger_pointer_or_publication(self):
        with catalog_authority_schema() as conn:
            with self.assertRaisesRegex(RuntimeError, "fixture rollback"), conn.transaction():
                checksum = seed_publication(conn)
                publisher(conn)
                ledger(conn, checksum)
                raise RuntimeError("fixture rollback")
            for table in (TABLE, "forge.active_model_catalogs", "forge.outbox_events"):
                self.assertEqual(conn.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)
