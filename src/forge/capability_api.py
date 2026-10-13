"""Capability governance routes, hidden from the pinned contract (``include_in_schema=False``) like every platform route.

Platform owner (mounted by ``forge.platform_api.mount_platform`` so they share its bearer, MFA and finite-error rules):
``GET capabilities``, ``PUT capabilities/{id}`` (create with ``expected_revision`` 0, update with the current revision),
``PUT capabilities/{id}/policy`` (platform default and force-off lock), ``GET|PUT companies/{org}/capabilities[/{id}]`` (per-company
override and lock) and ``GET capability-audit``.

Company administrator (``mount_company_capabilities``): ``GET /forge/v1/orgs/{org}/capabilities``, ``PUT .../capabilities/{id}``
with ``{"enabled": true|false|null}`` and ``GET .../capability-audit``. The database re-validates the live session and the
administrator of exactly that company on every call, so a member, another company's administrator and a missing company all get
the same 404; a locked capability is ``409 LOCKED``.
"""
import re
from uuid import UUID

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.capability_model import (CapabilityConflict, CapabilityDenied, CapabilityInvalid, CapabilityLocked, CapabilityNotFound)
from forge.invitations import capability_digest
from forge.platform_api import PREFIX, _UNAVAILABLE, _Refusal, _document, _envelope, _invalid

ENTRY_LIMIT = 16384
_DIGITS = re.compile(r'[0-9]{1,18}')
_NOT_FOUND = ('NOT_FOUND', 'The requested resource is unavailable.')
_COMPANY_FAILURES = ((CapabilityDenied, 404, *_NOT_FOUND), (CapabilityNotFound, 404, *_NOT_FOUND),
                     (CapabilityLocked, 409, 'LOCKED', 'The capability is locked by the platform.'),
                     (CapabilityConflict, 409, 'REVISION_CONFLICT', 'The revision changed.'),
                     (CapabilityInvalid, 422, 'INVALID_REQUEST', 'The request is invalid.'))


def _entry(record):
    item = record.entry
    return {'id': item.id, 'kind': item.kind, 'version': item.version, 'risk': item.risk, 'is_base': item.is_base,
            'default_state': item.default_state, 'min_sandbox_level': item.min_sandbox_level, 'manifest_sha256': item.manifest_sha256,
            'credential_locus': item.credential_locus, 'declared_permissions': list(item.declared_permissions),
            'granted_permissions': list(item.granted_permissions), 'revision': record.revision,
            'platform': {'state': record.platform.state, 'lock': record.platform.lock}}


def _audit(record):
    return {'id': record.id, 'scope': record.scope, 'organization_id': None if record.organization_id is None else str(record.organization_id),
            'actor_id': None if record.actor_id is None else str(record.actor_id), 'action': record.action, 'target': record.target,
            'before': record.before, 'after': record.after, 'at': record.at.isoformat()}


def _audit_query(request):
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or set(keys) - {'before', 'page'}:
        raise _invalid()
    values = {key: request.query_params[key] for key in keys}
    page = 50
    if 'page' in values:
        if not _DIGITS.fullmatch(values['page']) or not 1 <= int(values['page']) <= 100:
            raise _invalid()
        page = int(values['page'])
    before = values.get('before')
    if before is not None and (not _DIGITS.fullmatch(before) or int(before) < 1):
        raise _invalid()
    return None if before is None else int(before), page


def _policy_body(document):
    if set(document) != {'state', 'lock'} or document['state'] not in (None, 'on', 'off') or document['lock'] not in ('none', 'forced_off'):
        raise _invalid()
    return document['state'], document['lock']


def mount_platform_capabilities(app: FastAPI, *, capabilities, guarded, blocking):
    @app.get(PREFIX + '/capabilities', include_in_schema=False)
    async def catalog(request: Request):
        async def operation(token):
            return JSONResponse({'capabilities': [_entry(record) for record in await blocking(capabilities.catalog, token)]})
        return await guarded(request, operation)

    @app.put(PREFIX + '/capabilities/{identifier}', include_in_schema=False)
    async def put_entry(identifier: str, request: Request):
        async def operation(token):
            document = await _document(request, ENTRY_LIMIT)
            if set(document) != {'expected_revision', 'entry'} or type(document['expected_revision']) is not int or type(document['entry']) is not dict:
                raise _invalid()
            record = await blocking(capabilities.put_entry, token, identifier, document['expected_revision'], document['entry'])
            return JSONResponse(_entry(record))
        return await guarded(request, operation)

    @app.put(PREFIX + '/capabilities/{identifier}/policy', include_in_schema=False)
    async def set_policy(identifier: str, request: Request):
        async def operation(token):
            state, lock = _policy_body(await _document(request))
            return JSONResponse({'changed': await blocking(capabilities.set_platform_policy, token, identifier, state, lock)})
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies/{organization_id}/capabilities', include_in_schema=False)
    async def company_policy(organization_id: UUID, request: Request):
        async def operation(token):
            rows = await blocking(capabilities.company_policy, token, organization_id)
            return JSONResponse({'capabilities': [{'id': row.capability_id, 'state': row.layer.state, 'lock': row.layer.lock,
                                                   'org_enabled': row.org_enabled} for row in rows]})
        return await guarded(request, operation)

    @app.put(PREFIX + '/companies/{organization_id}/capabilities/{identifier}', include_in_schema=False)
    async def set_override(organization_id: UUID, identifier: str, request: Request):
        async def operation(token):
            state, lock = _policy_body(await _document(request))
            return JSONResponse({'changed': await blocking(capabilities.set_company_override, token, organization_id, identifier, state, lock)})
        return await guarded(request, operation)

    @app.get(PREFIX + '/capability-audit', include_in_schema=False)
    async def platform_audit(request: Request):
        async def operation(token):
            before, page = _audit_query(request)
            found = await blocking(capabilities.platform_audit, token, before, page)
            return JSONResponse({'entries': [_audit(record) for record in found], 'next_before': found[-1].id if len(found) == page else None})
        return await guarded(request, operation)


def bearer_guard(sessions, readiness, blocking):
    """The shared bearer check for the company and member routes: a live account session on a ready service, else 401/503."""
    async def authenticate(request):
        header = request.headers.getlist('authorization')
        scheme, separator, value = (header[0] if len(header) == 1 else '').partition(' ')
        unauthenticated = _Refusal(_envelope(401, 'UNAUTHENTICATED', 'A valid Forge bearer token is required.', headers={'WWW-Authenticate': 'Bearer'}))
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
    return authenticate


def company_failure(error):
    for failure, status, code, message in _COMPANY_FAILURES:
        if isinstance(error, failure):
            return _envelope(status, code, message)
    return _envelope(503, *_UNAVAILABLE)


def mount_company_capabilities(app: FastAPI, *, capabilities, sessions, readiness):
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)

    async def guarded(request, operation):
        try:
            return await operation(await authenticate(request))
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return company_failure(error)

    @app.get('/forge/v1/orgs/{organization_id}/capabilities', include_in_schema=False)
    async def view(organization_id: UUID, request: Request):
        async def operation(token):
            items = await blocking(capabilities.company_view, token, organization_id)
            return JSONResponse({'capabilities': [{'id': item.id, 'kind': item.kind, 'risk': item.risk, 'is_base': item.is_base,
                                                   'min_sandbox_level': item.min_sandbox_level, 'state': item.state, 'locked': item.locked,
                                                   'setting': item.setting} for item in items]})
        return await guarded(request, operation)

    @app.put('/forge/v1/orgs/{organization_id}/capabilities/{identifier}', include_in_schema=False)
    async def set_enabled(organization_id: UUID, identifier: str, request: Request):
        async def operation(token):
            document = await _document(request, 2048)
            if set(document) != {'enabled'} or document['enabled'] not in (True, False, None) or type(document['enabled']) not in (bool, type(None)):
                raise _invalid()
            return JSONResponse({'changed': await blocking(capabilities.set_enabled, token, organization_id, identifier, document['enabled'])})
        return await guarded(request, operation)

    @app.get('/forge/v1/orgs/{organization_id}/capability-audit', include_in_schema=False)
    async def audit(organization_id: UUID, request: Request):
        async def operation(token):
            before, page = _audit_query(request)
            found = await blocking(capabilities.org_audit, token, organization_id, before, page)
            return JSONResponse({'entries': [_audit(record) for record in found], 'next_before': found[-1].id if len(found) == page else None})
        return await guarded(request, operation)


_LEVEL = re.compile(r'(0|[1-4])')


async def _session_company(request, token, organizations, blocking):
    """The member's company: the one the session belongs to, or the named ``org`` when it is one of several (else 404/422)."""
    named = request.query_params.get('org')
    try:
        named = None if named is None else UUID(named)
    except ValueError:
        raise _invalid() from None
    companies = await blocking(organizations, token)
    if named is not None:
        if named not in companies:
            raise _Refusal(_envelope(404, *_NOT_FOUND))
        return named
    if len(companies) == 1:
        return companies[0]
    if not companies:
        raise _Refusal(_envelope(404, *_NOT_FOUND))
    raise _invalid()  # several companies: the member must say which


def mount_effective(app: FastAPI, *, policy, sessions, readiness, organizations):
    """``GET /forge/v1/capabilities/effective`` (a member session, ``sandbox_level`` 0..4 optional, ``org`` optional when the
    session has exactly one company) and the public ``GET /forge/v1/capabilities/keys``. Both are 503 without a signing key."""
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)
    headers = {'Cache-Control': 'no-store'}

    @app.get('/forge/v1/capabilities/effective', include_in_schema=False)
    async def effective(request: Request):
        try:
            token = await authenticate(request)
            if not policy.configured:
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            keys = [key for key, _ in request.query_params.multi_items()]
            if len(keys) != len(set(keys)) or set(keys) - {'sandbox_level', 'org'}:
                raise _invalid()
            level = request.query_params.get('sandbox_level')
            if level is not None and not _LEVEL.fullmatch(level):
                raise _invalid()
            org = await _session_company(request, token, organizations, blocking)
            document = await blocking(policy.document, token, org, None if level is None else int(level))
            return JSONResponse(document, headers=headers)
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return company_failure(error)

    @app.get('/forge/v1/capabilities/keys', include_in_schema=False)
    async def keys():
        try:
            return JSONResponse(policy.keys(), headers={'Cache-Control': 'public, max-age=300'})
        except Exception as error:
            return company_failure(error)

    @app.get('/forge/v1/capabilities/pinning', include_in_schema=False)
    async def pinning():
        """The keys to pin and the rotation statements that chain a new key to a pinned one (public; see ``forge.capability_rotation``)."""
        try:
            return JSONResponse(policy.pinning(), headers={'Cache-Control': 'public, max-age=300'})
        except Exception as error:
            return company_failure(error)


AUDIT_LIMIT = 65536


def mount_invocation_audit(app: FastAPI, *, log, sessions, readiness, organizations):
    """``POST /forge/v1/capabilities/audit``: a member's batch of tool-invocation metadata (allow-listed fields only, at most 100)."""
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)

    @app.post('/forge/v1/capabilities/audit', include_in_schema=False)
    async def ingest(request: Request):
        try:
            token = await authenticate(request)
            keys = [key for key, _ in request.query_params.multi_items()]
            if len(keys) != len(set(keys)) or set(keys) - {'org'}:
                raise _invalid()
            document = await _document(request, AUDIT_LIMIT)
            if set(document) != {'events'} or type(document['events']) is not list:
                raise _invalid()
            org = await _session_company(request, token, organizations, blocking)
            stored = await blocking(log.record, token, org, document['events'])
            return JSONResponse({'received': len(document['events']), 'stored': stored}, status_code=202)
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return company_failure(error)


ATTESTATION_LIMIT = 8192


def mount_client_attestation(app: FastAPI, *, reports, sessions, readiness, organizations):
    """``POST /forge/v1/client/attestation``: the device's sandbox attestation report (allow-listed fields only), advisory telemetry."""
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)

    @app.post('/forge/v1/client/attestation', include_in_schema=False)
    async def report(request: Request):
        try:
            token = await authenticate(request)
            keys = [key for key, _ in request.query_params.multi_items()]
            if len(keys) != len(set(keys)) or set(keys) - {'org'}:
                raise _invalid()
            document = await _document(request, ATTESTATION_LIMIT)
            org = await _session_company(request, token, organizations, blocking)
            stored = await blocking(reports.record, token, org, document)
            return JSONResponse({'level': document['level'], 'stored': stored}, status_code=202)
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return company_failure(error)
