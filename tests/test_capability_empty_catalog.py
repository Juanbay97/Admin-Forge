"""An empty capability catalog is a defined state (a signed, empty policy), never a 503."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.capability_effective import EffectivePolicy
from forge.capability_model import Snapshot
from forge.capability_signing import PolicySigner, verify_document
from forge.capability_store import _snapshot
from test_capability_effective import NOW, ORG, SIGNER, TOKEN, Store


class EmptyCatalogTests(unittest.TestCase):
    def test_no_catalog_rows_is_an_empty_snapshot_at_the_default_epochs(self):
        self.assertEqual(_snapshot([]), Snapshot(1, 1, (), {}, {}, {}))

    def test_the_effective_policy_is_signed_and_carries_no_capability(self):
        policy = EffectivePolicy(Store(_snapshot([])), SIGNER, clock=lambda: NOW)
        for level in (None, 0, 4):
            with self.subTest(level=level):
                document = policy.document(TOKEN, ORG, level)
                self.assertEqual((document['capabilities'], document['platform_epoch'], document['org_epoch']), ([], 1, 1))
                self.assertEqual(document['org'], str(ORG))
                verify_document(document, SIGNER.keyset(), now=NOW)

    def test_a_malformed_row_still_fails_closed(self):
        from forge.capability_model import CapabilityUnavailable
        with self.assertRaises(CapabilityUnavailable):
            _snapshot([('bad id', 'skill', '1.0.0', 'low', True, 'on', 0, None, 'none', [], [], None, 'none', None, 'none', None, 1, 1)])


if __name__ == '__main__':
    unittest.main()
