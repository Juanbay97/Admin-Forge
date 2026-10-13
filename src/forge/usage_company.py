"""Company per-person usage: what an organization administrator may see of the own company, over an injected store.

Authority is the database (the directory authority re-validates the live session and the administrator on every call); this
service bounds the arguments and returns names plus counters and integer micro-USD costs, never content.
"""
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from forge.invitations import capability_digest
from forge.usage_platform import DEFAULT_PAGE, MAX_PAGE, Counters, _range


@dataclass(frozen=True)
class MemberUsage:
    member_id: UUID
    email: str
    name: str
    state: str
    counters: Counters


class CompanyUsageStore(Protocol):
    def members(self, digest, organization_id, first_day, last_day, after, page) -> list: ...


class CompanyUsage:
    def __init__(self, store):
        self._store = store

    def members(self, token, organization_id, first_day: date, last_day: date, after=None, page=DEFAULT_PAGE):
        if type(organization_id) is not UUID or (after is not None and type(after) is not UUID):
            raise ValueError('Invalid usage request.')
        if type(page) is not int or not 1 <= page <= MAX_PAGE:
            raise ValueError('Invalid usage request.')
        try:
            _range(first_day, last_day)
        except Exception:
            raise ValueError('Invalid usage request.') from None
        return self._store.members(capability_digest(token), organization_id, first_day, last_day, after, page)
