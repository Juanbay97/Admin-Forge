"""Server-discovered identity context.

Callers never supply an organization id for ``me``: the context comes from the
live session. Authority is enforced in the database function; this layer only
normalizes and redacts.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from forge.invitations import capability_digest


class DirectoryDenied(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


class DirectorySuspended(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


class DirectoryUnavailable(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


@dataclass(frozen=True)
class Department:
    id: UUID
    name: str


@dataclass(frozen=True)
class MemberRow:
    """One membership of the validated account, in any status (store output)."""
    account_id: UUID
    email: str
    display_name: str
    organization_id: UUID
    organization_name: str
    status: str
    roles: tuple[str, ...]
    departments: tuple[Department, ...]


@dataclass(frozen=True)
class Membership:
    id: UUID
    display_name: str
    status: str
    roles: tuple[str, ...]
    departments: tuple[Department, ...]


@dataclass(frozen=True)
class Account:
    id: UUID
    email: str
    display_name: str


@dataclass(frozen=True)
class Me:
    account: Account
    organizations: tuple[Membership, ...]


class DirectoryStore(Protocol):
    def me(self, digest: str) -> list[MemberRow]: ...


class DirectoryService:
    def __init__(self, store: DirectoryStore):
        self._store = store

    def me(self, token: str) -> Me:
        rows = self._store.me(capability_digest(token))
        if not rows:
            raise DirectoryDenied()
        active = [row for row in rows if row.status == 'active']
        if not active:
            # Every membership is suspended or archived: access is denied, not empty.
            raise DirectorySuspended()
        first = active[0]
        if any(row.account_id != first.account_id for row in rows):
            raise DirectoryUnavailable()
        return Me(Account(first.account_id, first.email, first.display_name),
                  tuple(Membership(row.organization_id, row.organization_name, row.status,
                                   row.roles, row.departments) for row in active))
