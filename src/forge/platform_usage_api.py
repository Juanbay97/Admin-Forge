"""Platform usage routes (prices now, reports from 0037), mounted by ``forge.platform_api.mount_platform`` when a usage service is composed.

Hidden from the contract like every platform route. Values are integers in micro-USD per million tokens; responses carry
counters and identifiers only.
"""
from datetime import datetime

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
