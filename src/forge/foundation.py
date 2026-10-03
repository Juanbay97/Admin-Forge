"""Membership authorization over trusted adapter data, not token validation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class MembershipStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Future adapter output after validating the provider, issuer and subject.

    Constructing this value does not authenticate a caller. HTTP handlers must
    never construct it from unvalidated headers or user-supplied identity fields.
    """

    provider: str
    issuer: str
    subject: str


@dataclass(frozen=True)
class Membership:
    id: str
    organization_id: str
    identity: AuthenticatedIdentity
    status: MembershipStatus


@dataclass(frozen=True)
class Organization:
    id: str
    slug: str
    display_name: str
    active: bool


@dataclass(frozen=True)
class OrganizationConfiguration:
    organization_id: str
    revision: int
    internal_settings: Mapping[str, object] = field(default_factory=dict, repr=False)


class AuthorizationDenied(Exception):
    """No public bootstrap is available for the supplied authorization context."""


def build_public_bootstrap(
    identity: AuthenticatedIdentity | None,
    requested_organization_id: str,
    membership: Membership | None,
    organization: Organization,
    configuration: OrganizationConfiguration,
) -> dict[str, object]:
    """Authorize one request and project an explicit public subset of PF-10."""
    if (
        identity is None
        or not all(isinstance(value, str) and value.strip() for value in (
            identity.provider, identity.issuer, identity.subject
        ))
        or not requested_organization_id
        or membership is None
        or membership.identity != identity
        or membership.status is not MembershipStatus.ACTIVE
        or organization.active is not True
        or not (
            requested_organization_id == membership.organization_id
            == organization.id == configuration.organization_id
        )
    ):
        raise AuthorizationDenied("Public bootstrap is unavailable")

    return {
        "schema_version": "1.0",
        "organization": {
            "id": organization.id,
            "slug": organization.slug,
            "display_name": organization.display_name,
        },
        "membership": {"id": membership.id},
        "config_revision": configuration.revision,
    }
