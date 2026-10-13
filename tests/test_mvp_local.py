"""mvp_local: strict explicit config, secrets file, no environment discovery, port safety, assembly."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from forge.admin_mount import ADMIN_CSP
from forge.mvp_local import (ConfigError, FORBIDDEN_PORTS, MVP_PORTS, assemble, load_config, load_secrets,
                             main, role_settings, serve)
from forge.mvp_profile import MVP_PROFILE

ROLES = ('forge_account_service', 'forge_enrollment', 'forge_runtime', 'forge_gateway_service',
         'forge_branding_service', 'forge_platform_service', 'forge_capability_service')


def write(path, value):
    Path(path).write_text(json.dumps(value), 'utf-8')
    return str(path)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Workspace:
    """A temporary private-looking directory holding a valid config, secrets file and admin build."""
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root/'mailbox').mkdir()
        (self.root/'admin'/'assets').mkdir(parents=True)
        (self.root/'admin'/'index.html').write_text('<title>Forge admin</title>', 'utf-8')
        self.secrets_path = write(self.root/'secrets.json', {
            'roles': {role: 'password-for-' + role for role in ROLES},
            'delivery_key': Fernet.generate_key().decode(), 'gateway_key': Fernet.generate_key().decode(),
            'platform_key': Fernet.generate_key().decode()})
        self.port = free_port()
        self.config = {
            'version': 1, 'profile': MVP_PROFILE,
            'database': {'host': '127.0.0.1', 'port': 54329, 'dbname': 'forge_mvp'},
            'secrets_file': self.secrets_path, 'mailbox_dir': str(self.root/'mailbox'),
            'admin_dir': str(self.root/'admin'), 'require_admin_build': True,
            'control_plane_port': self.port, 'client_origin': 'http://127.0.0.1:3411',
            'cors_origins': ['http://127.0.0.1:3411'], 'gateway_allowed_endpoints': ['http://127.0.0.1:3413']}
        return self

    def path(self, **change):
        return write(self.root/'config.json', {**self.config, **change})

    def __exit__(self, *exc):
        self.directory.cleanup()


class ConfigTests(unittest.TestCase):
    def test_a_complete_config_loads_into_typed_values(self):
        with Workspace() as w:
            config = load_config(w.path())
            self.assertEqual((config.control_plane_port, config.client_origin, config.cors_origins),
                             (w.port, 'http://127.0.0.1:3411', ('http://127.0.0.1:3411',)))
            self.assertEqual((config.database, config.require_admin_build),
                             ({'host': '127.0.0.1', 'port': 54329, 'dbname': 'forge_mvp'}, True))
            self.assertEqual(config.gateway_policy.allowed, frozenset({'http://127.0.0.1:3413'}))
            self.assertEqual(config.admin_origin, 'http://127.0.0.1:%d' % w.port)

    def test_every_missing_key_and_any_unknown_key_is_refused_by_name(self):
        with Workspace() as w:
            for key in w.config:
                with self.subTest(missing=key), self.assertRaises(ConfigError) as caught:
                    load_config(write(w.root/'c.json', {k: v for k, v in w.config.items() if k != key}))
                self.assertEqual(str(caught.exception), 'CONFIG_INVALID:' + key)
            for path, extra in (('top', {'unknown': 1}), ('database', None)):
                document = json.loads(json.dumps(w.config))
                if extra:
                    document.update(extra)
                else:
                    document['database']['sslmode'] = 'disable'
                with self.subTest(unknown=path), self.assertRaises(ConfigError):
                    load_config(write(w.root/'c.json', document))

    def test_malformed_values_are_refused(self):
        bad = {'version': 2, 'profile': '0001-0005+0010-0018/PG17', 'control_plane_port': True,
               'control_plane_port ': '3410', 'client_origin': 'http://localhost:3411',
               'cors_origins': [], 'gateway_allowed_endpoints': ['http://example.test'],
               'require_admin_build': 'yes', 'secrets_file': 'relative.json', 'admin_dir': 'admin',
               'mailbox_dir': 5, 'database': {'host': '10.0.0.4', 'port': 5432, 'dbname': 'x'}}
        with Workspace() as w:
            for key, value in bad.items():
                with self.subTest(key=key), self.assertRaises(ConfigError):
                    load_config(w.path(**{key.strip(): value}))
            for database in ({'host': '127.0.0.1', 'port': 0, 'dbname': 'x'}, {'host': '127.0.0.1', 'port': 5432},
                             {'host': '127.0.0.1', 'port': 5432, 'dbname': ''}):
                with self.subTest(database=database), self.assertRaises(ConfigError):
                    load_config(w.path(database=database))

    def test_legacy_ports_and_colliding_origins_are_refused(self):
        with Workspace() as w:
            for port in FORBIDDEN_PORTS:
                with self.subTest(port=port):
                    for change in ({'control_plane_port': port}, {'client_origin': 'http://127.0.0.1:%d' % port},
                                   {'cors_origins': ['http://127.0.0.1:%d' % port]},
                                   {'gateway_allowed_endpoints': ['http://127.0.0.1:%d' % port]}):
                        with self.assertRaises(ConfigError):
                            load_config(w.path(**change))
            with self.assertRaises(ConfigError):
                load_config(w.path(client_origin='http://127.0.0.1:%d' % w.port))
        self.assertEqual(dict(MVP_PORTS), {'control_plane': 3410, 'client_ui': 3411, 'client_backend': 3412,
                                           'fake_gateway': 3413})
        self.assertEqual(FORBIDDEN_PORTS, frozenset({3319, 3320, 3331, 3332}))

    def test_unreadable_and_non_json_files_are_refused_without_echoing_content(self):
        with Workspace() as w:
            with self.assertRaises(ConfigError) as missing:
                load_config(str(w.root/'absent.json'))
            self.assertEqual(str(missing.exception), 'CONFIG_UNREADABLE')
            (w.root/'bad.json').write_text('{"database": "SECRET-IN-FILE"', 'utf-8')
            with self.assertRaises(ConfigError) as malformed:
                load_config(str(w.root/'bad.json'))
            self.assertEqual(str(malformed.exception), 'CONFIG_INVALID')
            self.assertNotIn('SECRET', str(malformed.exception))


class SecretsTests(unittest.TestCase):
    def test_valid_secrets_and_role_settings_come_only_from_the_files(self):
        with Workspace() as w:
            secrets = load_secrets(w.secrets_path)
            config = load_config(w.path())
            with patch.dict(os.environ, {'PGDATABASE': 'elsewhere', 'PGHOST': '203.0.113.9', 'PGPORT': '1',
                                         'PGUSER': 'root', 'PGPASSWORD': 'env-secret'}):
                settings = role_settings(config, secrets, 'forge_runtime')
            self.assertEqual({k: settings[k] for k in ('host', 'port', 'dbname', 'user', 'password')},
                             {'host': '127.0.0.1', 'port': 54329, 'dbname': 'forge_mvp', 'user': 'forge_runtime',
                              'password': 'password-for-forge_runtime'})
            self.assertTrue(settings['autocommit'])
            with self.assertRaises(KeyError):
                role_settings(config, secrets, 'postgres')

    def test_invalid_secrets_are_refused_and_never_echoed(self):
        with Workspace() as w:
            good = json.loads(Path(w.secrets_path).read_text('utf-8'))
            same = Fernet.generate_key().decode()
            cases = {'missing role': {**good, 'roles': {k: v for k, v in list(good['roles'].items())[1:]}},
                     'extra key': {**good, 'postgres_password': 'OPERATOR-SECRET'},
                     'bad fernet': {**good, 'gateway_key': 'not-a-fernet-key-SECRET'},
                     'shared key': {**good, 'delivery_key': same, 'gateway_key': same},
                     'shared platform key': {**good, 'platform_key': good['gateway_key']},
                     'missing platform key': {key: value for key, value in good.items() if key != 'platform_key'},
                     'empty password': {**good, 'roles': {**good['roles'], 'forge_runtime': ''}}}
            for name, document in cases.items():
                with self.subTest(name), self.assertRaises(ConfigError) as caught:
                    load_secrets(write(w.root/'s.json', document))
                self.assertEqual(str(caught.exception), 'SECRETS_INVALID')
            with self.assertRaises(ConfigError) as missing:
                load_secrets(str(w.root/'absent.json'))
            self.assertEqual(str(missing.exception), 'SECRETS_UNREADABLE')


class Ready:
    def __init__(self, value=True):
        self.value = value

    def check(self):
        return self.value


class AssemblyTests(unittest.TestCase):
    def client(self, w, readiness=None, **change):
        config = load_config(w.path(**change))
        app = FastAPI()
        assemble(app, config, Ready() if readiness is None else readiness)
        return config, TestClient(app, base_url=config.admin_origin, follow_redirects=False)

    def test_status_reports_readiness_and_the_admin_build_state(self):
        with Workspace() as w:
            config, client = self.client(w)
            with client:
                body = client.get('/status')
                self.assertEqual((body.status_code, body.json()), (200, {'status': 'ready', 'profile': MVP_PROFILE, 'admin': 'ready'}))
                self.assertEqual(body.headers['cache-control'], 'no-store')
            _, client = self.client(w, readiness=Ready(False))
            with client:
                self.assertEqual((client.get('/status').status_code, client.get('/status').json()['status']), (503, 'not_ready'))
            (w.root/'admin'/'index.html').unlink()
            _, client = self.client(w, require_admin_build=False)
            with client:
                body = client.get('/status').json()
                self.assertEqual(body['admin'], 'missing')
                self.assertEqual(client.get('/admin/').status_code, 503)

    def test_a_required_admin_build_that_is_missing_stops_assembly(self):
        with Workspace() as w:
            (w.root/'admin'/'index.html').unlink()
            with self.assertRaises(ConfigError) as caught:
                assemble(FastAPI(), load_config(w.path()), Ready())
            self.assertEqual(str(caught.exception), 'ADMIN_BUILD_MISSING')

    def test_admin_is_same_origin_with_csp_and_only_the_client_origin_gets_cors(self):
        with Workspace() as w:
            config, client = self.client(w)
            with client:
                page = client.get('/admin/')
                self.assertEqual((page.status_code, page.headers['content-security-policy']), (200, ADMIN_CSP))
                preflight = client.options('/forge/v1/accounts/login', headers={
                    'Origin': 'http://127.0.0.1:3411', 'Access-Control-Request-Method': 'POST'})
                self.assertEqual(preflight.headers['access-control-allow-origin'], 'http://127.0.0.1:3411')
                foreign = client.options('/forge/v1/accounts/login', headers={
                    'Origin': 'http://evil.test', 'Access-Control-Request-Method': 'POST'})
                self.assertNotIn('access-control-allow-origin', foreign.headers)
                self.assertEqual(client.post('/forge/v1/accounts/login', headers={'Origin': 'http://evil.test'}).status_code, 403)
                self.assertEqual(client.get('/status', headers={'Host': 'evil.test'}).status_code, 403)


class ServeTests(unittest.TestCase):
    def run_serve(self, w, **change):
        """Run the real uvicorn server on the configured port with a database-free composition."""
        stopping, failures = threading.Event(), []

        def compose(config, secrets, pools):
            app = FastAPI()
            assemble(app, config, Ready())
            return app

        def target():
            try:
                serve(w.path(**change), compose_fn=compose, stopping=stopping)
            except Exception as error:
                failures.append(error)
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread, stopping, failures

    def wait_listening(self, port, thread):
        for _ in range(100):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
                return True
            except OSError:
                thread.join(0.1)
        return False

    def test_a_valid_config_serves_status_and_admin_on_the_configured_port(self):
        with Workspace() as w:
            thread, stopping, failures = self.run_serve(w)
            try:
                self.assertTrue(self.wait_listening(w.port, thread), failures)
                base = 'http://127.0.0.1:%d' % w.port
                status = httpx.get(base + '/status')
                self.assertEqual((status.status_code, status.json()['status']), (200, 'ready'))
                self.assertEqual(httpx.get(base + '/admin/').headers['content-security-policy'], ADMIN_CSP)
                self.assertEqual(httpx.get(base + '/status', headers={'Host': 'evil.test'}).status_code, 403)
            finally:
                stopping.set()
                thread.join(15)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])

    def test_an_occupied_port_fails_closed_and_leaves_the_other_process_alone(self):
        with Workspace() as w, socket.socket() as other:
            other.bind(('127.0.0.1', w.port))
            other.listen(4)
            with self.assertRaises(ConfigError) as caught:
                serve(w.path(), compose_fn=lambda *a: FastAPI(), stopping=threading.Event())
            self.assertEqual(str(caught.exception), 'PORT_OCCUPIED')
            socket.create_connection(('127.0.0.1', w.port), timeout=1).close()

    def test_nothing_is_bound_when_the_config_or_secrets_are_invalid(self):
        with Workspace() as w:
            calls = []
            for change in ({'control_plane_port': 3319}, {'version': 9}):
                with self.assertRaises(ConfigError):
                    serve(w.path(**change), compose_fn=lambda *a: calls.append(a), stopping=threading.Event())
            Path(w.secrets_path).write_text('{}', 'utf-8')
            with self.assertRaises(ConfigError):
                serve(w.path(), compose_fn=lambda *a: calls.append(a), stopping=threading.Event())
            self.assertEqual(calls, [])
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', w.port))


class CliTests(unittest.TestCase):
    def test_failures_print_a_finite_code_and_exit_non_zero(self):
        with Workspace() as w:
            out = []
            with patch('builtins.print', lambda text, **kw: out.append(text)):
                self.assertEqual(main(['serve', '--config', str(w.root/'absent.json')]), 1)
                self.assertEqual(main(['serve', '--config', w.path(control_plane_port=3320)]), 1)
                self.assertEqual(main(['serve']), 2)
            self.assertEqual([json.loads(text)['code'] for text in out[:2]], ['CONFIG_UNREADABLE', 'CONFIG_INVALID:control_plane_port'])
            self.assertNotIn('password-for', ''.join(out))

    def test_the_process_drops_every_libpq_environment_variable_before_connecting(self):
        with Workspace() as w, patch.dict(os.environ, {'PGSERVICE': 'other', 'PGOPTIONS': '-c x=1', 'KEEP_ME': '1'}):
            with patch('builtins.print', lambda text, **kw: None):
                main(['serve', '--config', str(w.root/'absent.json')])
            self.assertEqual([name for name in os.environ if name.startswith('PG')], [])
            self.assertEqual(os.environ['KEEP_ME'], '1')


if __name__ == '__main__':
    unittest.main()
