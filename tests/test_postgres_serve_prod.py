"""Owned PostgreSQL: the production runtime end to end (migrate job, serve, health, host guard, drift)."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import httpx
from fastapi.testclient import TestClient
from forge.mvp_local import ConfigError
from forge.mvp_profile import MVP_PROFILE
from forge.serve_prod import compose_prod, healthcheck, main, serve
from postgres_support import settings
from test_postgres_migrate import fresh_database
from test_serve_prod import HOST, ORIGIN, Stack, wait_listening


@contextmanager
def deployment():
    """A migrated database reachable by the production environment (loopback bind, public host)."""
    with fresh_database() as admin, Stack() as s:
        base = settings()
        (s.fixture.root/'admin.pw').write_text(base['password'], 'utf-8')
        s.fixture.env.update(
            FORGE_DB_HOST=base['host'], FORGE_DB_PORT=str(base['port']), FORGE_DB_NAME=admin.info.dbname,
            FORGE_DB_SSLMODE='disable', FORGE_DB_ADMIN_PASSWORD_FILE=str(s.fixture.root/'admin.pw'))
        yield admin, s


def run_main(argv, env):
    output = io.StringIO()
    with patch('sys.stdout', output):
        code = main(argv, environ=env, configure_fn=lambda stream, level: None)
    return code, output.getvalue()


class PostgresServeProdTests(unittest.TestCase):
    def test_the_migrate_command_builds_the_schema_and_a_rerun_is_a_no_op(self):
        with deployment() as (admin, s):
            code, text = run_main(['migrate'], s.env)
            self.assertEqual(code, 0, text)
            first = json.loads(text)
            self.assertEqual(first['status'], 'ok')
            self.assertGreater(len(first['applied']), 20)
            self.assertNotIn('password-for', text)
            self.assertEqual(first['catalog'], {'created': 114}, 'a fresh install carries the whole capability seed')
            self.assertEqual(admin.execute('SELECT count(*) FROM forge.capability_catalog').fetchone(), (114,))
            code, text = run_main(['migrate'], s.env)
            self.assertEqual((code, json.loads(text)), (0, {'status': 'ok', 'applied': [], 'catalog': {'created': 0}}))
            self.assertEqual(admin.execute("SELECT count(*) FROM forge.capability_change_audit WHERE action='catalog.created'").fetchone(),
                             (114,), 'the second run changed nothing')

    def test_the_composed_app_is_ready_on_the_migrated_schema_and_refuses_a_foreign_host(self):
        with deployment() as (admin, s):
            self.assertEqual(run_main(['migrate'], s.env)[0], 0)
            pools = []
            try:
                app = compose_prod(s.config(), pools)
                with TestClient(app, base_url=ORIGIN) as client:
                    self.assertEqual(client.get('/livez').json(), {'status': 'live'})
                    status = client.get('/status')
                    self.assertEqual((status.status_code, status.json()), (200, {'status': 'ready', 'profile': MVP_PROFILE, 'admin': 'ready'}))
                    self.assertEqual(client.get('/status', headers={'Host': 'evil.test'}).status_code, 403)
                    self.assertEqual(client.get('/forge/v1/contract').status_code, 200)
                    admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
                    drifted = client.get('/status')
                    self.assertEqual((drifted.status_code, drifted.json()['status']), (503, 'not_ready'))
            finally:
                for pool in reversed(pools):
                    pool.close(timeout=5)

    def test_a_database_that_was_never_migrated_is_refused_before_anything_is_bound(self):
        with deployment() as (admin, s):
            bound = []
            with self.assertRaises(ConfigError) as caught:
                serve(s.config(), bind=lambda host, port: bound.append((host, port)), stopping=threading.Event())
            self.assertEqual((str(caught.exception), bound), ('DB_UNAVAILABLE', []))

    def test_serve_on_a_real_socket_follows_the_database_through_the_healthcheck(self):
        with deployment() as (admin, s):
            self.assertEqual(run_main(['migrate'], s.env)[0], 0)
            stopping, failures = threading.Event(), []

            def target():
                try:
                    serve(s.config(), stopping=stopping)
                except Exception as error:
                    failures.append(error)
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            try:
                self.assertTrue(wait_listening(s.port, thread), failures)
                base = 'http://127.0.0.1:%d' % s.port
                self.assertEqual(httpx.get(base + '/status', headers={'Host': HOST}).json()['status'], 'ready')
                self.assertEqual(httpx.get(base + '/status').status_code, 403)
                self.assertIs(healthcheck(s.config()), True)
                self.assertEqual(run_main(['healthcheck'], s.env), (0, ''))
                admin.execute('ALTER TABLE forge.departments ADD COLUMN drift integer')
                self.assertIs(healthcheck(s.config()), False)
                self.assertEqual(run_main(['healthcheck'], s.env)[0], 1)
            finally:
                stopping.set()
                thread.join(20)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main()
