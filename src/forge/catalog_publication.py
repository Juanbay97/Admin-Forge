"""Internal authenticated publication boundary; no HTTP or ambient composition."""
from dataclasses import dataclass
import re
from typing import Protocol
from uuid import UUID

from forge.authorization import AuthorizationSnapshot
from forge.entra import VerifiedPrincipal


class PublicationDenied(RuntimeError):
    def __init__(self):
        super().__init__("Catalog publication denied.")


class PublicationConflict(RuntimeError):
    def __init__(self):
        super().__init__("Catalog publication conflicts.")


class PublicationUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Catalog publication unavailable.")


class PrincipalValidator(Protocol):
    """Trusted composition supplies EntraTokenValidator or an explicit test fixture."""
    def validate_principal(self, token: str) -> VerifiedPrincipal | None: ...


@dataclass(frozen=True, repr=False)
class PublicationRequest:
    organization_id: UUID
    router_binding_id: UUID
    operation_id: UUID
    expected_revision: int
    payload_sha256: str


@dataclass(frozen=True, repr=False)
class PublicationResult:
    organization_id: UUID
    router_binding_id: UUID
    operation_id: UUID
    event_id: UUID
    revision: int
    audit_publication: str = "pending"


def valid_request(value):
    return (type(value) is PublicationRequest
            and all(type(getattr(value, field)) is UUID for field in
                    ("organization_id", "router_binding_id", "operation_id"))
            and type(value.expected_revision) is int
            and 0 <= value.expected_revision <= 2**63-2
            and type(value.payload_sha256) is str
            and re.fullmatch("[0-9a-f]{64}", value.payload_sha256) is not None)


def valid_principal(value):
    try:
        return (type(value) is VerifiedPrincipal
                and type(value.sub) is str and 0 < len(value.sub) <= 512
                and str(UUID(value.tid)) == value.tid and str(UUID(value.oid)) == value.oid
                and value.issuer == "https://login.microsoftonline.com/" + value.tid + "/v2.0")
    except (ValueError, TypeError, AttributeError):
        return False


class CatalogPublisher:
    """Discover membership via an explicit reader, then authorize under store locks.

    Prelookup roles/activity are never a reservation or permission. The store reloads
    all authority using the freshly verified principal before replay or mutation.
    """
    def __init__(self, validator: PrincipalValidator, membership_reader, store):
        self._validator = validator
        self._reader = membership_reader
        self._store = store

    def publish(self, token, request):
        if not valid_request(request) or type(token) is not str or not token:
            raise PublicationDenied()
        try:
            principal = self._validator.validate_principal(token)
            if not valid_principal(principal):
                raise PublicationDenied()
            observed = self._reader.read(principal.identity, str(request.organization_id))
            if (type(observed) is not AuthorizationSnapshot
                    or observed.identity != principal.identity
                    or observed.organization_id != request.organization_id
                    or type(observed.membership_id) is not UUID):
                raise PublicationDenied()
            result = self._store._publish(principal, observed.membership_id, request)
            if (type(result) is not PublicationResult
                    or any(type(getattr(result, field)) is not UUID for field in
                           ("organization_id", "router_binding_id", "operation_id", "event_id"))
                    or (result.organization_id, result.router_binding_id, result.operation_id) !=
                       (request.organization_id, request.router_binding_id, request.operation_id)
                    or type(result.revision) is not int or result.revision != request.expected_revision+1
                    or type(result.audit_publication) is not str or result.audit_publication != "pending"):
                raise PublicationUnavailable()
            return result
        except (PublicationDenied, PublicationConflict, PublicationUnavailable):
            raise
        except Exception:
            raise PublicationUnavailable() from None
