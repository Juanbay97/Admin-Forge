"""mvp_up unit contracts: generated runtime files obey the strict loaders, ports are prechecked, CLI wiring."""
import json
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from forge.mvp_local import ConfigError, MVP_PORTS, ROLES, load_config, load_secrets, main
from forge.mvp_up import precheck_ports, runtime_files
from forge.provisioning import MULTIUSER_SEED
from cryptography.fernet import Fernet


def files(directory, **change):
    values = dict(database={'host': '127.0.0.1', 'port': 55432, 'dbname': 'forge_dev'},
                  passwords={role: 'pw-' + role for role in ROLES}, delivery_key=Fernet.generate_key().decode(),
                  gateway_key=Fernet.generate_key().decode(), platform_key=Fernet.generate_key().decode(),
                  admin_dir=str(Path(directory)/'admin'),
                  require_admin_build=False)
    values.update(change)
    (Path(directory)/'mailbox').mkdir(exist_ok=True)
    return runtime_files(Path(directory), **values), values


class SeedTests(unittest.TestCase):
    def test_the_local_stack_seeds_the_multi_user_organizations(self):
        import forge.mvp_up
        self.assertIs(forge.mvp_up.MVP_SEED, MULTIUSER_SEED)


class RuntimeFilesTests(unittest.TestCase):
    def test_the_generated_config_and_secrets_load_through_the_strict_loaders(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, values = files(directory)
            config = load_config(config_path)
            self.assertEqual((config.control_plane_port, config.client_origin, config.cors_origins),
                             (MVP_PORTS['control_plane'], 'http://127.0.0.1:%d' % MVP_PORTS['client_ui'],
                              ('http://127.0.0.1:%d' % MVP_PORTS['client_ui'],)))
            self.assertEqual(config.gateway_policy.allowed, frozenset({'http://127.0.0.1:%d' % MVP_PORTS['fake_gateway']}))
            self.assertEqual((config.database, config.require_admin_build, config.mailbox_dir),
                             (values['database'], False, str(Path(directory)/'mailbox')))
            secrets = load_secrets(config.secrets_file)
            self.assertEqual((secrets.roles, secrets.gateway_key.decode(), secrets.platform_key.decode()),
                             (values['passwords'], values['gateway_key'], values['platform_key']))
            self.assertNotIn('pw-', Path(config_path).read_text('utf-8'))

    def test_the_local_stack_secrets_carry_a_policy_key_and_a_connector_key_that_load(self):
        from forge.capability_signing import b64u
        import os
        with tempfile.TemporaryDirectory() as directory:
            config_path, values = files(directory, policy_key=b64u(os.urandom(32)), connector_key=Fernet.generate_key().decode())
            secrets = load_secrets(load_config(config_path).secrets_file)
            self.assertEqual((secrets.policy_key, secrets.connector_key), (values['policy_key'], values['connector_key'].encode()))

    def test_the_admin_build_requirement_is_carried_into_the_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path, _ = files(directory, require_admin_build=True)
            self.assertTrue(load_config(config_path).require_admin_build)

    def test_existing_runtime_files_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            files(directory)
            before = (Path(directory)/'secrets.json').read_text('utf-8')
            with self.assertRaises(FileExistsError):
                files(directory)
            self.assertEqual((Path(directory)/'secrets.json').read_text('utf-8'), before)


class PortTests(unittest.TestCase):
    def free_ports(self, count):
        sockets = [socket.socket() for _ in range(count)]
        try:
            for item in sockets:
                item.bind(('127.0.0.1', 0))
            return [item.getsockname()[1] for item in sockets]
        finally:
            for item in sockets:
                item.close()

    def test_free_ports_pass_and_stay_free(self):
        ports = self.free_ports(2)
        precheck_ports(ports)
        for port in ports:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))

    def test_any_occupied_port_stops_before_resources_are_created(self):
        first, second = self.free_ports(2)
        with socket.socket() as other:
            other.bind(('127.0.0.1', second))
            other.listen(4)
            with self.assertRaises(ConfigError) as caught:
                precheck_ports([first, second])
            self.assertEqual(str(caught.exception), 'PORT_OCCUPIED')
            socket.create_connection(('127.0.0.1', second), timeout=1).close()


class CliTests(unittest.TestCase):
    def test_up_is_dispatched_with_the_admin_build_flag(self):
        calls = []
        with patch('forge.mvp_up.up', lambda stopping, **kw: calls.append(kw)):
            self.assertEqual(main(['up']), 0)
            self.assertEqual(main(['up', '--require-admin-build']), 0)
        self.assertEqual(calls, [{'require_admin_build': False}, {'require_admin_build': True}])

    def test_up_failures_are_finite_codes(self):
        out = []

        def refuse(stopping, **kw):
            raise ConfigError('PORT_OCCUPIED')
        with patch('forge.mvp_up.up', refuse), patch('builtins.print', lambda text, **kw: out.append(text)):
            self.assertEqual(main(['up']), 1)
        self.assertEqual(json.loads(out[0]), {'status': 'failed', 'code': 'PORT_OCCUPIED'})


class PackagingTests(unittest.TestCase):
    def test_the_built_admin_spa_is_declared_as_package_data_without_being_committed(self):
        root = Path(__file__).resolve().parents[1]
        data = tomllib.loads((root/'pyproject.toml').read_text('utf-8'))['tool']['setuptools']['package-data']['forge']
        self.assertIn('web/admin/**/*', data)
        self.assertEqual({'web/status.html', 'web/status.css', 'web/status.js'} - set(data), set())
        self.assertIn('src/forge/web/admin/', (root/'.gitignore').read_text('utf-8').splitlines())


class EntryPointTests(unittest.TestCase):
    def test_the_module_entry_point_reports_the_same_finite_code_as_the_function(self):
        """``-m forge.mvp_local`` runs as __main__: its error classes must still match the imported ones."""
        root = Path(__file__).resolve().parents[1]
        holder = socket.socket()
        try:
            holder.bind(('127.0.0.1', MVP_PORTS['fake_gateway']))
        except OSError:
            self.skipTest('the reserved fake gateway port is in use on this machine')
        try:
            holder.listen(1)
            environment = {key: os.environ[key] for key in ('SystemRoot', 'PATH', 'TEMP', 'TMP') if key in os.environ}
            environment['PYTHONPATH'] = str(root/'src')
            result = subprocess.run([sys.executable, '-B', '-m', 'forge.mvp_local', 'up'], cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=60)
        finally:
            holder.close()
        self.assertEqual((result.returncode, json.loads(result.stdout)), (1, {'status': 'failed', 'code': 'PORT_OCCUPIED'}))


if __name__ == '__main__':
    unittest.main()
