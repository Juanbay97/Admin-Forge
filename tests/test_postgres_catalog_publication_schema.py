"""Real owned PostgreSQL storage security, not publisher authorization."""
from dataclasses import replace
from uuid import UUID
import unittest

import psycopg

from postgres_support import (
    DatabaseFixture, ORG_A, ORG_B, connect, catalog_publication_schema,
    seed_outbox_migration_legacy,
)
from test_postgres_model_catalog import snapshot, legacy_state
from test_model_catalog import BINDING, OTHER
from forge.model_catalog_store import insert_catalog
from forge.postgres import PostgresReadinessProbe


def scope(conn, role="forge_config_publisher", org=ORG_A):
    conn.execute("SET LOCAL SESSION AUTHORIZATION " + role)
    conn.execute("SELECT set_config('forge.organization',%s,true)", ("" if org is None else str(org),))


def event(conn, *, event_id=UUID(int=901), org=ORG_A, binding=BINDING,
          revision=1, kind="model_catalog.published"):
    conn.execute(
        "INSERT INTO forge.outbox_events "
        "(event_id,organization_id,actor_id,request_id,resource_id,event_type,previous_revision,revision) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (event_id, org, UUID(int=902), UUID(int=903), binding, kind, revision-1, revision),
    )


def pointer(conn, *, org=ORG_A, binding=BINDING, revision=1, event_id=UUID(int=901)):
    conn.execute("INSERT INTO forge.active_model_catalogs "
                 "(organization_id,router_binding_id,catalog_revision,event_id) VALUES(%s,%s,%s,%s)",
                 (org, binding, revision, event_id))


class CatalogPublicationSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    def test_publisher_is_independent_restricted_nonowner_role(self):
        with catalog_publication_schema() as conn:
            role = conn.execute("SELECT oid,rolcanlogin,rolinherit,rolsuper,rolbypassrls,"
                                "rolcreatedb,rolcreaterole,rolreplication FROM pg_roles "
                                "WHERE rolname='forge_config_publisher'").fetchone()
            self.assertEqual(role[1:], (False,) * 7)
            self.assertEqual(conn.execute(
                "SELECT relrowsecurity,relforcerowsecurity,pg_get_userbyid(relowner) "
                "FROM pg_class WHERE oid='forge.active_model_catalogs'::regclass").fetchone(),
                (True, True, "forge_migrator"))
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_auth_members "
                                          "WHERE roleid=%s OR member=%s", (role[0], role[0])).fetchone()[0], 0)
            for relation, owner_column in (("pg_class", "relowner"), ("pg_proc", "proowner"),
                                            ("pg_namespace", "nspowner")):
                self.assertEqual(conn.execute("SELECT count(*) FROM " + relation +
                                              " WHERE " + owner_column + "=%s", (role[0],)).fetchone()[0], 0)
            for target in ("forge_runtime", "forge_designator", "forge_catalog_writer",
                           "forge_outbox_writer", "forge_migrator"):
                with self.subTest(target=target), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    scope(conn)
                    conn.execute("SET ROLE " + target)

    def test_minimal_privileges_for_every_table_and_no_ddl(self):
        allowed = {"model_catalog_snapshots": {"SELECT"},
                   "active_model_catalogs": {"SELECT", "INSERT", "UPDATE"},
                   "outbox_events": {"INSERT"}}
        with catalog_publication_schema() as conn:
            for table, in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='forge'"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                    with self.subTest(table=table, privilege=privilege):
                        self.assertEqual(conn.execute("SELECT has_table_privilege('forge_config_publisher',%s,%s)",
                                                      ("forge." + table, privilege)).fetchone()[0],
                                         privilege in allowed.get(table, set()))
            self.assertEqual(conn.execute(
                "SELECT has_database_privilege('forge_config_publisher',current_database(),'CREATE,TEMP'),"
                "has_schema_privilege('forge_config_publisher','forge','CREATE'),"
                "has_schema_privilege('forge_config_publisher','public','CREATE')").fetchone(),
                (False, False, False))

    def test_real_correlated_pointer_and_event_transaction(self):
        with catalog_publication_schema() as conn:
            with conn.transaction():
                insert_catalog(conn, snapshot())
            with conn.transaction():
                scope(conn)
                self.assertEqual(conn.execute("SELECT revision FROM forge.model_catalog_snapshots").fetchall(), [(1,)])
                event(conn)
                pointer(conn)
                self.assertEqual(conn.execute("SELECT organization_id,catalog_revision FROM forge.active_model_catalogs")
                                 .fetchall(), [(ORG_A, 1)])
            self.assertEqual(conn.execute("SELECT count(*) FROM forge.outbox_events").fetchone()[0], 1)

    def test_missing_or_foreign_context_denies_writes_and_hides_reads(self):
        with catalog_publication_schema() as conn:
            with conn.transaction():
                insert_catalog(conn, snapshot())
                event(conn)
                pointer(conn)
            for org in (None, ORG_B):
                with self.subTest(org=org), conn.transaction():
                    scope(conn, org=org)
                    self.assertEqual(conn.execute("SELECT * FROM forge.model_catalog_snapshots").fetchall(), [])
                    self.assertEqual(conn.execute("SELECT * FROM forge.active_model_catalogs").fetchall(), [])
                    self.assertEqual(conn.execute("UPDATE forge.active_model_catalogs SET catalog_revision=2").rowcount, 0)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    scope(conn, org=org)
                    event(conn, event_id=UUID(int=904), revision=2)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    scope(conn, org=org)
                    pointer(conn)

    def test_pointer_rejects_mismatched_org_binding_snapshot_and_event(self):
        with catalog_publication_schema() as conn:
            with conn.transaction():
                insert_catalog(conn, snapshot())
                event(conn)
            for values in ({"org": ORG_B}, {"binding": OTHER}, {"revision": 2},
                           {"event_id": UUID(int=999)}):
                with self.subTest(values=values), self.assertRaises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                    pointer(conn, **values)
            with conn.transaction():
                insert_catalog(conn, replace(snapshot(), revision=2))
                event(conn, event_id=UUID(int=905), revision=2, kind="membership.updated")
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                pointer(conn, revision=2, event_id=UUID(int=905))

    def test_pointer_update_requires_matching_snapshot_event_and_scope(self):
        with catalog_publication_schema() as conn:
            with conn.transaction():
                insert_catalog(conn, snapshot())
                insert_catalog(conn, replace(snapshot(), revision=2))
                event(conn)
                pointer(conn)
            with conn.transaction():
                scope(conn)
                event(conn, event_id=UUID(int=906), revision=2)
                self.assertEqual(conn.execute(
                    "UPDATE forge.active_model_catalogs SET catalog_revision=2,event_id=%s "
                    "WHERE organization_id=%s", (UUID(int=906), ORG_A)).rowcount, 1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                scope(conn)
                conn.execute("UPDATE forge.active_model_catalogs SET organization_id=%s", (ORG_B,))
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                scope(conn)
                conn.execute("UPDATE forge.active_model_catalogs SET event_id=%s", (UUID(int=901),))
            self.assertEqual(conn.execute("SELECT catalog_revision,event_id FROM forge.active_model_catalogs")
                             .fetchall(), [(2, UUID(int=906))])

    def test_existing_writer_and_publisher_event_types_are_separate(self):
        with catalog_publication_schema() as conn:
            for role, kind in (("forge_outbox_writer", "model_catalog.published"),
                               ("forge_config_publisher", "membership.updated"),
                               ("forge_config_publisher", "department.created")):
                with self.subTest(role=role, kind=kind), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    scope(conn, role)
                    event(conn, kind=kind)
            with conn.transaction():
                scope(conn, "forge_outbox_writer")
                event(conn, kind="membership.updated")
            with conn.transaction():
                scope(conn)
                event(conn, event_id=UUID(int=904), revision=2)

    def test_other_roles_never_read_or_write_private_pointer(self):
        with catalog_publication_schema() as conn:
            for role in ("forge_runtime", "forge_designator", "forge_identity_binder",
                         "forge_outbox_writer", "forge_catalog_writer"):
                for query in ("SELECT * FROM forge.active_model_catalogs",
                              "DELETE FROM forge.active_model_catalogs"):
                    with self.subTest(role=role, query=query), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                        scope(conn, role)
                        conn.execute(query)

    def test_publisher_cannot_mutate_snapshots_or_delete_pointer(self):
        with catalog_publication_schema() as conn:
            for query in ("UPDATE forge.model_catalog_snapshots SET revision=2",
                          "DELETE FROM forge.model_catalog_snapshots",
                          "TRUNCATE forge.active_model_catalogs",
                          "DELETE FROM forge.active_model_catalogs"):
                with self.subTest(query=query), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    scope(conn)
                    conn.execute(query)

    def test_failed_transaction_leaves_no_pointer_or_event(self):
        with catalog_publication_schema() as conn:
            with conn.transaction():
                insert_catalog(conn, snapshot())
            with self.assertRaisesRegex(RuntimeError, "fixture rollback"), conn.transaction():
                scope(conn)
                event(conn)
                pointer(conn)
                raise RuntimeError("fixture rollback")
            for table in ("active_model_catalogs", "outbox_events"):
                self.assertEqual(conn.execute("SELECT count(*) FROM forge." + table).fetchone()[0], 0)

    def test_old_readiness_stays_exact_and_new_schema_is_inactive(self):
        from forge.postgres import _OUTBOX_SCHEMA
        with self.db.pool() as pool:
            self.assertTrue(PostgresReadinessProbe(pool).check())
            with catalog_publication_schema() as conn:
                self.assertFalse(PostgresReadinessProbe(pool).check())
                self.assertFalse(conn.execute(_OUTBOX_SCHEMA).fetchone()[0])
                for mutation in (
                    "ALTER ROLE forge_config_publisher BYPASSRLS",
                    "GRANT forge_config_publisher TO forge_runtime",
                    "ALTER TABLE forge.active_model_catalogs DISABLE ROW LEVEL SECURITY",
                    "ALTER TABLE forge.outbox_events DROP CONSTRAINT outbox_events_event_type_check",
                ):
                    with self.subTest(mutation=mutation), conn.transaction(force_rollback=True):
                        conn.execute(mutation)
                        self.assertFalse(conn.execute(_OUTBOX_SCHEMA).fetchone()[0])
            self.assertTrue(PostgresReadinessProbe(pool).check())

    def test_populated_upgrade_and_injected_rollback_preserve_records(self):
        for failure in (True, False):
            self.db.reset()
            with connect() as conn:
                seed_outbox_migration_legacy(conn)
                event(conn, kind="membership.updated")
                before = legacy_state(conn)
                for table in ("membership_roles", "initial_admin_designations",
                              "initial_admin_outbox", "outbox_events"):
                    self.assertTrue(before[0][table])
            catalog_before = []
            def prepare(conn):
                insert_catalog(conn, snapshot())
                catalog_before.extend(conn.execute("SELECT * FROM forge.model_catalog_snapshots").fetchall())
            with self.subTest(failure=failure), catalog_publication_schema(
                    fail_migration=failure, before_migration=prepare) as conn:
                self.assertTrue(catalog_before)
                self.assertEqual(conn.execute("SELECT * FROM forge.model_catalog_snapshots").fetchall(), catalog_before)
                after = legacy_state(conn)
                self.assertEqual(after[0], before[0])
                # Exactly the existing outbox writer policy changes on success.
                retained = lambda policies: [p for p in policies if p[0] not in ("outbox_record", "catalog_event")]
                self.assertEqual(retained(after[1]), retained(before[1]))
                if failure:
                    self.assertEqual(after[1], before[1])
                self.assertEqual(conn.execute("SELECT to_regclass('forge.active_model_catalogs') IS NOT NULL")
                                 .fetchone()[0], not failure)
                self.assertEqual(conn.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_config_publisher'")
                                 .fetchone()[0], 0 if failure else 1)
            with connect() as conn:
                self.assertEqual(legacy_state(conn), before)
                self.assertIsNone(conn.execute("SELECT to_regclass('forge.active_model_catalogs')").fetchone()[0])
