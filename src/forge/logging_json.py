"""Structured JSON logs for the production profile: one line per request, no secrets, no PII.

Nothing here formats arbitrary text. A record contributes ``ts``, ``level`` and ``event`` plus
the allow-listed ``FIELDS`` only; an exception contributes its class name, never its message or
traceback; the request path is the *route template* (``/forge/v1/orgs/{organization_id}/members``),
so neither identifiers nor attacker-supplied paths nor query strings can reach a log line.
Request and response bodies and the ``Authorization`` header are never read.
"""
from datetime import datetime, timezone
import json
import logging
import re
import time
from uuid import uuid4

FIELDS = ('request_id', 'method', 'path', 'status', 'duration_ms', 'code', 'port')
_EVENT = re.compile(r'[a-z][a-z0-9_.]{0,63}')
_REQUEST_ID = re.compile(r'[A-Za-z0-9._-]{8,64}')
_SERVER_LOGGERS = ('uvicorn', 'uvicorn.error', 'psycopg.pool')
MESSAGE_LIMIT = 300


class JsonFormatter(logging.Formatter):
    def format(self, record):
        moment = datetime.fromtimestamp(record.created, timezone.utc)
        document = {'ts': moment.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (moment.microsecond // 1000),
                    'level': record.levelname.lower(),
                    'event': record.msg if record.name.startswith('forge') and type(record.msg) is str
                    and _EVENT.fullmatch(record.msg) else ('log' if record.name.startswith('forge') else record.name)}
        document.update({key: value for key, value in getattr(record, 'fields', {}).items() if key in FIELDS})
        if record.exc_info and record.exc_info[0] is not None:
            document['error'] = record.exc_info[0].__name__
        if record.name.startswith('uvicorn'):
            # Written by the server library, never by request data; the access log stays off.
            document['message'] = record.getMessage()[:MESSAGE_LIMIT]
        return json.dumps(document, separators=(',', ':'), ensure_ascii=True)


def configure_logging(stream, level='INFO'):
    """Route the application, uvicorn and pool loggers to ``stream`` as JSON; silence the access log."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    numeric = logging.getLevelName(level)
    for name in ('forge', 'uvicorn', 'uvicorn.error', 'psycopg.pool'):
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate = [handler], False
        logger.setLevel(numeric)  # setLevel also clears the per-logger enabled-for cache
    access = logging.getLogger('uvicorn.access')
    access.handlers, access.propagate = [logging.NullHandler()], False


def _template(request):
    route = request.scope.get('route')
    return getattr(route, 'path', None) or '(unmatched)'


def _level(status):
    """A 503 is the not-ready probe answer, polled by the healthcheck: noisy as an error, so a warning."""
    if status == 503:
        return logging.WARNING
    return logging.ERROR if status >= 500 else logging.INFO


def install_request_logging(app, *, logger=None, clock=time.perf_counter, new_id=lambda: uuid4().hex):
    """Outermost middleware: a request id, then one line per request, whatever happens inside."""
    logger = logging.getLogger('forge.request') if logger is None else logger

    @app.middleware('http')
    async def log_request(request, call_next):
        inbound = request.headers.get('x-request-id')
        request_id = inbound if inbound is not None and _REQUEST_ID.fullmatch(inbound) else new_id()
        request.state.request_id = request_id
        started = clock()
        fields = {'request_id': request_id, 'method': request.method}
        try:
            response = await call_next(request)
        except Exception as error:
            logger.error('request_failed', exc_info=error, extra={'fields': {
                **fields, 'path': _template(request), 'status': 500, 'duration_ms': round((clock() - started) * 1000, 3)}})
            raise
        response.headers['X-Request-ID'] = request_id
        logger.log(_level(response.status_code), 'request', extra={'fields': {
            **fields, 'path': _template(request), 'status': response.status_code,
            'duration_ms': round((clock() - started) * 1000, 3)}})
        return response
