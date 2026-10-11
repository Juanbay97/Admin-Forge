"""Server-discovered identity context and department directory.

Callers never supply an organization id for ``me``: the context comes from the
live session. Org-scoped department operations are admin-only and uniformly deny
foreign or unknown organizations. Authority is enforced in the database function;
this layer only normalizes and redacts.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from forge.invitations import capability_digest

MAX_NAME = 120


class DirectoryDenied(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


class DirectorySuspended(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


class DirectoryConflict(Exception):
    def __init__(self): super().__init__('Directory conflict.')


class DirectoryUnavailable(Exception):
    def __init__(self): super().__init__('Directory unavailable.')


class DirectoryLastAdmin(Exception):
    def __init__(self): super().__init__('Directory conflict.')


@dataclass(frozen=True)
class Department:
    id: UUID
    name: str


@dataclass(frozen=True)
class Member:
    """One member of an organization as an administrator sees it (no secrets)."""
    id: UUID
    email: str
    display_name: str
    status: str
    roles: tuple[str, ...]
    departments: tuple[Department, ...]


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
    def departments(self, digest: str, organization_id: UUID) -> list[Department]: ...
    def create_department(self, digest: str, organization_id: UUID, name: str) -> Department: ...
    def members(self, digest: str, organization_id: UUID) -> list[Member]: ...
    def set_member_status(self, digest: str, organization_id: UUID, member_id: UUID, status: str) -> Member: ...


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

    @staticmethod
    def _organization(organization_id):
        if type(organization_id) is not UUID:
            raise ValueError('Invalid organization.')

    def departments(self, token: str, organization_id: UUID) -> list[Department]:
        self._organization(organization_id)
        return list(self._store.departments(capability_digest(token), organization_id))

    def create_department(self, token: str, organization_id: UUID, name: str) -> Department:
        self._organization(organization_id)
        if (type(name) is not str or not 1 <= len(name.strip()) <= MAX_NAME
                or any(ord(char) < 32 or ord(char) == 127 for char in name)):
            raise ValueError('Invalid department name.')
        return self._store.create_department(capability_digest(token), organization_id, name.strip())

    def members(self, token: str, organization_id: UUID) -> list[Member]:
        self._organization(organization_id)
        return list(self._store.members(capability_digest(token), organization_id))

    def suspend_member(self, token: str, organization_id: UUID, member_id: UUID) -> Member:
        return self._set_status(token, organization_id, member_id, 'suspended')

    def reactivate_member(self, token: str, organization_id: UUID, member_id: UUID) -> Member:
        return self._set_status(token, organization_id, member_id, 'active')

    def _set_status(self, token, organization_id, member_id, status):
        self._organization(organization_id)
        if type(member_id) is not UUID:
            raise ValueError('Invalid member.')
        return self._store.set_member_status(capability_digest(token), organization_id, member_id, status)
