"""Platform catalog routes, mounted by ``forge.platform_api.mount_platform`` when a catalog service is composed.

Hidden (``include_in_schema=False``) like every platform route, so the contract pin is unchanged. Every call is guarded by the
shared wrapper (bearer, MFA, finite errors) and the database re-validates a fresh verified owner and audits the action. No
response carries key text, an upstream message or a sealed value.
"""
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.platform import MAX_REVISION
from forge.platform_api import PREFIX, _document, _invalid

BODY_LIMIT = 32768  # up to 64 aliases of 64 characters, each to an upstream id of up to 255
_PUBLISH_KEYS = {'expected_catalogue_revision', 'expected_gateway_revision', 'aliases', 'default_alias'}


def _revision(value, low):
    if type(value) is not int or not low <= value <= MAX_REVISION:
        raise _invalid()
    return value


def mount_catalog(app: FastAPI, *, catalog, guarded, blocking):
    @app.get(PREFIX + '/companies/{organization_id}/catalog', include_in_schema=False)
    async def read(organization_id: UUID, request: Request):
        async def operation(token):
            found = await blocking(catalog.read, token, organization_id)
            return JSONResponse({'configured': False} if found is None else {'configured': True, **found})
        return await guarded(request, operation)

    @app.post(PREFIX + '/companies/{organization_id}/catalog/discover', include_in_schema=False)
    async def discover(organization_id: UUID, request: Request):
        async def operation(token):
            if await _document(request, 64):
                raise _invalid()
            return JSONResponse(await catalog.discover(token, organization_id))
        return await guarded(request, operation)

    @app.put(PREFIX + '/companies/{organization_id}/catalog', include_in_schema=False)
    async def publish(organization_id: UUID, request: Request):
        async def operation(token):
            document = await _document(request, BODY_LIMIT)
            aliases = document.get('aliases')
            if (set(document) != _PUBLISH_KEYS or type(aliases) is not dict or type(document['default_alias']) is not str
                    or any(type(key) is not str or type(value) is not str for key, value in aliases.items())):
                raise _invalid()
            result = await blocking(catalog.publish, token, organization_id, uuid4(),
                                    _revision(document['expected_catalogue_revision'], 0),
                                    _revision(document['expected_gateway_revision'], 1), aliases, document['default_alias'])
            return JSONResponse(result)
        return await guarded(request, operation)
