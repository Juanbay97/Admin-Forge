"""The installer a member downloads from the portal, stamped with their company code (``GET /forge/v1/downloads/company``).

The bytes are exactly the published installer: the file ``latest.json`` names under the downloads directory the edge proxy also serves.
Only the response file name differs (``Prometheon-Forge-Setup-<company code>.exe``), which is how the desktop installer learns its
company without a second download. Before a byte is served the file is checked against the manifest (strictly inside the directory,
a plain ``*.exe`` name, size and SHA-256 equal), so a half-copied or swapped installer is a 503 rather than a corrupt download.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from threading import Lock

from forge.admin_mount import _file

MANIFEST = 'latest.json'
STAMPED_NAME = 'Prometheon-Forge-Setup-{}.exe'
_URL = re.compile(r'/downloads/([A-Za-z0-9][A-Za-z0-9._+-]{0,127}\.exe)', re.IGNORECASE)
_DIGEST = re.compile(r'[0-9a-f]{64}')
_MANIFEST_LIMIT = 65536


@dataclass(frozen=True)
class Published:
    path: Path
    size: int
    sha256: str


class PublishedInstaller:
    """Resolves and verifies the published Windows installer. ``published()`` raises ``LookupError`` for anything not servable."""

    def __init__(self, directory):
        self._root = Path(directory).resolve()
        self._lock = Lock()
        self._verified = None  # ((path, mtime_ns, size, digest), published): the digest is recomputed only when the file changes

    def _manifest_entry(self):
        manifest = _file(self._root, MANIFEST)
        if manifest is None or manifest.stat().st_size > _MANIFEST_LIMIT:
            raise LookupError
        try:
            document = json.loads(manifest.read_text(encoding='utf-8'))
            entry = document['platforms']['windows']
            url, digest, size = entry['url'], entry['sha256'], entry['size_bytes']
        except (OSError, ValueError, KeyError, TypeError):
            raise LookupError from None
        match = _URL.fullmatch(url) if type(url) is str else None
        if match is None or type(digest) is not str or not _DIGEST.fullmatch(digest) or type(size) is not int or isinstance(size, bool):
            raise LookupError
        return match.group(1), digest, size

    def published(self) -> Published:
        name, digest, size = self._manifest_entry()
        target = None if name.startswith('.') else _file(self._root, name)
        if target is None:
            raise LookupError
        status = target.stat()
        if status.st_size != size:
            raise LookupError
        key = (target, status.st_mtime_ns, status.st_size, digest)
        with self._lock:
            if self._verified is not None and self._verified[0] == key:
                return self._verified[1]
            actual = hashlib.sha256()
            try:
                with target.open('rb') as handle:
                    for block in iter(lambda: handle.read(1 << 20), b''):
                        actual.update(block)
            except OSError:
                raise LookupError from None
            if actual.hexdigest() != digest:
                raise LookupError
            result = Published(target, size, digest)
            self._verified = (key, result)
            return result
