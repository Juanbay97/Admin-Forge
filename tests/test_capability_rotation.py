"""Policy key rotation chain: a statement signed by the OLD key introduces the NEW key; a client pins new keys only that way."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.capability_rotation import (PINNING_SCHEMA, ROTATION_SCHEMA, RotationRejected, apply_rotations, key_usable, main,
                                       parse_rotations, sign_rotation, vectors, verify_rotation)
from forge.capability_signing import PolicySigner, b64u, canonical, unb64u

SEEDS = [bytes([n]) * 32 for n in (1, 2, 3)]
SIGNERS = [PolicySigner(seed) for seed in SEEDS]
PUBLIC = [signer.public_raw() for signer in SIGNERS]
KID = [signer.kid for signer in SIGNERS]
T1, T2 = '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z'
A_TO_B = sign_rotation(SEEDS[0], PUBLIC[1], T1)
B_TO_C = sign_rotation(SEEDS[1], PUBLIC[2], T2)


class StatementTests(unittest.TestCase):
    def test_the_statement_has_exactly_the_documented_shape_and_a_canonical_signature(self):
        self.assertEqual(A_TO_B, {'schema': ROTATION_SCHEMA, 'old_kid': KID[0], 'new_kid': KID[1], 'new_public_key': b64u(PUBLIC[1]),
                                  'issued_at': T1, 'sig': A_TO_B['sig']})
        self.assertEqual(ROTATION_SCHEMA, 'forge.policy-key-rotation.v1')
        self.assertEqual(PINNING_SCHEMA, 'forge.policy-pinning.v1')
        self.assertEqual(len(A_TO_B['sig']), 86)
        self.assertEqual(verify_rotation(A_TO_B, {KID[0]: PUBLIC[0]}), PUBLIC[1])
        self.assertEqual(canonical(A_TO_B), json.dumps({key: value for key, value in A_TO_B.items() if key != 'sig'},
                                                       sort_keys=True, separators=(',', ':')).encode())

    def test_every_forgery_or_malformation_is_one_stable_rejection(self):
        pinned = {KID[0]: PUBLIC[0]}
        forged = lambda **change: {**A_TO_B, **change}
        cases = {
            'unknown signer': (A_TO_B, {KID[2]: PUBLIC[2]}),
            'a different key under the same kid': (A_TO_B, {KID[0]: PUBLIC[2]}),
            'tampered new key': (forged(new_public_key=b64u(PUBLIC[2]), new_kid=KID[2]), pinned),
            'new kid does not match the key': (forged(new_kid=KID[2]), pinned),
            'tampered date': (forged(issued_at=T2), pinned),
            'wrong schema': (forged(schema='forge.policy-key-rotation.v2'), pinned),
            'extra key': ({**A_TO_B, 'role': 'admin'}, pinned),
            'missing signature': ({key: value for key, value in A_TO_B.items() if key != 'sig'}, pinned),
            'short signature': (forged(sig=A_TO_B['sig'][:-2]), pinned),
            'signature of another statement': (forged(sig=B_TO_C['sig']), pinned),
            'bad date': (forged(issued_at='2026-10-01'), pinned),
            'not an object': ([A_TO_B], pinned),
            'a key that is not 32 bytes': (forged(new_public_key='AAAA'), pinned),
        }
        for name, (statement, keys) in cases.items():
            with self.subTest(name), self.assertRaises(RotationRejected) as caught:
                verify_rotation(statement, keys)
            self.assertIn(str(caught.exception), ('bad_schema', 'unknown_key', 'bad_signature'))

    def test_signing_refuses_a_malformed_input(self):
        for args in ((b'short', PUBLIC[1], T1), (SEEDS[0], b'short', T1), (SEEDS[0], PUBLIC[1], 'tomorrow'), (SEEDS[0], PUBLIC[0], T1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                sign_rotation(*args)


class ClientChainTests(unittest.TestCase):
    """The reference of what a client does with the published statements (the desktop client implements the same rules)."""

    def test_a_pinned_key_adopts_the_next_key_and_the_chain_walks_in_any_order(self):
        for order in ((A_TO_B, B_TO_C), (B_TO_C, A_TO_B)):
            pinned = apply_rotations({KID[0]: PUBLIC[0]}, order)
            self.assertEqual({kid: key['public'] for kid, key in pinned.items()}, {KID[0]: PUBLIC[0], KID[1]: PUBLIC[1], KID[2]: PUBLIC[2]})
            self.assertEqual({kid: key['retired_at'] for kid, key in pinned.items()}, {KID[0]: T1, KID[1]: T2, KID[2]: None})

    def test_a_statement_from_a_key_that_is_not_pinned_changes_nothing(self):
        attacker = sign_rotation(bytes([9]) * 32, PolicySigner(bytes([8]) * 32).public_raw(), T1)
        pinned = apply_rotations({KID[0]: PUBLIC[0]}, [attacker, B_TO_C])
        self.assertEqual(set(pinned), {KID[0]})
        self.assertIsNone(pinned[KID[0]]['retired_at'])

    def test_a_replay_a_forgery_and_an_already_pinned_key_are_harmless(self):
        once = apply_rotations({KID[0]: PUBLIC[0]}, [A_TO_B])
        again = apply_rotations({kid: key['public'] for kid, key in once.items()}, [A_TO_B, A_TO_B])
        self.assertEqual({kid: key['public'] for kid, key in again.items()}, {KID[0]: PUBLIC[0], KID[1]: PUBLIC[1]})
        forged = {**A_TO_B, 'new_public_key': b64u(PUBLIC[2]), 'new_kid': KID[2]}
        self.assertEqual(set(apply_rotations({KID[0]: PUBLIC[0]}, [forged])), {KID[0]})

    def test_a_retired_key_is_good_only_for_documents_issued_before_its_replacement(self):
        pinned = apply_rotations({KID[0]: PUBLIC[0]}, [A_TO_B])
        self.assertTrue(key_usable(pinned[KID[0]], '2026-09-30T23:59:59Z'))
        self.assertFalse(key_usable(pinned[KID[0]], T1))
        self.assertFalse(key_usable(pinned[KID[0]], '2027-01-01T00:00:00Z'))
        self.assertTrue(key_usable(pinned[KID[1]], '2027-01-01T00:00:00Z'))


class ConfigurationTests(unittest.TestCase):
    def test_a_consistent_chain_is_accepted_in_order(self):
        parsed = parse_rotations([A_TO_B, B_TO_C], active_public=PUBLIC[2], retired=(PUBLIC[0], PUBLIC[1]))
        self.assertEqual(parsed, (A_TO_B, B_TO_C))
        self.assertEqual(parse_rotations([], active_public=PUBLIC[0], retired=()), ())

    def test_a_chain_that_does_not_hold_together_is_refused(self):
        other = sign_rotation(bytes([7]) * 32, PUBLIC[2], T1)
        cases = {
            'signer is not a retired key of this deployment': ([other], PUBLIC[2], (PUBLIC[0],)),
            'the new key is neither retired nor active': ([A_TO_B], PUBLIC[2], (PUBLIC[0],)),
            'a tampered signature': ([{**A_TO_B, 'sig': B_TO_C['sig']}], PUBLIC[1], (PUBLIC[0],)),
            'a duplicate': ([A_TO_B, A_TO_B], PUBLIC[1], (PUBLIC[0],)),
            'not a list': (A_TO_B, PUBLIC[1], (PUBLIC[0],)),
            'too many': ([A_TO_B] * 9, PUBLIC[1], (PUBLIC[0],)),
            'signed by the active key': ([sign_rotation(SEEDS[1], PUBLIC[2], T1)], PUBLIC[1], (PUBLIC[2],)),
        }
        for name, (items, active, retired) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                parse_rotations(items, active_public=active, retired=retired)


class PinningDocumentTests(unittest.TestCase):
    def test_the_signer_publishes_keys_and_the_chain_as_one_document(self):
        signer = PolicySigner(SEEDS[2], retired=(PUBLIC[0], PUBLIC[1]), rotations=(A_TO_B, B_TO_C))
        document = signer.pinning()
        self.assertEqual(document, {'schema': PINNING_SCHEMA, 'keys': signer.keyset()['keys'], 'rotations': [A_TO_B, B_TO_C]})
        self.assertEqual([key['status'] for key in document['keys']], ['active', 'retired', 'retired'])
        self.assertEqual(PolicySigner(SEEDS[0]).pinning(), {'schema': PINNING_SCHEMA, 'keys': PolicySigner(SEEDS[0]).keyset()['keys'], 'rotations': []})

    def test_the_published_key_set_is_unchanged_by_rotations(self):
        plain = PolicySigner(SEEDS[2], retired=(PUBLIC[0], PUBLIC[1]))
        rotated = PolicySigner(SEEDS[2], retired=(PUBLIC[0], PUBLIC[1]), rotations=(A_TO_B, B_TO_C))
        self.assertEqual(plain.keyset(), rotated.keyset())


class VectorTests(unittest.TestCase):
    def test_the_committed_vectors_equal_the_generated_ones_and_replay(self):
        path = ROOT/'contract'/'forge-policy-rotation.v1.json'
        committed = json.loads(path.read_text('utf-8'))
        self.assertEqual(committed, vectors())
        first = committed['pinned'][0]
        pinned = apply_rotations({first['kid']: unb64u(first['public_key'])}, committed['statements'])
        self.assertEqual(len(pinned), 3)
        self.assertEqual([(kid, key['retired_at']) for kid, key in pinned.items()], [(item['kid'], item['retired_at']) for item in committed['expected']])
        for case in committed['rejected']:
            with self.subTest(case['name']):
                self.assertEqual(set(apply_rotations({first['kid']: unb64u(first['public_key'])}, [case['statement']])), {first['kid']})


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_sign_prints_one_statement_the_old_key_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory)/'old.key', Path(directory)/'new.key'
            old.write_text(b64u(SEEDS[0]) + '\n', 'utf-8')
            new.write_text(b64u(SEEDS[1]), 'utf-8')
            code, text = self.run_cli(['sign', '--old-seed-file', str(old), '--new-seed-file', str(new), '--issued-at', T1])
            self.assertEqual((code, json.loads(text)), (0, A_TO_B))
            code, text = self.run_cli(['sign', '--old-seed-file', str(old), '--new-public-key', b64u(PUBLIC[1]), '--issued-at', T1])
            self.assertEqual((code, json.loads(text)), (0, A_TO_B))
            self.assertNotIn(b64u(SEEDS[0]), text)

    def test_every_failure_is_a_finite_code_that_never_echoes_a_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory)/'old.key'
            old.write_text(b64u(SEEDS[0]), 'utf-8')
            for argv in (['sign'], ['bogus'], ['sign', '--old-seed-file', str(old)],
                         ['sign', '--old-seed-file', str(Path(directory)/'missing'), '--new-public-key', b64u(PUBLIC[1])],
                         ['sign', '--old-seed-file', str(old), '--new-public-key', 'AAAA'],
                         ['sign', '--old-seed-file', str(old), '--new-public-key', b64u(PUBLIC[1]), '--issued-at', 'soon']):
                with self.subTest(argv=argv):
                    code, text = self.run_cli(argv)
                    self.assertNotEqual(code, 0)
                    self.assertIn(json.loads(text)['code'], ('INVALID_ARGUMENTS', 'KEY_FILE_INVALID', 'INVALID_KEY', 'INVALID_DATE'))
                    self.assertNotIn(b64u(SEEDS[0]), text)


if __name__ == '__main__':
    unittest.main()
