"""Platform administration: the platform owner, company reads and the audit log, over an injected store.

The platform owner is an owned account with a platform role and no membership. Authority never lives in this
process: every operation is a database function that re-validates the live account session and the owner role
(0028), so this service only turns a bearer capability into its digest, bounds the arguments and maps failures to
finite codes. ``python -m forge.platform bootstrap-owner`` is the operator entry point (``forge.platform_cli``).
"""
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol
from uuid import UUID

from forge.invitations import capability_digest

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


class PlatformStore(Protocol):
    def me(self, digest: str) -> PlatformIdentity: ...
    def companies(self, digest: str, after: str | None, page: int) -> list[Company]: ...
    def company(self, digest: str, organization_id: UUID) -> Company | None: ...
    def audit(self, digest: str, before: int | None, page: int) -> list[AuditEntry]: ...


def _page(value):
    if type(value) is not int or not 1 <= value <= MAX_PAGE:
        raise PlatformInvalid()
    return value


class PlatformService:
    def __init__(self, store: PlatformStore):
        self.store = store

    @staticmethod
    def _digest(token):
        try:
            return capability_digest(token)
        except (ValueError, TypeError):
            raise PlatformDenied() from None

    def me(self, token: str) -> PlatformIdentity:
        return self.store.me(self._digest(token))

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

    def audit(self, token: str, *, before: int | None = None, page: int = DEFAULT_PAGE) -> list[AuditEntry]:
        digest = self._digest(token)
        page = _page(page)
        if before is not None and (type(before) is not int or before < 1):
            raise PlatformInvalid()
        return self.store.audit(digest, before, page)


if __name__ == '__main__':
    from forge.platform_cli import main
    raise SystemExit(main())
