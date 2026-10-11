"""Fake gateway as a standalone loopback server: keys file, port safety, redacted CLI."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from forge.fake_gateway import DEFAULT_PORT, FakeGatewayConfiguration, GatewayPortOccupied, main, read_keys, serve
from forge.mvp_local import FORBIDDEN_PORTS, MVP_PORTS


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def keys_file(directory, text):
    path = Path(directory)/'keys.txt'
    path.write_text(text, 'utf-8')
    return str(path)


def wait_listening(port, thread):
    for _ in range(100):
        try:
            socket.create_connection(('127.0.0.1', port), timeout=0.2).close()
            return True
        except OSError:
            thread.join(0.1)
    return False


class Running:
    """The real uvicorn server on a free loopback port, stopped through its own event."""
    def __init__(self, target, *args, **kwargs):
        self.stopping, self.failures = threading.Event(), []

        def run():
            try:
                target(*args, stopping=self.stopping, **kwargs)
            except Exception as error:
                self.failures.append(error)
        self.thread = threading.Thread(target=run, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def wait(self, port):
        return wait_listening(port, self.thread)

    def __exit__(self, *exc):
        self.stopping.set()
        self.thread.join(15)
        assert not self.thread.is_alive()


class KeysFileTests(unittest.TestCase):
    def test_keys_are_read_one_per_line_ignoring_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(read_keys(keys_file(directory, 'fake-org-a-key\n\n  fake-org-b-key  \n')),
                             ('fake-org-a-key', 'fake-org-b-key'))

    def test_empty_oversized_malformed_or_unreadable_files_are_refused_without_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            for text in ('', '\n\n', 'key with space\n', 'k\x00\n', '\n'.join('key%d' % n for n in range(9))):
                with self.subTest(text=text[:12]), self.assertRaises(ValueError) as caught:
                    read_keys(keys_file(directory, text))
                self.assertEqual(str(caught.exception), 'KEYS_FILE_INVALID')
            with self.assertRaises(ValueError) as missing:
                read_keys(str(Path(directory)/'absent.txt'))
            self.assertEqual(str(missing.exception), 'KEYS_FILE_INVALID')


class ServeTests(unittest.TestCase):
    def test_the_default_port_is_the_single_reserved_fake_gateway_port(self):
        self.assertEqual(DEFAULT_PORT, MVP_PORTS['fake_gateway'])

    def test_serves_models_only_for_the_configured_keys_over_real_http(self):
        port = free_port()
        with Running(serve, FakeGatewayConfiguration(keys=('secret-key-a', 'secret-key-b'), port=port)) as running:
            self.assertTrue(running.wait(port), running.failures)
            base = 'http://127.0.0.1:%d' % port
            for key in ('secret-key-a', 'secret-key-b'):
                response = httpx.get(base + '/v1/models', headers={'Authorization': 'Bearer ' + key})
                self.assertEqual((response.status_code, sorted(m['id'] for m in response.json()['data'])),
                                 (200, ['fake-error', 'fake-fast', 'fake-malformed', 'fake-slow']))
                self.assertNotIn(key, response.text)
            self.assertEqual(httpx.get(base + '/v1/models', headers={'Authorization': 'Bearer other'}).status_code, 401)
        self.assertEqual(running.failures, [])

    def test_an_occupied_port_fails_closed_and_the_other_process_keeps_working(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1', free_port()))
            other.listen(4)
            port = other.getsockname()[1]
            with self.assertRaises(GatewayPortOccupied):
                serve(FakeGatewayConfiguration(keys=('k',), port=port), stopping=threading.Event())
            socket.create_connection(('127.0.0.1', port), timeout=1).close()


class CliTests(unittest.TestCase):
    def run_cli(self, argv, stopping=None):
        out = []
        with patch('builtins.print', lambda text, **kw: out.append(text)):
            code = main(argv, stopping=stopping)
        return code, [json.loads(line) for line in out]

    def test_the_ready_line_names_the_origin_but_never_a_key(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as directory:
            path = keys_file(directory, 'SECRET-KEY-VALUE\n')
            stopping, result = threading.Event(), []
            thread = threading.Thread(target=lambda: result.append(self.run_cli(['--keys-file', path, '--port', str(port)], stopping)))
            thread.start()
            try:
                self.assertTrue(wait_listening(port, thread))
                self.assertEqual(httpx.get('http://127.0.0.1:%d/v1/models' % port,
                                           headers={'Authorization': 'Bearer SECRET-KEY-VALUE'}).status_code, 200)
            finally:
                stopping.set()
                thread.join(15)
            code, lines = result[0]
            self.assertEqual((code, lines), (0, [{'status': 'ready', 'origin': 'http://127.0.0.1:%d' % port}]))
            self.assertNotIn('SECRET', json.dumps(lines))

    def test_legacy_ports_invalid_keys_and_occupied_ports_exit_with_finite_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = keys_file(directory, 'k\n')
            for port in FORBIDDEN_PORTS:
                with self.subTest(port=port):
                    self.assertEqual(self.run_cli(['--keys-file', path, '--port', str(port)]),
                                     (1, [{'status': 'failed', 'code': 'PORT_FORBIDDEN'}]))
            self.assertEqual(self.run_cli(['--keys-file', str(Path(directory)/'absent'), '--port', '40000']),
                             (1, [{'status': 'failed', 'code': 'KEYS_FILE_INVALID'}]))
            self.assertEqual(self.run_cli(['--port', '40000']), (2, [{'status': 'failed', 'code': 'INVALID_ARGUMENTS'}]))
            self.assertEqual(self.run_cli(['--keys-file', path, '--port', 'nope']), (2, [{'status': 'failed', 'code': 'INVALID_ARGUMENTS'}]))
            with socket.socket() as other:
                other.bind(('127.0.0.1', free_port()))
                other.listen(4)
                port = other.getsockname()[1]
                self.assertEqual(self.run_cli(['--keys-file', path, '--port', str(port)], threading.Event()),
                                 (1, [{'status': 'failed', 'code': 'PORT_OCCUPIED'}]))


if __name__ == '__main__':
    unittest.main()
