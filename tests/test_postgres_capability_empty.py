"""Owned PostgreSQL: with an empty catalog the store answers an empty snapshot, and only a proven member of the company gets it."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.capability_model import CapabilityDenied, Snapshot
from forge.capability_store import PostgresCapabilityStore
from capability_support import GovernanceWorld
from mvp_support import mvp_database


class EmptyCatalogTests(GovernanceWorld, unittest.TestCase):
    def test_a_member_reads_an_empty_snapshot_and_a_stranger_is_still_denied(self):
        with mvp_database() as db:
            self.build(db)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.capability_catalog').fetchone(), (0,))
            store = PostgresCapabilityStore(db.pool('forge_capability_service'))
            self.assertEqual(store.snapshot(self.digest['member_a'], self.org_a), Snapshot(1, 1, (), {}, {}, {}))
            self.assertEqual(store.admin_snapshot(self.digest['admin_a'], self.org_a), Snapshot(1, 1, (), {}, {}, {}))
            with self.assertRaises(CapabilityDenied):
                store.snapshot(self.digest['member_a'], self.org_b)


if __name__ == '__main__':
    unittest.main()
