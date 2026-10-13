"""Platform usage routes (prices now, reports from 0037), mounted by ``forge.platform_api.mount_platform`` when a usage service is composed.

Hidden from the contract like every platform route. Values are integers in micro-USD per million tokens; responses carry
counters and identifiers only.
"""
from datetime import date, datetime
import re
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.platform_api import PREFIX, _document, _invalid


def _price(item):
    return {'id': item.id, 'upstream_id': item.upstream_id, 'version': item.version, 'input_micros': item.input_micros,
            'output_micros': item.output_micros, 'currency': item.currency, 'effective_from': item.effective_from.isoformat(),
            'set_by': str(item.set_by)}


def _query(request, allowed):
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)) or set(keys) - allowed:
        raise _invalid()
    return {key: request.query_params[key] for key in keys}


_DAY = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
_PAGE = re.compile(r'[0-9]{1,3}')
COUNTER_FIELDS = ('requests', 'prompt_tokens', 'completion_tokens', 'estimated_requests', 'error_requests', 'cost_micros', 'unpriced_requests')


def _counters(counters):
    return {name: getattr(counters, name) for name in COUNTER_FIELDS}


def _window(request, extra):
    """``from`` and ``to`` (UTC dates, required) plus the route's own keys, each once; ``page`` an integer."""
    values = _query(request, {'from', 'to', 'page', *extra})
    if not {'from', 'to'} <= set(values) or not _DAY.fullmatch(values['from']) or not _DAY.fullmatch(values['to']):
        raise _invalid()
    try:
        first, last = date.fromisoformat(values['from']), date.fromisoformat(values['to'])
    except ValueError:
        raise _invalid() from None
    if 'page' in values and not _PAGE.fullmatch(values['page']):
        raise _invalid()
    return first, last, values


def mount_usage(app: FastAPI, *, usage, guarded, blocking):
    @app.post(PREFIX + '/prices', include_in_schema=False)
    async def set_price(request: Request):
        async def operation(token):
            document = await _document(request)
            if (set(document) - {'upstream_id', 'input_micros', 'output_micros', 'effective_from'}
                    or {'upstream_id', 'input_micros', 'output_micros'} - set(document)
                    or type(document['upstream_id']) is not str or type(document['input_micros']) is not int
                    or type(document['output_micros']) is not int
                    or ('effective_from' in document and type(document['effective_from']) is not str)):
                raise _invalid()
            starts = None
            if 'effective_from' in document:
                try:
                    starts = datetime.fromisoformat(document['effective_from'])
                except ValueError:
                    raise _invalid() from None
            created = await blocking(usage.set_price, token, document['upstream_id'], document['input_micros'],
                                     document['output_micros'], starts)
            return JSONResponse(_price(created), status_code=201)
        return await guarded(request, operation)

    @app.get(PREFIX + '/prices', include_in_schema=False)
    async def prices(request: Request):
        async def operation(token):
            values = _query(request, {'upstream_id'})
            found = await blocking(usage.prices, token, values.get('upstream_id'))
            return JSONResponse({'prices': [_price(item) for item in found]})
        return await guarded(request, operation)

    @app.get(PREFIX + '/usage/companies', include_in_schema=False)
    async def by_company(request: Request):
        async def operation(token):
            first, last, values = _window(request, {'after'})
            try:
                after = UUID(values['after']) if 'after' in values else None
            except ValueError:
                raise _invalid() from None
            page = int(values.get('page', 50))
            found = await blocking(usage.by_company, token, first, last, after, page)
            rows = [{'organization_id': str(item.organization_id), 'slug': item.slug, 'display_name': item.display_name,
                     **_counters(item.counters)} for item in found]
            return JSONResponse({'companies': rows, 'next_after': rows[-1]['organization_id'] if len(rows) == page else None})
        return await guarded(request, operation)

    @app.get(PREFIX + '/usage/models', include_in_schema=False)
    async def by_model(request: Request):
        async def operation(token):
            first, last, values = _window(request, {'after'})
            page = int(values.get('page', 50))
            found = await blocking(usage.by_model, token, first, last, values.get('after'), page)
            rows = [{'upstream_id': item.upstream_id, **_counters(item.counters)} for item in found]
            return JSONResponse({'models': rows, 'next_after': rows[-1]['upstream_id'] if len(rows) == page else None})
        return await guarded(request, operation)

    @app.get(PREFIX + '/usage/totals', include_in_schema=False)
    async def totals(request: Request):
        async def operation(token):
            first, last, values = _window(request, set())
            if 'page' in values:
                raise _invalid()
            found = await blocking(usage.totals, token, first, last)
            return JSONResponse({'companies': found.companies, **_counters(found.counters)})
        return await guarded(request, operation)
