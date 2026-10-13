"""Connector broker routes, hidden from the pinned contract (``include_in_schema=False``).

Member (a live session; the company is the session's own, or ``?org=`` when the member belongs to several):
``GET /forge/v1/connectors`` (status, no secret), ``POST /forge/v1/connectors/{id}/oauth/start`` (the authorize URL),
``DELETE /forge/v1/connectors/{id}/grant`` (disconnect), ``POST /forge/v1/mcp/{id}`` (the MCP proxy).
Company administrator: ``GET /forge/v1/connectors/credentials`` (status, last-four hint, revision), ``PUT|DELETE
/forge/v1/connectors/{id}/credential`` (write-only). Platform owner: ``PUT /forge/v1/platform/connectors/{id}/credential`` (the default
OAuth app). Public, unauthenticated by design: ``GET /forge/v1/connectors/oauth/callback`` on the configured public origin (the single-use
state is the capability). Every failure is a finite code with no detail; without a connector key every route answers 503.
"""
import re
from uuid import UUID

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from forge.capability_api import _session_company, bearer_guard
from forge.connector_model import (BrokerConflict, BrokerDenied, BrokerDisabled, BrokerError, BrokerInvalid, BrokerLimit, BrokerNotConfigured,
                                    BrokerNotFound, BrokerRateLimited, BrokerReauth, BrokerTooLarge, BrokerUpstream)
from forge.mcp_broker import REQUEST_LIMIT, BrokerMethodBlocked
from forge.platform_api import PREFIX, _UNAVAILABLE, _Refusal, _document, _envelope, _invalid

CREDENTIAL_LIMIT = 8192
_FAILURES = ((BrokerDenied, 404, 'NOT_FOUND', 'The requested resource is unavailable.'), (BrokerNotFound, 404, 'NOT_FOUND', 'The requested resource is unavailable.'),
             (BrokerInvalid, 422, 'INVALID_REQUEST', 'The request is invalid.'), (BrokerConflict, 409, 'REVISION_CONFLICT', 'The revision changed.'),
             (BrokerDisabled, 403, 'CONNECTOR_DISABLED', 'The connector is not enabled for this company.'),
             (BrokerNotConfigured, 409, 'NOT_CONFIGURED', 'The connector is not configured.'),
             (BrokerReauth, 409, 'REAUTH_REQUIRED', 'The connection must be authorized again.'),
             (BrokerMethodBlocked, 403, 'METHOD_NOT_ALLOWED', 'The method is not allowed.'),
             (BrokerTooLarge, 413, 'PAYLOAD_TOO_LARGE', 'The message is too large.'),
             (BrokerRateLimited, 429, 'RATE_LIMITED', 'Too many requests.'), (BrokerLimit, 429, 'RATE_LIMITED', 'Too many requests.'),
             (BrokerUpstream, 502, 'UPSTREAM_ERROR', 'The connector could not be reached.'))
_PAGE = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<meta name="referrer" content="no-referrer"><title>Forge</title></head><body style="font-family:system-ui;margin:3rem auto;max-width:28rem">'
         '<h1>%s</h1><p>%s</p></body></html>')
_PAGE_HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"}
_STATE = re.compile(r'[A-Za-z0-9_-]{20,128}')
_CODE = re.compile(r'[!-~]{1,2048}')


def broker_failure(error):
    for failure, status, code, message in _FAILURES:
        if isinstance(error, failure):
            return _envelope(status, code, message, retry=60 if status == 429 else None, headers={'Retry-After': '60'} if status == 429 else None)
    return _envelope(503, *_UNAVAILABLE)


def _credential_body(document):
    """``expected_revision`` (int), ``kind`` and the kind's own fields, exactly."""
    if (type(document.get('expected_revision')) is not int or type(document.get('kind')) is not str
            or set(document) - {'expected_revision', 'kind', 'api_key', 'client_id', 'client_secret'}):
        raise _invalid()
    fields = {key: value for key, value in document.items() if key not in ('expected_revision', 'kind')}
    return document['kind'], fields, document['expected_revision']


def mount_platform_connectors(app: FastAPI, *, service, guarded, blocking):
    @app.put(PREFIX + '/connectors/{identifier}/credential', include_in_schema=False)
    async def set_default(identifier: str, request: Request):
        async def operation(token):
            if service is None:
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            kind, fields, expected = _credential_body(await _document(request, CREDENTIAL_LIMIT))
            info = await blocking(service.platform_credential_set, token, identifier, kind, fields, expected)
            return JSONResponse({'revision': info.revision, 'hint': info.hint, 'kind': info.kind})
        return await guarded(request, operation)


def mount_connectors(app: FastAPI, *, service, oauth, broker, sessions, readiness, organizations):
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)

    async def guarded(request, operation):
        try:
            if service is None:
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            token = await authenticate(request)
            return await operation(token)
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return broker_failure(error)

    async def company(request, token):
        keys = [key for key, _ in request.query_params.multi_items()]
        if len(keys) != len(set(keys)) or set(keys) - {'org', 'expected_revision'}:
            raise _invalid()
        return await _session_company(request, token, organizations, blocking)

    @app.get('/forge/v1/connectors', include_in_schema=False)
    async def listing(request: Request):
        async def operation(token):
            org = await company(request, token)
            items = await blocking(service.status, token, org)
            return JSONResponse({'connectors': [{'id': item.id, 'name': item.name, 'category': item.category, 'transport': item.transport, 'auth': item.auth,
                                                 'state': item.state, 'status': item.status, 'configured': item.configured} for item in items]},
                                headers={'Cache-Control': 'no-store'})
        return await guarded(request, operation)

    @app.get('/forge/v1/connectors/credentials', include_in_schema=False)
    async def credentials(request: Request):
        async def operation(token):
            org = await company(request, token)
            items = await blocking(service.credential_status, token, org)
            return JSONResponse({'credentials': [{'id': item.capability_id, 'kind': item.org_kind, 'revision': item.org_revision, 'hint': item.org_hint,
                                                  'platform_default': item.platform_kind is not None} for item in items]}, headers={'Cache-Control': 'no-store'})
        return await guarded(request, operation)

    @app.put('/forge/v1/connectors/{identifier}/credential', include_in_schema=False)
    async def set_credential(identifier: str, request: Request):
        async def operation(token):
            org = await company(request, token)
            kind, fields, expected = _credential_body(await _document(request, CREDENTIAL_LIMIT))
            info = await blocking(service.credential_set, token, org, identifier, kind, fields, expected)
            return JSONResponse({'revision': info.revision, 'hint': info.hint, 'kind': info.kind}, headers={'Cache-Control': 'no-store'})
        return await guarded(request, operation)

    @app.delete('/forge/v1/connectors/{identifier}/credential', include_in_schema=False)
    async def clear_credential(identifier: str, request: Request):
        async def operation(token):
            org = await company(request, token)
            expected = request.query_params.get('expected_revision', '')
            if not expected.isascii() or not expected.isdigit():
                raise _invalid()
            return JSONResponse({'cleared': await blocking(service.credential_clear, token, org, identifier, int(expected))})
        return await guarded(request, operation)

    @app.post('/forge/v1/connectors/{identifier}/oauth/start', include_in_schema=False)
    async def start(identifier: str, request: Request):
        async def operation(token):
            org = await company(request, token)
            url = await blocking(oauth.start, token, org, identifier)
            return JSONResponse({'authorize_url': url}, headers={'Cache-Control': 'no-store'})
        return await guarded(request, operation)

    @app.delete('/forge/v1/connectors/{identifier}/grant', include_in_schema=False)
    async def disconnect(identifier: str, request: Request):
        async def operation(token):
            org = await company(request, token)
            return JSONResponse({'disconnected': await blocking(oauth.disconnect, token, org, identifier)})
        return await guarded(request, operation)

    @app.get('/forge/v1/connectors/oauth/callback', include_in_schema=False)
    async def callback(request: Request):
        def page(status, title, text):
            return HTMLResponse(_PAGE % (title, text), status_code=status, headers=_PAGE_HEADERS)
        try:
            if service is None or readiness is None or not await blocking(readiness.check):
                return page(503, 'Unavailable', 'This service is temporarily unavailable.')
            query = {key: request.query_params.getlist(key) for key in request.query_params.keys()}
            if any(len(values) != 1 for values in query.values()) or set(query) - {'code', 'state', 'error', 'error_description', 'iss'}:
                return page(400, 'Not connected', 'The authorization could not be completed. You can close this window and try again.')
            state = query.get('state', [''])[0]
            if not _STATE.fullmatch(state):
                return page(400, 'Not connected', 'The authorization could not be completed. You can close this window and try again.')
            if 'error' in query or 'code' not in query:
                await blocking(oauth.abort, state)
                return page(400, 'Not connected', 'The authorization was not granted. You can close this window.')
            code = query['code'][0]
            if not _CODE.fullmatch(code):
                return page(400, 'Not connected', 'The authorization could not be completed. You can close this window and try again.')
            await blocking(oauth.complete, state, code)
            return page(200, 'Connected', 'The connector is connected. You can close this window and return to Forge.')
        except BrokerError:
            return page(400, 'Not connected', 'The authorization could not be completed. You can close this window and try again.')
        except Exception:
            return page(503, 'Unavailable', 'This service is temporarily unavailable.')

    @app.post('/forge/v1/mcp/{identifier}', include_in_schema=False)
    async def proxy(identifier: str, request: Request):
        try:
            if service is None:
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            token = await authenticate(request)
            media = request.headers.get('content-type', '').split(';')[0].strip().lower()
            if media != 'application/json':
                raise _Refusal(_envelope(415, 'UNSUPPORTED_MEDIA_TYPE', 'The request body must be application/json.'))
            declared = request.headers.get('content-length')
            if declared is not None and (not declared.isascii() or not declared.isdigit() or int(declared) > REQUEST_LIMIT):
                raise BrokerTooLarge()
            data = bytearray()
            async for piece in request.stream():
                data.extend(piece)
                if len(data) > REQUEST_LIMIT:
                    raise BrokerTooLarge()
            org = await company(request, token)
            response = await blocking(broker.call, token, org, identifier, bytes(data), dict(request.headers))
            return StreamingResponse(response.body, status_code=response.status, headers={**response.headers, 'Cache-Control': 'no-store'})
        except _Refusal as refusal:
            return refusal.response
        except Exception as error:
            return broker_failure(error)
