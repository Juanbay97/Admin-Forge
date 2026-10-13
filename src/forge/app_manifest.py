"""App manifest: the extension contract between the platform catalog and a future embedded app host. Schema and validation only.

The grammar, the permission vocabulary and the finite error codes mirror the client host (``clients/openyak``
``frontend/src/lib/forge-extensions/validate.ts`` and ``manifest.ts``), which is the source of truth for these shapes: the
control plane must refuse exactly what the client would refuse. Nothing here loads, hosts or runs an app.

``sha256`` in the manifest is the hash of the entry file bytes; it is what the effective policy carries as ``manifest_sha256``
so the client can pin the entry it loads. ``manifest_digest`` is a separate canonical-JSON hash of the manifest itself (without
its signature) for tamper evidence in the catalog.
"""
from dataclasses import dataclass
import hashlib
import json
import re

MANIFEST_MAX_BYTES = 16 * 1024
# What an extension can hold in v1; the names reserved for later changes are refused as such, never silently ignored.
PERMISSIONS = ('ui.title', 'storage.local')
RESERVED_PERMISSIONS = ('network', 'fs', 'tools')
_KEYS = ('id', 'version', 'publisher', 'entry', 'permissions', 'sha256')
_OPTIONAL = ('signature',)
_ID = re.compile(r'\A[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+\Z')
_ID_MAX = 128
_SEMVER = re.compile(r'\A(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z')
_ENTRY = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.html\Z')
_SHA256 = re.compile(r'\A[0-9a-f]{64}\Z')
_SIGNATURE = re.compile(r'\A[A-Za-z0-9+/=_-]{1,1024}\Z')
_CONTROL = re.compile('[\u0000-\u001f\u007f\u2028\u2029]')


class ManifestError(Exception):
    """The message is one stable code: shape, oversize, unknown_key, missing_key, bad_id, bad_version, bad_publisher,
    bad_entry, bad_permissions, duplicate_permission, unknown_permission, reserved_permission, bad_sha256, bad_signature."""


@dataclass(frozen=True)
class Manifest:
    id: str
    version: str
    publisher: str
    entry: str
    permissions: tuple
    sha256: str
    signature: str | None = None


def _permission_error(name):
    if name in PERMISSIONS:
        return None
    return 'reserved_permission' if name.split('.')[0] in RESERVED_PERMISSIONS else 'unknown_permission'


def validate_manifest(raw) -> Manifest:
    if type(raw) is not dict:
        raise ManifestError('shape')
    if set(raw) - {*_KEYS, *_OPTIONAL}:
        raise ManifestError('unknown_key')
    if any(key not in raw for key in _KEYS):
        raise ManifestError('missing_key')
    identifier, version, publisher, entry, permissions, sha256 = (raw[key] for key in _KEYS)
    signature = raw.get('signature')
    if type(identifier) is not str or len(identifier) > _ID_MAX or not _ID.match(identifier):
        raise ManifestError('bad_id')
    if type(version) is not str or len(version) > 64 or not _SEMVER.match(version):
        raise ManifestError('bad_version')
    if type(publisher) is not str or not publisher.strip() or len(publisher) > 80 or _CONTROL.search(publisher):
        raise ManifestError('bad_publisher')
    # One top-level file name: no separators, no drive or scheme, no dot segments; the host never resolves paths.
    if type(entry) is not str or not _ENTRY.match(entry) or '..' in entry:
        raise ManifestError('bad_entry')
    if type(permissions) is not list:
        raise ManifestError('bad_permissions')
    seen = set()
    for name in permissions:
        if type(name) is not str:
            raise ManifestError('bad_permissions')
        problem = _permission_error(name)
        if problem:
            raise ManifestError(problem)
        if name in seen:
            raise ManifestError('duplicate_permission')
        seen.add(name)
    if type(sha256) is not str or not _SHA256.match(sha256):
        raise ManifestError('bad_sha256')
    if 'signature' in raw and (type(signature) is not str or not _SIGNATURE.match(signature)):
        raise ManifestError('bad_signature')
    return Manifest(identifier, version, publisher.strip(), entry, tuple(permissions), sha256, signature)


def parse_manifest(text: str) -> Manifest:
    """Manifest text: the size is checked on the bytes before any parsing happens."""
    if len(text.encode('utf-8')) > MANIFEST_MAX_BYTES:
        raise ManifestError('oversize')
    try:
        raw = json.loads(text)
    except ValueError:
        raise ManifestError('shape') from None
    return validate_manifest(raw)


def canonical_json(manifest: Manifest) -> bytes:
    """Sorted keys, no spaces, UTF-8, the signature excluded: the stable bytes a digest or a signature is taken over."""
    document = {'id': manifest.id, 'version': manifest.version, 'publisher': manifest.publisher, 'entry': manifest.entry,
                'permissions': list(manifest.permissions), 'sha256': manifest.sha256}
    return json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def manifest_digest(manifest: Manifest) -> str:
    return hashlib.sha256(canonical_json(manifest)).hexdigest()
