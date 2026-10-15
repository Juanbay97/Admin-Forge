"""Platform HTTP routes (``/forge/v1/platform/*``), mounted onto an existing account app and kept OUT of the pinned contract.

Every route is ``include_in_schema=False``, so the contract hash is unchanged and ``MeResponse`` is not widened:
``GET /forge/v1/platform/me`` is a separate document. Callers authenticate with the same account bearer token as
everywhere else; the platform's own checks (owner role, verified second factor, freshness) are database functions
that run on every call, so a route here never decides authority by itself. Failures are finite codes with no detail.

Authenticated (password session): ``GET me``, ``POST mfa/enroll``, ``POST login/mfa`` (a TOTP ``code`` or a
``recovery_code``). Authenticated and MFA-verified: ``GET companies``, ``GET companies/{id}``, ``GET audit``.
"""
import json
import re
from uuid import UUID, uuid4

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.api import ErrorDetail, ErrorEnvelope
from forge.branding import BrandingInvalid, parse, public_view
from forge.branding_api import _MESSAGES as BRANDING_MESSAGES
from forge.capability_model import CapabilityConflict, CapabilityDenied, CapabilityInvalid, CapabilityLocked, CapabilityNotFound
from forge.connector_model import BrokerConflict, BrokerInvalid, BrokerNotFound
from forge.invitations import capability_digest
from forge.platform import (COMPANY_CODE, MAX_PAGE, MAX_REVISION, CompanyConflict, KeyConflict, MfaEnrolled, MfaInvalid, MfaLocked, MfaRequired,
                            NoActiveMember, PlatformDenied, PlatformInvalid, PlatformNotFound, RevisionConflict)

PREFIX = '/forge/v1/platform'
JSON_LIMIT = 1024
LOCK_SECONDS = 900
_UNAVAILABLE = ('SERVICE_UNAVAILABLE', 'The service is temporarily unavailable.')
_FAILURES = ((PlatformDenied, 403, 'PLATFORM_DENIED', 'Platform access denied.'),
             (RevisionConflict, 409, 'REVISION_CONFLICT', 'The revision changed.'),
             (KeyConflict, 409, 'KEY_CONFLICT', 'A gateway key with this label already exists.'),
             (CompanyConflict, 409, 'COMPANY_CONFLICT', 'A company with this code already exists.'),
             (MfaRequired, 403, 'MFA_REQUIRED', 'A verified second factor is required.'),
             (MfaInvalid, 403, 'MFA_INVALID', 'The verification code was not accepted.'),
             (MfaLocked, 429, 'MFA_LOCKED', 'Too many attempts; try again later.'),
             (MfaEnrolled, 409, 'MFA_ENROLLED', 'A second factor is already enrolled.'),
             (NoActiveMember, 409, 'NO_ACTIVE_MEMBER', 'The company has no active member yet.'),
             (PlatformInvalid, 422, 'INVALID_REQUEST', 'The platform request is invalid.'),
             (PlatformNotFound, 404, 'NOT_FOUND', 'The requested resource is unavailable.'),
             (CapabilityLocked, 409, 'LOCKED', 'The capability is locked.'),
             (CapabilityConflict, 409, 'REVISION_CONFLICT', 'The revision changed.'),
             (CapabilityInvalid, 422, 'INVALID_REQUEST', 'The platform request is invalid.'),
             (CapabilityDenied, 403, 'PLATFORM_DENIED', 'Platform access denied.'),
             (CapabilityNotFound, 404, 'NOT_FOUND', 'The requested resource is unavailable.'),
             (BrokerConflict, 409, 'REVISION_CONFLICT', 'The revision changed.'),
             (BrokerInvalid, 422, 'INVALID_REQUEST', 'The platform request is invalid.'),
             (BrokerNotFound, 404, 'NOT_FOUND', 'The requested resource is unavailable.'))
_QUERY_KEYS = {'companies': {'after', 'page'}, 'audit': {'before', 'page'}}
_DIGITS = re.compile(r'[0-9]{1,18}')
_COMPANY_KEYS = {'slug', 'display_name', 'department', 'admin_email', 'admin_name'}


def _envelope(status, code, message, *, retry=None, headers=None):
    body = ErrorEnvelope(error=ErrorDetail(code=code, message=message, request_id=uuid4(), retryable=retry is not None or status == 503,
                                           retry_after_seconds=retry, reset_at=None))
    return JSONResponse(status_code=status, content=body.model_dump(mode='json'), headers=headers)


class _Refusal(Exception):
    def __init__(self, response):
        self.response = response


def _invalid():
    return _Refusal(_envelope(422, 'INVALID_REQUEST', 'The platform request is invalid.'))


def _unique(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError
    return dict(pairs)


async def _document(request, limit=JSON_LIMIT):
    """A small JSON object (the caller checks its keys and values)."""
    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if media != 'application/json':
        raise _Refusal(_envelope(415, 'UNSUPPORTED_MEDIA_TYPE', 'The request body must be application/json.'))
    declared = request.headers.get('content-length')
    if declared is not None and (not declared.isascii() or not declared.isdigit()):
        raise _invalid()
    if declared is not None and int(declared) > limit:
        raise _Refusal(_envelope(413, 'PAYLOAD_TOO_LARGE', 'The request body is too large.'))
    data = bytearray()
    async for piece in request.stream():
        data.extend(piece)
        if len(data) > limit:
            raise _Refusal(_envelope(413, 'PAYLOAD_TOO_LARGE', 'The request body is too large.'))
    try:
        document = json.loads(bytes(data).decode('utf-8'), object_pairs_hook=_unique)
    except (ValueError, UnicodeDecodeError):
        raise _invalid() from None
    if type(document) is not dict:
        raise _invalid()
    return document


async def _object(request):
    """A small JSON object whose values are all strings."""
    document = await _document(request)
    if any(type(value) is not str for value in document.values()):
        raise _invalid()
    return document


def _revision(value):
    if type(value) is not int or not 0 <= value <= MAX_REVISION:
        raise _invalid()
    return value


async def _factor_body(request):
    """Exactly one of ``code`` (a TOTP code) or ``recovery_code``."""
    document = await _object(request)
    if len(document) != 1 or set(document) - {'code', 'recovery_code'}:
        raise _invalid()
    ((key, value),) = document.items()
    return key, value


def _query(request, name):
    """Only the route's own keys, each at most once; ``page`` an integer in range, ``after``/``before`` well formed."""
    allowed = _QUERY_KEYS[name]
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or set(keys) - allowed:
        raise _invalid()
    values = {key: request.query_params[key] for key in keys}
    page = 50
    if 'page' in values:
        if not _DIGITS.fullmatch(values['page']) or not 1 <= int(values['page']) <= MAX_PAGE:
            raise _invalid()
        page = int(values['page'])
    if name == 'companies':
        after = values.get('after')
        if after is not None and not COMPANY_CODE.fullmatch(after):
            raise _invalid()
        return {'after': after, 'page': page}
    before = values.get('before')
    if before is not None and (not _DIGITS.fullmatch(before) or int(before) < 1):
        raise _invalid()
    return {'before': None if before is None else int(before), 'page': page}


def _company(company):
    return {'id': str(company.organization_id), 'slug': company.slug, 'display_name': company.display_name, 'active': company.active}


def mount_platform(app: FastAPI, *, service, sessions, readiness=None, keys=None, usage=None, capabilities=None, connectors=None, reads=None, catalog=None):
    """Add the platform routes (all ``include_in_schema=False``, so the contract pin is unchanged)."""
    def blocking(function, *arguments, **keywords):
        return run_sync(lambda: function(*arguments, **keywords), abandon_on_cancel=False)

    async def authenticate(request):
        header = request.headers.getlist('authorization')
        scheme, separator, value = (header[0] if len(header) == 1 else '').partition(' ')
        unauthenticated = _Refusal(_envelope(401, 'UNAUTHENTICATED', 'A valid Forge bearer token is required.',
                                             headers={'WWW-Authenticate': 'Bearer'}))
        if scheme.lower() != 'bearer' or not separator or len(value) != 43 or any(c.isspace() for c in value):
            raise unauthenticated
        try:
            if readiness is None or not await blocking(readiness.check):
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            capability_digest(value)
            identity = await blocking(sessions.validate, value)
        except _Refusal:
            raise
        except ValueError:
            identity = None
        except Exception:
            raise _Refusal(_envelope(503, *_UNAVAILABLE)) from None
        if identity is None:
            raise unauthenticated
        return value

    async def guarded(request, operation):
        try:
            token = await authenticate(request)
            return await operation(token)
        except _Refusal as refusal:
            return refusal.response
        except BrandingInvalid as error:
            return _envelope(422, 'INVALID_REQUEST', BRANDING_MESSAGES.get(error.reason, BRANDING_MESSAGES['shape']))
        except MfaLocked:
            return _envelope(429, 'MFA_LOCKED', 'Too many attempts; try again later.', retry=LOCK_SECONDS,
                             headers={'Retry-After': str(LOCK_SECONDS)})
        except Exception as error:
            for failure, status, code, message in _FAILURES:
                if isinstance(error, failure):
                    return _envelope(status, code, message)
            return _envelope(503, *_UNAVAILABLE)

    @app.get(PREFIX + '/me', include_in_schema=False)
    async def me(request: Request):
        async def operation(token):
            identity = await blocking(service.me, token)
            status = await blocking(service.mfa_status, token)
            return JSONResponse({'account_id': str(identity.account_id), 'role': identity.role,
                                 'mfa': {'state': status.state, 'verified': status.verified, 'fresh': status.fresh}})
        return await guarded(request, operation)

    @app.post(PREFIX + '/mfa/enroll', include_in_schema=False)
    async def enroll(request: Request):
        async def operation(token):
            enrollment = await blocking(service.enroll_mfa, token)
            return JSONResponse({'secret': enrollment.secret, 'otpauth_uri': enrollment.otpauth_uri,
                                 'recovery_codes': list(enrollment.recovery_codes)}, status_code=201)
        return await guarded(request, operation)

    @app.post(PREFIX + '/login/mfa', include_in_schema=False)
    async def verify(request: Request):
        async def operation(token):
            key, value = await _factor_body(request)
            await blocking(service.verify_mfa if key == 'code' else service.recover_mfa, token, value)
            return JSONResponse({'verified': True})
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies', include_in_schema=False)
    async def companies(request: Request):
        async def operation(token):
            arguments = _query(request, 'companies')
            found = await blocking(service.companies, token, **arguments)
            more = found[-1].slug if len(found) == arguments['page'] else None
            return JSONResponse({'companies': [_company(company) for company in found], 'next_after': more})
        return await guarded(request, operation)

    @app.post(PREFIX + '/companies', include_in_schema=False)
    async def create_company(request: Request):
        async def operation(token):
            document = await _object(request)
            if set(document) != _COMPANY_KEYS:
                raise _invalid()
            created = await blocking(service.create_company, token, **document)
            return JSONResponse({**_company(created.company), 'invitation': {
                'id': str(created.invitation_id), 'expires_at': created.expires_at.isoformat(),
                'delivery_state': created.delivery_state, 'delivery_channel': created.delivery_channel}}, status_code=201)
        return await guarded(request, operation)

    @app.post(PREFIX + '/companies/{organization_id}/suspend', include_in_schema=False)
    async def suspend(organization_id: UUID, request: Request):
        async def operation(token):
            return JSONResponse(_company(await blocking(service.suspend_company, token, organization_id)))
        return await guarded(request, operation)

    @app.post(PREFIX + '/companies/{organization_id}/reactivate', include_in_schema=False)
    async def reactivate(organization_id: UUID, request: Request):
        async def operation(token):
            return JSONResponse(_company(await blocking(service.reactivate_company, token, organization_id)))
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies/{organization_id}/branding', include_in_schema=False)
    async def read_branding(organization_id: UUID, request: Request):
        async def operation(token):
            return JSONResponse(public_view(await blocking(service.company_branding, token, organization_id)))
        return await guarded(request, operation)

    @app.put(PREFIX + '/companies/{organization_id}/branding', include_in_schema=False)
    async def save_branding(organization_id: UUID, request: Request):
        async def operation(token):
            document = await _document(request)
            if set(document) != {'expectedRevision', 'branding'}:
                raise _invalid()
            expected, value = _revision(document['expectedRevision']), parse(document['branding'])
            return JSONResponse(public_view(await blocking(service.save_company_branding, token, organization_id, expected, value)))
        return await guarded(request, operation)

    @app.post(PREFIX + '/companies/{organization_id}/branding/reset', include_in_schema=False)
    async def reset_branding(organization_id: UUID, request: Request):
        async def operation(token):
            document = await _document(request)
            if set(document) != {'expectedRevision'}:
                raise _invalid()
            return JSONResponse(public_view(await blocking(service.reset_company_branding, token, organization_id,
                                                           _revision(document['expectedRevision']))))
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies/{organization_id}', include_in_schema=False)
    async def company(organization_id: UUID, request: Request):
        async def operation(token):
            return JSONResponse(_company(await blocking(service.company, token, organization_id)))
        return await guarded(request, operation)

    @app.get(PREFIX + '/audit', include_in_schema=False)
    async def audit(request: Request):
        async def operation(token):
            arguments = _query(request, 'audit')
            found = await blocking(service.audit, token, **arguments)
            entries = [{'id': entry.id, 'actor_id': str(entry.actor_id), 'action': entry.action,
                        'organization_id': None if entry.organization_id is None else str(entry.organization_id),
                        'recorded_at': entry.recorded_at.isoformat()} for entry in found]
            return JSONResponse({'entries': entries, 'next_before': found[-1].id if len(found) == arguments['page'] else None})
        return await guarded(request, operation)

    if keys is not None:
        from forge.platform_keys_api import mount_keys
        mount_keys(app, keys=keys, guarded=guarded, blocking=blocking)
    if usage is not None:
        from forge.platform_usage_api import mount_usage
        mount_usage(app, usage=usage, guarded=guarded, blocking=blocking)
    if capabilities is not None:
        from forge.capability_api import mount_platform_capabilities
        mount_platform_capabilities(app, capabilities=capabilities, guarded=guarded, blocking=blocking)
    if connectors is not None:
        from forge.connector_api import mount_platform_connectors
        mount_platform_connectors(app, service=connectors, guarded=guarded, blocking=blocking)
    if catalog is not None:
        from forge.platform_catalog_api import mount_catalog
        mount_catalog(app, catalog=catalog, guarded=guarded, blocking=blocking)
    if reads is not None:
        from forge.platform_reads_api import mount_reads
        mount_reads(app, reads=reads, guarded=guarded, blocking=blocking)
