"""Admin static mount (same origin, strict CSP) and the loopback request guard.

The built SPA is served from an explicit directory under ``/admin``. A missing build
either stops startup (``required``) or degrades to a clear 503 message; it never
falls back to another path. The guard rejects any Host other than the configured
loopback authority (DNS rebinding) and any ``/forge/v1`` mutation whose browser
Origin is not allow-listed. Bearer tokens, not cookies, authenticate calls.
"""
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.cors import CORSMiddleware

from forge.api import ErrorDetail, ErrorEnvelope

ADMIN_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
             "img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
MUTATING = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
CONTENT_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript',
                 '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.json': 'application/json',
                 '.png': 'image/png', '.ico': 'image/x-icon', '.map': 'application/json', '.txt': 'text/plain'}
MISSING_MESSAGE = ('Admin web build is missing. Build it with `npm run build` in the admin directory, '
                   'then restart the control plane.')


class AdminBuildMissing(Exception):
    def __init__(self):
        super().__init__('ADMIN_BUILD_MISSING')


def _refusal(code, message):
    envelope = ErrorEnvelope(error=ErrorDetail(code=code, message=message, request_id=uuid4(), retryable=False,
                                               retry_after_seconds=None, reset_at=None))
    return JSONResponse(status_code=403, content=envelope.model_dump(mode='json'), headers={'Cache-Control': 'no-store'})


def _headers(cache):
    return {'Content-Security-Policy': ADMIN_CSP, 'Cache-Control': cache, 'X-Content-Type-Options': 'nosniff'}


def _file(root, relative):
    """A regular file strictly inside ``root``, or None; never follows a link out of it."""
    parts = relative.split('/')
    if not relative or any(part in ('', '.', '..') or '\\' in part or '\x00' in part for part in parts):
        return None
    try:
        resolved = root.joinpath(*parts).resolve(strict=True)
    except (OSError, ValueError):
        return None
    return resolved if root in resolved.parents and resolved.is_file() else None


def mount_admin(app: FastAPI, directory, *, required: bool):
    root = Path(directory)
    built = root.is_dir() and (root/'index.html').is_file()
    if not built and required:
        raise AdminBuildMissing()
    root = root.resolve() if built else root

    # The links the control plane mails (onboarding, owner set-password) name the public origin without /admin; the query
    # is kept (it carries only the public company code) and the fragment, which never reaches a server, survives a 307.
    def entry(target):
        def redirect(request: Request):
            query = request.url.query
            return RedirectResponse(target + ('?' + query if query else ''), status_code=307, headers={'Cache-Control': 'no-store'})
        return redirect
    for source, target in (('/join', '/admin/join'), ('/onboarding', '/admin/join'), ('/reset-password', '/admin/reset-password')):
        app.get(source, include_in_schema=False)(entry(target))

    @app.get('/admin', include_in_schema=False)
    def admin_redirect():
        return RedirectResponse('/admin/', status_code=307)

    @app.get('/admin/{path:path}', include_in_schema=False)
    def admin(path: str):
        if not built:
            return Response(MISSING_MESSAGE, status_code=503, media_type='text/plain', headers=_headers('no-store'))
        target = _file(root, path)
        if target is None:
            if '.' in path.rsplit('/', 1)[-1]:
                return Response('Not found.', status_code=404, media_type='text/plain', headers=_headers('no-store'))
            target = root/'index.html'  # client-side route: the SPA decides what to render
        cache = 'no-store' if target.name == 'index.html' else (
            'public, max-age=31536000, immutable' if target.parent.name == 'assets' else 'no-cache')
        return Response(target.read_bytes(), media_type=CONTENT_TYPES.get(target.suffix, 'application/octet-stream'),
                        headers=_headers(cache))


def apply_guard(app: FastAPI, *, host: str | None = None, hosts=None, origins, cors_origins):
    """CORS first (innermost), guard last (outermost): a foreign Host never reaches either.

    Exactly one of ``host`` (the single loopback authority) or ``hosts`` (a non-empty frozenset of
    trusted public authorities) names what a request's Host header may be; compared exactly.
    """
    if (host is None) == (hosts is None) or (hosts is not None and (type(hosts) is not frozenset or not hosts)):
        raise ValueError('Exactly one of host or a non-empty frozenset of hosts is required.')
    trusted = frozenset({host}) if hosts is None else hosts
    allowed = frozenset(origins)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=['GET', 'POST', 'PUT', 'OPTIONS'],
                       allow_headers=['Authorization', 'Content-Type'], allow_credentials=False)

    @app.middleware('http')
    async def loopback_guard(request, call_next):
        if request.headers.get('host') not in trusted:
            return _refusal('FORBIDDEN_HOST', 'The request host is not permitted.')
        if request.method in MUTATING and request.url.path.startswith('/forge/v1/'):
            origin = request.headers.get('origin')
            # Server-side callers (the client workspace backend) send no Origin; browsers always do.
            if origin is not None and origin not in allowed:
                return _refusal('FORBIDDEN_ORIGIN', 'The request origin is not permitted.')
        return await call_next(request)
