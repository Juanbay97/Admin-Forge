"""Opt-in0010 proof inside the exact owned PostgreSQL harness only."""
from dataclasses import replace
import hashlib
import json
import unittest

import psycopg

from postgres_support import (
    DatabaseFixture, connect, catalog_schema, seed_outbox_migration_legacy,
)
from test_model_catalog import catalog, ORG, BINDING, OTHER
from forge.model_catalog_store import (
    CatalogStorageError, encode_catalog, insert_catalog, read_catalog,
)

# Use the actual seeded organization; domain fixtures are otherwise synthetic.
from postgres_support import ORG_A, ORG_B


def snapshot():
    value = catalog()
    route = replace(value.aliases[0].routes[0], organization_id=ORG_A)
    alias = replace(value.aliases[0], routes=(route,))
    return replace(value, organization_id=ORG_A, aliases=(alias,))


def writer(conn, organization=ORG_A):
    conn.execute("SET LOCAL ROLE forge_catalog_writer")
    conn.execute("SELECT set_config('forge.organization',%s,true)", (str(organization),))


def legacy_state(conn):
    tables = ("identities", "organizations", "memberships", "configuration_revisions",
              "membership_roles", "initial_admin_designations", "initial_admin_outbox", "outbox_events")
    records = {table: sorted(conn.execute("SELECT * FROM forge." + table).fetchall(), key=repr)
               for table in tables}
    policies = conn.execute(
        "SELECT polname,polrelid,polroles,polqual::text,polwithcheck::text "
        "FROM pg_policy WHERE polrelid IN "
        "(SELECT oid FROM pg_class WHERE relname=ANY(%s)) ORDER BY polrelid,polname",
        (list(tables),),
    ).fetchall()
    return records, policies


class PostgresCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    def test_real_roundtrip_hash_and_no_publication(self):
        value = snapshot()
        with catalog_schema() as conn:
            before = conn.execute("SELECT selected_config_revision FROM forge.organizations "
                                  "WHERE id=%s", (ORG_A,)).fetchone()
            with conn.transaction():
                writer(conn)
                insert_catalog(conn, value)
                self.assertEqual(read_catalog(conn, ORG_A, BINDING, 1), value)
            payload, checksum = conn.execute(
                "SELECT payload,payload_sha256 FROM forge.model_catalog_snapshots").fetchone()
            self.assertEqual((payload, checksum), encode_catalog(value))
            self.assertEqual(conn.execute("SELECT selected_config_revision FROM forge.organizations "
                                          "WHERE id=%s", (ORG_A,)).fetchone(), before)
            self.assertEqual(conn.execute("SELECT count(*) FROM forge.outbox_events").fetchone()[0], 0)

    def test_duplicates_never_overwrite_and_caller_failure_rolls_back(self):
        with catalog_schema() as conn:
            with conn.transaction():
                writer(conn)
                insert_catalog(conn, snapshot())
            with self.assertRaises(CatalogStorageError), conn.transaction():
                writer(conn)
                insert_catalog(conn, snapshot())
            with self.assertRaisesRegex(RuntimeError, "caller rollback"), conn.transaction():
                writer(conn)
                insert_catalog(conn, replace(snapshot(), revision=2))
                raise RuntimeError("caller rollback")
            self.assertEqual(conn.execute("SELECT revision FROM forge.model_catalog_snapshots").fetchall(), [(1,)])

    def test_writer_cannot_update_delete_truncate_or_change_role(self):
        with catalog_schema() as conn:
            with conn.transaction():
                writer(conn)
                insert_catalog(conn, snapshot())
            for statement in ("UPDATE forge.model_catalog_snapshots SET revision=2",
                              "DELETE FROM forge.model_catalog_snapshots",
                              "TRUNCATE forge.model_catalog_snapshots", "SET ROLE forge_migrator"):
                with self.subTest(statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute("SET LOCAL SESSION AUTHORIZATION forge_catalog_writer")
                    conn.execute(statement)

    def test_cross_org_and_missing_context_fail_closed(self):
        with catalog_schema() as conn:
            with conn.transaction():
                writer(conn)
                insert_catalog(conn, snapshot())
            with conn.transaction():
                writer(conn, ORG_B)
                self.assertIsNone(read_catalog(conn, ORG_A, BINDING, 1))
            for organization in (None, ORG_B):
                with self.subTest(organization=organization), self.assertRaises(CatalogStorageError), conn.transaction():
                    conn.execute("SET LOCAL ROLE forge_catalog_writer")
                    if organization:
                        conn.execute("SELECT set_config('forge.organization',%s,true)", (str(organization),))
                    insert_catalog(conn, replace(snapshot(), revision=2))

    def test_runtime_designator_and_other_existing_roles_have_no_access(self):
        with catalog_schema() as conn:
            for role in ("forge_runtime", "forge_designator", "forge_identity_binder", "forge_outbox_writer"):
                with self.subTest(role=role), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    conn.execute("SET LOCAL SESSION AUTHORIZATION " + role)
                    conn.execute("SELECT * FROM forge.model_catalog_snapshots")

    def test_sql_rejects_row_binding_org_revision_and_checksum_mismatch(self):
        payload, checksum = encode_catalog(snapshot())
        with catalog_schema() as conn:
            for org, binding, revision, digest in (
                (ORG_B, BINDING, 1, checksum), (ORG_A, OTHER, 1, checksum),
                (ORG_A, BINDING, 2, checksum), (ORG_A, BINDING, 1, "0" * 64),
            ):
                with self.subTest(org=org, binding=binding, revision=revision), self.assertRaises(psycopg.IntegrityError), conn.transaction():
                    conn.execute("INSERT INTO forge.model_catalog_snapshots "
                                 "(organization_id,router_binding_id,revision,payload,payload_sha256) VALUES(%s,%s,%s,%s,%s)",
                                 (org, binding, revision, payload, digest))

    def test_privileged_malformed_payload_is_rejected_on_read(self):
        payload, _ = encode_catalog(snapshot())
        data = json.loads(payload)
        data["aliases"][0]["routes"][0]["capabilities"]["tools"] = None
        malformed = json.dumps(data, sort_keys=True, separators=(",", ":"))
        checksum = hashlib.sha256(malformed.encode()).hexdigest()
        with catalog_schema() as conn:
            conn.execute("INSERT INTO forge.model_catalog_snapshots "
                         "(organization_id,router_binding_id,revision,payload,payload_sha256) VALUES(%s,%s,1,%s,%s)",
                         (ORG_A, BINDING, malformed, checksum))
            with self.assertRaisesRegex(CatalogStorageError, "^Catalog storage unavailable$"), conn.transaction():
                writer(conn)
                read_catalog(conn, ORG_A, BINDING, 1)

    def test_explicit_transaction_required_and_absent_binding_not_substituted(self):
        with catalog_schema() as conn:
            with self.assertRaises(CatalogStorageError):
                insert_catalog(conn, snapshot())
            with self.assertRaises(CatalogStorageError):
                read_catalog(conn, ORG_A, BINDING, 1)
            with conn.transaction():
                writer(conn)
                insert_catalog(conn, snapshot())
                self.assertIsNone(read_catalog(conn, ORG_A, OTHER, 1))

    def test_populated_upgrade_and_injected_rollback_preserve_legacy(self):
        for failure in (True, False):
            self.db.reset()
            with connect() as conn:
                seed_outbox_migration_legacy(conn)
                before = legacy_state(conn)
                for table in ("membership_roles", "initial_admin_designations", "initial_admin_outbox"):
                    self.assertTrue(before[0][table])
            with self.subTest(failure=failure), catalog_schema(fail_migration=failure) as conn:
                self.assertEqual(legacy_state(conn), before)
                present = conn.execute("SELECT to_regclass('forge.model_catalog_snapshots') IS NOT NULL").fetchone()[0]
                self.assertEqual(present, not failure)
                self.assertEqual(conn.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_catalog_writer'").fetchone()[0],
                                 0 if failure else 1)
                if present:
                    self.assertEqual(conn.execute("SELECT count(*) FROM forge.model_catalog_snapshots").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                                                  "WHERE oid='forge.model_catalog_snapshots'::regclass").fetchone(), (True, True))
            with connect() as conn:
                self.assertIsNone(conn.execute("SELECT to_regclass('forge.model_catalog_snapshots')").fetchone()[0])
                self.assertEqual(conn.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_catalog_writer'").fetchone()[0], 0)

