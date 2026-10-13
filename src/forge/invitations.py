"""Owned-account onboarding over injected durable stores; no login or mail claims."""
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import secrets
from typing import Protocol
from uuid import UUID, uuid4

from forge.accounts import Enrollment, PasswordHasher, canonical_email, display_name, _decode
from forge.authorization import valid_identity
from forge.foundation import AuthenticatedIdentity


class InvitationDenied(ValueError):
    def __init__(self):
        super().__init__("Invitation unavailable.")


class ExistingAccountAuthenticationRequired(InvitationDenied):
    def __init__(self):
        ValueError.__init__(self, "Existing account authentication required.")


class InvitationUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Enrollment storage unavailable.")


@dataclass(frozen=True, repr=False)
class InvitationRequest:
    organization_id: UUID
    administrator_membership_id: UUID
    department_id: UUID
    email: str
    name: str
    lifetime_seconds: int = 86400


@dataclass(frozen=True, repr=False)
class IssuedInvitation:
    invitation_id: UUID
    capability: str
    expires_at: datetime


@dataclass(frozen=True, repr=False)
class InvitationPreview:
    """Who an unused invitation is for: the address and display name it was issued to (known only to the holder of its link)."""
    account_email: str
    display_name: str


class InvitationStore(Protocol):
    def issue(self, identity: AuthenticatedIdentity, request: InvitationRequest,
              invitation_id: UUID, membership_id: UUID, digest: str) -> datetime: ...

    def revoke(self, identity: AuthenticatedIdentity, organization_id: UUID,
               administrator_membership_id: UUID, invitation_id: UUID) -> bool: ...


class EnrollmentStore(Protocol):
    def accept(self, invitation_id: UUID, digest: str, encoded: str) -> Enrollment: ...
    def preview(self, invitation_id: UUID, digest: str) -> InvitationPreview: ...


def capability_digest(capability: str) -> str:
    if type(capability) is not str or len(capability) != 43:
        raise ValueError("Invalid invitation capability.")
    try:
        raw = _decode(capability, 32)
    except Exception:
        raise ValueError("Invalid invitation capability.") from None
    return hashlib.sha256(raw).hexdigest()


def validate_actor(identity, *identifiers):
    if not valid_identity(identity) or any(type(value) is not UUID for value in identifiers):
        raise ValueError("Invalid invitation context.")


class InvitationService:
    def __init__(self, invitations: InvitationStore, enrollment: EnrollmentStore,
                 hasher: PasswordHasher | None = None):
        self.invitations, self.enrollment = invitations, enrollment
        self.hasher = hasher or PasswordHasher()

    def issue(self, identity: AuthenticatedIdentity, request: InvitationRequest) -> IssuedInvitation:
        if type(request) is not InvitationRequest:
            raise ValueError("Invalid invitation request.")
        validate_actor(identity, request.organization_id, request.administrator_membership_id,
                       request.department_id)
        if type(request.lifetime_seconds) is not int or not 60 <= request.lifetime_seconds <= 604800:
            raise ValueError("Invalid invitation lifetime.")
        intent = replace(request, email=canonical_email(request.email), name=display_name(request.name))
        capability, invitation_id, member_id = secrets.token_urlsafe(32), uuid4(), uuid4()
        expires = self.invitations.issue(identity, intent, invitation_id, member_id,
                                         capability_digest(capability))
        return IssuedInvitation(invitation_id, capability, expires)

    def accept(self, invitation_id: UUID, capability: str, password: str) -> Enrollment:
        if type(invitation_id) is not UUID:
            raise ValueError("Invalid invitation identifier.")
        digest = capability_digest(capability)
        encoded = self.hasher.hash(password)
        return self.enrollment.accept(invitation_id, digest, encoded)

    def preview(self, invitation_id: UUID, capability: str) -> InvitationPreview:
        """Read-only: ``InvitationDenied`` for anything that is not a pending, unexpired invitation of an active company."""
        if type(invitation_id) is not UUID:
            raise ValueError("Invalid invitation identifier.")
        return self.enrollment.preview(invitation_id, capability_digest(capability))

    def revoke(self, identity: AuthenticatedIdentity, organization_id: UUID,
               administrator_membership_id: UUID, invitation_id: UUID) -> bool:
        validate_actor(identity, organization_id, administrator_membership_id, invitation_id)
        return self.invitations.revoke(identity, organization_id,
                                       administrator_membership_id, invitation_id)
