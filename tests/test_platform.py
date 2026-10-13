"""Platform service over an injected store: bearer capability -> digest, argument bounds, finite error codes."""
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.invitations import capability_digest
from cryptography.fernet import Fernet
from forge.platform import (AuditEntry, Company, MfaChallenge, MfaEnrolled, MfaInvalid, MfaLocked, MfaRequired, MfaStatus,
                            PlatformDenied, PlatformIdentity, PlatformInvalid, PlatformNotFound, PlatformService,
                            PlatformUnavailable)
from forge.platform_totp import SecretSealer, generate_secret, hash_recovery_code, match_step, totp

ACCOUNT, ORG = uuid4(), uuid4()
NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


class FakeStore:
    """Records what reached it; answers like the database would for the one known digest."""
    def __init__(self, known=None):
        self.known, self.calls = known, []

    def _check(self, digest):
        if digest != self.known:
            raise PlatformDenied()

    def me(self, digest):
        self.calls.append(('me', digest))
        self._check(digest)
        return PlatformIdentity(ACCOUNT, 'platform_owner')

    def companies(self, digest, after, page):
        self.calls.append(('companies', digest, after, page))
        self._check(digest)
        return [Company(ORG, 'acme', 'Acme', True)]

    def company(self, digest, organization_id):
        self.calls.append(('company', digest, organization_id))
        self._check(digest)
        return Company(ORG, 'acme', 'Acme', True) if organization_id == ORG else None

    def audit(self, digest, before, page):
        self.calls.append(('audit', digest, before, page))
        self._check(digest)
        return [AuditEntry(2, ACCOUNT, 'company.suspended', ORG, NOW)]


class MfaStore(FakeStore):
    """The MFA half of the store port: records calls, answers with a configured challenge."""
    def __init__(self, known=None, challenge=None, fail=None):
        super().__init__(known)
        self.challenge, self.fail = challenge, fail

    def mfa_status(self, digest):
        self.calls.append(('mfa_status', digest))
        self._check(digest)
        return MfaStatus('active', True, True)

    def mfa_enroll(self, digest, sealed, hashes):
        self.calls.append(('mfa_enroll', digest, sealed, tuple(hashes)))
        self._check(digest)
        if self.fail:
            raise self.fail

    def mfa_begin(self, digest):
        self.calls.append(('mfa_begin', digest))
        self._check(digest)
        if self.fail:
            raise self.fail
        return self.challenge

    def mfa_confirm(self, digest, step):
        self.calls.append(('mfa_confirm', digest, step))
        self._check(digest)

    def mfa_recover(self, digest, code_hash):
        self.calls.append(('mfa_recover', digest, code_hash))
        self._check(digest)


class MfaServiceTests(unittest.TestCase):
    NOW = 1760000000

    def setUp(self):
        self.token = secrets.token_urlsafe(32)
        self.digest = capability_digest(self.token)
        self.sealer = SecretSealer(Fernet.generate_key())
        self.secret = generate_secret()
        self.sealed = self.sealer.seal(self.secret)
        self.step = self.NOW // 30

    def service(self, store):
        return PlatformService(store, sealer=self.sealer, clock=lambda: self.NOW)

    def challenge(self, last_step=0, state='active', sealed=None):
        return MfaChallenge(state, sealed or self.sealed, last_step)

    def test_a_right_code_confirms_exactly_the_step_it_matched(self):
        store = MfaStore(self.digest, self.challenge())
        self.service(store).verify_mfa(self.token, totp(self.secret, self.step))
        self.assertEqual([call[0] for call in store.calls], ['mfa_begin', 'mfa_confirm'])
        self.assertEqual(store.calls[-1], ('mfa_confirm', self.digest, self.step))

    def test_the_previous_step_is_accepted_within_the_window_but_not_if_it_was_already_used(self):
        store = MfaStore(self.digest, self.challenge(last_step=self.step - 2))
        self.service(store).verify_mfa(self.token, totp(self.secret, self.step - 1))
        self.assertEqual(store.calls[-1], ('mfa_confirm', self.digest, self.step - 1))
        for used in (self.step - 1, self.step):  # replay: that step (or a later one) was already accepted
            replay = MfaStore(self.digest, self.challenge(last_step=used))
            with self.subTest(last_step=used), self.assertRaises(MfaInvalid):
                self.service(replay).verify_mfa(self.token, totp(self.secret, self.step - 1))
            self.assertEqual([call[0] for call in replay.calls], ['mfa_begin'], 'a replay never reaches confirm')

    def test_wrong_malformed_far_away_or_unenrolled_attempts_never_confirm(self):
        for code in ('000000', 'abcdef', '', None, totp(self.secret, self.step + 5), totp(generate_secret(), self.step)):
            store = MfaStore(self.digest, self.challenge())
            with self.subTest(code=code), self.assertRaises(MfaInvalid):
                self.service(store).verify_mfa(self.token, code)
            self.assertNotIn('mfa_confirm', [call[0] for call in store.calls])
        store = MfaStore(self.digest, self.challenge(state='none', sealed=''))
        with self.assertRaises(MfaInvalid):
            self.service(store).verify_mfa(self.token, totp(self.secret, self.step))
        unreadable = MfaStore(self.digest, self.challenge(sealed='not-a-sealed-secret'))
        with self.assertRaises(PlatformUnavailable):
            self.service(unreadable).verify_mfa(self.token, totp(self.secret, self.step))

    def test_a_locked_account_and_a_denied_caller_surface_their_own_code_before_any_check(self):
        locked = MfaStore(self.digest, self.challenge(), fail=MfaLocked())
        with self.assertRaises(MfaLocked):
            self.service(locked).verify_mfa(self.token, totp(self.secret, self.step))
        with self.assertRaises(PlatformDenied):
            self.service(MfaStore('0' * 64, self.challenge())).verify_mfa(self.token, '123456')

    def test_enrollment_returns_the_secret_the_uri_and_ten_codes_once_and_stores_only_sealed_and_hashed_material(self):
        store = MfaStore(self.digest)
        enrollment = self.service(store).enroll_mfa(self.token)
        (call,) = store.calls
        self.assertEqual((call[0], call[1]), ('mfa_enroll', self.digest))
        self.assertEqual(self.sealer.open(call[2]), __import__('base64').b32decode(enrollment.secret))
        self.assertIn('secret=' + enrollment.secret, enrollment.otpauth_uri)
        self.assertEqual(len(enrollment.recovery_codes), 10)
        self.assertEqual(sorted(call[3]), sorted(hash_recovery_code(code) for code in enrollment.recovery_codes))
        for code in enrollment.recovery_codes:
            self.assertNotIn(code.replace('-', ''), ' '.join(map(str, call[2:])))
        self.assertNotIn(enrollment.secret, repr(enrollment), 'the secret never reaches a log through repr')

    def test_an_already_enrolled_owner_is_refused_and_enrollment_needs_a_sealer(self):
        with self.assertRaises(MfaEnrolled):
            self.service(MfaStore(self.digest, fail=MfaEnrolled())).enroll_mfa(self.token)
        with self.assertRaises(PlatformUnavailable):
            PlatformService(MfaStore(self.digest)).enroll_mfa(self.token)

    def test_a_recovery_code_is_checked_for_shape_then_reserved_then_spent_as_a_hash(self):
        store = MfaStore(self.digest, self.challenge())
        self.service(store).recover_mfa(self.token, 'abcd-efgh-ijkl-mnop')
        self.assertEqual(store.calls[0][0], 'mfa_begin')
        self.assertEqual(store.calls[1], ('mfa_recover', self.digest, hash_recovery_code('ABCD-EFGH-IJKL-MNOP')))
        for bad in ('', 'short', None, 'ABCD-EFGH-IJKL-MNO1'):
            malformed = MfaStore(self.digest, self.challenge())
            with self.subTest(bad=bad), self.assertRaises(MfaInvalid):
                self.service(malformed).recover_mfa(self.token, bad)
            self.assertEqual([call[0] for call in malformed.calls], ['mfa_begin'], 'a bad guess still spends an attempt')

    def test_the_finite_codes_and_the_status_values(self):
        self.assertEqual({cls.__name__: cls().code for cls in (MfaRequired, MfaInvalid, MfaLocked, MfaEnrolled)},
                         {'MfaRequired': 'MFA_REQUIRED', 'MfaInvalid': 'MFA_INVALID', 'MfaLocked': 'MFA_LOCKED',
                          'MfaEnrolled': 'MFA_ENROLLED'})
        self.assertEqual(self.service(MfaStore(self.digest)).mfa_status(self.token), MfaStatus('active', True, True))


class PlatformServiceTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(32)
        self.store = FakeStore(capability_digest(self.token))
        self.service = PlatformService(self.store)

    def test_the_store_only_ever_sees_the_digest_never_the_bearer_capability(self):
        self.assertEqual(self.service.me(self.token), PlatformIdentity(ACCOUNT, 'platform_owner'))
        self.service.companies(self.token)
        self.service.company(self.token, ORG)
        self.service.audit(self.token)
        for call in self.store.calls:
            self.assertEqual(call[1], capability_digest(self.token))
            self.assertNotIn(self.token, [str(part) for part in call])

    def test_a_malformed_or_unknown_capability_is_denied_before_or_by_the_store(self):
        for token in ('short', '', None, 'a' * 44, 'é' * 43, secrets.token_urlsafe(32)):
            with self.subTest(token=token), self.assertRaises(PlatformDenied):
                self.service.me(token)
        self.assertEqual(self.store.calls[-1][0], 'me', 'a well-formed unknown token reaches the store, which denies it')
        self.assertEqual(len(self.store.calls), 1, 'the five malformed ones never reached the store')

    def test_company_pages_default_and_pass_the_cursor_through_unchanged(self):
        self.service.companies(self.token)
        self.service.companies(self.token, after='acme', page=100)
        self.assertEqual(self.store.calls[0][2:], (None, 50))
        self.assertEqual(self.store.calls[1][2:], ('acme', 100))

    def test_invalid_pages_and_cursors_are_refused_without_a_database_round_trip(self):
        for page in (0, 101, -1, True, 1.5, '5', None):
            with self.subTest(page=page), self.assertRaises(PlatformInvalid):
                self.service.companies(self.token, page=page)
        for after in ('ACME', 'a b', '-acme', 'x' * 64, '', "a'--", 5):
            with self.subTest(after=after), self.assertRaises(PlatformInvalid):
                self.service.companies(self.token, after=after)
        for before in (0, -3, True, '1', 1.0):
            with self.subTest(before=before), self.assertRaises(PlatformInvalid):
                self.service.audit(self.token, before=before)
        self.assertEqual(self.store.calls, [])

    def test_getting_a_company_returns_it_or_raises_not_found_and_rejects_non_uuids(self):
        self.assertEqual(self.service.company(self.token, ORG), Company(ORG, 'acme', 'Acme', True))
        with self.assertRaises(PlatformNotFound):
            self.service.company(self.token, uuid4())
        for bad in ('x', None, str(ORG), 7):
            with self.subTest(bad=bad), self.assertRaises(PlatformInvalid):
                self.service.company(self.token, bad)

    def test_audit_entries_carry_only_the_non_secret_columns(self):
        (entry,) = self.service.audit(self.token, before=9, page=5)
        self.assertEqual((entry.id, entry.actor_id, entry.action, entry.organization_id), (2, ACCOUNT, 'company.suspended', ORG))
        self.assertEqual(self.store.calls[-1][2:], (9, 5))
        self.assertEqual(set(AuditEntry.__dataclass_fields__), {'id', 'actor_id', 'action', 'organization_id', 'recorded_at'})

    def test_every_failure_is_a_finite_code(self):
        codes = {cls.__name__: cls().code for cls in (PlatformDenied, PlatformInvalid, PlatformNotFound, PlatformUnavailable)}
        self.assertEqual(codes, {'PlatformDenied': 'PLATFORM_DENIED', 'PlatformInvalid': 'PLATFORM_INVALID',
                                 'PlatformNotFound': 'PLATFORM_NOT_FOUND', 'PlatformUnavailable': 'PLATFORM_UNAVAILABLE'})


if __name__ == '__main__':
    unittest.main()
