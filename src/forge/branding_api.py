"""Branding HTTP routes, mounted onto an existing account app and kept OUT of the pinned contract.

Public (no session, rate-limited, uniform 404): ``GET /forge/v1/branding?org=<code>`` and the
content-addressed ``GET /forge/v1/branding/assets/<sha256>``. Authenticated: the member projection
``GET /forge/v1/orgs/{o}/branding`` and the administrator-only ``PUT`` (compare-and-swap), ``POST
.../reset`` and ``POST .../assets`` (raw PNG/WebP). Servers never send CSS: clients get typed tokens.

Browsers can only reach the mutating routes through the loopback guard (Host and Origin checks) that
``forge.admin_mount.apply_guard`` installs around the whole app; bearer tokens, not cookies, authenticate.
"""
import json
from math import ceil
import re
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from forge.api import ErrorDetail, ErrorEnvelope
from forge.branding import ASSET_KINDS, BrandingInvalid, member_view, parse, public_view
from forge.branding_assets import AssetRejected, MAX_BYTES, sanitize
from forge.branding_store import BrandingConflict, BrandingDenied, BrandingLimit, BrandingUnavailable
from forge.invitations import capability_digest

JSON_LIMIT = 8192
ASSET_HEADERS = {'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox"}
_CODE = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
_SHA = re.compile(r'[0-9a-f]{64}')
_MAX_REVISION = 2 ** 63 - 3
_MESSAGES = {
    'color': 'A color must be a #RRGGBB hex value.',
    'font': 'The font is not in the vetted list.',
    'name': 'The product name must be 1 to 40 plain characters.',
    'login_copy': 'The login copy must be at most 280 plain characters.',
    'contrast': 'The primary color must reach 3:1 contrast against white.',
    'unreadable': 'These colors cannot produce a readable theme: the accent needs 3:1 contrast against white and '
                  'the background tint must carry dark text.',
    'asset': 'An asset reference must be the content hash of an uploaded logo.',
    'shape': 'The branding document has an unexpected shape.',
    'unknown_asset': 'The referenced logo was not uploaded for this organization.',
    'quota': 'The organization already stores the maximum number of logos.',
    'revision': 'The expected revision must be a non-negative integer.',
    'kind': 'The asset kind must be logoLight, logoDark or isotipo.',
    'body': 'The request body is not valid JSON of the expected shape.',
    'asset_type': 'Only PNG and WebP images are accepted.',
    'asset_malformed': 'The image is malformed or outside the allowed dimensions.',
    'asset_size': 'The image is larger than the allowed size.',
}
_ASSET_REASONS = {413: 'asset_size', 415: 'asset_type', 422: 'asset_malformed'}


class RateLimiter:
    """Process-local token buckets: one per client address plus one global cap.

    Documented limit: a single-process loopback control plane. Several instances would each keep
    their own buckets, so a multi-instance deployment must front this with a shared limiter.
    The client address is the socket peer; ``X-Forwarded-For`` is never trusted.
    """
    OVERFLOW = '*overflow*'

    def __init__(self, *, per_client=(30, 1.0), overall=(300, 20.0), max_clients=4096, clock=monotonic):
        self.client_capacity, self.client_rate = per_client
        self.overall_capacity, self.overall_rate = overall
        self.max_clients, self.clock, self.lock = max_clients, clock, Lock()
        self._clients = {}
        self._overall = [float(self.overall_capacity), clock()]

    @property
    def tracked(self):
        return len(self._clients)

    @staticmethod
    def _refill(bucket, now, capacity, rate):
        bucket[0] = min(float(capacity), bucket[0] + (now - bucket[1]) * rate)
        bucket[1] = now

    def admit(self, client):
        """None when admitted, else the seconds until a request could be admitted."""
        with self.lock:
            now = self.clock()
            if client not in self._clients and len(self._clients) >= self.max_clients:
                self._clients = {key: bucket for key, bucket in self._clients.items()
                                 if bucket[0] + (now - bucket[1]) * self.client_rate < self.client_capacity}
                if len(self._clients) >= self.max_clients:
                    client = self.OVERFLOW
            bucket = self._clients.setdefault(client, [float(self.client_capacity), now])
            self._refill(bucket, now, self.client_capacity, self.client_rate)
            self._refill(self._overall, now, self.overall_capacity, self.overall_rate)
            if bucket[0] < 1:
                return (1 - bucket[0]) / self.client_rate
            if self._overall[0] < 1:
                return (1 - self._overall[0]) / self.overall_rate
            bucket[0] -= 1
            self._overall[0] -= 1
            return None


def _envelope(status, code, message, *, retry=None, headers=None, request_id=None):
    body = ErrorEnvelope(error=ErrorDetail(code=code, message=message, request_id=request_id or uuid4(),
                                           retryable=retry is not None or status == 503,
                                           retry_after_seconds=retry, reset_at=None))
    return JSONResponse(status_code=status, content=body.model_dump(mode='json'), headers=headers)


# One constant body for every public miss (unknown, inactive, malformed, unpublished): no request id varies.
_PUBLIC_MISS = ErrorEnvelope(error=ErrorDetail(
    code='NOT_FOUND', message='The requested resource is unavailable.', request_id=UUID(int=0), retryable=False,
    retry_after_seconds=None, reset_at=None)).model_dump_json().encode('utf-8')


def _miss():
    return Response(_PUBLIC_MISS, status_code=404, media_type='application/json')


def _etag_matches(header, tag):
    candidates = [part.strip() for part in (header or '').split(',')]
    return '*' in candidates or any(part.removeprefix('W/') == tag for part in candidates)


class _Refusal(Exception):
    def __init__(self, response):
        self.response = response


def _unique(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError
    return dict(pairs)


async def _read(request, limit):
    declared = request.headers.get('content-length')
    if declared is not None and (not declared.isascii() or not declared.isdigit()):
        raise _Refusal(_envelope(422, 'INVALID_REQUEST', _MESSAGES['body']))
    if declared is not None and int(declared) > limit:
        raise _Refusal(_envelope(413, 'PAYLOAD_TOO_LARGE', _MESSAGES['asset_size']))
    data = bytearray()
    async for piece in request.stream():
        data.extend(piece)
        if len(data) > limit:
            raise _Refusal(_envelope(413, 'PAYLOAD_TOO_LARGE', _MESSAGES['asset_size']))
    return bytes(data)


def _revision(value):
    if type(value) is not int or not 0 <= value <= _MAX_REVISION:
        raise _Refusal(_envelope(422, 'INVALID_REQUEST', _MESSAGES['revision']))
    return value


async def _json(request, keys):
    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if media != 'application/json':
        raise _Refusal(_envelope(415, 'UNSUPPORTED_MEDIA_TYPE', _MESSAGES['body']))
    raw = await _read(request, JSON_LIMIT)
    try:
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
    except (ValueError, UnicodeDecodeError):
        raise _Refusal(_envelope(422, 'INVALID_REQUEST', _MESSAGES['body'])) from None
    if type(document) is not dict or set(document) != keys:
        raise _Refusal(_envelope(422, 'INVALID_REQUEST', _MESSAGES['body']))
    return document


def mount_branding(app: FastAPI, *, store, sessions, readiness=None, limiter=None):
    """Add the branding routes (all ``include_in_schema=False``, so the contract pin is unchanged)."""
    limiter = RateLimiter() if limiter is None else limiter

    @app.middleware('http')
    async def branding_cache(request: Request, call_next):
        # Outermost of the account middleware: only successful public reads may be cached.
        response = await call_next(request)
        if request.method == 'GET' and response.status_code in (200, 304):
            if request.url.path == '/forge/v1/branding':
                response.headers['Cache-Control'] = 'no-cache'
            elif request.url.path.startswith('/forge/v1/branding/assets/'):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return response

    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    def throttle(request):
        client = request.client.host if request.client else 'unknown'
        wait = limiter.admit(client)
        if wait is not None:
            seconds = max(1, ceil(wait))
            raise _Refusal(_envelope(429, 'RATE_LIMITED', 'Too many requests.', retry=seconds,
                                     headers={'Retry-After': str(seconds)}))

    async def public(request, lookup):
        try:
            throttle(request)
            return await lookup()
        except _Refusal as refusal:
            return refusal.response
        except Exception:
            return _envelope(503, 'SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.')

    @app.get('/forge/v1/branding', include_in_schema=False)
    async def public_branding(request: Request):
        async def lookup():
            codes = request.query_params.getlist('org')
            if len(codes) != 1 or not _CODE.fullmatch(codes[0]):
                return _miss()
            found = await blocking(store.public, codes[0])
            if found is None:
                return _miss()
            tag = '"%d"' % found.revision
            headers = {'ETag': tag, 'X-Content-Type-Options': 'nosniff'}
            if _etag_matches(request.headers.get('if-none-match'), tag):
                return Response(status_code=304, headers=headers)
            return Response(json.dumps(public_view(found), separators=(',', ':'), sort_keys=True),
                            media_type='application/json', headers=headers)
        return await public(request, lookup)

    @app.get('/forge/v1/branding/assets/{sha256:path}', include_in_schema=False)
    async def public_asset(sha256: str, request: Request):
        async def lookup():
            if not _SHA.fullmatch(sha256):
                return _miss()
            served = await blocking(store.asset, sha256)
            if served is None:
                return _miss()
            tag = '"%s"' % sha256
            headers = {'ETag': tag, **ASSET_HEADERS}
            if _etag_matches(request.headers.get('if-none-match'), tag):
                return Response(status_code=304, headers=headers)
            return Response(served.data, media_type=served.content_type, headers=headers)
        return await public(request, lookup)

    async def authenticate(request):
        header = request.headers.getlist('authorization')
        scheme, separator, value = (header[0] if len(header) == 1 else '').partition(' ')
        if scheme.lower() != 'bearer' or not separator or len(value) != 43 or any(c.isspace() for c in value):
            raise _Refusal(_envelope(401, 'UNAUTHENTICATED', 'A valid Forge bearer token is required.',
                                     headers={'WWW-Authenticate': 'Bearer'}))
        try:
            if readiness is None or not await blocking(readiness.check):
                raise _Refusal(_envelope(503, 'SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.'))
            identity = await blocking(sessions.validate, value)
            digest = capability_digest(value)
        except _Refusal:
            raise
        except ValueError:
            identity = None
        except Exception:
            raise _Refusal(_envelope(503, 'SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.')) from None
        if identity is None:
            raise _Refusal(_envelope(401, 'UNAUTHENTICATED', 'A valid Forge bearer token is required.',
                                     headers={'WWW-Authenticate': 'Bearer'}))
        return digest

    async def guarded(request, operation):
        try:
            digest = await authenticate(request)
            return await operation(digest)
        except _Refusal as refusal:
            return refusal.response
        except BrandingDenied:
            return _envelope(404, 'NOT_FOUND', 'The requested resource is unavailable.')
        except BrandingConflict:
            return _envelope(409, 'REVISION_CONFLICT', 'The branding revision changed.')
        except BrandingLimit:
            return _envelope(422, 'INVALID_REQUEST', _MESSAGES['quota'])
        except BrandingInvalid as error:
            return _envelope(422, 'INVALID_REQUEST', _MESSAGES.get(error.reason, _MESSAGES['shape']))
        except ValueError:
            return _envelope(422, 'INVALID_REQUEST', _MESSAGES['unknown_asset'])
        except BrandingUnavailable:
            return _envelope(503, 'SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.')
        except Exception:
            return _envelope(503, 'SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.')

    @app.get('/forge/v1/orgs/{organization_id}/branding', include_in_schema=False)
    async def member_branding(organization_id: UUID, request: Request):
        async def operation(digest):
            return JSONResponse(member_view(await blocking(store.read, digest, organization_id)))
        return await guarded(request, operation)

    @app.put('/forge/v1/orgs/{organization_id}/branding', include_in_schema=False)
    async def save_branding(organization_id: UUID, request: Request):
        async def operation(digest):
            document = await _json(request, {'expectedRevision', 'branding'})
            expected = _revision(document['expectedRevision'])
            value = parse(document['branding'])
            return JSONResponse(public_view(await blocking(store.save, digest, organization_id, expected, value)))
        return await guarded(request, operation)

    @app.post('/forge/v1/orgs/{organization_id}/branding/reset', include_in_schema=False)
    async def reset_branding(organization_id: UUID, request: Request):
        async def operation(digest):
            document = await _json(request, {'expectedRevision'})
            expected = _revision(document['expectedRevision'])
            return JSONResponse(public_view(await blocking(store.reset, digest, organization_id, expected)))
        return await guarded(request, operation)

    @app.post('/forge/v1/orgs/{organization_id}/branding/assets', include_in_schema=False)
    async def upload_asset(organization_id: UUID, request: Request):
        async def operation(digest):
            kinds = request.query_params.getlist('kind')
            if len(kinds) != 1 or kinds[0] not in ASSET_KINDS:
                raise _Refusal(_envelope(422, 'INVALID_REQUEST', _MESSAGES['kind']))
            declared = request.headers.get('content-type')
            if declared is None:
                raise _Refusal(_envelope(415, 'UNSUPPORTED_MEDIA_TYPE', _MESSAGES['asset_type']))
            data = await _read(request, MAX_BYTES)
            try:
                asset = sanitize(data, declared)
            except AssetRejected as error:
                return _envelope(error.status, {413: 'PAYLOAD_TOO_LARGE', 415: 'UNSUPPORTED_MEDIA_TYPE'}.get(error.status, 'INVALID_REQUEST'),
                                 _MESSAGES[_ASSET_REASONS[error.status]])
            await blocking(store.put_asset, digest, organization_id, asset)
            return JSONResponse({'kind': kinds[0], 'sha256': asset.sha256, 'url': '/forge/v1/branding/assets/' + asset.sha256,
                                 'contentType': asset.content_type, 'width': asset.width, 'height': asset.height},
                                status_code=201)
        return await guarded(request, operation)
