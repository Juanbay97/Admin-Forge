"""Platform read routes, mounted by ``forge.platform_api.mount_platform`` when a reads service is composed.

Hidden (``include_in_schema=False``) like every platform route, so the contract pin is unchanged. Each call is guarded by the shared
wrapper (bearer, finite errors) and the database re-validates a fresh verified owner on every operation.
"""
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.platform import MAX_PAGE
from forge.platform_api import PREFIX, _DIGITS, _invalid
from forge.platform_usage_api import _counters, _window


def _member(item):
    return {'id': str(item.id), 'email': item.email, 'display_name': item.display_name, 'status': item.status,
            'roles': list(item.roles), 'departments': [{'id': str(entry.id), 'name': entry.name} for entry in item.departments]}


def _keys(request, allowed):
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or set(keys) - allowed:
        raise _invalid()
    return {key: request.query_params[key] for key in keys}


def mount_reads(app: FastAPI, *, reads, guarded, blocking):
    @app.get(PREFIX + '/companies/{organization_id}/members', include_in_schema=False)
    async def members(organization_id: UUID, request: Request):
        async def operation(token):
            values = _keys(request, {'after', 'page'})
            page = 50
            if 'page' in values:
                if not _DIGITS.fullmatch(values['page']) or not 1 <= int(values['page']) <= MAX_PAGE:
                    raise _invalid()
                page = int(values['page'])
            try:
                after = UUID(values['after']) if 'after' in values else None
            except ValueError:
                raise _invalid() from None
            found = await blocking(reads.members, token, organization_id, after, page)
            return JSONResponse({'members': [_member(item) for item in found],
                                 'next_after': str(found[-1].id) if len(found) == page else None})
        return await guarded(request, operation)

    @app.get(PREFIX + '/overview', include_in_schema=False)
    async def overview(request: Request):
        async def operation(token):
            first, last, values = _window(request, set())
            if 'page' in values:
                raise _invalid()
            found = await blocking(reads.overview, token, first, last)
            before = found.previous
            return JSONResponse({'companies': {'active': found.companies_active, 'suspended': found.companies_suspended},
                                 'active_users': found.active_users, **_counters(found.counters),
                                 'previous': {'active_users': before.active_users, 'requests': before.requests,
                                              'prompt_tokens': before.prompt_tokens, 'completion_tokens': before.completion_tokens,
                                              'cost_micros': before.cost_micros}})
        return await guarded(request, operation)

    @app.get(PREFIX + '/usage/days', include_in_schema=False)
    async def days(request: Request):
        async def operation(token):
            first, last, values = _window(request, set())
            if 'page' in values:
                raise _invalid()
            found = await blocking(reads.days, token, first, last)
            return JSONResponse({'days': [{'day': item.day.isoformat(), **_counters(item.counters), 'active_users': item.active_users}
                                          for item in found]})
        return await guarded(request, operation)
