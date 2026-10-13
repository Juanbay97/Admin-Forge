"""Connector secret sealing: every field of the binding is part of the ciphertext; a missing or wrong key fails closed."""
import base64
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.connector_cipher import Binding, ConnectorCipher, ConnectorCipherError

KEY = Fernet.generate_key()
ORG, OTHER_ORG = uuid4(), uuid4()
USER_A, USER_B = str(uuid4()), str(uuid4())
SECRET = {'access_token': 'tok-ACCESS-0123456789', 'refresh_token': 'tok-REFRESH-9876543210'}


def binding(**change):
    values = dict(organization=ORG, scope='user', subject=USER_A, capability='connector:github', revision=1)
    values.update(change)
    return Binding(**values)


class SealOpenTests(unittest.TestCase):
    def test_a_sealed_secret_opens_only_with_the_exact_binding(self):
        cipher = ConnectorCipher(KEY)
        token = cipher.seal(binding(), SECRET)
        self.assertEqual(cipher.open(binding(), token), SECRET)
        self.assertNotIn('ACCESS', token)

    def test_every_binding_field_drift_fails_to_open(self):
        cipher = ConnectorCipher(KEY)
        token = cipher.seal(binding(), SECRET)
        for name, value in (('organization', OTHER_ORG), ('scope', 'org'), ('subject', USER_B), ('capability', 'connector:notion'), ('revision', 2)):
            with self.subTest(field=name), self.assertRaises(ConnectorCipherError):
                cipher.open(binding(**{name: value}), token)

    def test_user_a_token_moved_to_user_b_row_fails(self):
        cipher = ConnectorCipher(KEY)
        moved = cipher.seal(binding(subject=USER_A), SECRET)
        with self.assertRaises(ConnectorCipherError):
            cipher.open(binding(subject=USER_B), moved)

    def test_org_scope_secrets_bind_no_user_and_are_distinct_from_user_scope(self):
        cipher = ConnectorCipher(KEY)
        org_token = cipher.seal(binding(scope='org', subject=''), {'api_key': 'k-123456'})
        self.assertEqual(cipher.open(binding(scope='org', subject=''), org_token), {'api_key': 'k-123456'})
        with self.assertRaises(ConnectorCipherError):
            cipher.open(binding(scope='user', subject=''), org_token)

    def test_tampered_foreign_and_malformed_tokens_fail_with_one_error_that_never_echoes(self):
        cipher = ConnectorCipher(KEY)
        token = cipher.seal(binding(), SECRET)
        for bad in (token[:-4] + 'AAAA', ConnectorCipher(Fernet.generate_key()).seal(binding(), SECRET), '', 'x' * 200, None, 5, token + 'x'):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(ConnectorCipherError) as caught:
                cipher.open(binding(), bad)
            self.assertNotIn('ACCESS', str(caught.exception))

    def test_invalid_bindings_and_secrets_are_refused_before_sealing(self):
        cipher = ConnectorCipher(KEY)
        for bad in ({'organization': 'not-uuid'}, {'scope': 'platform'}, {'capability': 'bad id'}, {'revision': 0}, {'revision': True}, {'subject': 5}):
            with self.subTest(bad=bad), self.assertRaises(ConnectorCipherError):
                cipher.seal(binding(**bad), SECRET)
        for secret in ({}, [], 'text', {'k': 5}, {'k': ''}, {'k': 'v' * 20000}, {'a' * 200: 'v'}):
            with self.subTest(secret=str(secret)[:20]), self.assertRaises(ConnectorCipherError):
                cipher.seal(binding(), secret)


class KeyTests(unittest.TestCase):
    def test_construction_fails_closed_without_a_valid_key(self):
        for bad in (None, b'', 'text', b'not-a-fernet-key', 5, [], ()):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(ConnectorCipherError):
                ConnectorCipher(bad)

    def test_rotation_seals_with_the_first_key_and_still_opens_with_the_old_one(self):
        old, new = Fernet.generate_key(), Fernet.generate_key()
        sealed_before = ConnectorCipher(old).seal(binding(), SECRET)
        rotated = ConnectorCipher([new, old])
        self.assertEqual(rotated.open(binding(), sealed_before), SECRET)
        sealed_after = rotated.seal(binding(), SECRET)
        self.assertEqual(ConnectorCipher(new).open(binding(), sealed_after), SECRET)
        with self.assertRaises(ConnectorCipherError):
            ConnectorCipher(old).open(binding(), sealed_after)

    def test_the_key_must_be_separate_from_the_keys_it_is_told_to_avoid(self):
        other = Fernet.generate_key()
        ConnectorCipher(KEY, distinct_from=[other])
        with self.assertRaises(ConnectorCipherError):
            ConnectorCipher(KEY, distinct_from=[KEY])
        raw_policy_seed = base64.urlsafe_b64encode(base64.urlsafe_b64decode(KEY)).decode().rstrip('=')
        with self.assertRaises(ConnectorCipherError):
            ConnectorCipher(KEY, distinct_from=[raw_policy_seed])

    def test_repr_never_shows_the_key(self):
        self.assertNotIn(KEY.decode(), repr(ConnectorCipher(KEY)))


class HintTests(unittest.TestCase):
    def test_the_hint_is_the_last_four_characters_only_for_long_enough_secrets(self):
        from forge.connector_cipher import hint
        self.assertEqual(hint('sk-abcdefgh1234'), '1234')
        self.assertIsNone(hint('short'))
        self.assertIsNone(hint(''))


if __name__ == '__main__':
    unittest.main()
