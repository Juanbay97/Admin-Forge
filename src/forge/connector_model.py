"""Connector broker types shared by the store, the OAuth flow, the MCP proxy and the routes: finite errors and typed rows. No I/O."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from forge.capability_policy import MAX_LEVEL, CatalogEntry, Layer, resolve_one


class BrokerError(Exception):
    """Every broker failure is one of these classes; none carries a value from a request, an upstream or the database."""


class BrokerDenied(BrokerError):
    """Not who the operation needs (a stranger, another company, a suspended member) or an unusable OAuth state: one code, no leak."""


class BrokerInvalid(BrokerError):
    pass


class BrokerNotFound(BrokerError):
    pass


class BrokerConflict(BrokerError):
    pass


class BrokerLimit(BrokerError):
    pass


class BrokerUnavailable(BrokerError):
    pass


class BrokerDisabled(BrokerError):
    """The connector is not ``on`` for this company (off, or force-disabled by the platform)."""


class BrokerNotConfigured(BrokerError):
    """The connector has no usable credential configuration (no OAuth app, no API key, or not a server-side connector)."""


class BrokerReauth(BrokerError):
    """The member's grant is missing, expired beyond refresh or revoked: the member must connect again."""


class BrokerUpstream(BrokerError):
    """The upstream failed, was refused by the egress guard or answered something the broker will not relay."""


class BrokerTooLarge(BrokerError):
    pass


class BrokerRateLimited(BrokerError):
    pass


@dataclass(frozen=True)
class ConnectorStatus:
    """One connector as a member sees it (no secret): public attributes, the policy verdict and the connection state."""
    id: str
    attributes: dict
    credential_locus: str
    state: str
    credential_scope: str | None
    credential_kind: str | None
    grant_status: str | None
    access_expires_at: datetime | None


@dataclass(frozen=True)
class ConnectorContext:
    """Everything one brokered call needs. ``credential_sealed`` and ``grant_sealed`` are opened by the broker, in memory only."""
    membership_id: UUID
    attributes: dict
    credential_locus: str
    state: str
    credential_scope: str | None
    credential_kind: str | None
    credential_sealed: str | None
    credential_revision: int | None
    grant_status: str | None
    grant_sealed: str | None
    grant_revision: int | None
    access_expires_at: datetime | None


@dataclass(frozen=True)
class CredentialInfo:
    revision: int
    hint: str | None
    kind: str


@dataclass(frozen=True)
class CredentialStatus:
    capability_id: str
    org_kind: str | None
    org_revision: int | None
    org_hint: str | None
    platform_kind: str | None


@dataclass(frozen=True)
class TakenState:
    """A consumed OAuth state plus what the code exchange needs (there is no session at the callback)."""
    organization_id: UUID
    membership_id: UUID
    capability_id: str
    sealed_verifier: str
    grant_revision: int
    attributes: dict
    state: str
    credential_scope: str | None
    credential_kind: str | None
    credential_sealed: str | None
    credential_revision: int | None


@dataclass(frozen=True)
class RemovedGrant:
    revision: int
    sealed: str


def connector_state(identifier, default_state, min_level, platform_state, platform_lock, company_state, company_lock, org_enabled):
    """The policy verdict for one connector, resolved fresh by the pure resolver (the sandbox gate does not apply to server-side connectors)."""
    entry = CatalogEntry(identifier, 'connector', '1', 'low', False, default_state, min_level, None)
    return resolve_one(entry, {identifier: Layer(platform_state, platform_lock)}, {identifier: Layer(company_state, company_lock)},
                       {} if org_enabled is None else {identifier: org_enabled}, MAX_LEVEL).state
