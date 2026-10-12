"""The in-memory fake satisfies the BrandingStore contract; the same suite runs against PostgreSQL."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from branding_contract import StoreContract
from branding_support import fake_harness
from forge import branding_store


class FakeStoreContractTests(StoreContract, unittest.TestCase):
    harness = staticmethod(fake_harness)


class PortTests(unittest.TestCase):
    def test_failures_are_distinct_uniform_exceptions_that_carry_no_detail(self):
        for error in (branding_store.BrandingDenied, branding_store.BrandingConflict, branding_store.BrandingLimit,
                      branding_store.BrandingUnavailable):
            self.assertTrue(issubclass(error, Exception))
            self.assertFalse(issubclass(error, ValueError))
            self.assertEqual(len(set(str(error()) for _ in range(2))), 1)
        self.assertEqual(len({str(error()) for error in (branding_store.BrandingDenied, branding_store.BrandingConflict)}), 2)

    def test_the_default_input_matches_the_default_branding(self):
        from forge.branding import DEFAULT, DEFAULT_INPUT, parse, public_view
        parsed = parse({'name': DEFAULT_INPUT.name, 'loginCopy': DEFAULT_INPUT.login_copy,
                        'theme': {'primary': DEFAULT_INPUT.primary, 'accent': DEFAULT_INPUT.accent, 'tint': DEFAULT_INPUT.tint,
                                  'heading': DEFAULT_INPUT.heading, 'body': DEFAULT_INPUT.body}})
        self.assertEqual(parsed, DEFAULT_INPUT)
        self.assertEqual(DEFAULT_INPUT.assets, {})
        self.assertEqual((DEFAULT.name, DEFAULT.login_copy), (DEFAULT_INPUT.name, DEFAULT_INPUT.login_copy))
        self.assertEqual(public_view(DEFAULT)['theme']['primary'], DEFAULT_INPUT.primary)


if __name__ == '__main__':
    unittest.main()
