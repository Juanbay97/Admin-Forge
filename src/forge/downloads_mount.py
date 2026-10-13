"""Read-only installer hosting for the local stack (``/downloads/*``).

In production the edge proxy serves the same directory first; this mount is the local and fallback implementation, with the
same rules: regular files strictly inside the directory, no dotfiles, no listing, ``latest.json`` never cached and versioned
files immutable. Nothing here writes, follows a link out of the directory or reveals why a path was refused.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from forge.admin_mount import _file

MANIFEST = 'latest.json'
_HEADERS = {'X-Content-Type-Options': 'nosniff'}


def mount_downloads(app: FastAPI, directory):
    root = Path(directory).resolve()

    @app.get('/downloads/{path:path}', include_in_schema=False)
    def downloads(path: str):
        target = None if any(part.startswith('.') for part in path.split('/')) else _file(root, path)
        if target is None:
            return Response('Not found.', status_code=404, media_type='text/plain', headers={**_HEADERS, 'Cache-Control': 'no-store'})
        manifest = target.name == MANIFEST and target.parent == root
        cache = 'no-cache' if manifest else 'public, max-age=31536000, immutable'
        kind = 'application/json' if target.suffix == '.json' else 'application/octet-stream'
        return FileResponse(target, media_type=kind, headers={**_HEADERS, 'Cache-Control': cache})