"""Policy key distribution: the hidden pinning route and the operator's rotation chain in the production configuration."""
import base64
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import contract
from forge.capability_effective import EffectivePolicy
from forge.capability_model import CapabilityUnavailable
from forge.capability_rotation import PINNING_SCHEMA, sign_rotation
from forge.capability_signing import PolicySigner, b64u, load_signer
from test_capability_effective import NOW, Store, client, store
from test_prod_config import Fixture, public_key

SEEDS = [bytes([n]) * 32 for n in (1, 2, 3)]
PUBLIC = [PolicySigner(seed).public_raw() for seed in SEEDS]
A_TO_B = sign_rotation(SEEDS[0], PUBLIC[1], '2026-10-01T00:00:00Z')
B_TO_C = sign_rotation(SEEDS[1], PUBLIC[2], '2026-11-01T00:00:00Z')
ROTATED = PolicySigner(SEEDS[2], retired=(PUBLIC[0], PUBLIC[1]), rotations=(A_TO_B, B_TO_C))
PATH = '/forge/v1/capabilities/pinning'


class PinningRouteTests(unittest.TestCase):
    def test_the_set_is_public_hidden_and_carries_the_keys_and_the_chain(self):
        http, app = client(EffectivePolicy(store(), ROTATED, clock=lambda: NOW))
        response = http.get(PATH)
        self.assertEqual((response.status_code, response.json()), (200, ROTATED.pinning()))
        self.assertEqual(response.json()['schema'], PINNING_SCHEMA)
        self.assertIn(PATH, {route.path for route in app.routes})
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))), 'outside the contract pin')

    def test_without_a_signing_key_there_is_nothing_to_pin(self):
        http, _ = client(EffectivePolicy(store(), None, clock=lambda: NOW))
        response = http.get(PATH)
        self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'))

    def test_the_service_answers_the_same_document(self):
        self.assertEqual(EffectivePolicy(store(), ROTATED).pinning(), ROTATED.pinning())
        with self.assertRaises(CapabilityUnavailable):
            EffectivePolicy(store(), None).pinning()


class RotationConfigTests(unittest.TestCase):
    SEED = base64.urlsafe_b64encode(SEEDS[2]).decode().rstrip('=')
    RETIRED = ' '.join(b64u(raw) for raw in PUBLIC[:2])
    CHAIN = json.dumps([A_TO_B, B_TO_C])

    def test_the_chain_is_optional_and_comes_from_the_environment_or_a_file(self):
        with Fixture() as f:
            base = dict(FORGE_POLICY_KEY=self.SEED, FORGE_POLICY_RETIRED_KEYS=self.RETIRED)
            self.assertEqual(f.load(**base).policy_rotations, ())
            self.assertEqual(f.load(**base, FORGE_POLICY_ROTATIONS='').policy_rotations, (), 'compose passes an empty value')
            self.assertEqual(f.load(**base, FORGE_POLICY_ROTATIONS=self.CHAIN).policy_rotations, (A_TO_B, B_TO_C))
            (f.root/'rotations.json').write_text(self.CHAIN + '\n', 'utf-8')
            config = f.load(**base, FORGE_POLICY_ROTATIONS_FILE=str(f.root/'rotations.json'))
            self.assertEqual(config.policy_rotations, (A_TO_B, B_TO_C))
            signer = load_signer(config.policy_key, retired=config.policy_retired_keys, rotations=config.policy_rotations)
            self.assertEqual(signer.pinning(), ROTATED.pinning())

    def test_a_chain_that_does_not_hold_together_fails_the_whole_load_by_name(self):
        with Fixture() as f:
            base = dict(FORGE_POLICY_KEY=self.SEED, FORGE_POLICY_RETIRED_KEYS=self.RETIRED)
            cases = {'not json': 'nope', 'an object': json.dumps(A_TO_B), 'a tampered signature': json.dumps([{**A_TO_B, 'sig': B_TO_C['sig']}]),
                     'a stranger': json.dumps([sign_rotation(bytes([9]) * 32, PUBLIC[2], '2026-10-01T00:00:00Z')]),
                     'a duplicate': json.dumps([A_TO_B, A_TO_B])}
            for name, value in cases.items():
                with self.subTest(name):
                    f.refused(self, 'FORGE_POLICY_ROTATIONS', **base, FORGE_POLICY_ROTATIONS=value)
            f.refused(self, 'FORGE_POLICY_ROTATIONS', **base, FORGE_POLICY_ROTATIONS=self.CHAIN, FORGE_POLICY_ROTATIONS_FILE=str(f.root/'x'))
            f.refused(self, 'FORGE_POLICY_ROTATIONS', **base, FORGE_POLICY_ROTATIONS_FILE=str(f.root/'missing.json'))
            f.refused(self, 'FORGE_POLICY_ROTATIONS', FORGE_POLICY_ROTATIONS=self.CHAIN)  # a chain without a signing key makes no sense
            f.refused(self, 'FORGE_POLICY_ROTATIONS', FORGE_POLICY_KEY=self.SEED, FORGE_POLICY_ROTATIONS=self.CHAIN)  # no retired keys to chain from

    def test_both_names_are_known_keys(self):
        from forge.prod_config import KNOWN_KEYS
        self.assertTrue({'FORGE_POLICY_ROTATIONS', 'FORGE_POLICY_ROTATIONS_FILE'} <= set(KNOWN_KEYS))
        self.assertEqual(public_key(SEEDS[0]), b64u(PUBLIC[0]))


if __name__ == '__main__':
    unittest.main()
