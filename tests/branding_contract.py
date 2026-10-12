"""Behavioural contract of a BrandingStore, run against the in-memory fake AND the PostgreSQL adapter.

A harness (``self.harness()``, a context manager) provides: ``store``, ``org_a``, ``org_b``, the session
digests ``admin_a``, ``member_a``, ``admin_b``, the company codes ``code_a``, ``code_b`` and
``deactivate(code)``. API tests rely on the fake, so it must pass exactly what the database passes.
"""
from forge import branding
from forge.branding import BrandingInput, DEFAULT
from forge.branding_assets import Asset
from forge.branding_store import BrandingConflict, BrandingDenied, BrandingLimit
import hashlib
from uuid import uuid4


def theme(name='Acme Labs', **change):
    values = dict(name=name, login_copy='Welcome to Acme.', primary='#0B1D26', accent='#E07A2D', tint='#E8DCC1',
                  heading='montserrat', body='inter', assets={})
    values.update(change)
    return BrandingInput(**values)


def logo(payload, content_type='image/png'):
    return Asset(content_type, payload, hashlib.sha256(payload).hexdigest(), 32, 32)


class StoreContract:
    def test_an_unbranded_organization_reads_as_the_default_revision_zero(self):
        with self.harness() as h:
            self.assertEqual(h.store.read(h.member_a, h.org_a), DEFAULT)
            self.assertEqual(h.store.read(h.admin_a, h.org_a), DEFAULT)
            self.assertEqual(h.store.public(h.code_a), DEFAULT)

    def test_only_the_member_read_carries_the_company_code_and_it_does_not_change_equality(self):
        with self.harness() as h:
            for who in (h.member_a, h.admin_a):
                self.assertEqual(h.store.read(who, h.org_a).code, h.code_a)
            self.assertEqual(h.store.read(h.admin_b, h.org_b).code, h.code_b)
            saved = h.store.save(h.admin_a, h.org_a, 0, theme())
            self.assertIsNone(saved.code)
            self.assertIsNone(h.store.public(h.code_a).code)
            read = h.store.read(h.member_a, h.org_a)
            self.assertEqual((read.code, read), (h.code_a, saved), 'the code is a carrier, not part of the branding value')

    def test_save_advances_the_revision_and_is_visible_to_members_and_the_public(self):
        with self.harness() as h:
            saved = h.store.save(h.admin_a, h.org_a, 0, theme())
            self.assertEqual((saved.revision, saved.name, saved.primary, saved.heading), (1, 'Acme Labs', '#0B1D26', 'montserrat'))
            self.assertEqual(h.store.read(h.member_a, h.org_a), saved)
            self.assertEqual(h.store.public(h.code_a), saved)
            self.assertEqual(h.store.public(h.code_b), DEFAULT, 'another organization is unaffected')
            second = h.store.save(h.admin_a, h.org_a, 1, theme('Acme Two', accent='#ABCDEF'))
            self.assertEqual((second.revision, second.accent), (2, '#ABCDEF'))

    def test_a_stale_revision_conflicts_and_changes_nothing(self):
        with self.harness() as h:
            first = h.store.save(h.admin_a, h.org_a, 0, theme())
            for expected in (0, 2, 9):
                with self.assertRaises(BrandingConflict):
                    h.store.save(h.admin_a, h.org_a, expected, theme('Other'))
            self.assertEqual(h.store.read(h.admin_a, h.org_a), first)

    def test_only_administrators_of_the_organization_may_save_or_upload(self):
        with self.harness() as h:
            for digest, org in ((h.member_a, h.org_a), (h.admin_b, h.org_a), (h.admin_a, h.org_b), (h.admin_a, uuid4()),
                                ('0' * 64, h.org_a), ('not-a-digest', h.org_a)):
                with self.subTest(digest=digest[:8], org=str(org)[:8]):
                    with self.assertRaises(BrandingDenied):
                        h.store.save(digest, org, 0, theme())
                    with self.assertRaises(BrandingDenied):
                        h.store.put_asset(digest, org, logo(b'x'))
                    with self.assertRaises(BrandingDenied):
                        h.store.reset(digest, org, 0)
            self.assertEqual(h.store.read(h.admin_a, h.org_a), DEFAULT)

    def test_reads_are_limited_to_members_of_that_organization(self):
        with self.harness() as h:
            for digest, org in ((h.admin_b, h.org_a), (h.member_a, h.org_b), (h.member_a, uuid4()), ('0' * 64, h.org_a)):
                with self.assertRaises(BrandingDenied):
                    h.store.read(digest, org)

    def test_assets_are_uploaded_idempotently_and_only_the_same_organization_can_reference_them(self):
        with self.harness() as h:
            mark = logo(b'\x89PNG-mark')
            self.assertIs(h.store.put_asset(h.admin_a, h.org_a, mark), True)
            self.assertIs(h.store.put_asset(h.admin_a, h.org_a, mark), False)
            with self.assertRaises(ValueError):
                h.store.save(h.admin_b, h.org_b, 0, theme(assets={'isotipo': mark.sha256}))
            saved = h.store.save(h.admin_a, h.org_a, 0, theme(assets={'isotipo': mark.sha256, 'logoDark': mark.sha256}))
            self.assertEqual(saved.assets, {'logoDark': mark.sha256, 'isotipo': mark.sha256})
            with self.assertRaises(ValueError):
                h.store.save(h.admin_a, h.org_a, 1, theme(assets={'logoLight': 'c' * 64}))
            self.assertEqual(h.store.read(h.admin_a, h.org_a).revision, 1)

    def test_assets_are_served_only_while_a_current_revision_references_them(self):
        with self.harness() as h:
            first, second = logo(b'\x89PNG-first'), logo(b'RIFF-second', 'image/webp')
            h.store.put_asset(h.admin_a, h.org_a, first)
            h.store.put_asset(h.admin_a, h.org_a, second)
            self.assertIsNone(h.store.asset(first.sha256), 'uploaded but unpublished')
            h.store.save(h.admin_a, h.org_a, 0, theme(assets={'logoLight': first.sha256}))
            served = h.store.asset(first.sha256)
            self.assertEqual((served.content_type, bytes(served.data)), ('image/png', b'\x89PNG-first'))
            self.assertIsNone(h.store.asset(second.sha256))
            h.store.save(h.admin_a, h.org_a, 1, theme(assets={'logoLight': second.sha256}))
            self.assertIsNone(h.store.asset(first.sha256), 'replaced by a newer revision')
            self.assertEqual(h.store.asset(second.sha256).content_type, 'image/webp')
            for value in ('A' * 64, 'f' * 64, 'short', '', None):
                self.assertIsNone(h.store.asset(value))

    def test_reset_is_a_new_revision_with_the_default_theme_and_no_assets(self):
        with self.harness() as h:
            mark = logo(b'reset-mark')
            h.store.put_asset(h.admin_a, h.org_a, mark)
            h.store.save(h.admin_a, h.org_a, 0, theme(assets={'isotipo': mark.sha256}))
            reset = h.store.reset(h.admin_a, h.org_a, 1)
            self.assertEqual(reset, branding.Branding(2, DEFAULT.name, DEFAULT.login_copy, DEFAULT.primary, DEFAULT.accent,
                                                      DEFAULT.tint, DEFAULT.heading, DEFAULT.body, {}))
            self.assertEqual(h.store.public(h.code_a), reset)
            with self.assertRaises(BrandingConflict):
                h.store.reset(h.admin_a, h.org_a, 1)
            self.assertIsNone(h.store.asset(mark.sha256), 'no longer referenced by the current revision')

    def test_the_asset_count_per_organization_is_capped_but_known_hashes_stay_accepted(self):
        with self.harness() as h:
            for index in range(24):
                self.assertIs(h.store.put_asset(h.admin_a, h.org_a, logo(b'logo-%d' % index)), True)
            with self.assertRaises(BrandingLimit):
                h.store.put_asset(h.admin_a, h.org_a, logo(b'one-too-many'))
            self.assertIs(h.store.put_asset(h.admin_a, h.org_a, logo(b'logo-3')), False)
            self.assertIs(h.store.put_asset(h.admin_b, h.org_b, logo(b'logo-3')), True, 'the cap is per organization')

    def test_unknown_inactive_and_malformed_company_codes_all_read_as_none(self):
        with self.harness() as h:
            h.deactivate(h.code_b)
            for code in (h.code_b, 'nope', 'ORG-A', "org-a'--", '', '-org-a', 'a' * 64, None, 'org-a\n', 'org_a'):
                with self.subTest(code=code):
                    self.assertIsNone(h.store.public(code))
            self.assertEqual(h.store.public(h.code_a), DEFAULT)
