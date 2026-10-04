"""Explicit local runtime contract; no accounts, ambient credentials or live IDP."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from forge.api import create_app
from forge.runtime import (
    LocalDatabaseConfiguration, RuntimeConfiguration, create_runtime_app,
)
from test_entra import config

ROOT = Path(__file__).resolve().parents[1]
UNCONFIGURED = dict(schema_version="1.0", runtime="unconfigured",
    configuration="missing", storage="not_configured",
    identity_provider="not_configured", onboarding="not_implemented",
    user_access="not_evaluated")


def database(**changes):
    return LocalDatabaseConfiguration(**(dict(host="127.0.0.1", port=5432,
        dbname="forge_test", password="SYNTHETIC_PASSWORD_NOT_USED") | changes))


class RuntimeTests(unittest.TestCase):
    def test_unconfigured_status_is_exact_and_default_api_stays_deny_all(self):
        with TestClient(create_runtime_app()) as client:
            self.assertEqual(client.get("/forge/v1/status").status_code, 200)
            self.assertEqual(client.get("/forge/v1/status").json(), UNCONFIGURED)
            self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
            self.assertEqual(client.get("/forge/v1/bootstrap",
                headers={"Authorization": "Bearer untrusted"}).status_code, 401)
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/forge/v1/status").status_code, 404)

    def test_unconfigured_never_constructs_pool_or_validator(self):
        factory = unittest.mock.Mock(side_effect=AssertionError("Must not construct"))
        with TestClient(create_runtime_app(_pool_factory=factory,
                _validator_factory=factory)) as client:
            self.assertEqual(client.get("/forge/v1/status").json(), UNCONFIGURED)
        factory.assert_not_called()

    def test_invalid_database_fields_reject_at_construction(self):
        for change in ({"host": "example.test"}, {"host": "/socket"},
                {"host": "127.0.0.1,example.test"}, {"host": "postgres://local"},
                {"port": True}, {"port": 0}, {"port": 65536},
                {"port": 10**400}, {"port": "5432"}, {"dbname": ""},
                {"dbname": "postgres://credential"}, {"dbname": "x=y"},
                {"dbname": "x "}, {"dbname": "x"*64}, {"password": ""},
                {"password": None}, {"password": "\x00"}, {"password": "x"*4097}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                database(**change)

    def test_explicit_controls_and_secret_repr(self):
        cfg = database()
        values = cfg.connection_kwargs()
        self.assertEqual(values.get("hostaddr"), "127.0.0.1")
        self.assertEqual(values.get("user"), "forge_runtime")
        self.assertEqual(values.get("require_auth"), "scram-sha-256")
        self.assertEqual(values.get("sslmode"), "disable")
        self.assertEqual(values.get("gssencmode"), "disable")
        self.assertNotIn(cfg.password, repr(cfg))
        with self.assertRaises(FrozenInstanceError):
            cfg.port = 9999

    def test_static_routes_run_locally_with_security_headers(self):
        with TestClient(create_runtime_app()) as client:
            for path, mime in (("/status", "text/html"), ("/status.css", "text/css"),
                               ("/status.js", "javascript")):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(mime, response.headers["content-type"])
                    self.assertEqual(response.headers.get("cache-control"), "no-store")
                    self.assertIn("default-src 'none'", response.headers.get(
                        "content-security-policy", ""))
            html = client.get("/status").text
            self.assertIn("Prometheon Forge", html)
            self.assertIn('lang="en"', html)
            self.assertIn('aria-live="polite"', html)
            self.assertNotIn("<input", html)
            self.assertNotIn("<form", html)
            self.assertNotIn("https://", html)

    def test_unconfigured_ignores_synthetic_pg_service_presence_in_own_child(self):
        script = """from forge.runtime import create_runtime_app
from fastapi.testclient import TestClient
import json
with TestClient(create_runtime_app()) as client:
 print(json.dumps(client.get('/forge/v1/status').json()))
"""
        result = subprocess.run([sys.executable, "-c", script],
            env={"SystemRoot": "C:\\Windows", "PYTHONPATH": str(ROOT/"src"),
                 "PGSERVICE": "SYNTHETIC_SERVICE_NOT_USED"},
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        self.assertEqual(json.loads(result.stdout), UNCONFIGURED)


class FakeConnection:
    """Lifecycle-only double; actual role/schema acceptance uses owned DB tests."""
    autocommit = True
    def __init__(self):
        from psycopg.pq import TransactionStatus
        self.info = type("Info", (), {"transaction_status": TransactionStatus.IDLE})()
        self.queries = []
        self.ready = True
    def transaction(self):
        from contextlib import nullcontext
        return nullcontext()
    def cursor(self, **kwargs):
        from contextlib import nullcontext
        return nullcontext(self)
    def execute(self, query, params=None):
        from threading import get_ident
        self.queries.append((query, get_ident()))
    def fetchone(self):
        return (self.ready,)


class FakePool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.conn = FakeConnection()
        self.closed = True
        self.operations = []
        self.fail_open = False
    def open(self, **kwargs):
        from threading import get_ident
        self.operations.append(("open", get_ident(), kwargs))
        self.closed = False
        if self.fail_open:
            raise RuntimeError("PRIVATE_RAW_ERROR_MARKER")
    def close(self, **kwargs):
        from threading import get_ident
        self.operations.append(("close", get_ident(), kwargs))
        self.closed = True
    def connection(self, **kwargs):
        from contextlib import nullcontext
        if self.closed:
            raise RuntimeError("PRIVATE_RAW_ERROR_MARKER")
        return nullcontext(self.conn)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.pool = None
        self.clock = [100.0]
        self.configuration = RuntimeConfiguration(config(), database())

    def factory(self, **kwargs):
        self.pool = FakePool(**kwargs)
        return self.pool

    def app(self, **changes):
        return create_runtime_app(self.configuration,
            _pool_factory=self.factory, _clock=lambda: self.clock[0], **changes)

    def test_ready_is_exact_but_identity_onboarding_and_access_are_not_verified(self):
        with TestClient(self.app()) as client:
            expected = UNCONFIGURED | dict(configuration="provided", runtime="ready",
                storage="ready", identity_provider="configured_unverified")
            self.assertEqual(client.get("/forge/v1/status").json(), expected)
            self.assertNotIn(self.configuration.database.password,
                client.get("/forge/v1/status").text)
            self.assertEqual(client.get("/forge/v1/bootstrap",
                headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertTrue(self.pool.closed)

    def test_pool_limits_connection_controls_and_lifecycle_threads(self):
        from threading import get_ident
        app = self.app()
        @app.get("/test-event-loop")
        async def thread():
            return get_ident()
        with TestClient(app) as client:
            loop_id = client.get("/test-event-loop").json()
            client.get("/forge/v1/status")
            self.assertEqual(self.pool.kwargs["min_size"], 0)
            self.assertEqual(self.pool.kwargs["max_size"], 2)
            self.assertEqual(self.pool.kwargs["max_waiting"], 4)
            self.assertEqual(self.pool.kwargs["num_workers"], 2)
            self.assertEqual(self.pool.kwargs["reconnect_timeout"], 1)
            self.assertEqual(self.pool.kwargs["kwargs"]["connect_timeout"], 2)
            self.assertEqual(self.pool.kwargs["kwargs"]["hostaddr"], "127.0.0.1")
            self.assertTrue(self.pool.kwargs["kwargs"]["autocommit"])
            self.assertEqual(self.pool.operations[0][2], {"wait": True, "timeout": 5})
            self.assertTrue(all(t != loop_id for _, t in self.pool.conn.queries))
        self.assertTrue(all(t != loop_id for _, t, _ in self.pool.operations))
        self.assertEqual(self.pool.operations[-1][2], {"timeout": 5})

    def test_partial_open_failure_closes_pool_and_serves_redacted_unavailable(self):
        def failure(**kwargs):
            pool = self.factory(**kwargs)
            pool.fail_open = True
            return pool
        app = create_runtime_app(self.configuration, _pool_factory=failure)
        with TestClient(app) as client:
            response = client.get("/forge/v1/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["runtime"], "unavailable")
            self.assertNotIn("PRIVATE", response.text)
            self.assertTrue(self.pool.closed)
            self.assertEqual(client.get("/healthz").status_code, 200)
        self.assertTrue(self.pool.closed)

    def test_constructor_failure_is_unavailable_without_leaking_error(self):
        def failure(**kwargs):
            raise RuntimeError("PRIVATE_RAW_ERROR_MARKER")
        with TestClient(create_runtime_app(self.configuration,
                _pool_factory=failure)) as client:
            response = client.get("/forge/v1/status")
            self.assertEqual(response.json()["storage"], "unavailable")
            self.assertNotIn("PRIVATE", response.text)

    def test_shutdown_closes_on_user_body_exception(self):
        app = self.app()
        with self.assertRaisesRegex(RuntimeError, "test-only"):
            with TestClient(app):
                raise RuntimeError("test-only")
        self.assertTrue(self.pool.closed)

    def test_status_cache_expires_and_failed_probe_has_completion_cooldown(self):
        app = self.app()
        with TestClient(app) as client:
            initial = len(self.pool.conn.queries)
            for _ in range(8):
                self.assertEqual(client.get("/forge/v1/status").json()["storage"], "ready")
            self.assertEqual(len(self.pool.conn.queries), initial)
            self.pool.conn.ready = False
            self.clock[0] += 5
            self.assertEqual(client.get("/forge/v1/status").json()["storage"], "unavailable")
            failed = len(self.pool.conn.queries)
            self.assertGreater(failed, initial)
            for _ in range(8):
                self.assertEqual(client.get("/forge/v1/status").json()["storage"], "unavailable")
            self.assertEqual(len(self.pool.conn.queries), failed)
            self.pool.conn.ready = True
            self.clock[0] += 5
            self.assertEqual(client.get("/forge/v1/status").json()["storage"], "ready")

    def test_expired_cache_exception_is_unavailable_and_single_flight_is_bounded(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        app = self.app()
        with TestClient(app):
            runtime = app.state.runtime
            entered, release = Event(), Event()
            calls = []
            class Blocking:
                def check(self):
                    calls.append(1)
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test release timeout")
                    raise RuntimeError("PRIVATE_RAW_ERROR_MARKER")
            runtime.probe = Blocking()
            self.clock[0] += 5
            with ThreadPoolExecutor(max_workers=8) as workers:
                active = workers.submit(runtime.status)
                self.assertTrue(entered.wait(1))
                rest = list(workers.map(lambda _: runtime.status(), range(20)))
                self.assertTrue(all(s["storage"] == "checking" for s in rest))
                release.set()
                self.assertEqual(active.result()["storage"], "unavailable")
            self.assertEqual(len(calls), 1)
            for _ in range(8):
                self.assertEqual(runtime.status()["storage"], "unavailable")
            self.assertEqual(len(calls), 1)

    def test_typed_configuration_rejects_untrusted_shapes(self):
        for value in ({}, "", True, database()):
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                create_runtime_app(value)
        for entra, db in (({}, database()), (config(), {}), (None, None)):
            with self.subTest(), self.assertRaises(ValueError):
                RuntimeConfiguration(entra, db)
        self.assertNotIn(self.configuration.database.password, repr(self.configuration))

    def test_unsupported_linked_client_fails_closed(self):
        with patch("forge.runtime.pq.version", return_value=170011):
            with self.assertRaisesRegex(ValueError, "supported libpq"):
                self.configuration.database.connection_kwargs()

    def test_connection_error_and_pool_repr_are_redacted(self):
        import psycopg
        from forge.runtime import _RuntimeConnection, STORAGE_UNAVAILABLE
        with patch.object(psycopg.Connection, "connect",
                side_effect=psycopg.OperationalError("PRIVATE_DSN_PASSWORD_MARKER")):
            with self.assertRaises(psycopg.OperationalError) as raised:
                _RuntimeConnection.connect("")
        self.assertEqual(str(raised.exception), STORAGE_UNAVAILABLE)

    def test_configured_pg_contamination_rejects_in_own_child_without_connection(self):
        import json
        script = """from forge.runtime import *
from forge.entra import EntraConfiguration
import json
configuration=RuntimeConfiguration(
 EntraConfiguration({'00000000-0000-0000-0000-000000000001'},
 '00000000-0000-0000-0000-000000000002',
 {'00000000-0000-0000-0000-000000000003'},{'forge.read'}),
 LocalDatabaseConfiguration('127.0.0.1',1,'forge_test','synthetic'))
try:
 create_runtime_app(configuration,_pool_factory=lambda **k: (_ for _ in ()).throw(AssertionError()))
except ValueError as e:
 print(json.dumps({'blocked':True,'message':str(e)}))
else:
 raise AssertionError('Expected rejection')
"""
        for name in ("PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGHOST",
                     "PGUSER", "PGPASSWORD", "PGOPTIONS", "PGSSLCERT",
                     "PGREQUIREAUTH", "PGGSSENCMODE"):
            with self.subTest(name=name):
                env = {"SystemRoot": "C:\\Windows", "PYTHONPATH": str(ROOT/"src"),
                       name: "PRIVATE_SYNTHETIC_VALUE_NOT_USED"}
                result = subprocess.run([sys.executable, "-c", script], env=env,
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["blocked"])
                self.assertNotIn("PRIVATE", result.stdout)
                self.assertNotIn(name, result.stdout)

    def test_unconfigured_does_not_inspect_pg_environment(self):
        with patch("forge.runtime._reject_pg_environment",
                   side_effect=AssertionError("No PG env discovery")) as guard:
            app = create_runtime_app()
            self.assertEqual(app.state.runtime.status(), UNCONFIGURED)
            guard.assert_not_called()

    def test_fixed_asset_routes_ignore_query_paths_and_redact_missing_resources(self):
        with TestClient(create_runtime_app()) as client:
            self.assertEqual(client.get("/status?name=../../secret&mime=evil").status_code, 200)
            self.assertEqual(client.get("/status.js?name=secret").status_code, 200)
            self.assertEqual(client.get("/status/../../secret").status_code, 404)
            with patch("forge.runtime.files", side_effect=RuntimeError("PRIVATE_PATH")):
                response = client.get("/status")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("PRIVATE", response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_ui_only_renders_fixed_labels_and_no_token_persistence_or_external_urls(self):
        with TestClient(create_runtime_app()) as client:
            js, css = client.get("/status.js").text, client.get("/status.css").text
            for forbidden in ("innerHTML", "localStorage", "sessionStorage",
                              "document.cookie", "https://", "http://"):
                self.assertNotIn(forbidden, js)
            self.assertIn('fetch("/forge/v1/status"', js)
            self.assertIn("Object.keys(value)", js)
            self.assertIn('credentials: "omit"', js)
            for color in ("#0B1D26", "#0F6B6D", "#E07A2D", "#E8DCC1", "#1A1A1A"):
                self.assertIn(color, css)
            self.assertIn(":focus-visible", css)
            self.assertIn("@media", css)

    def test_body_text_and_refresh_contrast_are_wcag_aa(self):
        def luminance(value):
            colors = [int(value[i:i+2], 16)/255 for i in (1, 3, 5)]
            linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in colors]
            return sum(v*w for v, w in zip(linear, (.2126,.7152,.0722)))
        for background in ("#0B1D26", "#0F6B6D", "#1A1A1A"):
            ratio = (luminance("#E8DCC1")+.05)/(luminance(background)+.05)
            self.assertGreaterEqual(ratio, 4.5)

    def test_cleanup_failure_is_redacted_and_not_silently_successful(self):
        app = self.app()
        with self.assertRaises(RuntimeError) as raised:
            with TestClient(app):
                self.pool.close = unittest.mock.Mock(
                    side_effect=RuntimeError("PRIVATE_CLEANUP_MARKER"))
        self.assertEqual(str(raised.exception), "Runtime storage unavailable.")

    def test_password_surrogates_controls_and_utf8_bytes_are_bounded(self):
        for password in ("\ud800", "\nsecret", "secret\x7f", "é"*2049):
            with self.subTest(size=len(password)), self.assertRaises(ValueError) as raised:
                database(password=password)
            self.assertEqual(str(raised.exception), "Runtime database password is invalid.")
        self.assertEqual(database(password="é"*2048).password, "é"*2048)

    def test_unsupported_option_parser_failure_is_redacted(self):
        with patch("forge.runtime.make_conninfo", side_effect=RuntimeError("PRIVATE_CONTROL")):
            with self.assertRaises(ValueError) as raised:
                self.configuration.database.connection_kwargs()
        self.assertEqual(str(raised.exception), "Runtime connection controls are unsupported.")

    def test_all_public_runtime_responses_have_no_store_and_no_config_secrets(self):
        app = self.app()
        with TestClient(app) as client:
            for path in ("/forge/v1/status", "/openapi.json", "/healthz", "/missing"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                    self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                    self.assertNotIn(self.configuration.database.password, response.text)
                    self.assertNotIn("127.0.0.1", response.text)
            self.assertEqual(client.options("/forge/v1/status",
                headers={"Origin":"https://example.test"}).status_code, 405)



# Every telemetry regression runs in a fresh child: no process-global provider or
# environment mutation affects other tests, and no exporter/SDK is installed.
TELEMETRY_CHILD = r"""
import json, sys
from contextlib import contextmanager
from unittest.mock import patch
from opentelemetry import trace, metrics, _logs
from fastapi.telemetry import _runtime
from fastapi.testclient import TestClient
from forge.api import create_app
from forge.runtime import create_runtime_app

calls = []
class LocalTracer(trace.NoOpTracer):
    def start_span(self, name, *args, **kwargs):
        calls.append(('span', name, kwargs.get('attributes')))
        return super().start_span(name, *args, **kwargs)
    @contextmanager
    def start_as_current_span(self, name, *args, **kwargs):
        yield self.start_span(name, *args, **kwargs)
class LocalTraceProvider(trace.TracerProvider):
    def get_tracer(self, *args, **kwargs):
        calls.append(('tracer',))
        return LocalTracer()
class LocalMeterProvider(metrics.MeterProvider):
    def get_meter(self, *args, **kwargs):
        calls.append(('meter',))
        return metrics.NoOpMeterProvider().get_meter(*args, **kwargs)
class LocalLoggerProvider(_logs.LoggerProvider):
    def get_logger(self, *args, **kwargs):
        calls.append(('logger',))
        return _logs.NoOpLoggerProvider().get_logger(*args, **kwargs)

providers = [LocalTraceProvider(), LocalMeterProvider(), LocalLoggerProvider()]
trace.set_tracer_provider(providers[0])
metrics.set_meter_provider(providers[1])
_logs.set_logger_provider(providers[2])
# Positive control proves the controlled providers are active, without export.
trace.get_tracer('control').start_span('control')
metrics.get_meter('control')
_logs.get_logger('control')
assert {'span', 'tracer', 'meter', 'logger'} <= {x[0] for x in calls}
calls.clear()
configs, endpoints = [], []
original = _runtime._configure_from_environment
def configure(config):
    configs.append({k: config[k] for k in
        ('tracing', 'metrics', 'logs', 'operation_spans', 'auto_configure')})
    return original(config)
def endpoint(signal):
    endpoints.append(signal)
    return None  # Never construct an exporter or consult a real endpoint.
with patch.object(_runtime, '_configure_from_environment', configure), \
        patch.object(_runtime, '_export_endpoint', endpoint):
    for factory in (create_app, create_runtime_app):
        with TestClient(factory()) as client:
            for path in ('/healthz', '/status', '/forge/v1/status',
                    '/forge/v1/bootstrap', '/missing'):
                client.get(path + '?token=SYNTHETIC_TOKEN&identity=SYNTHETIC_IDENTITY')
            client.post('/healthz', json={'token': 'SYNTHETIC_TOKEN'})
            client.get('/forge/v1/bootstrap?organization_id=INVALID_SYNTHETIC_ID',
                headers={'Authorization': 'Bearer SYNTHETIC_TOKEN'})
assert trace.get_tracer_provider() is providers[0]
assert metrics.get_meter_provider() is providers[1]
assert _logs.get_logger_provider() is providers[2]
print(json.dumps({'calls': calls, 'configs': configs, 'endpoints': endpoints}))
"""


class TelemetryIsolationTests(unittest.TestCase):
    def child(self, environment=None):
        import json
        result = subprocess.run([sys.executable, '-c', TELEMETRY_CHILD],
            env={'SystemRoot': 'C:\\Windows', 'PYTHONPATH': str(ROOT/'src'),
                 **(environment or {})}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_shared_factory_explicitly_disables_all_native_telemetry(self):
        for factory in (create_app, create_runtime_app):
            with self.subTest(factory=factory.__name__):
                settings = factory()._telemetry
                for key in ('tracing', 'metrics', 'logs', 'operation_spans',
                            'auto_configure'):
                    self.assertIs(settings[key], False, key)

    def test_synthetic_global_providers_receive_no_request_or_identity_data(self):
        result = self.child()
        self.assertEqual(result['calls'], [])
        self.assertNotIn('SYNTHETIC_TOKEN', str(result))
        self.assertNotIn('SYNTHETIC_IDENTITY', str(result))

    def test_otel_environment_cannot_activate_configuration_or_export(self):
        result = self.child({'OTEL_EXPORTER_OTLP_ENDPOINT':
            'https://synthetic.invalid/never-contact', 'OTEL_TRACES_EXPORTER': 'otlp',
            'OTEL_METRICS_EXPORTER': 'otlp', 'OTEL_LOGS_EXPORTER': 'otlp',
            'OTEL_SDK_DISABLED': 'false', 'OTEL_SERVICE_NAME': 'SYNTHETIC_IDENTITY'})
        self.assertEqual(result['calls'], [])
        self.assertEqual(result['endpoints'], [])
        self.assertEqual(result['configs'], [dict.fromkeys(('tracing', 'metrics',
            'logs', 'operation_spans', 'auto_configure'), False)] * 2)


if __name__ == "__main__":
    unittest.main()
