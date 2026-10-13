"""Capability governance types shared by the store, the service and the HTTP routes: the finite errors and the typed rows.

No I/O. Errors carry no value from the database or the request; a route maps each class to one finite code.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from forge.capability_policy import CatalogEntry, Layer


class CapabilityError(Exception):
    pass


class CapabilityDenied(CapabilityError):
    """Not who the operation needs (a member, another company's administrator, a stale session): one code, no existence leak."""


class CapabilityInvalid(CapabilityError):
    pass


class CapabilityNotFound(CapabilityError):
    pass


class CapabilityConflict(CapabilityError):
    """A duplicate catalog id or a stale revision."""


class CapabilityLocked(CapabilityError):
    """The super administrator force-disabled it: no company administrator may change it."""


class CapabilityUnavailable(CapabilityError):
    pass


@dataclass(frozen=True)
class CatalogRecord:
    entry: CatalogEntry
    revision: int
    platform: Layer


@dataclass(frozen=True)
class Snapshot:
    """The layers of one company plus both epochs; ``resolve(entries, platform, company, org, level)`` turns them into states."""
    platform_epoch: int
    org_epoch: int
    entries: tuple
    platform: dict
    company: dict
    org: dict


@dataclass(frozen=True)
class CompanyPolicyRow:
    capability_id: str
    layer: Layer
    org_enabled: bool | None


@dataclass(frozen=True)
class AuditRecord:
    id: int
    scope: str
    organization_id: UUID | None
    actor_id: UUID | None
    action: str
    target: str
    before: str | None
    after: str | None
    at: datetime
