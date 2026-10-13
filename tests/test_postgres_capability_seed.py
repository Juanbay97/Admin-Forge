"""Owned PostgreSQL: the idempotent catalog seed sync (creates, never overwrites, audited, one epoch bump)."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_seed import SyncResult, load_seed, sync
from capability_support import GovernanceWorld
from mvp_support import mvp_database


class SeedSyncTests(GovernanceWorld, unittest.TestCase):
    def counts(self, db):
        return dict(db.admin.execute("SELECT kind,count(*) FROM forge.capability_catalog GROUP BY kind").fetchall())

    def test_the_seed_creates_the_whole_inventory_once_and_a_second_run_changes_nothing(self):
        with mvp_database() as db:
            entries = load_seed()
            first = sync(db.admin, entries)
            self.assertEqual((first.created, first.updated, first.unchanged), (len(entries), 0, 0))
            counts = self.counts(db)
            self.assertEqual((counts['skill'], counts['connector'], counts['plugin']), (25, 46, 15))
            self.assertGreaterEqual(counts['tool'], 22)
            epoch = db.admin.execute('SELECT epoch FROM forge.capability_platform_epoch').fetchone()[0]
            audits = db.admin.execute('SELECT count(*) FILTER (WHERE actor_id IS NULL AND action=%s),count(*) FROM forge.capability_change_audit', ('catalog.created',)).fetchone()
            self.assertEqual((epoch, audits), (2, (len(entries), len(entries))))
            second = sync(db.admin, entries)
            self.assertEqual(second, SyncResult(0, 0, len(entries)))
            self.assertEqual(db.admin.execute('SELECT epoch FROM forge.capability_platform_epoch').fetchone()[0], 2)
            self.assertEqual(db.admin.execute('SELECT count(*),max(revision) FROM forge.capability_catalog').fetchone(), (len(entries), 1))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.capability_change_audit').fetchone()[0], len(entries))

    def test_a_platform_edit_survives_a_plain_sync_and_update_applies_the_seed_again(self):
        with mvp_database() as db:
            self.build(db)
            entries = load_seed()
            sync(db.admin, entries)
            self.role.call('SELECT * FROM forge.cap_catalog_put(%s,%s,1,%s::jsonb)', (self.owner, 'skill:pdf', '{"version":"2.0.0","risk":"low","is_base":true,"default_state":"off","min_sandbox_level":0}'))
            self.assertEqual(sync(db.admin, entries), SyncResult(0, 0, len(entries)), 'a plain sync never overwrites')
            self.assertEqual(db.admin.execute("SELECT version,default_state,revision FROM forge.capability_catalog WHERE id='skill:pdf'").fetchone(), ('2.0.0', 'off', 2))
            result = sync(db.admin, entries, update=True)
            self.assertEqual((result.created, result.updated), (0, 1))
            self.assertEqual(db.admin.execute("SELECT version,default_state,revision FROM forge.capability_catalog WHERE id='skill:pdf'").fetchone(), ('1.0.0', 'on', 3))
            self.assertEqual(db.admin.execute("SELECT before_state,after_state FROM forge.capability_change_audit WHERE action='catalog.updated' AND actor_id IS NULL").fetchone(), ('r2', 'r3'))

    def test_a_failure_leaves_nothing_behind(self):
        with mvp_database() as db:
            entries = load_seed()
            broken = [*entries[:3], {**entries[3], 'risk': 'severe'}]
            with self.assertRaises(Exception):
                sync(db.admin, broken)
            self.assertEqual(db.admin.execute('SELECT (SELECT count(*) FROM forge.capability_catalog),(SELECT count(*) FROM forge.capability_change_audit),(SELECT epoch FROM forge.capability_platform_epoch)').fetchone(), (0, 0, 1))

    def test_seeded_defaults_resolve_as_the_binding_rules_require(self):
        with mvp_database() as db:
            self.build(db)
            sync(db.admin, load_seed())
            from forge.capability_policy import resolve
            from forge.capability_store import PostgresCapabilityStore
            store = PostgresCapabilityStore(db.pool('forge_capability_service'))
            snapshot = store.snapshot(self.digest['member_a'], self.org_a)
            states = {item.id: item.state for item in resolve(snapshot.entries, snapshot.platform, snapshot.company, snapshot.org, 3)}
            self.assertEqual({states[name] for name in states if name.startswith(('skill:', 'connector:'))}, {'on'})
            self.assertEqual({states[name] for name in states if name.startswith('plugin:')}, {'off'})
            self.assertEqual((states['tool:code_execute'], states['tool:bash'], states['tool:browser']), ('on', 'blocked_attestation', 'off'))


if __name__ == '__main__':
    unittest.main()
