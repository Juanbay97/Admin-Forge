"""Platform model discovery and catalog publication for one company (migration 0048).

The platform owner assigns gateway keys to a company (``forge.gateway_keys``); this service lets the same owner ask those
keys which models they can reach, select models with aliases and a default, and publish the company catalog. It reuses the
company catalog code: discovery asks each key through the same bounded ``HttpxModelsAdapter`` and the publication is the same
immutable snapshot (``forge.gateway_catalog.publication_material``) bound to the company profile, so the member routes, the
rebinding across key rotation and the administrator's read are unchanged.

Authority is the database (a fresh verified owner on every call). This service only turns the bearer into its digest, opens the
sealed key text for one request (never stored or returned), bounds the arguments and reports a finite per-key state.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from anyio.to_thread import run_sync

from forge.gateway_catalog import publication_material, valid_selection
from forge.gateway_configuration import GatewayCipher, GatewayRecord
from forge.invitations import capability_digest
from forge.platform import PlatformInvalid, RevisionConflict

# The finite per-key outcomes shown to the owner: never an upstream message, a status line or any key material.
OK, INACTIVE, DISABLED, NO_KEY, UNREADABLE, UNREACHABLE = 'ok', 'inactive', 'disabled', 'no_key', 'unreadable', 'unreachable'


@dataclass(frozen=True, repr=False)
class CatalogKey:
    """One assigned key as the discovery function returns it; the sealed value never leaves this module."""
    revision: int
    binding_id: UUID
    key_id: UUID
    label: str
    origin: str
    priority: int
    assigned_active: bool
    key_status: str
    key_revision: int
    encrypted_key: str | None


@dataclass(frozen=True, repr=False)
class CatalogStatus:
    revision: int
    binding_id: UUID
    ceiling: list | None
    discovered: list | None
    discovered_at: datetime | None
    catalogue_revision: int
    default_alias: str | None
    publication_state: str
    mapping: dict | None


class CatalogStore(Protocol):
    def keys(self, digest: str, org: UUID) -> list: ...
    def save_discovery(self, digest: str, org: UUID, revision: int, binding: UUID, ids: list) -> datetime: ...
    def status(self, digest: str, org: UUID) -> CatalogStatus | None: ...
    def publish(self, digest: str, org: UUID, operation: UUID, expected: int, gateway_revision: int, binding: UUID,
                mapping: dict, default: str, payload: str, checksum: str, selection_sha: str) -> int: ...


class PlatformCatalog:
    def __init__(self, store: CatalogStore, cipher: GatewayCipher, adapter):
        self._store, self._cipher, self._adapter = store, cipher, adapter

    @staticmethod
    def _org(org):
        if type(org) is not UUID:
            raise PlatformInvalid()

    def read(self, token, org):
        """The profile, the stored discovery and the published selection; ``None`` while no key is assigned."""
        self._org(org)
        status = self._store.status(capability_digest(token), org)
        if status is None:
            return None
        return {'gateway_revision': status.revision, 'ceiling': None if status.ceiling is None else sorted(status.ceiling),
                'discovered': None if status.discovered is None else {'model_ids': sorted(status.discovered),
                                                                      'at': status.discovered_at.isoformat()},
                'catalogue': {'revision': status.catalogue_revision, 'default_model': status.default_alias,
                              'state': status.publication_state, 'aliases': dict(sorted((status.mapping or {}).items()))}}

    async def discover(self, token, org):
        """Ask every active assigned key for its models, store the union as the company's discovery and report each key."""
        self._org(org)
        digest = capability_digest(token)
        rows = await run_sync(self._store.keys, digest, org, abandon_on_cancel=False)
        probes = await asyncio.gather(*(self._probe(org, row) for row in rows))
        union = sorted({model for _, ids in probes for model in ids})
        discovered_at = None
        if rows and union:
            discovered_at = await run_sync(self._store.save_discovery, digest, org, rows[0].revision, rows[0].binding_id, union,
                                           abandon_on_cancel=False)
        keys = [{'key_id': str(row.key_id), 'label': row.label, 'origin': row.origin, 'priority': row.priority,
                 'state': state, 'model_count': len(ids), 'model_ids': ids}
                for row, (state, ids) in zip(rows, probes)]
        return {'keys': keys, 'model_ids': union, 'discovered_at': None if discovered_at is None else discovered_at.isoformat()}

    async def _probe(self, org, row):
        if not row.assigned_active:
            return INACTIVE, []
        if row.key_status != 'active':
            return DISABLED, []
        if row.encrypted_key is None:
            return NO_KEY, []
        try:
            key = self._cipher.open_key(org, GatewayRecord(row.revision, row.binding_id, row.origin, row.encrypted_key,
                                                            row.key_id, row.key_revision))
        except Exception:
            return UNREADABLE, []
        try:
            return OK, list(await self._adapter.discover_async(key))
        except Exception:
            return UNREACHABLE, []

    def publish(self, token, org, operation, expected, gateway_revision, mapping, default):
        """Publish the selection on the company's profile binding; the ceiling becomes the selected upstream models."""
        self._org(org)
        if not valid_selection(operation, expected, gateway_revision, mapping, default):
            raise PlatformInvalid()
        digest = capability_digest(token)
        status = self._store.status(digest, org)
        if status is None or status.revision != gateway_revision:
            raise RevisionConflict()
        if status.discovered is None or not set(mapping.values()) <= set(status.discovered):
            raise PlatformInvalid()
        payload, checksum, selection_sha = publication_material(org, status.binding_id, expected, gateway_revision, mapping, default)
        revision = self._store.publish(digest, org, operation, expected, gateway_revision, status.binding_id, dict(mapping), default,
                                       payload, checksum, selection_sha)
        return {'revision': revision, 'default_model': default, 'models': sorted(mapping)}
