"""Mandatory real PostgreSQL proof: no SQLite fallback, mocks or silent skips."""
import unittest
from uuid import UUID

import psycopg
from psycopg import sql

from postgres_support import (
    ALICE, ARCHIVED, BOB, CAROL, KEYS, MEMBER_A, ORG_A, ORG_B, TABLES,
    DatabaseFixture, connect, rows, set_context,
)


class PostgresIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    def assert_empty(self, conn):
        for table in TABLES:
            with self.subTest(table=table):
                self.assertEqual(rows(conn, table), [])

    def test_unfiltered_reads_are_scoped_to_owned_identity_and_org(self):
        for org, subject, identity in ((ORG_A, 'alice', ALICE),
                                      (ORG_A, 'carol', CAROL), (ORG_B, 'bob', BOB)):
            with self.subTest(org=org, subject=subject), self.db.runtime() as conn:
                with conn.transaction():
                    set_context(conn, organization=org, subject=subject)
                    self.assertEqual([r[0] for r in rows(conn, 'identities')], [identity])
                    self.assertEqual([r[0] for r in rows(conn, 'organizations')], [org])
                    memberships = rows(conn, 'memberships')
                    self.assertEqual(len(memberships), 1)
                    self.assertEqual(memberships[0][0], org)
                    self.assertEqual(memberships[0][2], identity)
                    self.assertEqual([r[0] for r in rows(conn, 'configuration_revisions')], [org])

    def test_missing_context_denies_every_table(self):
        with self.db.runtime() as conn:
            self.assert_empty(conn)

    def test_each_missing_or_empty_context_component_denies(self):
        for omitted in KEYS:
            for value in (None, '', '   '):
                with self.subTest(omitted=omitted, value=value), self.db.runtime() as conn:
                    with conn.transaction():
                        values = dict(organization=ORG_A, provider='test', issuer='issuer', subject='alice')
                        values[omitted] = value
                        set_context(conn, **values)
                        self.assert_empty(conn)

    def test_partial_context_denies(self):
        for supplied in KEYS:
            with self.subTest(supplied=supplied), self.db.runtime() as conn:
                with conn.transaction():
                    conn.execute('SELECT set_config(%s,%s,true)',
                                 ('forge.' + supplied, str(ORG_A) if supplied == 'organization' else 'alice'))
                    self.assert_empty(conn)

    def test_malformed_organization_context_denies_without_query_error(self):
        for invalid in ('not-a-uuid', "' OR true --", '00000000-0000-0000-0000-00000000000z'):
            with self.subTest(invalid=invalid), self.db.runtime() as conn:
                with conn.transaction():
                    set_context(conn, organization=invalid)
                    self.assert_empty(conn)

    def test_crossed_org_subject_pairs_do_not_authorize_org_data(self):
        for org, subject in ((ORG_A, 'bob'), (ORG_B, 'alice'), (ORG_B, 'carol'),
                             (ORG_B, 'suspended'), (ORG_B, 'archived')):
            with self.subTest(org=org, subject=subject), self.db.runtime() as conn:
                with conn.transaction():
                    set_context(conn, organization=org, subject=subject)
                    for table in ('organizations', 'memberships', 'configuration_revisions'):
                        self.assertEqual(rows(conn, table), [])
                    self.assertEqual(len(rows(conn, 'identities')), 1)

    def test_provider_issuer_subject_are_all_exact_authority(self):
        for key in ('provider', 'issuer', 'subject'):
            with self.subTest(key=key), self.db.runtime() as conn:
                with conn.transaction():
                    values = dict(organization=ORG_A, provider='test', issuer='issuer', subject='alice')
                    values[key] = 'untrusted'
                    set_context(conn, **values)
                    self.assert_empty(conn)

    def test_suspended_is_internally_visible_archived_is_hidden(self):
        for subject, expected in (('suspended', 1), ('archived', 0)):
            with self.subTest(subject=subject), self.db.runtime() as conn:
                with conn.transaction():
                    set_context(conn, subject=subject)
                    self.assertEqual(len(rows(conn, 'memberships')), expected)
                    self.assertEqual(len(rows(conn, 'organizations')), expected)
                    self.assertEqual(len(rows(conn, 'configuration_revisions')), expected)
                    self.assertEqual(len(rows(conn, 'identities')), 1)

    def test_same_backend_cleans_context_after_commit_and_rollback(self):
        with self.db.runtime() as conn:
            pid = conn.info.backend_pid
            for rollback in (False, True):
                with self.subTest(rollback=rollback):
                    try:
                        with conn.transaction():
                            set_context(conn)
                            self.assertEqual(len(rows(conn, 'organizations')), 1)
                            if rollback:
                                raise RuntimeError('intentional rollback')
                    except RuntimeError:
                        if not rollback:
                            raise
                    self.assertEqual(conn.info.backend_pid, pid)
                    self.assertEqual(conn.execute('SELECT pg_backend_pid()').fetchone()[0], pid)
                    for key in KEYS:
                        value = conn.execute('SELECT current_setting(%s,true)',
                                             ('forge.' + key,)).fetchone()[0]
                        self.assertIn(value, (None, ''))
                    self.assert_empty(conn)
            with conn.transaction():
                set_context(conn, organization=ORG_B, subject='bob')
                self.assertEqual([r[0] for r in rows(conn, 'organizations')], [ORG_B])

    def test_context_helper_rejects_autocommit_without_outer_transaction(self):
        with self.db.runtime() as conn:
            with self.assertRaisesRegex(RuntimeError, 'outer transaction'):
                set_context(conn)

    def test_role_attributes_memberships_ownership_and_grants(self):
        with self.db.runtime() as conn:
            self.assertEqual(conn.execute('SELECT current_user, session_user').fetchone(),
                             ('forge_runtime', 'forge_runtime'))
            attrs = conn.execute('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication '
                                 "FROM pg_roles WHERE rolname=current_user").fetchone()
            self.assertEqual(attrs, (False,) * 5)
            memberships = conn.execute('SELECT count(*) FROM pg_auth_members '
                                       'WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)').fetchone()[0]
            self.assertEqual(memberships, 0)
            owners = conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                  "WHERE n.nspname='forge' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0]
            self.assertEqual(owners, 0)
            self.assertFalse(conn.execute("SELECT has_schema_privilege(current_user,'forge','CREATE')").fetchone()[0])
            self.assertFalse(conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0])
            self.assertFalse(conn.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE')").fetchone()[0])
            self.assertFalse(conn.execute("SELECT has_database_privilege(current_user,current_database(),'TEMP')").fetchone()[0])
            for table in TABLES:
                self.assertTrue(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                              ('forge.' + table, 'SELECT')).fetchone()[0])
                for privilege in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                    self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',
                                                   ('forge.' + table, privilege)).fetchone()[0])

    def test_enable_force_and_explicit_policy_checks_on_every_table(self):
        with connect() as conn:
            metadata = conn.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,"
                                    "pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n "
                                    "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND c.relkind='r'").fetchall()
            self.assertEqual(len(metadata), 4)
            for _, enabled, forced, owner in metadata:
                self.assertTrue(enabled)
                self.assertTrue(forced)
                self.assertEqual(owner, 'forge_migrator')
            policies = conn.execute("SELECT count(*) FROM pg_policy WHERE polrelid IN "
                "(SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge') AND polqual IS NOT NULL AND polwithcheck IS NOT NULL").fetchone()[0]
            self.assertEqual(policies, 4)

    def test_force_rls_applies_to_migration_owner_and_helpers_are_invokers(self):
        with connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='forge' AND p.prosecdef").fetchone()[0], 0)
            with conn.transaction():
                conn.execute('SET LOCAL ROLE forge_migrator')
                self.assert_empty(conn)
                set_context(conn)
                self.assertEqual([r[0] for r in rows(conn, 'organizations')], [ORG_A])

    def test_runtime_cannot_write_create_change_policy_or_assume_owner(self):
        statements = (
            'INSERT INTO forge.configuration_revisions VALUES (%s,3)',
            'UPDATE forge.configuration_revisions SET revision=3 WHERE organization_id=%s',
            'DELETE FROM forge.configuration_revisions WHERE organization_id=%s',
            'CREATE TABLE forge.forbidden(id int)', 'CREATE TABLE public.forbidden(id int)',
            'CREATE TEMP TABLE forbidden(id int)', 'ALTER TABLE forge.identities DISABLE ROW LEVEL SECURITY',
            'DROP POLICY identity_scope ON forge.identities', 'SET ROLE forge_migrator',
            'SET SESSION AUTHORIZATION forge_migrator',
        )
        with self.db.runtime() as conn:
            for statement in statements:
                with self.subTest(statement=statement):
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                        set_context(conn)
                        conn.execute(statement, (ORG_A,) if '%s' in statement else None)

    def test_identity_uniqueness_and_nonempty_components(self):
        with connect() as conn:
            with self.assertRaises(psycopg.errors.UniqueViolation), conn.transaction():
                conn.execute('INSERT INTO forge.identities VALUES (%s,%s,%s,%s)',
                             (UUID(int=99), 'test', 'issuer', 'alice'))
            for column in ('provider', 'issuer', 'subject'):
                with self.subTest(column=column):
                    with self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                        conn.execute(sql.SQL('UPDATE forge.identities SET {}=%s WHERE id=%s').format(
                            sql.Identifier(column)), ('   ', ALICE))

    def test_membership_unique_org_identity_and_org_id_and_status(self):
        for mid, identity, error in ((UUID(int=99), ALICE, psycopg.errors.UniqueViolation),
                                     (MEMBER_A, BOB, psycopg.errors.UniqueViolation)):
            with connect() as conn, self.assertRaises(error), conn.transaction():
                conn.execute('INSERT INTO forge.memberships VALUES (%s,%s,%s,%s)',
                             (ORG_A, mid, identity, 'active'))
        with connect() as conn, self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute('UPDATE forge.memberships SET status=%s WHERE id=%s', ('unknown', MEMBER_A))

    def test_configuration_positive_revision_and_unique_composite_key(self):
        for revision, error in ((0, psycopg.errors.CheckViolation),
                                (-1, psycopg.errors.CheckViolation), (1, psycopg.errors.UniqueViolation)):
            with self.subTest(revision=revision), connect() as conn:
                with self.assertRaises(error), conn.transaction():
                    conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,%s)', (ORG_A, revision))

    def test_selected_config_cannot_reference_only_foreign_org_revision(self):
        with connect() as conn:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation), conn.transaction():
                conn.execute('UPDATE forge.organizations SET selected_config_revision=2 WHERE id=%s', (ORG_A,))
            self.assertEqual(conn.execute('SELECT selected_config_revision FROM forge.organizations WHERE id=%s',
                                          (ORG_A,)).fetchone()[0], 1)

    def test_selected_configuration_fk_is_deferred_and_allows_atomic_insertion(self):
        org = UUID(int=88)
        with connect() as conn, conn.transaction():
            conn.execute('INSERT INTO forge.organizations VALUES (%s,%s,%s,true,7)', (org, 'new', 'New'))
            conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,7)', (org,))
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT condeferrable,condeferred FROM pg_constraint "
                "WHERE conname='selected_configuration'").fetchone(), (True, True))

    def test_restricted_writer_using_hides_foreign_updates_and_deletes(self):
        with self.db.writer() as conn, conn.transaction():
            set_context(conn)
            self.assertEqual([r[0] for r in rows(conn, 'configuration_revisions')], [ORG_A])
            self.assertEqual(conn.execute('UPDATE forge.configuration_revisions SET revision=revision '
                'WHERE organization_id=%s', (ORG_A,)).rowcount, 1)
            self.assertEqual(conn.execute('UPDATE forge.configuration_revisions SET revision=revision '
                'WHERE organization_id=%s', (ORG_B,)).rowcount, 0)
            self.assertEqual(conn.execute('DELETE FROM forge.configuration_revisions WHERE organization_id=%s',
                                          (ORG_B,)).rowcount, 0)

    def test_restricted_writer_with_check_rejects_fk_valid_cross_org_insert(self):
        with self.db.writer() as conn:
            with conn.transaction():
                set_context(conn)
                self.assertEqual(conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,3)',
                                              (ORG_A,)).rowcount, 1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege) as caught, conn.transaction():
                set_context(conn)
                conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,3)', (ORG_B,))
            self.assertIn('row-level security', str(caught.exception))

    def test_restricted_writer_with_check_rejects_fk_valid_cross_org_update(self):
        with self.db.writer() as conn:
            with conn.transaction():
                set_context(conn)
                conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,3)', (ORG_A,))
                self.assertEqual(conn.execute('UPDATE forge.configuration_revisions SET revision=4 '
                    'WHERE organization_id=%s AND revision=3', (ORG_A,)).rowcount, 1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege) as caught, conn.transaction():
                set_context(conn)
                conn.execute('UPDATE forge.configuration_revisions SET organization_id=%s '
                             'WHERE organization_id=%s AND revision=4', (ORG_B, ORG_A))
            self.assertIn('row-level security', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
