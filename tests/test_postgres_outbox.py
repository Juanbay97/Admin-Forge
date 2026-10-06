"""Real PostgreSQL proof for generic recording and additive migration safety."""
import unittest
from uuid import uuid4
import psycopg
from postgres_support import DatabaseFixture, connect, ORG_A, ORG_B, MEMBER_A


class PostgresOutboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseFixture()

    def setUp(self):
        self.db.reset()

    def test_destination_is_present_and_forces_rls(self):
        with connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                "WHERE oid=to_regclass('forge.outbox_events')").fetchall(),
                [(True, True)])
            from forge.postgres import _OUTBOX_SCHEMA
            self.assertTrue(conn.execute(_OUTBOX_SCHEMA).fetchone()[0])

    def event(self, organization=ORG_A, revision=2):
        from forge.outbox import Event
        return Event(uuid4(), organization, uuid4(), uuid4(), MEMBER_A,
                     'membership.updated', revision - 1, revision)

    def test_commit_and_failures_share_the_callers_transaction(self):
        from forge.outbox_store import record_event
        for fail_at in ('resource', 'event', None):
            self.db.reset()
            event = self.event()
            try:
                with connect() as conn, conn.transaction():
                    conn.execute('UPDATE forge.memberships SET revision=2 WHERE id=%s', (MEMBER_A,))
                    if fail_at == 'resource':
                        raise RuntimeError('injected')
                    record_event(conn, event)
                    if fail_at == 'event':
                        raise RuntimeError('injected')
            except RuntimeError:
                pass
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT revision FROM forge.memberships WHERE id=%s',
                    (MEMBER_A,)).fetchone()[0], 1 if fail_at else 2)
                self.assertEqual(conn.execute('SELECT event_id,revision FROM forge.outbox_events').fetchall(),
                    [] if fail_at else [(event.event_id, 2)])

    def test_duplicate_event_or_resource_revision_aborts_without_partial_mutation(self):
        from dataclasses import replace
        from forge.outbox_store import record_event, OutboxUnavailable
        event = self.event()
        with connect() as conn, conn.transaction():
            record_event(conn, event)
        for duplicate in (event, replace(event, event_id=uuid4())):
            with self.assertRaisesRegex(OutboxUnavailable, '^Outbox recording unavailable$'):
                with connect() as conn, conn.transaction():
                    conn.execute('UPDATE forge.memberships SET revision=3 WHERE id=%s', (MEMBER_A,))
                    record_event(conn, duplicate)
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM forge.outbox_events').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT revision FROM forge.memberships WHERE id=%s',
                    (MEMBER_A,)).fetchone()[0], 1)

    def test_recorder_requires_existing_transaction(self):
        from forge.outbox_store import record_event, OutboxUnavailable
        with connect() as conn:
            with self.assertRaises(OutboxUnavailable):
                record_event(conn, self.event())
            self.assertEqual(conn.execute('SELECT count(*) FROM forge.outbox_events').fetchone()[0], 0)

    def test_scoped_insert_only_writer_and_context_cleanup(self):
        from forge.outbox_store import record_event, OutboxUnavailable
        with connect() as conn:
            for context in (None, '', 'malformed', str(ORG_B)):
                with self.subTest(context=context), self.assertRaises(OutboxUnavailable), conn.transaction():
                    conn.execute('SET LOCAL ROLE forge_outbox_writer')
                    if context is not None:
                        conn.execute("SELECT set_config('forge.organization',%s,true)", (context,))
                    record_event(conn, self.event())
            for organization, revision in ((ORG_A, 2), (ORG_B, 3)):
                with conn.transaction():
                    conn.execute('SET LOCAL ROLE forge_outbox_writer')
                    conn.execute("SELECT set_config('forge.organization',%s,true)", (str(organization),))
                    record_event(conn, self.event(organization, revision))
                self.assertIn(conn.execute("SELECT current_setting('forge.organization',true)").fetchone()[0], (None, ''))
            self.assertEqual(conn.execute('SELECT organization_id FROM forge.outbox_events ORDER BY revision').fetchall(),
                             [(ORG_A,), (ORG_B,)])
            for role in ('forge_runtime', 'forge_designator', 'forge_identity_binder', 'forge_outbox_writer'):
                for statement in ('SELECT * FROM forge.outbox_events',
                                  'DELETE FROM forge.outbox_events', 'SET ROLE forge_migrator'):
                    with self.subTest(role=role, statement=statement), self.assertRaises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                        conn.execute('SET LOCAL SESSION AUTHORIZATION ' + role)
                        conn.execute(statement)

    def test_database_constraints_reject_invalid_shapes(self):
        from forge.outbox_store import record_event
        event = self.event()
        with connect() as conn, conn.transaction():
            record_event(conn, event)
        for change in ("schema_version=2", "outcome='secret-marker'", "event_type='bad'",
                       'previous_revision=-1', 'revision=7', 'actor_id=NULL'):
            with self.subTest(change=change), self.assertRaises(psycopg.IntegrityError), connect() as conn, conn.transaction():
                conn.execute('UPDATE forge.outbox_events SET ' + change)

    def test_fresh_populated_and_failed_migration_preserve_prior_storage(self):
        self.assertEqual([row[:3] for row in self.db.outbox_migration_evidence],
                         [(False, False, 0), (True, False, 2), (True, True, 2)])


    def test_populated_migration_snapshots_include_nonempty_legacy_events(self):
        self.assertEqual(
            [row[3] for row in self.db.outbox_migration_evidence],
            [(0, 0, 0), (1, 1, 1), (1, 1, 1)],
        )
