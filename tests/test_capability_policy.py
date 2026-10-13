"""Capability resolver: layered precedence, default-deny for unknown ids, force-off and the sandbox attestation gate."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_policy import (CatalogEntry, Layer, MAX_LEVEL, effective_level, resolve, resolve_one)


def entry(identifier, *, default='on', minimum=0, base=True, kind=None, declared=(), granted=(), locus='server'):
    kind = kind or identifier.split(':')[0]
    return CatalogEntry(identifier, kind, '1.0.0', 'low', base, default, minimum, None, locus, tuple(declared), tuple(granted))


SKILL = entry('skill:pdf')
CONNECTOR = entry('connector:github')
EXEC = entry('tool:code_execute', minimum=3, base=False)
SHELL = entry('tool:bash', minimum=4, base=False)
PLUGIN = entry('plugin:bio', default='off', base=False)


def states(effective):
    return {item.id: item.state for item in effective}


class PrecedenceTests(unittest.TestCase):
    def test_a_new_company_with_no_policy_rows_inherits_the_catalog_defaults(self):
        result = states(resolve([SKILL, CONNECTOR, PLUGIN], {}, {}, {}, 0))
        self.assertEqual(result, {'skill:pdf': 'on', 'connector:github': 'on', 'plugin:bio': 'off'})

    def test_order_is_platform_then_company_then_org_setting(self):
        platform = {'skill:pdf': Layer('off')}
        self.assertEqual(resolve_one(SKILL, platform, {}, {}, 0).state, 'off', 'the platform default beats the catalog default')
        company = {'skill:pdf': Layer('on')}
        self.assertEqual(resolve_one(SKILL, platform, company, {}, 0).state, 'on', 'the company override beats the platform default')
        self.assertEqual(resolve_one(SKILL, platform, company, {'skill:pdf': False}, 0).state, 'off', 'the org administrator beats the company override')
        self.assertEqual(resolve_one(PLUGIN, {}, {}, {'plugin:bio': True}, 0).state, 'on', 'an administrator can enable what the catalog ships off')

    def test_force_off_at_platform_or_company_level_beats_every_enable(self):
        enable_everywhere = ({'skill:pdf': Layer('on', 'forced_off')}, {}, {'skill:pdf': True})
        self.assertEqual(resolve_one(SKILL, *enable_everywhere, 0).state, 'forced_off')
        company_lock = ({}, {'skill:pdf': Layer(None, 'forced_off')}, {'skill:pdf': True})
        self.assertEqual(resolve_one(SKILL, *company_lock, 0).state, 'forced_off')

    def test_an_unlocked_layer_with_no_state_inherits_from_below(self):
        self.assertEqual(resolve_one(SKILL, {'skill:pdf': Layer(None)}, {'skill:pdf': Layer(None)}, {}, 0).state, 'on')

    def test_unknown_ids_resolve_off_and_unknown_layers_are_ignored(self):
        unknown = resolve_one(None, {}, {}, {}, 3, identifier='skill:ghost')
        self.assertEqual((unknown.id, unknown.state), ('skill:ghost', 'off'))
        result = resolve([SKILL], {'skill:ghost': Layer('on')}, {'skill:ghost': Layer('on')}, {'skill:ghost': True}, 0)
        self.assertEqual(states(result), {'skill:pdf': 'on'}, 'only catalog entries are ever listed')


class AttestationGateTests(unittest.TestCase):
    def test_below_the_minimum_an_enabled_exec_tool_is_blocked_and_at_it_is_on(self):
        self.assertEqual(resolve_one(EXEC, {}, {}, {}, 2).state, 'blocked_attestation')
        self.assertEqual(resolve_one(EXEC, {}, {}, {}, 3).state, 'on')
        self.assertEqual(resolve_one(EXEC, {}, {}, {}, 4).state, 'on')

    def test_shells_need_container_level_four(self):
        self.assertEqual(resolve_one(SHELL, {}, {}, {}, 3).state, 'blocked_attestation')
        self.assertEqual(resolve_one(SHELL, {}, {}, {}, 4).state, 'on')

    def test_a_missing_or_invalid_report_is_level_zero(self):
        for reported in (None, -1, 5, 3.0, True, '3'):
            with self.subTest(reported=reported):
                self.assertEqual(effective_level(reported), 0)
                self.assertEqual(resolve_one(EXEC, {}, {}, {}, effective_level(reported)).state, 'blocked_attestation')
        self.assertEqual([effective_level(level) for level in range(MAX_LEVEL + 1)], [0, 1, 2, 3, 4])

    def test_no_administrator_setting_overrides_the_gate(self):
        result = resolve_one(EXEC, {'tool:code_execute': Layer('on')}, {'tool:code_execute': Layer('on')}, {'tool:code_execute': True}, 2)
        self.assertEqual(result.state, 'blocked_attestation')

    def test_disabled_and_forced_off_tools_are_not_reported_as_blocked(self):
        self.assertEqual(resolve_one(EXEC, {}, {}, {'tool:code_execute': False}, 0).state, 'off')
        self.assertEqual(resolve_one(EXEC, {'tool:code_execute': Layer(None, 'forced_off')}, {}, {}, 0).state, 'forced_off')

    def test_the_gate_only_applies_to_entries_with_a_minimum(self):
        self.assertEqual(resolve_one(SKILL, {}, {}, {}, 0).state, 'on')


class AppPermissionTests(unittest.TestCase):
    def test_only_granted_and_declared_permissions_are_exposed(self):
        app = entry('app:acme.hello', default='off', base=False, declared=('ui.title', 'storage.local'), granted=('storage.local', 'ui.title.x'))
        self.assertEqual(resolve_one(app, {}, {}, {'app:acme.hello': True}, 0).granted_permissions, ('storage.local',))

    def test_non_app_entries_expose_no_permissions_and_apps_default_off(self):
        self.assertIsNone(resolve_one(SKILL, {}, {}, {}, 0).granted_permissions)
        app = entry('app:acme.hello', default='off', base=False, declared=('ui.title',), granted=('ui.title',))
        effective = resolve_one(app, {}, {}, {}, 0)
        self.assertEqual((effective.state, effective.granted_permissions), ('off', ('ui.title',)))


class EffectiveShapeTests(unittest.TestCase):
    def test_the_view_for_the_client_is_flat_with_enabled_and_reason(self):
        on = resolve_one(SKILL, {}, {}, {}, 0).view()
        self.assertEqual((on['id'], on['kind'], on['state'], on['enabled']), ('pdf', 'skill', 'on', True))
        self.assertNotIn('reason', on)
        blocked = resolve_one(EXEC, {}, {}, {}, 0).view()
        self.assertEqual((blocked['enabled'], blocked['reason'], blocked['min_sandbox_level']), (False, 'blocked_attestation', 3))
        forced = resolve_one(SKILL, {'skill:pdf': Layer(None, 'forced_off')}, {}, {}, 0).view()
        self.assertEqual((forced['enabled'], forced['reason']), (False, 'forced_off'))

    def test_entries_are_validated_at_construction(self):
        for bad in (dict(identifier='skill:Bad Id'), dict(identifier='gadget:x'), dict(identifier='skill:x', default='maybe'),
                    dict(identifier='skill:x', minimum=5)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                entry(bad.pop('identifier'), **bad)

    def test_a_kind_that_disagrees_with_the_id_is_refused(self):
        with self.assertRaises(ValueError):
            entry('skill:x', kind='tool')


if __name__ == '__main__':
    unittest.main()
