"""TOTP (RFC 6238 over RFC 4226) with the standard-library only: published vectors, the verification window, enrollment
material, recovery codes and the sealing of the shared secret."""
import base64
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.platform_totp import (RECOVERY_CODES, SecretSealer, SecretUnreadable, generate_recovery_codes, generate_secret,
                                 hash_recovery_code, hotp, match_step, normalize_recovery_code, otpauth_uri, totp)

RFC_SECRET = b'12345678901234567890'  # RFC 4226 / RFC 6238 appendix: ASCII "12345678901234567890"


class PublishedVectors(unittest.TestCase):
    def test_hotp_matches_the_rfc_4226_appendix_d_table(self):
        expected = ('755224', '287082', '359152', '969429', '338314', '254676', '287922', '162583', '399871', '520489')
        self.assertEqual([hotp(RFC_SECRET, counter) for counter in range(10)], list(expected))

    def test_totp_matches_the_rfc_6238_sha1_table_for_every_published_time(self):
        table = ((59, '94287082'), (1111111109, '07081804'), (1111111111, '14050471'), (1234567890, '89005924'),
                 (2000000000, '69279037'), (20000000000, '65353130'))
        for seconds, code in table:
            with self.subTest(seconds=seconds):
                self.assertEqual(totp(RFC_SECRET, seconds // 30, digits=8), code)

    def test_the_six_digit_code_is_the_low_six_digits_of_the_published_eight_digit_one(self):
        self.assertEqual(totp(RFC_SECRET, 59 // 30), '287082')
        self.assertEqual(totp(RFC_SECRET, 1111111109 // 30), '081804')  # leading zero is kept


class VerificationWindow(unittest.TestCase):
    NOW = 1111111109

    def test_the_current_the_previous_and_the_next_step_are_accepted_and_report_their_step(self):
        step = self.NOW // 30
        for offset in (-1, 0, 1):
            with self.subTest(offset=offset):
                self.assertEqual(match_step(RFC_SECRET, totp(RFC_SECRET, step + offset), self.NOW), step + offset)

    def test_two_steps_away_and_wrong_codes_are_refused(self):
        step = self.NOW // 30
        for offset in (-2, 2, -10):
            with self.subTest(offset=offset):
                self.assertIsNone(match_step(RFC_SECRET, totp(RFC_SECRET, step + offset), self.NOW))
        self.assertIsNone(match_step(RFC_SECRET, '000000', self.NOW))

    def test_only_exactly_six_ascii_digits_are_even_considered(self):
        valid = totp(RFC_SECRET, self.NOW // 30)
        for code in (valid + '0', valid[:-1], ' ' + valid, valid + ' ', valid[:3] + ' ' + valid[3:], '', 'abcdef', '１２３４５６',
                     None, 123456, valid.encode()):
            with self.subTest(code=code):
                self.assertIsNone(match_step(RFC_SECRET, code, self.NOW))

    def test_a_different_secret_never_matches_the_same_code(self):
        other = generate_secret()
        self.assertIsNone(match_step(other, totp(RFC_SECRET, self.NOW // 30), self.NOW))


class EnrollmentMaterial(unittest.TestCase):
    def test_a_secret_is_twenty_random_bytes_and_never_repeats(self):
        first, second = generate_secret(), generate_secret()
        self.assertEqual((len(first), len(second)), (20, 20))
        self.assertNotEqual(first, second)

    def test_the_provisioning_uri_carries_the_base32_secret_and_url_encoded_labels(self):
        uri = otpauth_uri(RFC_SECRET, 'owner@example.test')
        self.assertEqual(uri, 'otpauth://totp/Prometheon%20Forge:owner%40example.test?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
                              '&issuer=Prometheon%20Forge&algorithm=SHA1&digits=6&period=30')
        self.assertEqual(base64.b32decode('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'), RFC_SECRET)
        with self.assertRaises(ValueError):
            otpauth_uri(RFC_SECRET, 'bad\nlabel')


class RecoveryCodes(unittest.TestCase):
    def test_ten_distinct_eighty_bit_codes_in_four_groups(self):
        codes = generate_recovery_codes()
        self.assertEqual((len(codes), len(set(codes)), RECOVERY_CODES), (10, 10, 10))
        for code in codes:
            self.assertRegex(code, r'^[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$')
        self.assertNotEqual(generate_recovery_codes(), codes)

    def test_hashing_ignores_case_dashes_and_spaces_and_is_a_sha256_hex_digest(self):
        code = 'ABCD-EFGH-IJKL-MNOP'
        reference = hash_recovery_code(code)
        self.assertRegex(reference, r'^[0-9a-f]{64}$')
        for variant in ('abcd-efgh-ijkl-mnop', 'ABCDEFGHIJKLMNOP', ' abcd efgh ijkl mnop ', 'AbCd-EfGh-IjKl-MnOp'):
            with self.subTest(variant=variant):
                self.assertEqual(hash_recovery_code(variant), reference)
        self.assertNotEqual(hash_recovery_code('ABCD-EFGH-IJKL-MNOQ'), reference)

    def test_malformed_codes_normalize_to_nothing_and_never_hash(self):
        self.assertEqual(normalize_recovery_code('abcd-efgh-ijkl-mnop'), 'ABCDEFGHIJKLMNOP')
        for bad in ('', 'ABCD-EFGH-IJKL', 'ABCD-EFGH-IJKL-MNOPQ', 'ABCD-EFGH-IJKL-MNO1', 'ABCD-EFGH-IJKL-MNO!', None, 42,
                    'ABCD-EFGH-IJKL-MNOP\n0'):
            with self.subTest(bad=bad):
                self.assertIsNone(normalize_recovery_code(bad))
                with self.assertRaises(ValueError):
                    hash_recovery_code(bad)


class SecretSealing(unittest.TestCase):
    def test_a_sealed_secret_round_trips_and_does_not_contain_the_secret(self):
        sealer = SecretSealer(Fernet.generate_key())
        secret = generate_secret()
        sealed = sealer.seal(secret)
        self.assertEqual(sealer.open(sealed), secret)
        self.assertNotIn(base64.b32encode(secret).decode(), sealed)
        self.assertNotEqual(sealer.seal(secret), sealed, 'a fresh nonce every time')

    def test_a_wrong_key_a_tampered_token_and_junk_are_one_finite_failure(self):
        sealer, other = SecretSealer(Fernet.generate_key()), SecretSealer(Fernet.generate_key())
        sealed = sealer.seal(generate_secret())
        for token in (sealed[:-4] + 'AAAA', 'junk', '', None):
            with self.subTest(token=token), self.assertRaises(SecretUnreadable):
                sealer.open(token)
        with self.assertRaises(SecretUnreadable):
            other.open(sealed)

    def test_the_key_must_be_explicit_fernet_bytes_and_the_secret_must_be_twenty_bytes(self):
        for key in ('not bytes', b'short', None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                SecretSealer(key)
        for secret in (b'', b'x' * 19, b'x' * 21, 'text'):
            with self.subTest(secret=secret), self.assertRaises(ValueError):
                SecretSealer(Fernet.generate_key()).seal(secret)


if __name__ == '__main__':
    unittest.main()
