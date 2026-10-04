"""Reader proof on an owned PostgreSQL server and actual size-one pool."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import time
import unittest
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import psycopg
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from forge.api import BootstrapRecords
from forge.foundation import AuthenticatedIdentity, MembershipStatus
from forge.postgres import PostgresBootstrapReader
from postgres_support import (
    KEYS, MEMBER_A, ORG_A, ORG_B, TABLES, DatabaseFixture, ProbeConnection,
    connect, rows, set_context,
)

ALICE = AuthenticatedIdentity('test', 'issuer', 'alice')
BOB = AuthenticatedIdentity('test', 'issuer', 'bob')


class DirtyPool(ConnectionPool):
    @contextmanager
    def connection(self, timeout=None):
        with super().connection(timeout=timeout) as conn:
            conn.execute('BEGIN')
            set_context(conn)
            yield conn


class PostgresReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()
        self.pool = self.db.pool(connection_class=ProbeConnection)
        self.addCleanup(self.pool.close, timeout=5)
        self.reader = PostgresBootstrapReader(self.pool, acquisition_timeout=0.2)

    def assert_clean(self, expected_pid=None):
        with self.pool.connection() as conn:
            self.assertEqual(conn.info.transaction_status, psycopg.pq.TransactionStatus.IDLE)
            if expected_pid is not None:
                self.assertEqual(conn.info.backend_pid, expected_pid)
            for key in KEYS:
                self.assertIn(conn.execute('SELECT current_setting(%s,true)',
                    ('forge.' + key,)).fetchone()[0], (None, ''))
            for table in TABLES:
                self.assertEqual(rows(conn, table), [])
            return conn.info.backend_pid

    def test_unbound_entra_identity_cannot_bootstrap(self):
        tenant, oid = str(UUID(int=101)), str(UUID(int=102))
        issuer = 'https://login.microsoftonline.com/' + tenant + '/v2.0'
        with connect() as conn:
            conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',
                         ('entra', issuer, oid, UUID(int=11)))
        self.assertIsNone(self.reader.read(AuthenticatedIdentity('entra', issuer, oid), str(ORG_A)))
        self.assert_clean()

    def test_column_only_mutation_grants_reject_runtime(self):
        for privilege, columns in (('UPDATE', 'subject'), ('INSERT', 'subject'),
                                  ('REFERENCES', 'subject'),
                                  ('REFERENCES', 'entra_tenant_id,entra_object_id')):
            with self.subTest(privilege=privilege, columns=columns), connect() as conn:
                conn.execute('GRANT ' + privilege + '(' + columns + ') ON forge.identities TO forge_runtime')
                try:
                    self.assertFalse(conn.execute(
                        "SELECT has_table_privilege('forge_runtime','forge.identities',%s)",
                        (privilege,)).fetchone()[0])
                    with self.assertRaisesRegex(RuntimeError, 'runtime role'):
                        self.reader.read(ALICE, str(ORG_A))
                finally:
                    conn.execute('REVOKE ' + privilege + '(' + columns + ') ON forge.identities FROM forge_runtime')
        self.assert_clean()

    def test_pair_column_mutations_are_detected_without_table_grants(self):
        for privilege in ('UPDATE', 'INSERT', 'REFERENCES'):
            with self.subTest(privilege=privilege), connect() as conn:
                clause = privilege + '(entra_tenant_id,entra_object_id)'
                conn.execute('GRANT ' + clause + ' ON forge.identities TO forge_runtime')
                try:
                    self.assertFalse(conn.execute(
                        "SELECT has_table_privilege('forge_runtime','forge.identities',%s)",
                        (privilege,)).fetchone()[0])
                    with self.assertRaisesRegex(RuntimeError, 'runtime role'):
                        self.reader.read(ALICE, str(ORG_A))
                finally:
                    conn.execute('REVOKE ' + clause + ' ON forge.identities FROM forge_runtime')
        self.assert_clean()

    def test_bound_entra_identity_retains_membership_and_revocation_checks(self):
        from forge.entra import VerifiedPrincipal
        from forge.identity_store import PostgresIdentityBinder
        tid, oid = str(UUID(int=101)), str(UUID(int=102))
        principal = VerifiedPrincipal('guest-or-client-sub', tid, oid,
            'https://login.microsoftonline.com/' + tid + '/v2.0')
        with connect() as conn:
            conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',
                         ('entra', principal.issuer, oid, UUID(int=11)))
        self.assertIsNone(self.reader.read(principal.identity, str(ORG_A)))
        binder_pool = self.db.pool(user='forge_identity_binder')
        self.addCleanup(binder_pool.close, timeout=5)
        self.assertIsNotNone(PostgresIdentityBinder(binder_pool).bind_existing(UUID(int=11), principal))
        data = self.reader.read(principal.identity, str(ORG_A))
        self.assertEqual(data.membership.id, str(MEMBER_A))
        self.assertIsNone(self.reader.read(principal.identity, str(ORG_B)))
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
        self.assertIs(self.reader.read(principal.identity, str(ORG_A)).membership.status,
                      MembershipStatus.SUSPENDED)
        with connect() as conn:
            conn.execute('DELETE FROM forge.memberships WHERE id=%s', (MEMBER_A,))
        self.assertIsNone(self.reader.read(principal.identity, str(ORG_A)))
        self.assert_clean()

    def test_maps_existing_immutable_records_and_exact_selected_revision(self):
        data = self.reader.read(ALICE, str(ORG_A))
        self.assertIsInstance(data, BootstrapRecords)
        self.assertEqual(data.membership.id, str(MEMBER_A))
        self.assertEqual(data.membership.organization_id, str(ORG_A))
        self.assertEqual(data.membership.identity, ALICE)
        self.assertIs(data.membership.status, MembershipStatus.ACTIVE)
        self.assertEqual(data.organization.id, str(ORG_A))
        self.assertEqual(data.organization.slug, 'org-a')
        self.assertEqual(data.organization.display_name, 'ORG-A')
        self.assertIs(data.organization.active, True)
        self.assertEqual(data.configuration.organization_id, str(ORG_A))
        self.assertEqual(data.configuration.revision, 1)
        self.assertEqual(dict(data.configuration.internal_settings), {})
        with self.assertRaises(FrozenInstanceError):
            data.membership.id = 'changed'
        with self.pool.connection() as conn:
            self.assertEqual(conn.observed_context, (str(ORG_A), 'test', 'issuer', 'alice'))
        self.assertFalse(self.pool.closed)

    def test_same_physical_backend_for_a_b_absence_and_no_residual_context(self):
        pid = self.assert_clean()
        for identity, org, expected in ((ALICE, ORG_A, 1), (BOB, ORG_B, 2)):
            data = self.reader.read(identity, str(org))
            self.assertEqual(data.configuration.revision, expected)
            self.assert_clean(pid)
        self.assertIsNone(self.reader.read(ALICE, str(ORG_B)))
        self.assert_clean(pid)

    def test_identity_triple_and_parameterized_hostile_values_deny(self):
        for identity in (AuthenticatedIdentity('wrong', 'issuer', 'alice'),
                         AuthenticatedIdentity('test', 'wrong', 'alice'),
                         AuthenticatedIdentity('test', 'issuer', 'wrong'),
                         AuthenticatedIdentity('test', 'issuer', "alice' OR true --")):
            with self.subTest(identity=identity):
                self.assertIsNone(self.reader.read(identity, str(ORG_A)))
        self.assertEqual(self.reader.read(ALICE, str(ORG_A)).membership.identity, ALICE)

    def test_crossed_org_foreign_suspension_archived_and_missing_deny(self):
        for identity, org in ((ALICE, ORG_B), (BOB, ORG_A),
            (AuthenticatedIdentity('test', 'issuer', 'suspended'), ORG_B),
            (AuthenticatedIdentity('test', 'issuer', 'archived'), ORG_A),
            (ALICE, UUID(int=999))):
            with self.subTest(identity=identity, org=org):
                self.assertIsNone(self.reader.read(identity, str(org)))
        with connect() as conn:
            conn.execute('DELETE FROM forge.memberships WHERE organization_id=%s AND id=%s',
                         (ORG_A, MEMBER_A))
        self.assertIsNone(self.reader.read(ALICE, str(ORG_A)))

    def test_owned_suspended_and_inactive_are_returned_for_transport_policy(self):
        identity = AuthenticatedIdentity('test', 'issuer', 'suspended')
        self.assertIs(self.reader.read(identity, str(ORG_A)).membership.status,
                      MembershipStatus.SUSPENDED)
        with connect() as conn:
            conn.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (ORG_A,))
        self.assertIs(self.reader.read(ALICE, str(ORG_A)).organization.active, False)

    def test_live_membership_revocation_and_selected_configuration(self):
        self.assertEqual(self.reader.read(ALICE, str(ORG_A)).configuration.revision, 1)
        with connect() as conn, conn.transaction():
            conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,3)', (ORG_A,))
            conn.execute('UPDATE forge.organizations SET selected_config_revision=3 WHERE id=%s',
                         (ORG_A,))
        self.assertEqual(self.reader.read(ALICE, str(ORG_A)).configuration.revision, 3)
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s", (MEMBER_A,))
        self.assertIs(self.reader.read(ALICE, str(ORG_A)).membership.status,
                      MembershipStatus.SUSPENDED)
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='archived' WHERE id=%s", (MEMBER_A,))
        self.assertIsNone(self.reader.read(ALICE, str(ORG_A)))

    def test_real_sql_error_rolls_back_context_and_reuses_same_backend(self):
        pid = self.assert_clean()
        with self.pool.connection() as conn:
            conn.fail_data = 'sql'
        with self.assertRaises(psycopg.errors.DivisionByZero):
            self.reader.read(ALICE, str(ORG_A))
        self.assert_clean(pid)
        self.assertEqual(self.reader.read(BOB, str(ORG_B)).configuration.revision, 2)
        self.assert_clean(pid)

    def test_rejects_admin_connection_and_elevated_runtime_role(self):
        admin = self.db.pool(user='postgres')
        self.addCleanup(admin.close, timeout=5)
        with self.assertRaisesRegex(RuntimeError, 'runtime role'):
            PostgresBootstrapReader(admin).read(ALICE, str(ORG_A))
        for attribute in ('SUPERUSER', 'BYPASSRLS'):
            with self.subTest(attribute=attribute):
                with connect() as conn:
                    conn.execute('ALTER ROLE forge_runtime ' + attribute)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'runtime role'):
                        self.reader.read(ALICE, str(ORG_A))
                finally:
                    with connect() as conn:
                        conn.execute('ALTER ROLE forge_runtime NO' + attribute)
                self.assert_clean()

    def test_rejects_table_owner_and_inherited_role(self):
        with connect() as conn:
            conn.execute('ALTER TABLE forge.identities OWNER TO forge_runtime')
        try:
            with self.assertRaisesRegex(RuntimeError, 'runtime role'):
                self.reader.read(ALICE, str(ORG_A))
        finally:
            with connect() as conn:
                conn.execute('ALTER TABLE forge.identities OWNER TO forge_migrator')
                # Changing ownership removes the temporary owner's old ACL entry.
                conn.execute('GRANT SELECT ON forge.identities TO forge_runtime, forge_test_writer')
        with connect() as conn:
            conn.execute('GRANT forge_migrator TO forge_runtime')
        try:
            with self.assertRaisesRegex(RuntimeError, 'runtime role'):
                self.reader.read(ALICE, str(ORG_A))
        finally:
            with connect() as conn:
                conn.execute('REVOKE forge_migrator FROM forge_runtime')

    def test_dirty_transaction_and_non_autocommit_are_rejected(self):
        for pool in (self.db.pool(pool_class=DirtyPool), self.db.pool(autocommit=False)):
            self.addCleanup(pool.close, timeout=5)
            with self.assertRaisesRegex(RuntimeError, 'idle autocommit'):
                PostgresBootstrapReader(pool).read(ALICE, str(ORG_A))
        self.assert_clean()

    def test_invalid_identity_and_org_fail_closed_before_borrowing(self):
        self.pool.close(timeout=5)
        for identity, org in ((None, str(ORG_A)),
            (AuthenticatedIdentity('', 'issuer', 'alice'), str(ORG_A)),
            (AuthenticatedIdentity('test', ' ', 'alice'), str(ORG_A)),
            (AuthenticatedIdentity('test', 'issuer', ''), str(ORG_A)),
            (AuthenticatedIdentity('test', 'issuer', 42), str(ORG_A)),
            (ALICE, 'malformed'), (ALICE, None)):
            with self.subTest(identity=identity, org=org):
                self.assertIsNone(self.reader.read(identity, org))

    def test_closed_and_exhausted_pool_fail_bounded_without_silent_reopen(self):
        with self.pool.connection():
            start = time.monotonic()
            with self.assertRaises(PoolTimeout):
                self.reader.read(ALICE, str(ORG_A))
            self.assertLess(time.monotonic() - start, 2)
        self.pool.close(timeout=5)
        with self.assertRaises(PoolClosed):
            self.reader.read(ALICE, str(ORG_A))
        self.assertTrue(self.pool.closed)

    def test_timeout_configuration_requires_finite_positive_bound(self):
        for timeout in (0, -1, float('inf'), float('nan'), True, 'forever', 31):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                PostgresBootstrapReader(self.pool, acquisition_timeout=timeout)

    def test_simultaneous_reads_serialize_without_cross_tenant_rows(self):
        pid = self.assert_clean()
        requests = [(ALICE, ORG_A), (BOB, ORG_B)] * 6
        def read(pair):
            identity, org = pair
            data = self.reader.read(identity, str(org))
            return data.organization.id, data.membership.identity
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(list(workers.map(read, requests)),
                             [(str(org), identity) for identity, org in requests])
        self.assert_clean(pid)


if __name__ == '__main__':
    unittest.main()
