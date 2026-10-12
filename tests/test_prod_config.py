"""prod_config: environment and *_FILE secret loading for the production profile; no ports, no database."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from forge.gateway_origins import DEFAULT_ENDPOINT
from forge.mvp_local import ConfigError, FORBIDDEN_PORTS, ROLES
from forge.prod_config import KNOWN_KEYS, load_prod_config, strip_libpq_environment

ORIGIN = 'https://forge.example.test'


class Fixture:
    """A temporary secrets directory plus the minimal valid production environment."""
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root/'roles').mkdir()
        for role in ROLES:
            (self.root/'roles'/role).write_text('password-for-%s\n' % role, 'utf-8')
        self.delivery, self.gateway = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        (self.root/'delivery.key').write_text(self.delivery + '\n', 'utf-8')
        (self.root/'gateway.key').write_text(self.gateway, 'utf-8')
        self.env = {
            'FORGE_PUBLIC_ORIGIN': ORIGIN, 'FORGE_DB_HOST': 'postgres', 'FORGE_DB_NAME': 'forge',
            'FORGE_ROLE_PASSWORDS_DIR': str(self.root/'roles'),
            'FORGE_DELIVERY_KEY_FILE': str(self.root/'delivery.key'),
            'FORGE_GATEWAY_KEY_FILE': str(self.root/'gateway.key')}
        return self

    def __exit__(self, *exc):
        self.directory.cleanup()

    def load(self, **change):
        env = {**self.env, **change}
        return load_prod_config({key: value for key, value in env.items() if value is not None})

    def refused(self, test, key, **change):
        with test.assertRaises(ConfigError) as caught:
            self.load(**change)
        test.assertEqual(str(caught.exception), 'CONFIG_INVALID:' + key)


class LoadTests(unittest.TestCase):
    def test_secrets_come_from_files_and_defaults_apply(self):
        with Fixture() as f:
            config = f.load()
            self.assertEqual(config.public_origin, ORIGIN)
            self.assertEqual((config.db.host, config.db.port, config.db.dbname), ('postgres', 5432, 'forge'))
            self.assertEqual((config.port, config.bind_host), (3410, '0.0.0.0'))
            self.assertEqual(config.roles, {role: 'password-for-%s' % role for role in ROLES})
            self.assertEqual((config.delivery_key, config.gateway_key), (f.delivery.encode(), f.gateway.encode()))
            self.assertEqual(config.gateway_policy.allowed, frozenset({DEFAULT_ENDPOINT}))
            self.assertIsNone(config.db.admin_password)

    def test_a_direct_value_is_used_only_when_no_file_is_given(self):
        with Fixture() as f:
            key = Fernet.generate_key().decode()
            config = f.load(FORGE_GATEWAY_KEY_FILE=None, FORGE_GATEWAY_KEY=key)
            self.assertEqual(config.gateway_key, key.encode())
            f.refused(self, 'FORGE_GATEWAY_KEY', FORGE_GATEWAY_KEY=key)  # both a file and a value: ambiguous

    def test_a_missing_or_malformed_secret_is_refused_by_name(self):
        with Fixture() as f:
            f.refused(self, 'FORGE_GATEWAY_KEY', FORGE_GATEWAY_KEY_FILE=None)
            f.refused(self, 'FORGE_DELIVERY_KEY', FORGE_DELIVERY_KEY_FILE=str(f.root/'absent'))
            (f.root/'bad.key').write_text('not-a-fernet-key', 'utf-8')
            f.refused(self, 'FORGE_GATEWAY_KEY', FORGE_GATEWAY_KEY_FILE=str(f.root/'bad.key'))
            f.refused(self, 'FORGE_GATEWAY_KEY', FORGE_GATEWAY_KEY_FILE=str(f.root/'delivery.key'))  # keys must differ
            (f.root/'roles'/ROLES[2]).write_text('\n', 'utf-8')
            f.refused(self, 'FORGE_ROLE_PASSWORDS_DIR')
            (f.root/'roles'/ROLES[2]).unlink()
            f.refused(self, 'FORGE_ROLE_PASSWORDS_DIR')

    def test_admin_credentials_are_optional_and_only_for_the_migrate_job(self):
        with Fixture() as f:
            (f.root/'admin.pw').write_text('s3cret\n', 'utf-8')
            config = f.load(FORGE_DB_ADMIN_USER='postgres', FORGE_DB_ADMIN_PASSWORD_FILE=str(f.root/'admin.pw'))
            self.assertEqual((config.db.admin_user, config.db.admin_password), ('postgres', 's3cret'))

    def test_invalid_values_are_refused_by_name(self):
        with Fixture() as f:
            for value in ('http://forge.example.test', ORIGIN + '/', ORIGIN + '/x', 'https://user@forge.example.test',
                          'forge.example.test', 'https://10.0.0.5', '', None):
                with self.subTest(origin=value):
                    f.refused(self, 'FORGE_PUBLIC_ORIGIN', FORGE_PUBLIC_ORIGIN=value)
            f.refused(self, 'FORGE_DB_HOST', FORGE_DB_HOST='bad host')
            f.refused(self, 'FORGE_DB_HOST', FORGE_DB_HOST=None)
            f.refused(self, 'FORGE_DB_NAME', FORGE_DB_NAME='')
            f.refused(self, 'FORGE_DB_PORT', FORGE_DB_PORT='0')
            f.refused(self, 'FORGE_DB_PORT', FORGE_DB_PORT='five')
            f.refused(self, 'FORGE_DB_SSLMODE', FORGE_DB_SSLMODE='sometimes')
            f.refused(self, 'FORGE_BIND_HOST', FORGE_BIND_HOST='all')
            f.refused(self, 'FORGE_PORT', FORGE_PORT='70000')
            f.refused(self, 'FORGE_ADMIN_DIR', FORGE_ADMIN_DIR='relative/admin')

    def test_legacy_demo_ports_are_never_served(self):
        with Fixture() as f:
            for port in FORBIDDEN_PORTS:
                with self.subTest(port=port):
                    f.refused(self, 'FORGE_PORT', FORGE_PORT=str(port))
            self.assertEqual(f.load(FORGE_PORT='8080').port, 8080)

    def test_only_one_worker_is_allowed(self):
        with Fixture() as f:
            self.assertEqual(f.load(FORGE_WORKERS='1').port, 3410)
            for value in ('2', '0', 'many', ''):
                with self.subTest(workers=value):
                    f.refused(self, 'FORGE_WORKERS', FORGE_WORKERS=value)

    def test_gateway_origin_allow_list_comes_from_the_environment(self):
        with Fixture() as f:
            config = f.load(FORGE_GATEWAY_ORIGINS='https://ia.example.test,https://gw.example.test')
            self.assertEqual(config.gateway_policy.allowed, frozenset({'https://ia.example.test', 'https://gw.example.test'}))
            f.refused(self, 'FORGE_GATEWAY_ORIGINS', FORGE_GATEWAY_ORIGINS='http://127.0.0.1:3413')

    def test_unknown_forge_keys_are_refused_but_other_variables_are_ignored(self):
        with Fixture() as f:
            f.refused(self, 'unknown_key', FORGE_SURPRISE='1')
            f.refused(self, 'unknown_key', FORGE_PG_PASSWORD='x')
            config = f.load(PATH='/usr/bin', HOME='/root', UNRELATED='x', PGPASSWORD='ambient', PGHOST='evil')
            self.assertEqual(config.db.host, 'postgres')
            self.assertIn('FORGE_PUBLIC_ORIGIN', KNOWN_KEYS)


class DerivedValueTests(unittest.TestCase):
    def test_host_set_and_origins_derive_from_the_public_origin_only(self):
        with Fixture() as f:
            config = f.load()
            self.assertEqual((config.trusted_hosts, config.browser_origins),
                             (frozenset({'forge.example.test'}), (ORIGIN,)))
            custom = f.load(FORGE_PUBLIC_ORIGIN='https://forge.example.test:8443')
            self.assertEqual((custom.trusted_hosts, custom.browser_origins),
                             (frozenset({'forge.example.test:8443'}), ('https://forge.example.test:8443',)))
            self.assertEqual(f.load(FORGE_PUBLIC_ORIGIN='https://forge.example.test:443').trusted_hosts,
                             frozenset({'forge.example.test', 'forge.example.test:443'}))

    def test_role_settings_are_explicit_libpq_parameters(self):
        with Fixture() as f:
            settings = f.load(FORGE_DB_PORT='6543', FORGE_DB_SSLMODE='verify-full').role_settings(ROLES[0])
            self.assertEqual((settings['host'], settings['port'], settings['dbname'], settings['user'],
                              settings['password'], settings['sslmode']),
                             ('postgres', 6543, 'forge', ROLES[0], 'password-for-%s' % ROLES[0], 'verify-full'))
            self.assertIs(settings['autocommit'], True)
            self.assertIn('statement_timeout', settings['options'])

    def test_repr_never_shows_a_secret(self):
        with Fixture() as f:
            (f.root/'admin.pw').write_text('admin-only-secret', 'utf-8')
            text = repr(f.load(FORGE_DB_ADMIN_PASSWORD_FILE=str(f.root/'admin.pw')))
            for secret in (f.delivery, f.gateway, 'password-for-', 'admin-only-secret'):
                self.assertNotIn(secret, text)

    def test_errors_carry_only_the_finite_code_not_the_value(self):
        with Fixture() as f:
            with self.assertRaises(ConfigError) as caught:
                f.load(FORGE_PUBLIC_ORIGIN='http://leaky-value.example.test')
            self.assertNotIn('leaky', str(caught.exception))


class LibpqEnvironmentTests(unittest.TestCase):
    def test_every_pg_variable_is_removed_and_the_rest_is_kept(self):
        env = {'PGPASSWORD': 'x', 'PGSERVICE': 'y', 'PGOPTIONS': '-c x', 'PATH': '/bin', 'FORGE_PORT': '1'}
        strip_libpq_environment(env)
        self.assertEqual(env, {'PATH': '/bin', 'FORGE_PORT': '1'})


if __name__ == '__main__':
    unittest.main()
