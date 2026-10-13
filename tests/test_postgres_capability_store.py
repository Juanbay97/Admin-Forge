"""Owned PostgreSQL: the capability store adapter on the 7th pool feeds the pure resolver (defaults, force-off, attestation gate, tenant isolation)."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_model import (CapabilityConflict, CapabilityDenied, CapabilityInvalid, CapabilityLocked, CapabilityNotFound,
                                    CapabilityUnavailable)
from forge.capability_policy import Layer, resolve
from forge.capability_store import PostgresCapabilityStore
from forge.platform import MfaRequired, PlatformDenied
from capability_support import GovernanceWorld, entry
from mvp_support import mvp_database
import json

SKILL, CONNECTOR, EXEC, SHELL, PLUGIN = 'skill:pdf', 'connector:github', 'tool:code_execute', 'tool:bash', 'plugin:bio'


class StoreWorld(GovernanceWorld):
    def build(self, db):
        super().build(db)
        self.store = PostgresCapabilityStore(db.pool('forge_capability_service'))
        for identifier, change in ((SKILL, {}), (CONNECTOR, {}), (EXEC, dict(risk='high', is_base=False, min_sandbox_level=3)),
                                   (SHELL, dict(risk='high', is_base=False, min_sandbox_level=4)), (PLUGIN, dict(default_state='off', is_base=False))):
            self.store.put_entry(self.owner, identifier, 0, json.loads(entry(**change)))

    def states(self, digest, org, level):
        snapshot = self.store.snapshot(digest, org)
        return {item.id: item.state for item in resolve(snapshot.entries, snapshot.platform, snapshot.company, snapshot.org, level)}


class StoreTests(StoreWorld, unittest.TestCase):
    def test_a_company_with_no_policy_rows_gets_the_base_set_on_and_exec_tools_gated_by_the_reported_level(self):
        with mvp_database() as db:
            self.build(db)
            token = self.digest['member_a']
            self.assertEqual(self.states(token, self.org_a, 0), {SKILL: 'on', CONNECTOR: 'on', EXEC: 'blocked_attestation', SHELL: 'blocked_attestation', PLUGIN: 'off'})
            self.assertEqual(self.states(token, self.org_a, 3)[EXEC], 'on')
            self.assertEqual((self.states(token, self.org_a, 3)[SHELL], self.states(token, self.org_a, 4)[SHELL]), ('blocked_attestation', 'on'))
            snapshot = self.store.snapshot(token, self.org_a)
            self.assertEqual((snapshot.platform_epoch, snapshot.org_epoch), (6, 1))

    def test_the_layers_decide_in_the_documented_order_through_the_store(self):
        with mvp_database() as db:
            self.build(db)
            self.assertTrue(self.store.set_platform_policy(self.owner, PLUGIN, 'on', 'none'))
            self.assertEqual(self.states(self.digest['member_a'], self.org_a, 0)[PLUGIN], 'on', 'a platform default beats the catalog default')
            self.assertTrue(self.store.set_org(self.digest['admin_a'], self.org_a, PLUGIN, False))
            self.assertEqual(self.states(self.digest['member_a'], self.org_a, 0)[PLUGIN], 'off', 'the administrator turns it off for the company')
            self.assertEqual(self.states(self.digest['member_b'], self.org_b, 0)[PLUGIN], 'on', 'only the own company')
            self.assertTrue(self.store.set_company_override(self.owner, self.org_a, SKILL, None, 'forced_off'))
            with self.assertRaises(CapabilityLocked):
                self.store.set_org(self.digest['admin_a'], self.org_a, SKILL, True)
            self.assertEqual(self.states(self.digest['member_a'], self.org_a, 4)[SKILL], 'forced_off')
            self.assertEqual(self.states(self.digest['member_b'], self.org_b, 4)[SKILL], 'on')

    def test_the_company_policy_and_admin_snapshot_show_the_layers(self):
        with mvp_database() as db:
            self.build(db)
            self.store.set_company_override(self.owner, self.org_a, CONNECTOR, 'off', 'forced_off')
            self.store.set_org(self.digest['admin_a'], self.org_a, SKILL, False)
            rows = {row.capability_id: row for row in self.store.company_policy(self.owner, self.org_a)}
            self.assertEqual((rows[CONNECTOR].layer, rows[CONNECTOR].org_enabled), (Layer('off', 'forced_off'), None))
            self.assertEqual((rows[SKILL].layer, rows[SKILL].org_enabled), (Layer(None, 'none'), False))
            admin = self.store.admin_snapshot(self.digest['admin_a'], self.org_a)
            self.assertEqual((admin.org[SKILL], admin.company[CONNECTOR]), (False, Layer('off', 'forced_off')))

    def test_catalog_records_carry_their_revision_and_platform_layer(self):
        with mvp_database() as db:
            self.build(db)
            self.store.set_platform_policy(self.owner, SKILL, 'off', 'none')
            records = {record.entry.id: record for record in self.store.catalog(self.owner)}
            self.assertEqual((records[SKILL].revision, records[SKILL].platform), (1, Layer('off', 'none')))
            self.assertEqual(records[EXEC].entry.min_sandbox_level, 3)
            updated = self.store.put_entry(self.owner, SKILL, 1, json.loads(entry(risk='medium')))
            self.assertEqual((updated.revision, updated.entry.risk), (2, 'medium'))

    def test_every_refusal_is_a_typed_error(self):
        with mvp_database() as db:
            self.build(db)
            with self.assertRaises(CapabilityConflict):
                self.store.put_entry(self.owner, SKILL, 0, json.loads(entry()))
            with self.assertRaises(CapabilityInvalid):
                self.store.put_entry(self.owner, 'gadget:x', 0, json.loads(entry()))
            with self.assertRaises(CapabilityNotFound):
                self.store.set_org(self.digest['admin_a'], self.org_a, 'skill:ghost', True)
            with self.assertRaises(CapabilityDenied):
                self.store.snapshot(self.digest['member_a'], self.org_b)
            with self.assertRaises(CapabilityDenied):
                self.store.set_org(self.digest['member_a'], self.org_a, SKILL, True)
            with self.assertRaises(PlatformDenied):
                self.store.put_entry(self.digest['admin_a'], SKILL, 1, json.loads(entry()))
            with self.assertRaises(MfaRequired):
                self.store.set_platform_policy(self.owner_password_only, SKILL, 'off', 'none')
            with self.assertRaises(CapabilityNotFound):
                self.store.set_company_override(self.owner, uuid4(), SKILL, 'on', 'none')

    def test_audit_pages_are_typed_and_scoped(self):
        with mvp_database() as db:
            self.build(db)
            self.store.set_org(self.digest['admin_a'], self.org_a, SKILL, False)
            self.store.set_org(self.digest['admin_b'], self.org_b, SKILL, False)
            own = self.store.org_audit(self.digest['admin_a'], self.org_a, None, 10)
            self.assertEqual([(row.scope, row.organization_id, row.action, row.target, row.before, row.after) for row in own],
                             [('org', self.org_a, 'org.setting_set', SKILL, None, 'off')])
            self.assertIsNotNone(own[0].actor_id)
            everything = self.store.platform_audit(self.owner, None, 100)
            self.assertEqual({row.organization_id for row in everything}, {None, self.org_a, self.org_b})
            self.assertEqual(len(self.store.platform_audit(self.owner, everything[0].id, 2)), 2)

    def test_a_pool_that_is_not_the_capability_role_is_unavailable(self):
        with mvp_database() as db:
            self.build(db)
            wrong = PostgresCapabilityStore(db.pool('forge_platform_service'))
            with self.assertRaises(CapabilityUnavailable):
                wrong.catalog(self.owner)


if __name__ == '__main__':
    unittest.main()
