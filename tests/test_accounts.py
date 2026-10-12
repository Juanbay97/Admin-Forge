"""Deterministic input/KDF/service contract; real cost never weakened for fixtures."""
import base64
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sys
import threading
import time
import unittest
from unittest.mock import patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from forge import accounts
from forge.accounts import (
    ACCOUNT_ISSUER, Enrollment, PasswordHasher, PasswordWorkUnavailable,
    canonical_email, display_name,
)
from forge.foundation import AuthenticatedIdentity
from forge.invitations import (
    InvitationService, InvitationRequest, IssuedInvitation, capability_digest,
)

PASSWORD = "a sufficiently long password"
IDENTITY = AuthenticatedIdentity("forge", ACCOUNT_ISSUER, str(UUID(int=19)))
REQUEST = InvitationRequest(UUID(int=1), UUID(int=2), UUID(int=3), " USER@Example.COM ", " User ")


class Stores:
    def __init__(self):
        self.calls = []

    def issue(self, identity, request, invitation_id, membership_id, digest):
        self.calls.append((identity, request, invitation_id, membership_id, digest))
        return datetime.now(timezone.utc)

    def accept(self, invitation_id, digest, encoded):
        self.calls.append((invitation_id, digest, encoded))
        return Enrollment(UUID(int=4), UUID(int=5), UUID(int=1), UUID(int=3))

    def revoke(self, identity, organization_id, administrator_membership_id, invitation_id):
        self.calls.append((identity, organization_id, administrator_membership_id, invitation_id))
        return True


class AccountTests(unittest.TestCase):
    def test_canonical_email_is_explicit_and_preserves_aliases(self):
        self.assertEqual(canonical_email(" USER.Name+tag@Example.COM "), "user.name+tag@example.com")
        self.assertNotEqual(canonical_email("a.b@example.com"), canonical_email("ab@example.com"))

    def test_invalid_email_and_name_are_bounded(self):
        for value in (None, "", "not-email", "x@x", "x\n@example.com", "é@example.com", "..a@example.com", "a@-x.com", "a"*65+"@x.com"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_email(value)
        self.assertEqual(display_name(" Jane Doe "), "Jane Doe")
        for value in (None, "", "\nJane", "x"*121):
            with self.subTest(name=value), self.assertRaises(ValueError):
                display_name(value)

    def test_forge_identity_is_not_email_or_entra(self):
        result = Enrollment(UUID(int=4), UUID(int=5), UUID(int=1), UUID(int=3))
        self.assertEqual(result.identity, AuthenticatedIdentity("forge", ACCOUNT_ISSUER, str(UUID(int=4))))

    def test_real_scrypt_roundtrip_and_fresh_salts(self):
        hasher = PasswordHasher()
        first, second = hasher.hash(PASSWORD), hasher.hash(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("forge$scrypt$v1$131072$8$1$"))
        self.assertTrue(hasher.verify(PASSWORD, first))
        self.assertFalse(hasher.verify("a wrong but long password", first))
        self.assertNotIn(PASSWORD, first)

    def test_unbounded_encoded_parameters_reject_before_kdf(self):
        encoded = "forge$scrypt$v1$131072$8$1$" + "A"*22 + "$" + "A"*43
        with patch("forge.accounts.Scrypt", create=True) as kdf:
            for value in (None, "x"*300, encoded.replace("131072", "1073741824"), encoded.replace("$8$", "$0$"), encoded.replace("$v1$", "$v999$"), encoded+"$extra"):
                with self.subTest(encoded=value):
                    self.assertFalse(PasswordHasher().verify(PASSWORD, value))
            kdf.assert_not_called()

    def test_password_byte_limits_reject_before_kdf(self):
        with patch("forge.accounts.Scrypt", create=True) as kdf:
            for value in (None, "short", "x"*1025, "💡"*300, "a"*20+"\x00"):
                with self.subTest(password=value), self.assertRaises(ValueError):
                    PasswordHasher().hash(value)
            kdf.assert_not_called()

    def test_memory_admission_rejects_without_allocating(self):
        with patch("forge.accounts._KDF_SLOT") as slot, patch("forge.accounts.Scrypt") as kdf:
            slot.acquire.return_value = False
            with self.assertRaises(PasswordWorkUnavailable):
                PasswordHasher().hash(PASSWORD)
            kdf.assert_not_called()
            slot.release.assert_not_called()

    def test_simultaneous_sign_ins_queue_for_the_single_memory_slot_instead_of_failing(self):
        # Several members sign in at once: one derivation at a time (memory bound), everybody is served.
        encoded = PasswordHasher().hash(PASSWORD)
        running, peak, outcomes = [0], [0], []
        lock = threading.Lock()

        class SlowKdf:
            def __init__(self, **_):
                pass

            def verify(self, *_):
                with lock:
                    running[0] += 1
                    peak[0] = max(peak[0], running[0])
                time.sleep(0.1)
                with lock:
                    running[0] -= 1

        def sign_in():
            try:
                outcomes.append(PasswordHasher().verify(PASSWORD, encoded))
            except PasswordWorkUnavailable:
                outcomes.append("unavailable")
        with patch("forge.accounts.Scrypt", SlowKdf):
            workers = [threading.Thread(target=sign_in) for _ in range(4)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
        self.assertEqual(outcomes, [True] * 4)
        self.assertEqual(peak[0], 1)

    def test_the_wait_for_the_memory_slot_is_bounded(self):
        encoded = PasswordHasher().hash(PASSWORD)
        with patch("forge.accounts._KDF_WAIT", 0.05), patch("forge.accounts.Scrypt") as kdf:
            self.assertTrue(accounts._KDF_SLOT.acquire(blocking=False))
            try:
                started = time.monotonic()
                with self.assertRaises(PasswordWorkUnavailable):
                    PasswordHasher().verify(PASSWORD, encoded)
                self.assertLess(time.monotonic() - started, 2)
            finally:
                accounts._KDF_SLOT.release()
            kdf.assert_not_called()

    def test_kdf_failure_releases_memory_slot(self):
        with patch("forge.accounts._KDF_SLOT") as slot, patch("forge.accounts.Scrypt") as kdf:
            slot.acquire.return_value = True
            kdf.return_value.derive.side_effect = RuntimeError("internal failure")
            with self.assertRaises(RuntimeError):
                PasswordHasher().hash(PASSWORD)
            slot.release.assert_called_once()

    def test_single_use_capability_shape_hash_only(self):
        secret = secrets.token_urlsafe(32)
        digest = capability_digest(secret)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(secret, digest)
        for value in (None, "", "A"*44, "x"*10000, "="*43, "A"*42+"B"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                capability_digest(value)

    def test_issue_passes_validated_intent_not_capability_to_store(self):
        store = Stores()
        invitation = InvitationService(store, store).issue(IDENTITY, REQUEST)
        self.assertIsInstance(invitation, IssuedInvitation)
        self.assertEqual(store.calls[0][1].email, "user@example.com")
        self.assertEqual(store.calls[0][1].name, "User")
        self.assertEqual(store.calls[0][-1], capability_digest(invitation.capability))
        self.assertNotIn(invitation.capability, repr(invitation))
        self.assertNotIn(invitation.capability, repr(store.calls))

    def test_request_rejects_before_store_and_never_accepts_role_claims(self):
        store = Stores()
        service = InvitationService(store, store)
        for request in (None, replace(REQUEST, organization_id="org"), replace(REQUEST, department_id=None), replace(REQUEST, lifetime_seconds=True), replace(REQUEST, lifetime_seconds=604801), replace(REQUEST, name="")):
            with self.subTest(request=request), self.assertRaises(ValueError):
                service.issue(IDENTITY, request)
        for identity in (None, {}, AuthenticatedIdentity("", "issuer", "sub")):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                service.issue(identity, REQUEST)
        self.assertEqual(store.calls, [])

    def test_accept_passes_hashes_only_and_invalid_capability_before_kdf(self):
        store = Stores()
        hasher = unittest.mock.Mock(spec=PasswordHasher)
        hasher.hash.return_value = "ENCODED_HASH"
        service = InvitationService(store, store, hasher)
        secret = secrets.token_urlsafe(32)
        self.assertEqual(service.accept(UUID(int=9), secret, PASSWORD).account_id, UUID(int=4))
        self.assertEqual(store.calls[0], (UUID(int=9), capability_digest(secret), "ENCODED_HASH"))
        hasher.reset_mock()
        with self.assertRaises(ValueError):
            service.accept(UUID(int=9), "invalid", PASSWORD)
        hasher.hash.assert_not_called()

    def test_revoke_requires_trusted_identity_and_uuid_context(self):
        store = Stores()
        service = InvitationService(store, store)
        self.assertTrue(service.revoke(IDENTITY, UUID(int=1), UUID(int=2), UUID(int=3)))
        with self.assertRaises(ValueError):
            service.revoke(IDENTITY, UUID(int=1), UUID(int=2), "not-id")
        self.assertEqual(len(store.calls), 1)


if __name__ == "__main__":
    unittest.main()
