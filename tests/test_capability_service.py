"""Capability service over a fake store: argument validation before any call, the administrator view and typed pass-through."""
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_model import CapabilityInvalid, CapabilityLocked, Snapshot
from forge.capability_policy import CatalogEntry, Layer
from forge.capability_service import Capabilities, MAX_ATTRIBUTES_BYTES
from forge.invitations import capability_digest

TOKEN = secrets.token_urlsafe(32)
ORG = uuid4()
SKILL = CatalogEntry('skill:pdf', 'skill', '1.0.0', 'low', True, 'on', 0, None)
EXEC = CatalogEntry('tool:code_execute', 'tool', '1.0.0', 'high', False, 'on', 3, None)
PLUGIN = CatalogEntry('plugin:bio', 'plugin', '1.0.0', 'low', False, 'off', 0, None)
ENTRY = {'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0}
APP = {'version': '1.0.0', 'risk': 'medium', 'is_base': False, 'default_state': 'off', 'min_sandbox_level': 0, 'manifest_sha256': 'a' * 64,
       'declared_permissions': ['ui.title', 'storage.local'], 'granted_permissions': ['ui.title']}


class FakeStore:
    def __init__(self, **fixture):
        self.calls, self.fixture = [], fixture

    def __getattr__(self, name):
        def call(*arguments):
            self.calls.append((name, arguments))
            return self.fixture.get(name, True)
        return call


def snapshot(**change):
    values = dict(platform_epoch=3, org_epoch=2, entries=(SKILL, EXEC, PLUGIN), platform={}, company={}, org={})
    values.update(change)
    return Snapshot(**values)


class PlatformArgumentTests(unittest.TestCase):
    def test_the_token_is_digested_before_any_store_call(self):
        store = FakeStore()
        Capabilities(store).set_platform_policy(TOKEN, 'skill:pdf', 'off', 'none')
        self.assertEqual(store.calls, [('set_platform_policy', (capability_digest(TOKEN), 'skill:pdf', 'off', 'none'))])

    def test_malformed_arguments_never_reach_the_store(self):
        store = FakeStore()
        service = Capabilities(store)
        bad = (lambda: service.set_platform_policy(TOKEN, 'skill:Bad', 'on', 'none'), lambda: service.set_platform_policy(TOKEN, 'skill:pdf', 'maybe', 'none'),
               lambda: service.set_platform_policy(TOKEN, 'skill:pdf', 'on', 'locked'), lambda: service.set_company_override(TOKEN, 'not-uuid', 'skill:pdf', 'on', 'none'),
               lambda: service.put_entry(TOKEN, 'skill:pdf', -1, ENTRY), lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'extra': 1}),
               lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {k: v for k, v in ENTRY.items() if k != 'risk'}),
               lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'risk': 'severe'}), lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'min_sandbox_level': 9}),
               lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'attributes': 'x'}),
               lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'attributes': {'k': 'v' * MAX_ATTRIBUTES_BYTES}}),
               lambda: service.put_entry(TOKEN, 'app:acme.hello', 0, {**APP, 'default_state': 'on'}),
               lambda: service.put_entry(TOKEN, 'app:acme.hello', 0, {k: v for k, v in APP.items() if k != 'manifest_sha256'}),
               lambda: service.put_entry(TOKEN, 'app:acme.hello', 0, {**APP, 'declared_permissions': ['network']}),
               lambda: service.put_entry(TOKEN, 'app:acme.hello', 0, {**APP, 'granted_permissions': ['camera']}),
               lambda: service.put_entry(TOKEN, 'skill:pdf', 0, {**ENTRY, 'declared_permissions': ['ui.title']}))
        for index, call in enumerate(bad):
            with self.subTest(case=index), self.assertRaises(CapabilityInvalid):
                call()
        self.assertEqual(store.calls, [])

    def test_valid_entries_are_normalized_to_the_document_the_database_takes(self):
        store = FakeStore()
        Capabilities(store).put_entry(TOKEN, 'app:acme.hello', 0, APP)
        ((name, (digest, identifier, expected, document)),) = store.calls
        self.assertEqual((name, identifier, expected), ('put_entry', 'app:acme.hello', 0))
        self.assertEqual(document['declared_permissions'], ['ui.title', 'storage.local'])
        self.assertEqual((document['credential_locus'], document['attributes']), ('none', {}), 'an app carries no server credentials')


class AdminViewTests(unittest.TestCase):
    def test_the_view_shows_the_configured_state_the_lock_and_the_setting_without_attestation(self):
        store = FakeStore(admin_snapshot=snapshot(platform={'skill:pdf': Layer(None, 'forced_off')}, org={'plugin:bio': True}))
        items = {item.id: item for item in Capabilities(store).company_view(TOKEN, ORG)}
        self.assertEqual((items['skill:pdf'].state, items['skill:pdf'].locked, items['skill:pdf'].setting), ('forced_off', True, None))
        self.assertEqual((items['plugin:bio'].state, items['plugin:bio'].locked, items['plugin:bio'].setting), ('on', False, True))
        self.assertEqual((items['tool:code_execute'].state, items['tool:code_execute'].min_sandbox_level), ('on', 3),
                         'the administrator sees what is configured; the member device decides attestation')

    def test_set_enabled_validates_before_the_call_and_the_lock_passes_through(self):
        store = FakeStore()
        service = Capabilities(store)
        for bad in (('skill:Bad', True), ('skill:pdf', 'yes'), ('skill:pdf', 1)):
            with self.assertRaises(CapabilityInvalid):
                service.set_enabled(TOKEN, ORG, *bad)
        with self.assertRaises(CapabilityInvalid):
            service.set_enabled(TOKEN, 'org', 'skill:pdf', True)
        self.assertEqual(store.calls, [])
        self.assertTrue(service.set_enabled(TOKEN, ORG, 'skill:pdf', None))

        class Locked(FakeStore):
            def set_org(self, *arguments):
                raise CapabilityLocked()
        with self.assertRaises(CapabilityLocked):
            Capabilities(Locked()).set_enabled(TOKEN, ORG, 'skill:pdf', True)

    def test_audit_paging_arguments_are_bounded(self):
        store = FakeStore()
        service = Capabilities(store)
        for page in (0, 101, '5', True):
            with self.assertRaises(CapabilityInvalid):
                service.org_audit(TOKEN, ORG, None, page)
        for before in (0, -1, '3', True):
            with self.assertRaises(CapabilityInvalid):
                service.platform_audit(TOKEN, before, 10)
        self.assertEqual(store.calls, [])
        service.org_audit(TOKEN, ORG, 5, 10)
        self.assertEqual(store.calls[0][0], 'org_audit')


if __name__ == '__main__':
    unittest.main()
