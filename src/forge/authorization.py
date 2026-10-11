"""Pure membership authorization over trusted internal data, not authentication."""
from dataclasses import dataclass
from uuid import UUID

from forge.foundation import AuthenticatedIdentity, MembershipStatus

ORGANIZATION_ROLES = frozenset({
    "organization_admin", "department_manager", "skill_reviewer", "member",
})
MEMBER_ACTIONS = frozenset({"members.invite", "members.update", "members.suspend"})


@dataclass(frozen=True, repr=False)
class AuthorizationSnapshot:
    """Observation only; construction never authenticates or reserves a permission."""
    identity: AuthenticatedIdentity
    organization_id: UUID
    membership_id: UUID
    revision: int
    roles: frozenset[str]
    membership_status: MembershipStatus
    organization_active: bool

    def __post_init__(self):
        # Copy collections, not role values. Strings/lists/mappings are not roles.
        if type(self.roles) not in (set, frozenset):
            raise ValueError("Authorization roles require an immutable set.")
        object.__setattr__(self, "roles", frozenset(self.roles))


def valid_identity(identity: object) -> bool:
    return type(identity) is AuthenticatedIdentity and all(
        type(value) is str and bool(value.strip())
        for value in (identity.provider, identity.issuer, identity.subject)
    )


def valid_snapshot(snapshot: object) -> bool:
    return (
        type(snapshot) is AuthorizationSnapshot
        and valid_identity(snapshot.identity)
        and type(snapshot.organization_id) is UUID
        and type(snapshot.membership_id) is UUID
        and type(snapshot.revision) is int
        and 0 < snapshot.revision <= 2**63 - 1
        and type(snapshot.roles) is frozenset
        and all(type(role) is str and role in ORGANIZATION_ROLES
                for role in snapshot.roles)
        and snapshot.membership_status is MembershipStatus.ACTIVE
        and snapshot.organization_active is True
    )


def permits(snapshot: AuthorizationSnapshot | None, action: str) -> bool:
    """Exact default-deny organization policy, not a reusable mutation capability."""
    return bool(
        valid_snapshot(snapshot) and type(action) is str and action in MEMBER_ACTIONS | {"models.publish"}
        and "organization_admin" in snapshot.roles
    )
