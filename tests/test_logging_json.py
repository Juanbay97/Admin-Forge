"""logging_json: one JSON line per request with a request id, and nothing that could carry a secret or PII."""
import io
import json
import logging
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from forge.logging_json import FIELDS, JsonFormatter, configure_logging, install_request_logging

REQUEST_FIELDS = {'ts', 'level', 'event', 'request_id', 'method', 'path', 'status', 'duration_ms'}


def record(name='forge.request', level=logging.INFO, message='request', fields=None, exc_info=None):
    made = logging.LogRecord(name, level, __file__, 1, message, (), exc_info)
    if fields is not None:
        made.fields = fields
    return made


class FormatterTests(unittest.TestCase):
    def test_a_record_is_one_compact_json_line_with_ts_level_and_event(self):
        line = JsonFormatter().format(record(fields={'method': 'GET', 'status': 200}))
        self.assertNotIn('\n', line)
        document = json.loads(line)
        self.assertRegex(document['ts'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        self.assertEqual((document['level'], document['event'], document['method'], document['status']),
                         ('info', 'request', 'GET', 200))

    def test_only_allow_listed_fields_survive(self):
        document = json.loads(JsonFormatter().format(record(fields={
            'status': 200, 'authorization': 'Bearer secret', 'email': 'a@b.example', 'body': 'x', 'query': 'token=1'})))
        self.assertEqual(set(document) - {'ts', 'level', 'event'}, {'status'})
        for name in ('authorization', 'email', 'body', 'query'):
            self.assertNotIn(name, FIELDS)

    def test_an_event_that_is_not_a_plain_identifier_is_replaced(self):
        document = json.loads(JsonFormatter().format(record(message='user a@b.example failed with Bearer secret')))
        self.assertEqual(document['event'], 'log')
        self.assertEqual(json.loads(JsonFormatter().format(record(message='listening')))['event'], 'listening')

    def test_an_exception_contributes_only_its_class_name(self):
        try:
            raise ValueError('contains Bearer secret and a@b.example')
        except ValueError:
            made = record(level=logging.ERROR, message='request_failed', exc_info=sys.exc_info())
        line = JsonFormatter().format(made)
        self.assertEqual(json.loads(line)['error'], 'ValueError')
        self.assertNotIn('secret', line)
        self.assertNotIn('Traceback', line)

    def test_server_library_messages_are_kept_but_application_messages_are_never_free_text(self):
        server = json.loads(JsonFormatter().format(record(name='uvicorn.error', message='Started server process [1]')))
        self.assertEqual((server['event'], server['message']), ('uvicorn.error', 'Started server process [1]'))
        pool = json.loads(JsonFormatter().format(record(name='psycopg.pool', message='password=hunter2 failed')))
        self.assertNotIn('message', pool)
        self.assertNotIn('hunter2', json.dumps(pool))
        long = json.loads(JsonFormatter().format(record(name='uvicorn.error', message='x' * 1000)))
        self.assertEqual(len(long['message']), 300)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, made):
        self.lines.append(JsonFormatter().format(made))


def application(ids=None, clock=None):
    app = FastAPI()

    @app.get('/forge/v1/orgs/{organization_id}/probe')
    def probe(organization_id: str):
        return {'ok': True}

    @app.post('/forge/v1/accounts/login')
    def login():
        return {'access_token': 'secret-token-value'}

    @app.get('/boom')
    def boom():
        raise ValueError('contains Bearer secret')
    logger, capture = logging.getLogger('forge.test_request'), Capture()
    logger.handlers, logger.propagate, logger.level = [capture], False, logging.INFO
    install_request_logging(app, logger=logger, **({'clock': clock} if clock else {}), **({'new_id': ids} if ids else {}))
    return app, capture


class RequestLoggingTests(unittest.TestCase):
    def test_each_request_emits_one_line_with_the_contract_fields_and_a_matching_header(self):
        app, capture = application()
        with TestClient(app) as client:
            response = client.get('/forge/v1/orgs/11111111-1111-4111-8111-111111111111/probe?token=secret&email=a@b.example',
                                  headers={'Authorization': 'Bearer secret-bearer'})
        self.assertEqual(len(capture.lines), 1)
        document = json.loads(capture.lines[0])
        self.assertEqual(set(document), REQUEST_FIELDS)
        self.assertEqual((document['level'], document['event'], document['method'], document['status']),
                         ('info', 'request', 'GET', 200))
        self.assertEqual(document['request_id'], response.headers['x-request-id'])
        self.assertIsInstance(document['duration_ms'], (int, float))
        self.assertGreaterEqual(document['duration_ms'], 0)

    def test_the_path_is_the_route_template_and_never_the_query_or_identifiers(self):
        app, capture = application()
        with TestClient(app) as client:
            client.get('/forge/v1/orgs/11111111-1111-4111-8111-111111111111/probe?token=secret&email=a@b.example')
        line = capture.lines[0]
        self.assertEqual(json.loads(line)['path'], '/forge/v1/orgs/{organization_id}/probe')
        for leaked in ('secret', 'a@b.example', '11111111', 'token'):
            self.assertNotIn(leaked, line)

    def test_authorization_and_bodies_never_reach_the_log(self):
        app, capture = application()
        with TestClient(app) as client:
            client.post('/forge/v1/accounts/login', json={'email': 'person@example.test', 'password': 'hunter2'},
                        headers={'Authorization': 'Bearer secret'})
        line = capture.lines[0]
        for leaked in ('secret', 'person@example.test', 'hunter2', 'secret-token-value'):
            self.assertNotIn(leaked, line)
        self.assertEqual(json.loads(line)['method'], 'POST')

    def test_unmatched_paths_are_logged_without_the_attacker_supplied_path(self):
        app, capture = application()
        with TestClient(app) as client:
            self.assertEqual(client.get('/nobody@example.test/Bearer-secret').status_code, 404)
        document = json.loads(capture.lines[0])
        self.assertEqual((document['status'], document['path']), (404, '(unmatched)'))
        self.assertNotIn('nobody', capture.lines[0])

    def test_a_valid_inbound_request_id_is_kept_and_an_invalid_one_is_replaced(self):
        app, capture = application(ids=lambda: 'generated-id-0001')
        with TestClient(app) as client:
            kept = client.get('/boom-not-found', headers={'X-Request-ID': 'proxy-id-12345678'})
            replaced = client.get('/boom-not-found', headers={'X-Request-ID': 'bad id with spaces & secret'})
        self.assertEqual(kept.headers['x-request-id'], 'proxy-id-12345678')
        self.assertEqual(replaced.headers['x-request-id'], 'generated-id-0001')
        self.assertEqual([json.loads(line)['request_id'] for line in capture.lines], ['proxy-id-12345678', 'generated-id-0001'])
        self.assertNotIn('secret', ''.join(capture.lines))

    def test_the_duration_comes_from_the_injected_monotonic_clock(self):
        ticks = iter([10.0, 10.25])
        app, capture = application(clock=lambda: next(ticks))
        with TestClient(app) as client:
            client.get('/forge/v1/orgs/x/probe')
        self.assertEqual(json.loads(capture.lines[0])['duration_ms'], 250.0)

    def test_a_not_ready_503_is_a_warning_not_an_error_but_other_5xx_are_errors(self):
        app, capture = application()

        @app.get('/not-ready')
        def not_ready():
            from fastapi.responses import JSONResponse
            return JSONResponse({'status': 'not_ready'}, status_code=503)

        @app.get('/bad-gateway')
        def bad_gateway():
            from fastapi.responses import JSONResponse
            return JSONResponse({}, status_code=502)
        with TestClient(app) as client:
            for path in ('/not-ready', '/bad-gateway', '/forge/v1/orgs/x/probe', '/missing'):
                client.get(path)
        self.assertEqual([(json.loads(line)['status'], json.loads(line)['level']) for line in capture.lines],
                         [(503, 'warning'), (502, 'error'), (200, 'info'), (404, 'info')])

    def test_an_unhandled_error_is_logged_as_a_failure_with_only_the_class_and_re_raised(self):
        app, capture = application()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get('/boom', headers={'Authorization': 'Bearer secret'})
        self.assertEqual(response.status_code, 500)
        document = json.loads(capture.lines[0])
        self.assertEqual((document['level'], document['status']), ('error', 500))
        self.assertNotIn('secret', capture.lines[0])
        self.assertNotIn('Traceback', capture.lines[0])


class ConfigureLoggingTests(unittest.TestCase):
    NAMES = ('forge', 'uvicorn', 'uvicorn.error', 'uvicorn.access', 'psycopg.pool')

    def setUp(self):
        self.saved = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate,
                             logging.getLogger(name).level) for name in self.NAMES}

    def tearDown(self):
        for name, (handlers, propagate, level) in self.saved.items():
            logger = logging.getLogger(name)
            logger.handlers, logger.propagate = handlers, propagate
            logger.setLevel(level)

    def test_application_and_server_loggers_write_json_to_the_stream_only(self):
        stream = io.StringIO()
        configure_logging(stream, 'INFO')
        logging.getLogger('uvicorn.error').info('Application startup complete.')
        logging.getLogger('forge.serve').info('listening', extra={'fields': {'status': 0}})
        logging.getLogger('psycopg.pool').warning('connection failed password=hunter2')
        documents = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([item['event'] for item in documents], ['uvicorn.error', 'listening', 'psycopg.pool'])
        self.assertNotIn('hunter2', stream.getvalue())
        for name in self.NAMES:
            self.assertFalse(logging.getLogger(name).propagate)

    def test_the_level_filters_lower_severities(self):
        stream = io.StringIO()
        configure_logging(stream, 'WARNING')
        logging.getLogger('forge.serve').info('listening')
        logging.getLogger('forge.serve').error('stopped')
        self.assertEqual([json.loads(line)['event'] for line in stream.getvalue().splitlines()], ['stopped'])

    def test_the_access_log_is_silenced(self):
        stream = io.StringIO()
        configure_logging(stream, 'DEBUG')
        logging.getLogger('uvicorn.access').info('127.0.0.1 - "GET /x?token=secret HTTP/1.1" 200')
        self.assertEqual(stream.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
