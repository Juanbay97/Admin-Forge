"""serve_prod: production assembly (health, host guard, logs), serve/healthcheck/migrate commands; no database."""
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from forge import serve_prod
from forge.admin_mount import ADMIN_CSP
from forge.mvp_local import ConfigError, ROLES
from forge.mvp_profile import MVP_PROFILE
from forge.prod_config import load_prod_config
from forge.serve_prod import UnconfiguredDelivery, assemble_prod, compose_prod, healthcheck, main, serve
from test_prod_config import Fixture, ORIGIN

HOST = 'forge.example.test'


class Ready:
    def __init__(self, value=True):
        self.value, self.calls = value, 0

    def check(self):
        self.calls += 1
        return self.value


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Stack:
    """A valid environment (loopback bind, a real temporary admin build) and its loaded config."""
    def __enter__(self):
        self.fixture = Fixture().__enter__()
        self.admin = self.fixture.root/'admin'
        self.admin.mkdir()
        (self.admin/'index.html').write_text('<title>Forge admin</title>', 'utf-8')
        self.port = free_port()
        self.fixture.env.update(FORGE_ADMIN_DIR=str(self.admin), FORGE_PORT=str(self.port), FORGE_BIND_HOST='127.0.0.1')
        return self

    def __exit__(self, *exc):
        self.fixture.__exit__(*exc)

    @property
    def env(self):
        return dict(self.fixture.env)

    def config(self, **change):
        return self.fixture.load(**change)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


def assembled(stack, readiness=None, **change):
    app = FastAPI()
    readiness = Ready() if readiness is None else readiness
    assemble_prod(app, stack.config(**change), readiness)
    return app, readiness


class AssemblyTests(unittest.TestCase):
    def test_livez_is_process_liveness_and_never_consults_readiness(self):
        with Stack() as s:
            app, readiness = assembled(s, Ready(False))
            with TestClient(app, base_url=ORIGIN) as client:
                response = client.get('/livez')
            self.assertEqual((response.status_code, response.json(), response.headers['cache-control']),
                             (200, {'status': 'live'}, 'no-store'))
            self.assertEqual(readiness.calls, 0)

    def test_status_attests_the_schema_and_is_503_when_it_is_not_ready(self):
        with Stack() as s:
            with TestClient(assembled(s, Ready(True))[0], base_url=ORIGIN) as client:
                ready = client.get('/status')
            self.assertEqual((ready.status_code, ready.json()), (200, {'status': 'ready', 'profile': MVP_PROFILE, 'admin': 'ready'}))
            with TestClient(assembled(s, Ready(False))[0], base_url=ORIGIN) as client:
                drifted = client.get('/status')
            self.assertEqual((drifted.status_code, drifted.json()['status'], drifted.headers['cache-control']),
                             (503, 'not_ready', 'no-store'))

    def test_a_foreign_host_is_refused_everywhere_including_the_health_routes(self):
        with Stack() as s:
            with TestClient(assembled(s)[0], base_url=ORIGIN) as client:
                for path in ('/livez', '/status', '/admin/', '/forge/v1/accounts/login'):
                    for host in ('evil.test', '127.0.0.1:3410', HOST + ':9999'):
                        with self.subTest(path=path, host=host):
                            response = client.get(path, headers={'Host': host})
                            self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'FORBIDDEN_HOST'))

    def test_only_the_public_origin_may_mutate_and_no_cors_is_granted(self):
        with Stack() as s:
            with TestClient(assembled(s)[0], base_url=ORIGIN) as client:
                self.assertNotEqual(client.post('/forge/v1/accounts/login', headers={'Origin': ORIGIN}).status_code, 403)
                for origin in ('https://evil.test', 'http://127.0.0.1:3411', 'http://forge.example.test'):
                    with self.subTest(origin=origin):
                        response = client.post('/forge/v1/accounts/login', headers={'Origin': origin})
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'FORBIDDEN_ORIGIN'))
                preflight = client.options('/forge/v1/accounts/login', headers={'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST'})
                self.assertNotIn('access-control-allow-origin', preflight.headers)

    def test_the_admin_build_is_served_with_the_strict_csp_and_a_missing_build_stops_startup(self):
        with Stack() as s:
            with TestClient(assembled(s)[0], base_url=ORIGIN) as client:
                page = client.get('/admin/')
            self.assertEqual((page.status_code, page.headers['content-security-policy']), (200, ADMIN_CSP))
            (s.admin/'index.html').unlink()
            with self.assertRaises(ConfigError) as caught:
                assembled(s)
            self.assertEqual(str(caught.exception), 'ADMIN_BUILD_MISSING')

    def test_every_request_including_a_refusal_logs_one_json_line_with_a_request_id(self):
        with Stack() as s:
            capture, logger = Capture(), logging.getLogger('forge.request')
            from forge.logging_json import JsonFormatter
            capture.setFormatter(JsonFormatter())
            saved = (logger.handlers[:], logger.propagate, logger.level)
            logger.handlers, logger.propagate = [capture], False
            logger.setLevel(logging.INFO)
            try:
                with TestClient(assembled(s)[0], base_url=ORIGIN) as client:
                    ok = client.get('/livez', headers={'Authorization': 'Bearer secret'})
                    refused = client.get('/livez?token=secret', headers={'Host': 'evil.test', 'Authorization': 'Bearer secret'})
            finally:
                logger.handlers, logger.propagate = saved[0], saved[1]
                logger.setLevel(saved[2])
            documents = [json.loads(line) for line in capture.lines]
            self.assertEqual([(item['status'], item['path']) for item in documents], [(200, '/livez'), (403, '(unmatched)')])
            self.assertEqual([item['request_id'] for item in documents], [ok.headers['x-request-id'], refused.headers['x-request-id']])
            self.assertNotIn('secret', ''.join(capture.lines))


class FakePool:
    created = []

    def __init__(self, conninfo, *, kwargs, **options):
        self.kwargs = kwargs
        FakePool.created.append(self)

    def open(self, wait=False, timeout=None):
        pass


class ComposeTests(unittest.TestCase):
    def setUp(self):
        FakePool.created = []

    def test_pools_use_the_configs_role_settings_and_the_app_is_the_production_assembly(self):
        with Stack() as s:
            config, pools = s.config(FORGE_DB_PORT='6543', FORGE_DB_SSLMODE='disable'), []
            app = compose_prod(config, pools, pool_factory=FakePool, readiness_factory=lambda *a: Ready(True))
            self.assertEqual(pools, FakePool.created)
            self.assertEqual([pool.kwargs['user'] for pool in pools], list(ROLES))
            self.assertEqual({pool.kwargs['port'] for pool in pools}, {6543})
            self.assertEqual({pool.kwargs['sslmode'] for pool in pools}, {'disable'})
            with TestClient(app, base_url=ORIGIN) as client:
                self.assertEqual(client.get('/livez').status_code, 200)
                self.assertEqual(client.get('/livez', headers={'Host': 'evil.test'}).status_code, 403)

    def test_an_unattested_schema_refuses_to_compose_but_leaves_the_pools_to_close(self):
        with Stack() as s:
            pools = []
            with self.assertRaises(ConfigError) as caught:
                compose_prod(s.config(), pools, pool_factory=FakePool, readiness_factory=lambda *a: Ready(False))
            self.assertEqual(str(caught.exception), 'SCHEMA_ATTESTATION_FAILED')
            self.assertEqual(len(pools), len(ROLES))

    def test_a_database_that_cannot_be_reached_is_a_finite_code_and_leaves_the_pools_to_close(self):
        class Unreachable(FakePool):
            def open(self, wait=False, timeout=None):
                raise RuntimeError('connection to server at "db" failed: password authentication failed for user x')
        with Stack() as s:
            pools = []
            with self.assertRaises(ConfigError) as caught:
                compose_prod(s.config(), pools, pool_factory=Unreachable)
            self.assertEqual(str(caught.exception), 'DB_UNAVAILABLE')
            self.assertEqual(len(pools), 1)

    def test_without_a_configured_channel_delivery_fails_loudly_instead_of_writing_a_mailbox(self):
        with self.assertRaises(RuntimeError) as caught:
            UnconfiguredDelivery().deliver(None, 'person@example.test', 'Person', 'https://forge.example.test/onboarding')
        self.assertEqual(str(caught.exception), 'DELIVERY_NOT_CONFIGURED')
        self.assertNotIn('person', str(caught.exception))


def wait_listening(port, thread):
    for _ in range(100):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
            return True
        except OSError:
            thread.join(0.1)
    return False


class ServeTests(unittest.TestCase):
    def run_serve(self, s, **kwargs):
        stopping, failures = threading.Event(), []

        def compose(config, pools):
            return assembled(s, Ready(True))[0]

        def target():
            try:
                serve(s.config(), compose_fn=kwargs.pop('compose_fn', compose), stopping=stopping, **kwargs)
            except Exception as error:
                failures.append(error)
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, stopping, failures

    def test_it_serves_on_the_configured_bind_with_the_public_host_and_stops_gracefully(self):
        with Stack() as s:
            thread, stopping, failures = self.run_serve(s)
            try:
                self.assertTrue(wait_listening(s.port, thread), failures)
                base = 'http://127.0.0.1:%d' % s.port
                self.assertEqual(httpx.get(base + '/livez', headers={'Host': HOST}).json(), {'status': 'live'})
                self.assertEqual(httpx.get(base + '/status', headers={'Host': HOST}).status_code, 200)
                self.assertEqual(httpx.get(base + '/livez').status_code, 403)  # Host 127.0.0.1:port is not the public host
            finally:
                stopping.set()
                thread.join(15)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])

    def test_the_listener_is_bound_only_after_composition_succeeds_and_with_the_configured_address(self):
        with Stack() as s:
            bound, closed = [], []

            class Listener:
                def close(self):
                    closed.append(True)

            def bind(host, port):
                bound.append((host, port))
                return Listener()

            class Server:
                def __init__(self, config):
                    self.config = config

                def run(self, sockets=None):
                    self.sockets = sockets

            with self.assertRaises(ConfigError):
                serve(s.config(), compose_fn=lambda config, pools: (_ for _ in ()).throw(ConfigError('SCHEMA_ATTESTATION_FAILED')),
                      bind=bind, stopping=threading.Event())
            self.assertEqual(bound, [])
            with patch('uvicorn.Server', Server), patch('uvicorn.Config') as config_type:
                serve(s.config(), compose_fn=lambda config, pools: FastAPI(), bind=bind, stopping=threading.Event())
            self.assertEqual((bound, closed), ([('127.0.0.1', s.port)], [True]))
            options = config_type.call_args.kwargs
            self.assertIs(options['access_log'], False)
            self.assertIsNone(options['log_config'])
            self.assertEqual(options.get('workers', 1), 1)  # one process: pools, readiness cache and rate state are per process
            self.assertEqual(options['timeout_graceful_shutdown'], 10)

    def test_pools_are_closed_in_reverse_order_even_when_composition_fails(self):
        with Stack() as s:
            closed = []

            class Pool:
                def __init__(self, name):
                    self.name = name

                def close(self, timeout=None):
                    closed.append(self.name)

            def compose(config, pools):
                pools.extend([Pool('a'), Pool('b')])
                raise ConfigError('SCHEMA_ATTESTATION_FAILED')
            with self.assertRaises(ConfigError):
                serve(s.config(), compose_fn=compose, bind=lambda *a: self.fail('bound'), stopping=threading.Event())
            self.assertEqual(closed, ['b', 'a'])

    def test_an_occupied_port_fails_closed_and_leaves_the_other_process_alone(self):
        with Stack() as s, socket.socket() as other:
            other.bind(('127.0.0.1', s.port))
            other.listen(4)
            with self.assertRaises(ConfigError) as caught:
                serve(s.config(), compose_fn=lambda config, pools: FastAPI(), stopping=threading.Event())
            self.assertEqual(str(caught.exception), 'PORT_OCCUPIED')
            socket.create_connection(('127.0.0.1', s.port), timeout=1).close()


class HealthcheckTests(unittest.TestCase):
    def check(self, s, outcome, **change):
        seen = []

        def fetch(host, port, authority, timeout):
            seen.append((host, port, authority))
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return healthcheck(s.config(**change), fetch=fetch), seen

    def test_ready_means_200_and_a_ready_body_sent_to_the_bind_with_the_public_host_header(self):
        with Stack() as s:
            healthy, seen = self.check(s, (200, b'{"status":"ready","profile":"p","admin":"ready"}'))
            self.assertIs(healthy, True)
            self.assertEqual(seen, [('127.0.0.1', s.port, HOST)])

    def test_a_wildcard_bind_is_probed_on_loopback_and_a_specific_bind_on_itself(self):
        with Stack() as s:
            self.assertEqual(self.check(s, (200, b'{"status":"ready"}'), FORGE_BIND_HOST='0.0.0.0')[1][0][0], '127.0.0.1')
            self.assertEqual(self.check(s, (200, b'{"status":"ready"}'), FORGE_BIND_HOST='10.1.2.3')[1][0][0], '10.1.2.3')

    def test_anything_but_a_ready_200_is_unhealthy(self):
        with Stack() as s:
            for outcome in ((503, b'{"status":"not_ready"}'), (200, b'{"status":"not_ready"}'), (200, b'not json'),
                            (200, b'[]'), (403, b'{"status":"ready"}'), OSError('refused'), TimeoutError()):
                with self.subTest(outcome=repr(outcome)):
                    self.assertIs(self.check(s, outcome)[0], False)

    def test_against_a_real_server_it_follows_readiness(self):
        with Stack() as s:
            readiness, stopping = Ready(True), threading.Event()
            thread = threading.Thread(target=lambda: serve(
                s.config(), compose_fn=lambda config, pools: assembled(s, readiness)[0], stopping=stopping), daemon=True)
            thread.start()
            try:
                self.assertTrue(wait_listening(s.port, thread))
                self.assertIs(healthcheck(s.config()), True)
                readiness.value = False
                self.assertIs(healthcheck(s.config()), False)
            finally:
                stopping.set()
                thread.join(15)
            self.assertIs(healthcheck(s.config()), False)  # nothing listening any more


class MainTests(unittest.TestCase):
    def run_main(self, argv, env, **handlers):
        output = io.StringIO()
        handlers.setdefault('configure_fn', lambda stream, level: None)  # never rewire the global loggers from a test
        with patch('sys.stdout', output):
            code = main(argv, environ=env, **handlers)
        return code, output.getvalue()

    def test_usage_errors_exit_two_with_a_finite_code(self):
        for argv in ([], ['bogus'], ['serve', '--extra']):
            with self.subTest(argv=argv):
                code, text = self.run_main(argv, {})
                self.assertEqual((code, json.loads(text)), (2, {'status': 'failed', 'code': 'INVALID_ARGUMENTS'}))

    def test_an_invalid_configuration_fails_before_anything_runs(self):
        with Stack() as s:
            calls = []
            env = {**s.env, 'FORGE_PUBLIC_ORIGIN': 'http://leaky.example.test'}
            for command in ('serve', 'healthcheck'):
                code, text = self.run_main([command], env, serve_fn=lambda c: calls.append(c), healthcheck_fn=lambda c: calls.append(c))
                self.assertEqual((code, json.loads(text)), (1, {'status': 'failed', 'code': 'CONFIG_INVALID:FORGE_PUBLIC_ORIGIN'}))
                self.assertNotIn('leaky', text)
            self.assertEqual(calls, [])

    def test_serve_runs_with_the_loaded_config_and_a_clean_stop_exits_zero(self):
        with Stack() as s:
            seen = []
            code, text = self.run_main(['serve'], s.env, serve_fn=lambda config: seen.append(config))
            self.assertEqual((code, text), (0, ''))
            self.assertEqual(seen[0].public_origin, ORIGIN)

    def test_serve_failures_are_finite_codes(self):
        with Stack() as s:
            def occupied(config):
                raise ConfigError('PORT_OCCUPIED')

            def broken(config):
                raise RuntimeError('boom password-for-secret')
            self.assertEqual(self.run_main(['serve'], s.env, serve_fn=occupied)[0:2], (1, '{"status": "failed", "code": "PORT_OCCUPIED"}\n'))
            code, text = self.run_main(['serve'], s.env, serve_fn=broken)
            self.assertEqual((code, json.loads(text)), (1, {'status': 'failed', 'code': 'SERVE_PROD_UNAVAILABLE'}))
            self.assertNotIn('secret', text)
            self.assertEqual(self.run_main(['serve'], s.env, serve_fn=lambda c: (_ for _ in ()).throw(KeyboardInterrupt()))[0], 0)

    def test_healthcheck_exits_zero_only_when_healthy(self):
        with Stack() as s:
            self.assertEqual(self.run_main(['healthcheck'], s.env, healthcheck_fn=lambda config: True), (0, ''))
            self.assertEqual(self.run_main(['healthcheck'], s.env, healthcheck_fn=lambda config: False)[0], 1)

    def test_migrate_is_the_one_shot_runner_with_its_own_arguments_and_the_same_environment(self):
        seen = []

        def migrate_fn(argv, *, environ):
            seen.append((list(argv), dict(environ)))
            return 0
        with Stack() as s:
            self.assertEqual(self.run_main(['migrate', '--migrations-dir', '/srv/migrations'], s.env, migrate_fn=migrate_fn)[0], 0)
            self.assertEqual(seen[0][0], ['--migrations-dir', '/srv/migrations'])
            self.assertEqual(seen[0][1], s.env)

    def test_the_process_drops_every_libpq_variable_before_anything_else(self):
        with Stack() as s, patch.dict(os.environ, {'PGSERVICE': 'other', 'PGOPTIONS': '-c x=1', 'KEEP_ME': '1'}):
            output = io.StringIO()
            with patch('sys.stdout', output):
                main(['serve'], serve_fn=lambda config: None)  # environ=None: the real process environment
            self.assertEqual([name for name in os.environ if name.startswith('PG')], [])
            self.assertEqual(os.environ['KEEP_ME'], '1')

    def test_the_single_worker_choice_is_documented_with_its_reason(self):
        text = ' '.join(serve_prod.__doc__.split())
        self.assertIn('one uvicorn worker', text)
        self.assertIn('connection budget', text)


if __name__ == '__main__':
    unittest.main()
