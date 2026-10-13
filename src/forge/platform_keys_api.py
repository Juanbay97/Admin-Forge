"""Platform gateway-key routes, mounted by ``forge.platform_api.mount_platform`` when a key service is composed.

Hidden (``include_in_schema=False``) like every platform route, so the contract pin is unchanged. Key text is accepted
only by ``POST gateway-keys`` and ``POST gateway-keys/{id}/rotate`` (write-only); every response is metadata. The same
bearer, MFA and finite-error rules as the rest of the platform apply because each call is guarded by the shared wrapper
and the database re-validates a fresh verified owner on every operation.
"""
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.gateway_keys import MAX_ASSIGNMENTS
from forge.platform import MAX_REVISION
from forge.platform_api import PREFIX, _document, _invalid

BODY_LIMIT = 8192  # a pasted key is up to 4096 characters
_ENTRY_KEYS = {'key_id', 'priority', 'active'}


def _key(info):
    return {'id': str(info.id), 'label': info.label, 'origin': info.origin, 'revision': info.revision,
            'status': info.status, 'has_key': info.has_key, 'hint': info.hint, 'companies': info.companies}


def _assignment(item):
    return {'key_id': str(item.key_id), 'label': item.label, 'origin': item.origin, 'priority': item.priority,
            'active': item.active, 'key_status': item.key_status, 'has_key': item.has_key}


def _entries(document):
    """``keys``: a list of exact ``{key_id, priority, active}`` objects, converted to typed tuples."""
    if set(document) != {'keys'} or type(document['keys']) is not list or len(document['keys']) > MAX_ASSIGNMENTS:
        raise _invalid()
    entries = []
    for entry in document['keys']:
        if (type(entry) is not dict or set(entry) != _ENTRY_KEYS or type(entry['key_id']) is not str
                or type(entry['priority']) is not int or type(entry['active']) is not bool):
            raise _invalid()
        try:
            entries.append((UUID(entry['key_id']), entry['priority'], entry['active']))
        except ValueError:
            raise _invalid() from None
    return entries


def mount_keys(app: FastAPI, *, keys, guarded, blocking):
    @app.post(PREFIX + '/gateway-keys', include_in_schema=False)
    async def create(request: Request):
        async def operation(token):
            document = await _document(request, BODY_LIMIT)
            if (set(document) - {'label', 'origin', 'key'} or {'label', 'origin'} - set(document)
                    or any(type(value) is not str for value in document.values())):
                raise _invalid()
            created = await blocking(keys.create, token, document['label'], document['origin'], document.get('key'))
            return JSONResponse(_key(created), status_code=201)
        return await guarded(request, operation)

    @app.get(PREFIX + '/gateway-keys', include_in_schema=False)
    async def listing(request: Request):
        async def operation(token):
            found = await blocking(keys.keys, token)
            return JSONResponse({'keys': [_key(item) for item in found], 'allowed_origins': list(keys.allowed_origins)})
        return await guarded(request, operation)

    @app.post(PREFIX + '/gateway-keys/{key_id}/rotate', include_in_schema=False)
    async def rotate(key_id: UUID, request: Request):
        async def operation(token):
            document = await _document(request, BODY_LIMIT)
            if (set(document) != {'expected_revision', 'key'} or type(document['expected_revision']) is not int
                    or not 1 <= document['expected_revision'] <= MAX_REVISION or type(document['key']) is not str):
                raise _invalid()
            return JSONResponse(_key(await blocking(keys.rotate, token, key_id, document['expected_revision'], document['key'])))
        return await guarded(request, operation)

    @app.post(PREFIX + '/gateway-keys/{key_id}/{state}', include_in_schema=False)
    async def change_state(key_id: UUID, state: str, request: Request):
        async def operation(token):
            if state not in ('enable', 'disable'):
                raise _invalid()
            return JSONResponse(_key(await blocking(keys.set_status, token, key_id, state == 'enable')))
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies/{organization_id}/gateway-keys', include_in_schema=False)
    async def assignments(organization_id: UUID, request: Request):
        async def operation(token):
            found = await blocking(keys.assignments, token, organization_id)
            return JSONResponse({'keys': [_assignment(item) for item in found]})
        return await guarded(request, operation)

    @app.put(PREFIX + '/companies/{organization_id}/gateway-keys', include_in_schema=False)
    async def assign(organization_id: UUID, request: Request):
        async def operation(token):
            entries = _entries(await _document(request))
            found = await blocking(keys.assign, token, organization_id, entries)
            return JSONResponse({'keys': [_assignment(item) for item in found]})
        return await guarded(request, operation)

    @app.get(PREFIX + '/companies/{organization_id}/model-access', include_in_schema=False)
    async def read_ceiling(organization_id: UUID, request: Request):
        async def operation(token):
            return JSONResponse({'models': await blocking(keys.ceiling, token, organization_id)})
        return await guarded(request, operation)

    @app.put(PREFIX + '/companies/{organization_id}/model-access', include_in_schema=False)
    async def set_ceiling(organization_id: UUID, request: Request):
        async def operation(token):
            document = await _document(request, BODY_LIMIT)
            if (set(document) != {'models'} or type(document['models']) is not list
                    or any(type(model) is not str for model in document['models'])):
                raise _invalid()
            return JSONResponse({'models': await blocking(keys.set_ceiling, token, organization_id, document['models'])})
        return await guarded(request, operation)
