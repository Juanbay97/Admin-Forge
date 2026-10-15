"""Platform administration: the platform owner, mandatory TOTP, company reads and the audit log, over an injected store.

The platform owner is an owned account with a platform role and no membership. Authority never lives in this
process: every operation is a database function that re-validates the live account session, the owner role and (from
0029) a verified MFA state for that very session, so this service only turns a bearer capability into its digest,
bounds the arguments, runs the TOTP arithmetic and maps failures to finite codes. The database owns the replay guard
and the attempt budget. ``python -m forge.platform bootstrap-owner`` is the operator entry point (``forge.platform_cli``).
"""
import base64
from dataclasses import dataclass
from datetime import datetime
import re
import secrets
import time
from typing import Protocol
from uuid import UUID, uuid4

from forge.accounts import canonical_email, display_name as clean_name
from forge.branding import DEFAULT_INPUT, Branding, BrandingInput
from forge.invitations import InvitationRequest, IssuedInvitation, capability_digest
from forge.platform_totp import (SecretSealer, SecretUnreadable, generate_recovery_codes, generate_secret, hash_recovery_code,
                                 match_step, otpauth_uri)

COMPANY_CODE = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
DEFAULT_PAGE = 50
MAX_PAGE = 100


class PlatformError(Exception):
    """Base of every platform failure; ``code`` is finite and never carries a value from a request."""
    code = 'PLATFORM_UNAVAILABLE'
    message = 'Platform administration is unavailable.'

    def __init__(self):
        super().__init__(self.message)


class PlatformDenied(PlatformError):
    """Not a platform owner, no live session, or any other reason: one outcome, never explained."""
    code = 'PLATFORM_DENIED'
    message = 'Platform access denied.'


class PlatformInvalid(PlatformError):
    code = 'PLATFORM_INVALID'
    message = 'The platform request is invalid.'


class PlatformNotFound(PlatformError):
    code = 'PLATFORM_NOT_FOUND'
    message = 'The requested company does not exist.'


class PlatformUnavailable(PlatformError):
    code = 'PLATFORM_UNAVAILABLE'


class CompanyConflict(PlatformError):
    code = 'COMPANY_CONFLICT'
    message = 'A company with this code already exists.'


class KeyConflict(PlatformError):
    code = 'KEY_CONFLICT'
    message = 'A gateway key with this label already exists.'


class NoActiveMember(PlatformError):
    """The company has nobody a publication event may name yet (no active member)."""
    code = 'NO_ACTIVE_MEMBER'
    message = 'The company has no active member yet.'


class RevisionConflict(PlatformError):
    code = 'REVISION_CONFLICT'
    message = 'The branding revision changed.'


class MfaRequired(PlatformError):
    """A platform call without a verified (or, for a change, a fresh) MFA state for this session."""
    code = 'MFA_REQUIRED'
    message = 'A verified second factor is required.'


class MfaInvalid(PlatformError):
    """Wrong, malformed, replayed or unusable code: one outcome, never explained."""
    code = 'MFA_INVALID'
    message = 'The verification code was not accepted.'


class MfaLocked(PlatformError):
    code = 'MFA_LOCKED'
    message = 'Too many attempts; try again later.'


class MfaEnrolled(PlatformError):
    code = 'MFA_ENROLLED'
    message = 'A second factor is already enrolled.'


@dataclass(frozen=True)
class PlatformIdentity:
    account_id: UUID
    role: str


@dataclass(frozen=True)
class Company:
    organization_id: UUID
    slug: str
    display_name: str
    active: bool


@dataclass(frozen=True)
class AuditEntry:
    """Who, what, which company and when: the audit log has no other columns."""
    id: int
    actor_id: UUID
    action: str
    organization_id: UUID | None
    recorded_at: datetime


@dataclass(frozen=True)
class CreatedCompany:
    """The new company and where its first-admin invitation stands; the capability itself is never part of it."""
    company: Company
    invitation_id: UUID
    expires_at: datetime
    delivery_state: str
    delivery_channel: str


@dataclass(frozen=True)
class MfaStatus:
    state: str  # none | pending | active
    verified: bool  # this session has passed the second factor
    fresh: bool  # ... recently enough for a change


@dataclass(frozen=True)
class MfaChallenge:
    """What the database hands back after reserving an attempt: the sealed secret and the last accepted step."""
    state: str
    sealed: str
    last_step: int


@dataclass(frozen=True, repr=False)
class MfaEnrollment:
    """Shown to the owner exactly once; ``repr`` never carries the secret or the codes."""
    secret: str
    otpauth_uri: str
    recovery_codes: tuple

    def __repr__(self):
        return 'MfaEnrollment(...)'


class PlatformStore(Protocol):
    def set_company_active(self, digest: str, organization_id: UUID, turn_on: bool) -> bool: ...
    def company_branding(self, digest: str, organization_id: UUID) -> Branding: ...
    def save_company_branding(self, digest: str, organization_id: UUID, expected: int, change: str, value: BrandingInput) -> Branding: ...
    def create_company(self, digest: str, ids: dict, details: dict, invitation_digest: str, lifetime: int) -> datetime: ...
    def mfa_status(self, digest: str) -> MfaStatus: ...
    def mfa_enroll(self, digest: str, sealed: str, hashes: list[str]) -> None: ...
    def mfa_begin(self, digest: str) -> MfaChallenge: ...
    def mfa_confirm(self, digest: str, step: int) -> None: ...
    def mfa_recover(self, digest: str, code_hash: str) -> None: ...
    def me(self, digest: str) -> PlatformIdentity: ...
    def companies(self, digest: str, after: str | None, page: int) -> list[Company]: ...
    def company(self, digest: str, organization_id: UUID) -> Company | None: ...
    def audit(self, digest: str, before: int | None, page: int) -> list[AuditEntry]: ...


def _page(value):
    if type(value) is not int or not 1 <= value <= MAX_PAGE:
        raise PlatformInvalid()
    return value


ACCOUNT_LABEL = 'platform-owner'
MAX_REVISION = 2 ** 63 - 3
INVITATION_SECONDS = 604800  # the first administrator has a week to accept


class PlatformService:
    def __init__(self, store: PlatformStore, sealer: SecretSealer | None = None, clock=time.time, delivery=None):
        self.store, self.sealer, self.clock, self.delivery = store, sealer, clock, delivery

    @staticmethod
    def _digest(token):
        try:
            return capability_digest(token)
        except (ValueError, TypeError):
            raise PlatformDenied() from None

    def me(self, token: str) -> PlatformIdentity:
        return self.store.me(self._digest(token))

    def mfa_status(self, token: str) -> MfaStatus:
        return self.store.mfa_status(self._digest(token))

    def enroll_mfa(self, token: str) -> MfaEnrollment:
        """Start (or restart, while still pending) the TOTP enrollment; the secret and codes are returned once."""
        digest = self._digest(token)
        if self.sealer is None:
            raise PlatformUnavailable()
        secret, codes = generate_secret(), generate_recovery_codes()
        self.store.mfa_enroll(digest, self.sealer.seal(secret), [hash_recovery_code(code) for code in codes])
        return MfaEnrollment(base64.b32encode(secret).decode('ascii').rstrip('='), otpauth_uri(secret, ACCOUNT_LABEL), tuple(codes))

    def verify_mfa(self, token: str, code) -> None:
        """Spend one attempt, then accept a code only for a step newer than the last accepted one."""
        digest = self._digest(token)
        challenge = self.store.mfa_begin(digest)
        if self.sealer is None or challenge.state not in ('pending', 'active'):
            raise MfaInvalid()
        try:
            secret = self.sealer.open(challenge.sealed)
        except SecretUnreadable:
            raise PlatformUnavailable() from None
        step = match_step(secret, code, self.clock())
        if step is None or step <= challenge.last_step:
            raise MfaInvalid()
        self.store.mfa_confirm(digest, step)

    def recover_mfa(self, token: str, code) -> None:
        digest = self._digest(token)
        self.store.mfa_begin(digest)  # the attempt is spent first, so guessing recovery codes is as bounded as guessing codes
        try:
            code_hash = hash_recovery_code(code)
        except ValueError:
            raise MfaInvalid() from None
        self.store.mfa_recover(digest, code_hash)

    def companies(self, token: str, *, after: str | None = None, page: int = DEFAULT_PAGE) -> list[Company]:
        digest = self._digest(token)
        page = _page(page)
        if after is not None and (type(after) is not str or not COMPANY_CODE.fullmatch(after)):
            raise PlatformInvalid()
        return self.store.companies(digest, after, page)

    def company(self, token: str, organization_id: UUID) -> Company:
        digest = self._digest(token)
        if type(organization_id) is not UUID:
            raise PlatformInvalid()
        found = self.store.company(digest, organization_id)
        if found is None:
            raise PlatformNotFound()
        return found

    def create_company(self, token: str, *, slug: str, display_name: str, department: str, admin_email: str,
                       admin_name: str) -> CreatedCompany:
        """Create the company and its first-admin invitation, then deliver the invitation (its failure never undoes the company)."""
        digest = self._digest(token)
        try:
            if type(slug) is not str or not COMPANY_CODE.fullmatch(slug):
                raise ValueError
            details = {'slug': slug, 'display_name': clean_name(display_name),
                       'department': clean_name(department), 'admin_email': canonical_email(admin_email),
                       'admin_name': clean_name(admin_name)}
        except (ValueError, TypeError):
            raise PlatformInvalid() from None
        if self.delivery is None:
            raise PlatformUnavailable()
        ids = {name: uuid4() for name in ('organization', 'department', 'invitation', 'membership')}
        capability = secrets.token_urlsafe(32)
        expires = self.store.create_company(digest, ids, details, capability_digest(capability), INVITATION_SECONDS)
        try:
            request = InvitationRequest(ids['organization'], ids['membership'], ids['department'], details['admin_email'],
                                        details['admin_name'])
            message = self.delivery.queue_invitation(IssuedInvitation(ids['invitation'], capability, expires), request,
                                                     company_code=slug)
            state = self.delivery.dispatch(message).value
        except Exception:
            state = 'failed'  # the company exists; only a finite state is reported, never the relay's message
        return CreatedCompany(Company(ids['organization'], slug, details['display_name'], True), ids['invitation'], expires,
                              state, self.delivery.channel)

    def suspend_company(self, token: str, organization_id: UUID) -> Company:
        """Deny every member, administrator and inference path of the company at once; nothing is deleted."""
        return self._set_active(token, organization_id, False)

    def reactivate_company(self, token: str, organization_id: UUID) -> Company:
        return self._set_active(token, organization_id, True)

    def _set_active(self, token, organization_id, turn_on):
        digest = self._digest(token)
        if type(organization_id) is not UUID:
            raise PlatformInvalid()
        self.store.set_company_active(digest, organization_id, turn_on)
        return self.company(token, organization_id)

    def company_branding(self, token: str, organization_id: UUID) -> Branding:
        digest = self._digest(token)
        if type(organization_id) is not UUID:
            raise PlatformInvalid()
        return self.store.company_branding(digest, organization_id)

    def save_company_branding(self, token: str, organization_id: UUID, expected: int, value: BrandingInput) -> Branding:
        return self._save_branding(token, organization_id, expected, 'save', value)

    def reset_company_branding(self, token: str, organization_id: UUID, expected: int) -> Branding:
        return self._save_branding(token, organization_id, expected, 'reset', DEFAULT_INPUT)

    def _save_branding(self, token, organization_id, expected, change, value):
        digest = self._digest(token)
        if (type(organization_id) is not UUID or type(expected) is not int or not 0 <= expected <= MAX_REVISION
                or type(value) is not BrandingInput):
            raise PlatformInvalid()
        return self.store.save_company_branding(digest, organization_id, expected, change, value)

    def audit(self, token: str, *, before: int | None = None, page: int = DEFAULT_PAGE) -> list[AuditEntry]:
        digest = self._digest(token)
        page = _page(page)
        if before is not None and (type(before) is not int or before < 1):
            raise PlatformInvalid()
        return self.store.audit(digest, before, page)


if __name__ == '__main__':
    from forge.platform_cli import main
    raise SystemExit(main())
