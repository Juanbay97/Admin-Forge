"""Unpublished private catalog persistence; trusted callers own transactions.

No authentication, pool ownership, publication, member access or router inspection.
Database permissions constrain the internal writer; administrator corruption is
outside that boundary. Reads still reject corrupt or noncanonical stored data.
"""
import hashlib
import json
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.model_catalog import (
    AliasSnapshot, Capabilities, CatalogSnapshot, Modality, RouteEvidence, Verification, UnknownCapabilities,
)

MAX_PAYLOAD_BYTES = 1024 * 1024


class CatalogStorageError(RuntimeError):
    def __init__(self):
        super().__init__("Catalog storage unavailable")


def _require(condition):
    if not condition:
        raise ValueError()


def _uuid(value):
    _require(type(value) is str)
    result = UUID(value)
    _require(str(result) == value)
    return result


def _fields(value, keys):
    _require(type(value) is dict and set(value) == set(keys.split()))


def _array(value):
    _require(type(value) is list and bool(value))
    return value


def _document(snapshot):
    _require(type(snapshot) is CatalogSnapshot)
    _require(type(snapshot.revision) is int and 0 < snapshot.revision < 2**63)
    return {
        "schema_version": 2 if any(type(route.capabilities) is UnknownCapabilities
            for alias in snapshot.aliases for route in alias.routes) else 1,
        "organization_id": str(snapshot.organization_id),
        "router_binding_id": str(snapshot.router_binding_id),
        "revision": snapshot.revision,
        "aliases": [
            {"name": alias.name, "routes": [
                {"organization_id": str(route.organization_id),
                 "router_binding_id": str(route.router_binding_id),
                 "route_id": str(route.route_id), "evidence_id": str(route.evidence_id),
                 "verification": route.verification.value,
                 "capabilities": route.capabilities.public_projection()}
                for route in sorted(alias.routes, key=lambda item: str(item.route_id))
            ]}
            for alias in sorted(snapshot.aliases, key=lambda item: item.name)
        ],
    }


def _serialize(snapshot):
    return json.dumps(_document(snapshot), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def _restore(data):
    _fields(data, "schema_version organization_id router_binding_id revision aliases")
    _require(type(data["schema_version"]) is int and data["schema_version"] in (1, 2))
    aliases = []
    for alias in _array(data["aliases"]):
        _fields(alias, "name routes")
        routes = []
        for route in _array(alias["routes"]):
            _fields(route, "organization_id router_binding_id route_id evidence_id verification capabilities")
            cap = route["capabilities"]
            if "capability_state" in cap:
                _require(data["schema_version"] == 2)
                _require(cap == UnknownCapabilities().public_projection())
                capability = UnknownCapabilities()
            else:
                _fields(cap, "input_modalities output_modalities tools streaming max_context_tokens max_output_tokens")
                modalities = {}
                for key in ("input_modalities", "output_modalities"):
                    values = _array(cap[key])
                    _require(all(type(value) is str for value in values))
                    _require(len(set(values)) == len(values))
                    modalities[key] = frozenset(Modality(value) for value in values)
                capability = Capabilities(**{**cap, **modalities})
            routes.append(RouteEvidence(
                *(_uuid(route[key]) for key in ("organization_id", "router_binding_id",
                                               "route_id", "evidence_id")),
                Verification(route["verification"]),
                capability,
            ))
        aliases.append(AliasSnapshot(alias["name"], tuple(routes)))
    return CatalogSnapshot(_uuid(data["organization_id"]), _uuid(data["router_binding_id"]),
                           data["revision"], tuple(aliases))


def encode_catalog(snapshot):
    """Accept the typed domain only; never an arbitrary serialized blob."""
    try:
        payload = _serialize(snapshot)
        _require(len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES)
        # Reconstruct even typed input; persistence never trusts a mutated object.
        restored = _restore(json.loads(payload))
        _require(_serialize(restored) == payload)
        return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()
    except Exception:
        raise CatalogStorageError() from None


def decode_catalog(payload, checksum):
    try:
        _require(type(payload) is str and type(checksum) is str)
        _require(len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES)
        _require(hashlib.sha256(payload.encode("utf-8")).hexdigest() == checksum)
        snapshot = _restore(json.loads(payload))
        # Reject duplicate keys, whitespace, alternate UUIDs, unsorted arrays,
        # extra fields and noncanonical numeric encodings, not merely valid JSON.
        _require(_serialize(snapshot) == payload)
        return snapshot
    except Exception:
        raise CatalogStorageError() from None


def _key(organization_id, router_binding_id, revision):
    _require(type(organization_id) is UUID and type(router_binding_id) is UUID)
    _require(type(revision) is int and 0 < revision < 2**63)


def insert_catalog(connection, snapshot):
    """Append once inside a caller-owned transaction; duplicates always fail."""
    payload, checksum = encode_catalog(snapshot)
    try:
        _require(connection.info.transaction_status is TransactionStatus.INTRANS)
        connection.execute(
            "INSERT INTO forge.model_catalog_snapshots "
            "(organization_id,router_binding_id,revision,payload,payload_sha256) "
            "VALUES (%s,%s,%s,%s,%s)",
            (snapshot.organization_id, snapshot.router_binding_id, snapshot.revision,
             payload, checksum),
        )
    except Exception:
        raise CatalogStorageError() from None


def read_catalog(connection, organization_id, router_binding_id, revision):
    """Private typed read; absent/foreign rows return None under the caller's RLS."""
    try:
        _key(organization_id, router_binding_id, revision)
        _require(connection.info.transaction_status is TransactionStatus.INTRANS)
        with connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                "SELECT payload,payload_sha256 FROM forge.model_catalog_snapshots "
                "WHERE organization_id=%s AND router_binding_id=%s AND revision=%s",
                (organization_id, router_binding_id, revision),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = decode_catalog(*row)
        _require((snapshot.organization_id, snapshot.router_binding_id, snapshot.revision)
                 == (organization_id, router_binding_id, revision))
        return snapshot
    except Exception:
        raise CatalogStorageError() from None

