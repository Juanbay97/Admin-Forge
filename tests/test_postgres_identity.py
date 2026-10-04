"""Existing-identity binding proof on genuine owned PostgreSQL, never live Entra."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import time
import unittest
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import psycopg
from psycopg import sql
from psycopg_pool import ConnectionPool

from forge.entra import VerifiedPrincipal
from forge.identity_store import (
    IdentityBinding, IdentityBindingUnavailable, PostgresIdentityBinder,
)
from forge.postgres import PostgresBootstrapReader
from postgres_support import ALICE, BOB, CAROL, MEMBER_A, ORG_A, ORG_B, TABLES, DatabaseFixture, connect

TID, OID, OTHER_TID = UUID(int=101), UUID(int=102), UUID(int=103)
PRINCIPAL = VerifiedPrincipal('client-specific-sub', str(TID), str(OID),
    'https://login.microsoftonline.com/' + str(TID) + '/v2.0')
BINDING_KEYS = ('identity', 'issuer', 'tenant', 'object')


def binding_context(conn, identity_id=ALICE, principal=PRINCIPAL):
    for key, value in zip(BINDING_KEYS, (identity_id, principal.issuer, principal.tid, principal.oid)):
        conn.execute('SELECT set_config(%s,%s,true)', ('forge.binding_' + key, str(value)))


class DirtyBinderPool(ConnectionPool):
    @contextmanager
    def connection(self, timeout=None):
        with super().connection(timeout=timeout) as conn:
            conn.execute('BEGIN')
            binding_context(conn)
            yield conn


class FaultCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        result = super().execute(query, params, **kwargs)
        if 'UPDATE forge.identities AS i SET' in str(query):
            self.connection.update_calls += 1
            self.connection.observed_limits = (
                self.connection.execute('SHOW lock_timeout').fetchone()[0],
                self.connection.execute('SHOW statement_timeout').fetchone()[0],
            )
            if self.connection.fail_binding:
                self.connection.fail_binding = False
                # Fail after the real UPDATE: metadata and context must roll back.
                super().execute('SELECT 1 / 0')
        return result


class FaultConnection(psycopg.Connection):
    fail_binding = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_calls = 0

    def cursor(self, *args, **kwargs):
        return FaultCursor(self, **kwargs)


class PostgresIdentityBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()
        with connect() as conn:
            conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',
                         ('entra', PRINCIPAL.issuer, PRINCIPAL.oid, ALICE))
            other = replace(PRINCIPAL, tid=str(OTHER_TID),
                issuer='https://login.microsoftonline.com/' + str(OTHER_TID) + '/v2.0')
            conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,subject=%s WHERE id=%s',
                         ('entra', other.issuer, other.oid, BOB))
        self.pool = self.db.pool(user='forge_identity_binder', connection_class=FaultConnection)
        self.addCleanup(self.pool.close, timeout=5)
        self.binder = PostgresIdentityBinder(self.pool, acquisition_timeout=0.2)

    def metadata(self, identity=ALICE):
        with connect() as conn:
            return conn.execute('SELECT entra_tenant_id,entra_object_id FROM forge.identities WHERE id=%s',
                                (identity,)).fetchone()

    def assert_clean(self, pid=None):
        with self.pool.connection() as conn:
            self.assertIs(conn.info.transaction_status, psycopg.pq.TransactionStatus.IDLE)
            if pid is not None:
                self.assertEqual(conn.info.backend_pid, pid)
            for key in BINDING_KEYS:
                self.assertIn(conn.execute('SELECT current_setting(%s,true)',
                    ('forge.binding_' + key,)).fetchone()[0], (None, ''))
            self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [])
            self.assertEqual(conn.execute('SHOW lock_timeout').fetchone()[0], '0')
            self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0], '5s')
            return conn.info.backend_pid

    def assert_unavailable(self, callable):
        with self.assertRaises(IdentityBindingUnavailable) as caught:
            callable()
        self.assertEqual(str(caught.exception), 'Identity binding unavailable')
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertIsNone(caught.exception.__cause__)

    def test_exact_binding_is_immutable_and_preserves_existing_ids(self):
        pid = self.assert_clean()
        result = self.binder.bind_existing(ALICE, PRINCIPAL)
        self.assertEqual(result, IdentityBinding(ALICE))
        self.assertNotIn(str(ALICE), repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.identity_id = BOB
        self.assertEqual(self.metadata(), (TID, OID))
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT identity_id FROM forge.memberships WHERE id=%s',
                                          (MEMBER_A,)).fetchone()[0], ALICE)
        self.assert_clean(pid)
        self.assertFalse(self.pool.closed)

    def test_same_object_different_sub_is_idempotent_but_tenants_distinct(self):
        self.assertIsNotNone(self.binder.bind_existing(ALICE, PRINCIPAL))
        self.assertEqual(self.binder.bind_existing(ALICE, replace(PRINCIPAL, sub='different-sub')),
                         IdentityBinding(ALICE))
        other = replace(PRINCIPAL, tid=str(OTHER_TID),
            issuer='https://login.microsoftonline.com/' + str(OTHER_TID) + '/v2.0')
        self.assertIsNone(self.binder.bind_existing(ALICE, other))
        self.assertEqual(self.binder.bind_existing(BOB, other), IdentityBinding(BOB))
        self.assertEqual(self.metadata(BOB), (OTHER_TID, OID))
        self.assertEqual(self.metadata(), (TID, OID))

    def test_missing_uuid_generic_and_wrong_canonical_match_cannot_bind_or_create(self):
        with connect() as conn:
            before = tuple(conn.execute(sql.SQL('SELECT count(*) FROM forge.{}').format(
                sql.Identifier(table))).fetchone()[0] for table in TABLES)
        for identity, principal in ((UUID(int=999), PRINCIPAL), (CAROL, PRINCIPAL),
            (ALICE, replace(PRINCIPAL, oid=str(UUID(int=999)))),
            (ALICE, replace(PRINCIPAL, issuer='issuer')),
            (BOB, PRINCIPAL)):
            with self.subTest(identity=identity):
                self.assertIsNone(self.binder.bind_existing(identity, principal))
        self.assertEqual(self.metadata(), (None, None))
        with connect() as conn:
            self.assertEqual(before, tuple(conn.execute(sql.SQL('SELECT count(*) FROM forge.{}').format(
                sql.Identifier(table))).fetchone()[0] for table in TABLES))
        self.assert_clean()

    def test_invalid_shapes_reject_before_closed_pool_borrow(self):
        self.pool.close(timeout=5)
        principals = [None, object(), replace(PRINCIPAL, tid=42), replace(PRINCIPAL, oid=True),
            replace(PRINCIPAL, oid=PRINCIPAL.oid.replace('-', '')),
            replace(PRINCIPAL, tid='bad'), replace(PRINCIPAL, sub=' '),
            replace(PRINCIPAL, sub=42), replace(PRINCIPAL, sub='x' * 1025),
            replace(PRINCIPAL, issuer=None)]
        for principal in principals:
            with self.subTest(principal=type(principal)):
                self.assertIsNone(self.binder.bind_existing(ALICE, principal))
        for identity in (None, str(ALICE), True, 42):
            self.assertIsNone(self.binder.bind_existing(identity, PRINCIPAL))

    def test_real_post_update_error_rolls_back_and_reuses_clean_backend(self):
        pid = self.assert_clean()
        with self.pool.connection() as conn:
            conn.fail_binding = True
        self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
        self.assertEqual(self.metadata(), (None, None))
        self.assert_clean(pid)
        self.assertEqual(self.binder.bind_existing(ALICE, PRINCIPAL), IdentityBinding(ALICE))
        self.assert_clean(pid)

    def test_concurrent_same_binding_across_independent_pools_is_idempotent(self):
        second = self.db.pool(user='forge_identity_binder')
        self.addCleanup(second.close, timeout=5)
        binders = (self.binder, PostgresIdentityBinder(second))
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda n: binders[n % 2].bind_existing(
                ALICE, replace(PRINCIPAL, sub='sub-' + str(n))), range(12)))
        self.assertEqual(results, [IdentityBinding(ALICE)] * 12)
        self.assertEqual(self.metadata(), (TID, OID))
        self.assert_clean()
        with second.connection() as conn:
            for key in BINDING_KEYS:
                self.assertIn(conn.execute('SELECT current_setting(%s,true)',
                    ('forge.binding_' + key,)).fetchone()[0], (None, ''))

    def test_lock_contention_has_bounded_failure_then_recovers(self):
        with connect() as conn, conn.transaction():
            conn.execute('SELECT id FROM forge.identities WHERE id=%s FOR UPDATE', (ALICE,))
            start = time.monotonic()
            self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(self.metadata(), (None, None))
        self.assert_clean()
        self.assertIsNotNone(self.binder.bind_existing(ALICE, PRINCIPAL))

    def test_closed_and_exhausted_pools_fail_redacted_without_reopening(self):
        with self.pool.connection():
            start = time.monotonic()
            self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            self.assertLess(time.monotonic() - start, 2)
        self.pool.close(timeout=5)
        self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
        self.assertTrue(self.pool.closed)

    def test_dirty_and_non_autocommit_connections_fail_before_sql(self):
        for pool in (self.db.pool(user='forge_identity_binder', pool_class=DirtyBinderPool),
                     self.db.pool(user='forge_identity_binder', autocommit=False)):
            self.addCleanup(pool.close, timeout=5)
            self.assert_unavailable(lambda: PostgresIdentityBinder(pool).bind_existing(ALICE, PRINCIPAL))
        self.assertEqual(self.metadata(), (None, None))
        self.assert_clean()

    def test_runtime_admin_and_elevated_binder_roles_reject(self):
        for role in ('forge_runtime', 'postgres', 'forge_test_writer'):
            pool = self.db.pool(user=role)
            self.addCleanup(pool.close, timeout=5)
            self.assert_unavailable(lambda: PostgresIdentityBinder(pool).bind_existing(ALICE, PRINCIPAL))
        for attribute in ('SUPERUSER', 'BYPASSRLS', 'CREATEDB', 'CREATEROLE', 'REPLICATION'):
            with self.subTest(attribute=attribute), connect() as conn:
                conn.execute('ALTER ROLE forge_identity_binder ' + attribute)
                try:
                    self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
                finally:
                    conn.execute('ALTER ROLE forge_identity_binder NO' + attribute)

    def test_membership_owner_and_extra_column_grants_reject(self):
        with connect() as conn:
            conn.execute('GRANT forge_runtime TO forge_identity_binder')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('REVOKE forge_runtime FROM forge_identity_binder')
            for grant, revoke in (
                ('GRANT UPDATE(subject) ON forge.identities TO forge_identity_binder',
                 'REVOKE UPDATE(subject) ON forge.identities FROM forge_identity_binder'),
                ('GRANT SELECT(organization_id) ON forge.memberships TO forge_identity_binder',
                 'REVOKE SELECT(organization_id) ON forge.memberships FROM forge_identity_binder'),
                ('GRANT INSERT(subject) ON forge.identities TO forge_identity_binder',
                 'REVOKE INSERT(subject) ON forge.identities FROM forge_identity_binder'),
                ('GRANT REFERENCES(subject) ON forge.identities TO forge_identity_binder',
                 'REVOKE REFERENCES(subject) ON forge.identities FROM forge_identity_binder'),
                ('GRANT REFERENCES(entra_tenant_id,entra_object_id) ON forge.identities TO forge_identity_binder',
                 'REVOKE REFERENCES(entra_tenant_id,entra_object_id) ON forge.identities FROM forge_identity_binder'),
            ):
                with self.subTest(grant=grant):
                    conn.execute(grant)
                    try:
                        self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
                    finally:
                        conn.execute(revoke)
            conn.execute('ALTER TABLE forge.identities OWNER TO forge_identity_binder')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('ALTER TABLE forge.identities OWNER TO forge_migrator')
                conn.execute('GRANT SELECT ON forge.identities TO forge_identity_binder')
                conn.execute('GRANT UPDATE(entra_tenant_id,entra_object_id) ON forge.identities TO forge_identity_binder')
        self.assert_clean()

    def test_rls_and_session_switch_safeguards(self):
        with connect() as conn:
            conn.execute('ALTER TABLE forge.identities NO FORCE ROW LEVEL SECURITY')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('ALTER TABLE forge.identities FORCE ROW LEVEL SECURITY')
        pool = self.db.pool(user='forge_identity_binder', options='-c row_security=off')
        self.addCleanup(pool.close, timeout=5)
        self.assert_unavailable(lambda: PostgresIdentityBinder(pool).bind_existing(ALICE, PRINCIPAL))

    def test_binder_direct_rls_is_self_only_and_org_context_cannot_broaden(self):
        with self.db.binder() as conn:
            self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [])
            with conn.transaction():
                binding_context(conn)
                self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [(ALICE,)])
                # Even forged old organization context cannot activate the old policy.
                for key, value in (('organization', ORG_B), ('provider', 'entra'),
                    ('issuer', 'https://login.microsoftonline.com/' + str(OTHER_TID) + '/v2.0'),
                    ('subject', OID)):
                    conn.execute('SELECT set_config(%s,%s,true)', ('forge.' + key, str(value)))
                self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [(ALICE,)])
                self.assertEqual(conn.execute('UPDATE forge.identities SET entra_tenant_id=%s,entra_object_id=%s '
                    'WHERE id=%s', (OTHER_TID, OID, BOB)).rowcount, 0)
            for key in BINDING_KEYS:
                with conn.transaction():
                    binding_context(conn)
                    conn.execute('SELECT set_config(%s,%s,true)', ('forge.binding_' + key, ''))
                    self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [])
            with conn.transaction():
                binding_context(conn)
                conn.execute("SELECT set_config('forge.binding_identity','malformed',true)")
                self.assertEqual(conn.execute('SELECT id FROM forge.identities').fetchall(), [])

    def test_binder_column_acl_and_with_check_prevent_relink_or_membership(self):
        denied = (
            'INSERT INTO forge.identities(id,provider,issuer,subject) VALUES (%s,%s,%s,%s)',
            'DELETE FROM forge.identities WHERE id=%s',
            'UPDATE forge.identities SET subject=%s WHERE id=%s',
            'INSERT INTO forge.memberships VALUES (%s,%s,%s,%s)',
            'SELECT * FROM forge.memberships',
            'SET ROLE forge_runtime',
            'CREATE TEMP TABLE forbidden(id int)',
        )
        params = ((UUID(int=999), 'entra', PRINCIPAL.issuer, PRINCIPAL.oid), (ALICE,),
                  ('other', ALICE), (ORG_A, UUID(int=999), ALICE, 'active'), None, None, None)
        with self.db.binder() as conn:
            for statement, args in zip(denied, params):
                with self.subTest(statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                    binding_context(conn)
                    conn.execute(statement, args)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                binding_context(conn)
                conn.execute('UPDATE forge.identities SET entra_tenant_id=%s,entra_object_id=%s WHERE id=%s',
                             (OTHER_TID, OID, ALICE))

    def test_database_consistency_partial_pair_and_canonical_constraints(self):
        cases = [
            (TID, None, 'entra', PRINCIPAL.issuer, PRINCIPAL.oid),
            (None, OID, 'entra', PRINCIPAL.issuer, PRINCIPAL.oid),
            (TID, OID, 'test', PRINCIPAL.issuer, PRINCIPAL.oid),
            (TID, OID, 'entra', 'issuer', PRINCIPAL.oid),
            (TID, OID, 'entra', PRINCIPAL.issuer, 'raw-sub'),
            (TID, OID, 'entra', PRINCIPAL.issuer.upper(), PRINCIPAL.oid),
        ]
        with connect() as conn:
            for tid, oid, provider, issuer, subject in cases:
                with self.subTest(case=(tid, oid, provider)), self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                    conn.execute('INSERT INTO forge.identities '
                        '(id,provider,issuer,subject,entra_tenant_id,entra_object_id) VALUES (%s,%s,%s,%s,%s,%s)',
                        (UUID(int=999), provider, issuer, subject, tid, oid))
            conn.execute('UPDATE forge.identities SET entra_tenant_id=%s,entra_object_id=%s WHERE id=%s',
                         (TID, OID, ALICE))
            with self.assertRaises(psycopg.errors.UniqueViolation), conn.transaction():
                conn.execute('INSERT INTO forge.identities '
                    '(id,provider,issuer,subject,entra_tenant_id,entra_object_id) VALUES (%s,%s,%s,%s,%s,%s)',
                    (UUID(int=999), 'entra', PRINCIPAL.issuer, PRINCIPAL.oid, TID, OID))
            names = conn.execute("SELECT conname FROM pg_constraint WHERE conrelid='forge.identities'::regclass").fetchall()
            self.assertIn(('entra_binding_unique',), names)

    def test_write_once_guard_applies_to_privileged_updates_not_just_binder(self):
        self.binder.bind_existing(ALICE, PRINCIPAL)
        attempts = (
            ('entra_tenant_id', None), ('entra_object_id', None), ('entra_tenant_id', OTHER_TID),
            ('entra_object_id', UUID(int=999)), ('provider', 'test'), ('issuer', 'different'),
            ('subject', 'different'), ('id', UUID(int=999)),
        )
        with connect() as conn:
            for column, value in attempts:
                with self.subTest(column=column), self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                    conn.execute(sql.SQL('UPDATE forge.identities SET {}=%s WHERE id=%s').format(
                        sql.Identifier(column)), (value, ALICE))
            self.assertEqual(conn.execute('UPDATE forge.identities SET entra_tenant_id=entra_tenant_id '
                                          'WHERE id=%s', (ALICE,)).rowcount, 1)

    def test_binding_without_membership_creates_no_access(self):
        with connect() as conn:
            conn.execute('DELETE FROM forge.memberships WHERE identity_id=%s', (ALICE,))
        self.assertIsNotNone(self.binder.bind_existing(ALICE, PRINCIPAL))
        reader_pool = self.db.pool()
        self.addCleanup(reader_pool.close, timeout=5)
        self.assertIsNone(PostgresBootstrapReader(reader_pool).read(PRINCIPAL.identity, str(ORG_A)))
        with connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM forge.memberships WHERE identity_id=%s',
                                          (ALICE,)).fetchone()[0], 0)

    def test_missing_required_privilege_schema_ownership_and_role_switch_reject(self):
        with connect() as conn:
            conn.execute('REVOKE UPDATE(entra_object_id) ON forge.identities FROM forge_identity_binder')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('GRANT UPDATE(entra_object_id) ON forge.identities TO forge_identity_binder')
            conn.execute('ALTER SCHEMA forge OWNER TO forge_identity_binder')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('ALTER SCHEMA forge OWNER TO forge_migrator')
                conn.execute('GRANT USAGE ON SCHEMA forge TO forge_identity_binder')
            conn.execute('ALTER FUNCTION forge.binding_identity() OWNER TO forge_identity_binder')
            try:
                self.assert_unavailable(lambda: self.binder.bind_existing(ALICE, PRINCIPAL))
            finally:
                conn.execute('ALTER FUNCTION forge.binding_identity() OWNER TO forge_migrator')
                conn.execute('GRANT EXECUTE ON FUNCTION forge.binding_identity() TO forge_identity_binder')
        pool = self.db.pool(user='postgres', options='-c role=forge_identity_binder')
        self.addCleanup(pool.close, timeout=5)
        with pool.connection() as conn:
            self.assertEqual(conn.execute('SELECT current_user,session_user').fetchone(),
                             ('forge_identity_binder', 'postgres'))
        self.assert_unavailable(lambda: PostgresIdentityBinder(pool).bind_existing(ALICE, PRINCIPAL))

    def test_local_limits_are_effective_and_restored_with_clean_context(self):
        pool = self.db.pool(user='forge_identity_binder', connection_class=FaultConnection,
                            options='-c statement_timeout=8000 -c lock_timeout=2000')
        self.addCleanup(pool.close, timeout=5)
        with pool.connection() as conn:
            pid = conn.info.backend_pid
        self.assertIsNotNone(PostgresIdentityBinder(pool).bind_existing(ALICE, PRINCIPAL))
        with pool.connection() as conn:
            self.assertEqual(conn.info.backend_pid, pid)
            self.assertEqual(conn.observed_limits, ('1s', '5s'))
            self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0], '8s')
            self.assertEqual(conn.execute('SHOW lock_timeout').fetchone()[0], '2s')
            for key in BINDING_KEYS:
                self.assertIn(conn.execute('SELECT current_setting(%s,true)',
                    ('forge.binding_' + key,)).fetchone()[0], (None, ''))

    def test_binder_role_has_exact_acl_and_helpers_have_no_public_execute(self):
        with self.db.binder() as conn:
            for table in TABLES:
                self.assertEqual(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',
                    ('forge.' + table, 'SELECT')).fetchone()[0], table == 'identities')
                for privilege in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                    self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',
                        ('forge.' + table, privilege)).fetchone()[0])
            for column in ('id', 'provider', 'issuer', 'subject', 'entra_tenant_id', 'entra_object_id'):
                self.assertEqual(conn.execute('SELECT has_column_privilege(current_user,%s,%s,%s)',
                    ('forge.identities', column, 'UPDATE')).fetchone()[0],
                    column in ('entra_tenant_id', 'entra_object_id'))
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON "
                "n.oid=p.pronamespace WHERE n.nspname='forge' AND p.prosecdef").fetchone()[0], 0)
            public = conn.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace, "
                "LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                "WHERE n.nspname='forge' AND p.proname IN ('binding_identity','guard_entra_binding') "
                "AND a.grantee=0 AND a.privilege_type='EXECUTE'").fetchone()[0]
            self.assertEqual(public, 0)

    def test_fresh_migration_proof(self):
        self.assertEqual(self.db.migration_evidence[0], (2, 0, 0, 4, 1))

    def test_populated_upgrade_preserves_generic_entra_and_membership(self):
        self.assertEqual(self.db.migration_evidence[1], (2, 2, 1, 4, 1))

    def test_migration_transaction_rollback_preserves_0001(self):
        self.assertEqual(self.db.migration_evidence[2], (0, 2, 1, 4, 0))

    def test_failed_migration_rolls_back_ddl_policies_role_and_existing_data(self):
        self.assertEqual(self.db.migration_evidence[3],
                         (0, 2, 1, 4, 0, '22012', True, True))

    def test_acquisition_configuration_rejects_unbounded_or_coerced_numbers(self):
        for value in (0, -1, 31, True, 'forever', float('nan'), float('inf'), 10**400):
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                PostgresIdentityBinder(self.pool, acquisition_timeout=value)


if __name__ == '__main__':
    unittest.main()
