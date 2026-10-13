"""Platform reads for the console: who a company's members are (and, from 0044, the overview and the per-day usage series).

Authority is the database (a fresh verified platform owner on every call). This service only bounds the arguments, turns the bearer
capability into its digest and returns finite, content-free values: directory fields an administrator already sees, counters
and identifiers, never a secret, a prompt or a key.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from forge.directory import Department
from forge.invitations import capability_digest
from forge.platform import MAX_PAGE, PlatformInvalid


@dataclass(frozen=True)
class PlatformMember:
    """One member of a company as the platform owner sees it: the same fields a company administrator already has."""
    id: UUID
    email: str
    display_name: str
    status: str
    roles: tuple[str, ...]
    departments: tuple[Department, ...]


class ReadsStore(Protocol):
    def members(self, digest, organization_id, after, page) -> list: ...


class PlatformReads:
    def __init__(self, store):
        self._store = store

    def members(self, token, organization_id, after=None, page=50):
        if (type(organization_id) is not UUID or (after is not None and type(after) is not UUID)
                or type(page) is not int or not 1 <= page <= MAX_PAGE):
            raise PlatformInvalid()
        return self._store.members(capability_digest(token), organization_id, after, page)
