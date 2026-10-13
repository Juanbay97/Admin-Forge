"""Capability governance service: argument validation, the digesting of the session token and the administrator view.

Authority is the database (a fresh verified platform owner, or an active administrator of exactly that company, on every
call); this service only bounds and normalizes arguments before any store call and turns layers into the states an
administrator sees. The member-facing signed document is built in ``forge.capability_effective``.
"""
from dataclasses import dataclass
import json
from uuid import UUID

from forge.app_manifest import PERMISSIONS
from forge.capability_model import CapabilityInvalid
from forge.capability_policy import ID, LOCKS, MAX_LEVEL, CatalogEntry, Layer, resolve_one
from forge.invitations import capability_digest

MAX_ATTRIBUTES_BYTES = 4096
MAX_PAGE = 100
MAX_REVISION = 2 ** 63 - 3
_ENTRY_KEYS = {'version', 'risk', 'is_base', 'default_state', 'min_sandbox_level', 'manifest_sha256', 'credential_locus',
               'declared_permissions', 'granted_permissions', 'attributes'}
_REQUIRED = {'version', 'risk', 'is_base', 'default_state', 'min_sandbox_level'}


@dataclass(frozen=True)
class AdminItem:
    """One capability as a company administrator sees it: the configured state (attestation is the member device's call)."""
    id: str
    kind: str
    risk: str
    is_base: bool
    min_sandbox_level: int
    state: str
    locked: bool
    setting: bool | None


def _id(identifier):
    if type(identifier) is not str or not ID.match(identifier):
        raise CapabilityInvalid()
    return identifier


def _org(org):
    if type(org) is not UUID:
        raise CapabilityInvalid()
    return org


def _state(state):
    if state not in (None, 'on', 'off'):
        raise CapabilityInvalid()
    return state


def _lock(lock):
    if lock not in LOCKS:
        raise CapabilityInvalid()
    return lock


def _page(page):
    if type(page) is not int or not 1 <= page <= MAX_PAGE:
        raise CapabilityInvalid()
    return page


def _before(before):
    if before is not None and (type(before) is not int or not 1 <= before <= MAX_REVISION):
        raise CapabilityInvalid()
    return before


def entry_document(identifier, document):
    """The validated catalog document for one entry (no defaults the database would not also apply, plus the credential locus)."""
    _id(identifier)
    if type(document) is not dict or set(document) - _ENTRY_KEYS or _REQUIRED - set(document):
        raise CapabilityInvalid()
    kind = identifier.split(':', 1)[0]
    declared = document.get('declared_permissions', [])
    granted = document.get('granted_permissions', [])
    attributes = document.get('attributes', {})
    if (type(declared) is not list or type(granted) is not list or type(attributes) is not dict
            or any(name not in PERMISSIONS for name in (*declared, *granted)) or len(set(declared)) != len(declared)
            or len(set(granted)) != len(granted) or (kind != 'app' and (declared or granted))):
        raise CapabilityInvalid()
    try:
        if len(json.dumps(attributes, separators=(',', ':'))) > MAX_ATTRIBUTES_BYTES:
            raise CapabilityInvalid()
    except (TypeError, ValueError):
        raise CapabilityInvalid() from None
    locus = document.get('credential_locus', 'server' if kind == 'connector' else 'none')
    if kind == 'app' and (document['default_state'] != 'off' or type(document.get('manifest_sha256')) is not str):
        raise CapabilityInvalid()  # an app is off by default and pinned to the entry bytes the client will check
    try:
        CatalogEntry(identifier, kind, document['version'], document['risk'], document['is_base'], document['default_state'],
                     document['min_sandbox_level'], document.get('manifest_sha256'), locus, tuple(declared), tuple(granted))
    except ValueError:
        raise CapabilityInvalid() from None
    return {'version': document['version'], 'risk': document['risk'], 'is_base': document['is_base'], 'default_state': document['default_state'],
            'min_sandbox_level': document['min_sandbox_level'], 'manifest_sha256': document.get('manifest_sha256'),
            'credential_locus': locus, 'declared_permissions': list(declared), 'granted_permissions': list(granted),
            'attributes': attributes}


class Capabilities:
    def __init__(self, store):
        self._store = store

    # platform owner
    def catalog(self, token):
        return self._store.catalog(capability_digest(token))

    def put_entry(self, token, identifier, expected, document):
        if type(expected) is not int or not 0 <= expected <= MAX_REVISION:
            raise CapabilityInvalid()
        return self._store.put_entry(capability_digest(token), _id(identifier), expected, entry_document(identifier, document))

    def set_platform_policy(self, token, identifier, state, lock):
        return self._store.set_platform_policy(capability_digest(token), _id(identifier), _state(state), _lock(lock))

    def company_policy(self, token, org):
        return self._store.company_policy(capability_digest(token), _org(org))

    def set_company_override(self, token, org, identifier, state, lock):
        return self._store.set_company_override(capability_digest(token), _org(org), _id(identifier), _state(state), _lock(lock))

    def platform_audit(self, token, before, page):
        return self._store.platform_audit(capability_digest(token), _before(before), _page(page))

    # company administrator
    def company_view(self, token, org):
        snapshot = self._store.admin_snapshot(capability_digest(token), _org(org))
        items = []
        for entry in snapshot.entries:
            effective = resolve_one(entry, snapshot.platform, snapshot.company, snapshot.org, MAX_LEVEL)
            locked = (snapshot.platform.get(entry.id, Layer()).lock == 'forced_off'
                      or snapshot.company.get(entry.id, Layer()).lock == 'forced_off')
            items.append(AdminItem(entry.id, entry.kind, entry.risk, entry.is_base, entry.min_sandbox_level, effective.state, locked,
                                   snapshot.org.get(entry.id)))
        return items

    def set_enabled(self, token, org, identifier, want):
        """Enable (True), disable (False) or return to the inherited state (None); a locked capability is ``CapabilityLocked``."""
        if want is not None and type(want) is not bool:
            raise CapabilityInvalid()
        return self._store.set_org(capability_digest(token), _org(org), _id(identifier), want)

    def org_audit(self, token, org, before, page):
        return self._store.org_audit(capability_digest(token), _org(org), _before(before), _page(page))
