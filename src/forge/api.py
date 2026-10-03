"""Default-deny HTTP bootstrap over trusted, synchronous adapter ports."""

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException

from forge.foundation import (
    AuthenticatedIdentity, AuthorizationDenied, Membership, MembershipStatus,
    Organization, OrganizationConfiguration, build_public_bootstrap,
)


class TokenValidator(Protocol):
    """Validate a Forge token; None is rejection, exceptions are operational failure."""

    def validate(self, token: str) -> AuthenticatedIdentity | None: ...


@dataclass(frozen=True)
class BootstrapRecords:
    membership: Membership | None
    organization: Organization | None
    configuration: OrganizationConfiguration | None


class BootstrapReader(Protocol):
    """Reload records scoped to the validated identity and requested organization."""

    def read(
        self, identity: AuthenticatedIdentity, organization_id: str,
    ) -> BootstrapRecords | None: ...


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicOrganization(PublicModel):
    id: UUID
    slug: str
    display_name: str


class PublicMembership(PublicModel):
    id: UUID


class PublicBootstrap(PublicModel):
    schema_version: Literal["1.0"]
    organization: PublicOrganization
    membership: PublicMembership
    config_revision: int


class ErrorDetail(PublicModel):
    code: str
    message: str
    request_id: UUID
    retryable: bool
    retry_after_seconds: int | None
    reset_at: str | None


class ErrorEnvelope(PublicModel):
    error: ErrorDetail


class Health(PublicModel):
    status: Literal["ok"]


class ApiFailure(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code


MESSAGES = {
    "UNAUTHENTICATED": "A valid Forge bearer token is required.",
    "NOT_FOUND": "The requested resource is unavailable.",
    "MEMBERSHIP_SUSPENDED": "Your organization membership is suspended.",
    "SERVICE_UNAVAILABLE": "The service is temporarily unavailable.",
    "INVALID_REQUEST": "The request is invalid.",
    "METHOD_NOT_ALLOWED": "The request method is not allowed.",
}


def error_response(status: int, code: str, headers=None) -> JSONResponse:
    envelope = ErrorEnvelope(error=ErrorDetail(
        code=code, message=MESSAGES[code], request_id=uuid4(),
        retryable=status == 503, retry_after_seconds=None, reset_at=None,
    ))
    public_headers = dict(headers or {})
    if status == 401:
        public_headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=status, content=envelope.model_dump(mode="json"),
        headers=public_headers,
    )


def valid_identity(value: object) -> bool:
    return isinstance(value, AuthenticatedIdentity) and all(
        isinstance(field, str) and bool(field.strip())
        for field in (value.provider, value.issuer, value.subject)
    )


def create_app(
    token_validator: TokenValidator | None = None,
    bootstrap_reader: BootstrapReader | None = None,
) -> FastAPI:
    """Sync dependencies/handlers use FastAPI's worker pool, never the event loop.

    Unconfigured applications reject every token. Injection is trusted composition,
    not token validation by itself; no development identity exists in runtime.
    """
    app = FastAPI(title="Prometheon Forge control API", version="0.1.0")
    bearer = HTTPBearer(auto_error=False, scheme_name="ForgeBearer")

    @app.exception_handler(ApiFailure)
    async def api_failure(request: Request, exc: ApiFailure):
        return error_response(exc.status, exc.code)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Framework diagnostics may contain user input: do not serialize exc.errors().
        return error_response(422, "INVALID_REQUEST")

    @app.exception_handler(HTTPException)
    async def http_failure(request: Request, exc: HTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INVALID_REQUEST")
        # Only preserve the framework's non-sensitive Allow header, not its detail.
        headers = {"Allow": exc.headers["Allow"]} if exc.headers and "Allow" in exc.headers else None
        return error_response(exc.status_code, code, headers)

    def authenticated_identity(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
    ) -> AuthenticatedIdentity:
        if (
            len(request.headers.getlist("authorization")) != 1
            or credentials is None
            or not credentials.credentials
            or any(character.isspace() for character in credentials.credentials)
        ):
            raise ApiFailure(401, "UNAUTHENTICATED")
        if token_validator is None:
            raise ApiFailure(401, "UNAUTHENTICATED")
        try:
            identity = token_validator.validate(credentials.credentials)
        except Exception:
            raise ApiFailure(503, "SERVICE_UNAVAILABLE") from None
        if not valid_identity(identity):
            raise ApiFailure(401, "UNAUTHENTICATED")
        return identity

    @app.get("/healthz", response_model=Health)
    def health():
        """Process liveness only; no adapter, database or upstream readiness claim."""
        return {"status": "ok"}

    @app.get(
        "/forge/v1/bootstrap", response_model=PublicBootstrap,
        responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 422, 503)},
    )
    def bootstrap(
        identity: Annotated[AuthenticatedIdentity, Depends(authenticated_identity)],
        organization_id: UUID,
    ):
        # Dependencies authenticate before framework query errors are surfaced.
        if bootstrap_reader is None:
            raise ApiFailure(503, "SERVICE_UNAVAILABLE")
        requested = str(organization_id)
        try:
            data = bootstrap_reader.read(identity, requested)
        except Exception:
            raise ApiFailure(503, "SERVICE_UNAVAILABLE") from None
        if data is None:
            raise ApiFailure(404, "NOT_FOUND")
        if not isinstance(data, BootstrapRecords):
            raise ApiFailure(503, "SERVICE_UNAVAILABLE")
        member, organization, config = data.membership, data.organization, data.configuration
        if not (
            isinstance(member, Membership)
            and isinstance(organization, Organization)
            and isinstance(config, OrganizationConfiguration)
            and member.identity == identity
            and organization.active is True
            and requested == member.organization_id == organization.id == config.organization_id
        ):
            raise ApiFailure(404, "NOT_FOUND")
        if member.status is MembershipStatus.SUSPENDED:
            raise ApiFailure(403, "MEMBERSHIP_SUSPENDED")
        try:
            public = build_public_bootstrap(identity, requested, member, organization, config)
            return PublicBootstrap.model_validate(public)
        except AuthorizationDenied:
            raise ApiFailure(404, "NOT_FOUND") from None
        except Exception:
            # Invalid adapter data and response-validation diagnostics remain private.
            raise ApiFailure(503, "SERVICE_UNAVAILABLE") from None

    return app
