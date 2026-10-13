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
from forge.platform import (AuditEntry, Company, PlatformDenied, PlatformIdentity, PlatformInvalid, PlatformNotFound,
                            PlatformService, PlatformUnavailable)

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
