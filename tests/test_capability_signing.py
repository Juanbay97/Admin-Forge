"""Signed effective policy: canonical JSON, Ed25519 with a key id, tamper/expiry/epoch rejection and the published contract vectors."""
import base64
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from forge import capability_contract
from forge.capability_signing import (DocumentRejected, LIFETIME_SECONDS, PolicySigner, SCHEMA, canonical, kid_of, load_signer, verify_document)

SEED = bytes(range(32))
OTHER = bytes(range(1, 33))
ORG = '11111111-1111-4111-8111-111111111111'
CAPABILITIES = [{'id': 'pdf', 'kind': 'skill', 'state': 'on', 'enabled': True, 'min_sandbox_level': 0, 'version': '1.0.0', 'manifest_sha256': None,
                 'credential_locus': 'none'}]
NOW = 1_800_000_000


def body(**change):
    document = {'schema': SCHEMA, 'org': ORG, 'platform_epoch': 5, 'org_epoch': 3, 'issued_at': '2027-01-15T08:00:00Z',
                'expires_at': '2027-01-16T08:00:00Z', 'reported_level': 3, 'capabilities': CAPABILITIES}
    document.update(change)
    return document


class CanonicalTests(unittest.TestCase):
    def test_sorted_keys_no_whitespace_ascii_only_and_the_signature_is_excluded(self):
        self.assertEqual(canonical({'b': [1, {'z': None, 'a': True}], 'a': 'é', 'sig': 'x'}), b'{"a":"\\u00e9","b":[1,{"a":true,"z":null}]}')
        self.assertEqual(canonical({'sig': 'x'}), b'{}')


class SignerTests(unittest.TestCase):
    def test_a_signed_document_verifies_and_carries_the_key_id(self):
        signer = PolicySigner(SEED)
        signed = signer.sign(body())
        self.assertEqual((signed['kid'], signed['schema']), (signer.kid, SCHEMA))
        self.assertEqual(signer.kid, kid_of(Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw()))
        verify_document(signed, signer.keyset(), now=NOW)
        self.assertEqual(signer.sign(body()), signed, 'Ed25519 is deterministic')

    def test_tampering_any_field_or_the_signature_fails(self):
        signer = PolicySigner(SEED)
        signed = signer.sign(body())
        mutations = (('org', '22222222-2222-4222-8222-222222222222'), ('platform_epoch', 6), ('org_epoch', 4), ('reported_level', 4), ('issued_at', '2027-01-15T08:00:01Z'),
                     ('expires_at', '2027-02-16T08:00:00Z'), ('schema', 'forge.capability-policy.v2'))
        for key, value in mutations:
            with self.subTest(field=key), self.assertRaises(DocumentRejected) as caught:
                verify_document({**signed, key: value}, signer.keyset(), now=NOW)
            self.assertIn(str(caught.exception), ('bad_signature', 'bad_schema'))
        edited = copy.deepcopy(signed)
        edited['capabilities'][0]['enabled'] = False
        with self.assertRaises(DocumentRejected):
            verify_document(edited, signer.keyset(), now=NOW)
        edited = copy.deepcopy(signed)
        edited['capabilities'].append({'id': 'x', 'kind': 'skill'})
        with self.assertRaises(DocumentRejected):
            verify_document(edited, signer.keyset(), now=NOW)
        flipped = signed['sig'][:-2] + ('AA' if not signed['sig'].endswith('AA') else 'BB')
        with self.assertRaises(DocumentRejected):
            verify_document({**signed, 'sig': flipped}, signer.keyset(), now=NOW)
        for sig in ('', 'short', None, 5):
            with self.assertRaises(DocumentRejected):
                verify_document({**signed, 'sig': sig}, signer.keyset(), now=NOW)
        with self.assertRaises(DocumentRejected):
            verify_document({key: value for key, value in signed.items() if key != 'sig'}, signer.keyset(), now=NOW)

    def test_an_unknown_key_id_a_foreign_key_and_a_retired_key_set(self):
        signer, other = PolicySigner(SEED), PolicySigner(OTHER)
        signed = signer.sign(body())
        with self.assertRaises(DocumentRejected) as caught:
            verify_document(signed, other.keyset(), now=NOW)
        self.assertEqual(str(caught.exception), 'unknown_key')
        rotated = PolicySigner(OTHER, retired=(Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw(),))
        keys = rotated.keyset()
        self.assertEqual([(key['kid'], key['status']) for key in keys['keys']], [(rotated.kid, 'active'), (signer.kid, 'retired')])
        verify_document(signed, keys, now=NOW)  # overlapping keys: a document signed before the rotation still verifies
        verify_document(rotated.sign(body()), keys, now=NOW)

    def test_expiry_and_epoch_monotonicity_are_the_client_rules(self):
        signer = PolicySigner(SEED)
        signed = signer.sign(body())
        expires = 1_800_000_000 - 1  # a fixed instant before the NOW constant
        with self.assertRaises(DocumentRejected) as caught:
            verify_document(signed, signer.keyset(), now=1_900_000_000)
        self.assertEqual(str(caught.exception), 'expired')
        for minimum, accepted in (((5, 3), True), ((5, 2), True), ((4, 9), False), ((5, 4), False), ((6, 0), False)):
            with self.subTest(minimum=minimum):
                if accepted:
                    verify_document(signed, signer.keyset(), now=NOW, minimum_epochs=minimum)
                else:
                    with self.assertRaises(DocumentRejected) as caught:
                        verify_document(signed, signer.keyset(), now=NOW, minimum_epochs=minimum)
                    self.assertEqual(str(caught.exception), 'rollback')
        self.assertEqual(LIFETIME_SECONDS, 24 * 3600)

    def test_the_key_comes_from_a_base64_seed_and_a_bad_one_is_refused(self):
        encoded = base64.urlsafe_b64encode(SEED).decode().rstrip('=')
        self.assertEqual(load_signer(encoded).kid, PolicySigner(SEED).kid)
        for bad in ('', 'AAAA', encoded[:-4], encoded + 'AAAA', None, 5, '!!!'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load_signer(bad)


class ContractVectorTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(capability_contract.COMMITTED_PATH.read_text('utf-8'))

    def test_the_committed_file_is_exactly_what_the_generator_produces(self):
        self.assertEqual(self.contract, capability_contract.build())
        self.assertEqual(capability_contract.main(['--check']), 0)

    def test_every_positive_vector_verifies_and_every_negative_one_is_rejected_for_its_reason(self):
        keyset = self.contract['key_set']
        self.assertEqual(self.contract['contract_version'], 'forge.capability-policy.v1')
        self.assertIn('TEST', self.contract['note'])
        for vector in self.contract['vectors']:
            with self.subTest(vector=vector['name']):
                canonical_bytes = canonical(vector['document'])
                self.assertEqual(canonical_bytes.decode('ascii'), vector['canonical'])
                if vector['expect'] == 'valid':
                    verify_document(vector['document'], keyset, now=vector['now'], minimum_epochs=tuple(vector.get('minimum_epochs', (0, 0))))
                else:
                    with self.assertRaises(DocumentRejected) as caught:
                        verify_document(vector['document'], keyset, now=vector['now'], minimum_epochs=tuple(vector.get('minimum_epochs', (0, 0))))
                    self.assertEqual(str(caught.exception), vector['expect'])
        self.assertEqual({vector['expect'] for vector in self.contract['vectors']},
                         {'valid', 'bad_signature', 'unknown_key', 'expired', 'rollback'})

    def test_the_vectors_cover_a_blocked_attestation_a_locked_item_and_an_app_with_its_pin(self):
        states = {(item['kind'], item['state']) for vector in self.contract['vectors'] for item in vector['document'].get('capabilities', [])}
        self.assertTrue({('tool', 'blocked_attestation'), ('skill', 'forced_off'), ('app', 'on')} <= states)
        app = next(item for vector in self.contract['vectors'] for item in vector['document'].get('capabilities', []) if item['kind'] == 'app')
        self.assertRegex(app['manifest_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(app['granted_permissions'], ['ui.title'])

    def test_the_schema_section_lists_exactly_the_fields_the_server_signs(self):
        self.assertEqual(set(self.contract['schema']['document']), {'schema', 'org', 'platform_epoch', 'org_epoch', 'issued_at', 'expires_at',
                                                                    'reported_level', 'capabilities', 'kid', 'sig'})
        self.assertEqual(self.contract['schema']['canonicalization'], 'json.dumps(document without sig, sort_keys=True, separators=(",", ":"), ensure_ascii=True)')


if __name__ == '__main__':
    unittest.main()
