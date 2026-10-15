"""Owned account catalogue orchestration; credentials and routes remain private."""
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Protocol
from uuid import UUID, uuid5
from forge.gateway_configuration import GatewayCipher, GatewayRecord, GatewayUnavailable
from forge.gateway_catalog_adapter import validated_ids
from forge.invitations import capability_digest
from forge.model_catalog import (AliasSnapshot, CatalogSnapshot, RouteEvidence,
    UnknownCapabilities, Verification)
from forge.model_catalog_store import encode_catalog, decode_catalog


@dataclass(frozen=True, repr=False)
class Discovery:
    gateway: GatewayRecord
    model_ids: tuple[str, ...]


class CatalogStore(Protocol):
    def gateway(self, digest: str, org: UUID) -> GatewayRecord | None: ...
    def save_discovery(self, digest: str, org: UUID, gateway: GatewayRecord, ids: tuple[str, ...]) -> None: ...
    def discovery(self, digest: str, org: UUID) -> Discovery: ...
    def publish(self, digest: str, org: UUID, operation: UUID, expected: int,
        discovery: Discovery, mapping: dict[str, str], default: str,
        payload: str, checksum: str, selection_sha: str) -> int: ...
    def admin_status(self, digest: str, org: UUID) -> tuple[int, str | None, str]: ...
    def member_catalog(self, digest: str, org: UUID) -> tuple[str, str, str] | None: ...


ALIAS = re.compile(r'[a-z][a-z0-9_-]{0,63}')
UPSTREAM = re.compile(r'[!-~]{1,255}')


def valid_selection(operation, expected, gateway_revision, mapping, default):
    """The shape every catalogue publication carries, whoever authorizes it (an administrator or the platform owner)."""
    if (type(operation) is not UUID or type(expected) is not int or not 0 <= expected < 2**63-2
            or type(gateway_revision) is not int or not 1 <= gateway_revision < 2**63-1
            or type(mapping) is not dict or not 1 <= len(mapping) <= 64
            or type(default) is not str or default not in mapping):
        return False
    return all(type(alias) is str and ALIAS.fullmatch(alias) and type(upstream) is str and UPSTREAM.fullmatch(upstream)
               for alias, upstream in mapping.items())


def publication_material(org, binding_id, expected, gateway_revision, mapping, default):
    """The immutable snapshot payload, its checksum and the selection identity for one publication."""
    aliases = tuple(AliasSnapshot(alias, (RouteEvidence(org, binding_id,
        uuid5(binding_id, 'route:' + alias + ':' + upstream),
        uuid5(binding_id, 'discovery:' + upstream), Verification.UNVERIFIED,
        UnknownCapabilities()),)) for alias, upstream in sorted(mapping.items()))
    payload, checksum = encode_catalog(CatalogSnapshot(org, binding_id, expected + 1, aliases))
    return payload, checksum, selection_identity(mapping, default, gateway_revision)


def selection_identity(mapping, default, gateway_revision):
    material = json.dumps({'mapping': mapping, 'default': default,
        'gateway_revision': gateway_revision}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(material.encode()).hexdigest()


class GatewayCatalog:
    def __init__(self, store: CatalogStore, cipher: GatewayCipher, adapter):
        self._store, self._cipher, self._adapter = store, cipher, adapter

    @staticmethod
    def _actor(token, org):
        if type(org) is not UUID:
            raise ValueError('Invalid organization.')
        return capability_digest(token)

    def refresh(self, token: str, org: UUID):
        digest = self._actor(token, org)
        # This short transaction closes before network IO. Saving rechecks all
        # authority and the exact binding after the bounded request completes.
        record = self._store.gateway(digest, org)
        if record is None:
            raise GatewayUnavailable()
        ids = validated_ids(self._adapter.discover(self._cipher.open_key(org, record)))
        self._store.save_discovery(digest, org, record, ids)
        return {'gateway_revision': record.revision, 'model_ids': list(ids),
                'capability_state': 'unknown', 'verification': 'unverified'}

    async def refresh_async(self, token: str, org: UUID):
        """HTTP composition awaits network IO on its existing server event loop.

        Synchronous PostgreSQL operations use the framework's bounded worker
        limiter and are not abandoned if their caller is cancelled.
        """
        from anyio.to_thread import run_sync
        digest = self._actor(token, org)
        record = await run_sync(self._store.gateway, digest, org, abandon_on_cancel=False)
        if record is None:
            raise GatewayUnavailable()
        key = self._cipher.open_key(org, record)
        ids = validated_ids(await self._adapter.discover_async(key))
        await run_sync(self._store.save_discovery, digest, org, record, ids, abandon_on_cancel=False)
        return {'gateway_revision': record.revision, 'model_ids': list(ids),
                'capability_state': 'unknown', 'verification': 'unverified'}

    def publish(self, token: str, org: UUID, operation: UUID, expected: int,
            gateway_revision: int, mapping: dict[str, str], default: str):
        digest = self._actor(token, org)
        if not valid_selection(operation, expected, gateway_revision, mapping, default):
            raise ValueError('Invalid catalogue selection.')
        discovery = self._store.discovery(digest, org)
        record = discovery.gateway
        self._cipher.verify(org, record)
        if record.revision != gateway_revision:
            from forge.gateway_configuration import GatewayConflict
            raise GatewayConflict()
        if not set(mapping.values()) <= set(validated_ids(discovery.model_ids)):
            raise ValueError('Model unavailable in trusted discovery.')
        payload, checksum, selection_sha = publication_material(org, record.binding_id, expected, gateway_revision, mapping, default)
        revision = self._store.publish(digest, org, operation, expected, discovery,
            dict(mapping), default, payload, checksum, selection_sha)
        return {'revision': revision, 'default_model': default,
                'models': [alias for alias in sorted(mapping)]}

    def read(self, token: str, org: UUID):
        record = self._store.member_catalog(self._actor(token, org), org)
        if record is None:
            from forge.gateway_configuration import GatewayDenied
            raise GatewayDenied()
        payload, checksum, default = record
        try:
            snapshot = decode_catalog(payload, checksum)
            if snapshot.organization_id != org or default not in {alias.name for alias in snapshot.aliases}:
                raise GatewayUnavailable()
            return {**snapshot.public_projection(), 'default_model': default}
        except Exception:
            raise GatewayUnavailable() from None

    def admin_status(self, token: str, org: UUID):
        revision, default, state = self._store.admin_status(self._actor(token, org), org)
        if (type(revision) is not int or not 0 <= revision < 2**63-1
                or state not in ('UNPUBLISHED','CURRENT','STALE_GATEWAY')
                or (state == 'UNPUBLISHED' and (revision != 0 or default is not None))
                or (state != 'UNPUBLISHED' and (revision == 0 or type(default) is not str
                    or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', default)))):
            raise GatewayUnavailable()
        return {'catalogue_revision': revision, 'default_model': default, 'publication_state': state}
