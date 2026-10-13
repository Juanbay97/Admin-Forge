"""Production configuration: environment variables and ``*_FILE`` secret files only.

The dev profile (``forge.mvp_local``) stays loopback-only and file-configured; this module is
its production counterpart. Every failure is a finite non-secret ``CONFIG_INVALID:<KEY>`` code
raised before any port is bound or any pool opened; a value from the environment or from a
secret file is never echoed. ``PG*`` libpq variables are ignored here and removed from the
process by ``strip_libpq_environment`` so they can never steer a connection.
"""
import base64
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from forge.gateway_origins import canonical_origin, policy_from_env, ORIGINS_VARIABLE
from forge.mvp_local import ConfigError, FORBIDDEN_PORTS, ROLES, _fail
from forge.smtp_delivery import SMTP_KEYS, load_smtp_settings

DEFAULT_PORT = 3410
DEFAULT_BIND_HOST = '0.0.0.0'
DEFAULT_ADMIN_DIR = str(Path(__file__).resolve().parent/'web'/'admin')
SSL_MODES = ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full')
LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
_SECRETS = ('FORGE_DELIVERY_KEY', 'FORGE_GATEWAY_KEY', 'FORGE_PLATFORM_KEY', 'FORGE_POLICY_KEY', 'FORGE_CONNECTOR_KEY', 'FORGE_DB_ADMIN_PASSWORD')
_PLAIN = ('FORGE_PUBLIC_ORIGIN', 'FORGE_DB_HOST', 'FORGE_DB_PORT', 'FORGE_DB_NAME', 'FORGE_DB_SSLMODE',
          'FORGE_DB_ADMIN_USER', 'FORGE_ROLE_PASSWORDS_DIR', 'FORGE_ADMIN_DIR', 'FORGE_PORT', 'FORGE_BIND_HOST',
          'FORGE_WORKERS', 'FORGE_LOG_LEVEL', ORIGINS_VARIABLE, 'FORGE_GATEWAY_CA_FILE', 'FORGE_CONNECTOR_TEST_FIXTURES_FILE',
          'FORGE_POLICY_RETIRED_KEYS', 'FORGE_POLICY_RETIRED_KEYS_FILE')
# Later changes that add settings extend this tuple; any other FORGE_* name is a typo and refused.
KNOWN_KEYS = (*_PLAIN, *_SECRETS, *(name + '_FILE' for name in _SECRETS), *SMTP_KEYS)
_DB_HOST = re.compile(r'[A-Za-z0-9]([A-Za-z0-9._-]{0,251}[A-Za-z0-9])?')
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}')


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    dbname: str
    sslmode: str
    admin_user: str
    admin_password: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ProdConfig:
    public_origin: str
    db: DbConfig
    roles: dict = field(repr=False)
    delivery_key: bytes = field(repr=False)
    gateway_key: bytes = field(repr=False)
    platform_key: bytes = field(repr=False)  # seals the platform owner's TOTP secret; a key of its own
    gateway_policy: object
    admin_dir: str
    port: int = DEFAULT_PORT
    bind_host: str = DEFAULT_BIND_HOST
    log_level: str = 'INFO'
    smtp: object = None  # `SmtpSettings` when any FORGE_SMTP_* key is set; serving requires it, migrating does not
    gateway_ca_file: str | None = None  # an extra CA for private gateways (the allow-list stays https-only); None = system trust
    policy_key: str | None = field(default=None, repr=False)  # Ed25519 seed (base64url) signing the effective policy; None = those routes answer 503
    connector_key: bytes | None = field(default=None, repr=False)  # seals connector credentials; None = the connector routes answer 503
    connector_fixtures: dict | None = None  # loopback/dev fixture hosts for the egress guard; NEVER set in production
    policy_retired_keys: tuple = ()  # retired PUBLIC policy keys of a rotation, kept in the published key set

    @property
    def trusted_hosts(self):
        """The only Host header values accepted: derived from the public origin, nothing else."""
        parts = urlsplit(self.public_origin)
        if parts.port is None:
            return frozenset({parts.hostname})
        authority = '%s:%d' % (parts.hostname, parts.port)
        return frozenset({parts.hostname, authority}) if parts.port == 443 else frozenset({authority})

    @property
    def public_host(self):
        """The Host header browsers (and the healthcheck) send for the public origin."""
        parts = urlsplit(self.public_origin)
        return parts.hostname if parts.port in (None, 443) else '%s:%d' % (parts.hostname, parts.port)

    @property
    def browser_origins(self):
        return (self.public_origin,)

    def role_settings(self, role):
        """Every connection parameter is explicit, so libpq environment variables never apply."""
        return dict(host=self.db.host, port=self.db.port, dbname=self.db.dbname, user=role,
                    password=self.roles[role], sslmode=self.db.sslmode, autocommit=True, connect_timeout=2,
                    options='-c statement_timeout=5000 -c lock_timeout=2000')


def strip_libpq_environment(environ):
    """libpq consults PGSERVICE/PGOPTIONS-style variables even for explicit parameters: drop them all."""
    for name in [name for name in environ if name.startswith('PG')]:
        del environ[name]


def _read(path, key):
    try:
        value = Path(path).read_text('utf-8').rstrip('\r\n')
    except (OSError, ValueError):
        _fail(key)
    return value


def _secret(env, key):
    """The ``KEY_FILE`` content, else the direct ``KEY`` value; both at once is ambiguous and refused."""
    path, direct = env.get(key + '_FILE'), env.get(key)
    if path is not None and direct is not None:
        _fail(key)
    if path is not None:
        if not path or not Path(path).is_absolute():
            _fail(key)
        return _read(path, key)
    return direct


def _fernet(env, key):
    value = _secret(env, key)
    try:
        if not value:
            raise ValueError
        encoded = value.encode('ascii')
        Fernet(encoded)
    except (ValueError, TypeError):
        _fail(key)
    return encoded


def _policy_key(env, others):
    """The optional effective-policy signing seed: base64url of 32 bytes, never the same secret as another key."""
    value = _secret(env, 'FORGE_POLICY_KEY')
    if value is None:
        return None
    from forge.capability_signing import load_signer, unb64u
    try:
        load_signer(value)
        if unb64u(value) in {base64.urlsafe_b64decode(other) for other in others}:
            raise ValueError
    except ValueError:
        _fail('FORGE_POLICY_KEY')
    return value


def _retired_policy_keys(env, policy_key):
    """The optional retired PUBLIC policy keys of a rotation (these are not secrets): kept in the published key set. Needs a signing key."""
    path, direct = env.get('FORGE_POLICY_RETIRED_KEYS_FILE'), env.get('FORGE_POLICY_RETIRED_KEYS')
    if path is not None and direct is not None:
        _fail('FORGE_POLICY_RETIRED_KEYS')
    if path is not None:
        if not path or not Path(path).is_absolute():
            _fail('FORGE_POLICY_RETIRED_KEYS')
        direct = _read(path, 'FORGE_POLICY_RETIRED_KEYS')
    from forge.capability_signing import parse_retired_keys, split_retired_keys
    try:
        items = split_retired_keys(direct or '')
        if items and policy_key is None:
            raise ValueError
        return parse_retired_keys(items, active=policy_key) if items else ()
    except (ValueError, TypeError):
        _fail('FORGE_POLICY_RETIRED_KEYS')


def _connector_key(env, others):
    """The optional connector sealing key: a Fernet key of its own, never one of the other secrets."""
    value = _secret(env, 'FORGE_CONNECTOR_KEY')
    if value is None:
        return None
    from forge.connector_cipher import ConnectorCipher, ConnectorCipherError
    try:
        key = value.encode('ascii')
        ConnectorCipher(key, distinct_from=list(others))
    except (ValueError, TypeError, ConnectorCipherError):
        _fail('FORGE_CONNECTOR_KEY')
    return key


def _connector_fixtures(env):
    path = env.get('FORGE_CONNECTOR_TEST_FIXTURES_FILE')
    if path is None:
        return None
    from forge.egress_guard import load_fixtures
    try:
        if not Path(path).is_absolute():
            raise ValueError
        return load_fixtures(path)
    except (OSError, ValueError):
        _fail('FORGE_CONNECTOR_TEST_FIXTURES_FILE')


def _roles(env):
    directory = env.get('FORGE_ROLE_PASSWORDS_DIR')
    if not directory or not Path(directory).is_absolute() or not Path(directory).is_dir():
        _fail('FORGE_ROLE_PASSWORDS_DIR')
    roles = {role: _read(Path(directory)/role, 'FORGE_ROLE_PASSWORDS_DIR') for role in ROLES}
    if not all(roles.values()):
        _fail('FORGE_ROLE_PASSWORDS_DIR')
    return roles


def _port(value, key):
    if type(value) is not str or not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 65535:
        _fail(key)
    return int(value)


def _db(env):
    host = env.get('FORGE_DB_HOST')
    if type(host) is not str or not (_DB_HOST.fullmatch(host) or _is_ip(host)):
        _fail('FORGE_DB_HOST')
    dbname = env.get('FORGE_DB_NAME')
    if type(dbname) is not str or not _IDENTIFIER.fullmatch(dbname):
        _fail('FORGE_DB_NAME')
    sslmode = env.get('FORGE_DB_SSLMODE', 'require')
    if sslmode not in SSL_MODES:
        _fail('FORGE_DB_SSLMODE')
    admin = env.get('FORGE_DB_ADMIN_USER', 'postgres')
    if not _IDENTIFIER.fullmatch(admin):
        _fail('FORGE_DB_ADMIN_USER')
    password = _secret(env, 'FORGE_DB_ADMIN_PASSWORD')
    if password is not None and not password:
        _fail('FORGE_DB_ADMIN_PASSWORD')
    return DbConfig(host, _port(env.get('FORGE_DB_PORT', '5432'), 'FORGE_DB_PORT'), dbname, sslmode, admin, password)


def _is_ip(value):
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def load_prod_config(environ):
    """Validate an environment mapping into ``ProdConfig``; raises ``ConfigError('CONFIG_INVALID:<KEY>')``."""
    env = {name: value for name, value in environ.items() if not name.startswith('PG')}
    if any(name.startswith('FORGE_') and name not in KNOWN_KEYS for name in env):
        _fail('unknown_key')
    if 'FORGE_WORKERS' in env and env['FORGE_WORKERS'] != '1':
        # Pools (2 connections per role), the readiness cache and rate-limit state are per process.
        _fail('FORGE_WORKERS')
    try:
        public = canonical_origin(env.get('FORGE_PUBLIC_ORIGIN'))
    except ValueError:
        _fail('FORGE_PUBLIC_ORIGIN')
    db = _db(env)
    roles = _roles(env)
    delivery, gateway = _fernet(env, 'FORGE_DELIVERY_KEY'), _fernet(env, 'FORGE_GATEWAY_KEY')
    if delivery == gateway:
        _fail('FORGE_GATEWAY_KEY')
    platform = _fernet(env, 'FORGE_PLATFORM_KEY')
    if platform in (delivery, gateway):
        _fail('FORGE_PLATFORM_KEY')
    policy_key = _policy_key(env, (delivery, gateway, platform))
    policy_retired = _retired_policy_keys(env, policy_key)
    connector_key = _connector_key(env, (delivery, gateway, platform, *(() if policy_key is None else (policy_key,))))
    connector_fixtures = _connector_fixtures(env)
    try:
        policy = policy_from_env(env)
    except ValueError:
        _fail(ORIGINS_VARIABLE)
    admin_dir = env.get('FORGE_ADMIN_DIR', DEFAULT_ADMIN_DIR)
    if not Path(admin_dir).is_absolute():
        _fail('FORGE_ADMIN_DIR')
    port = _port(env.get('FORGE_PORT', str(DEFAULT_PORT)), 'FORGE_PORT')
    if port in FORBIDDEN_PORTS:
        _fail('FORGE_PORT')
    bind = env.get('FORGE_BIND_HOST', DEFAULT_BIND_HOST)
    if not _is_ip(bind):
        _fail('FORGE_BIND_HOST')
    level = env.get('FORGE_LOG_LEVEL', 'INFO')
    if level not in LOG_LEVELS:
        _fail('FORGE_LOG_LEVEL')
    smtp = load_smtp_settings(env) if any(name.startswith('FORGE_SMTP_') for name in env) else None
    gateway_ca = env.get('FORGE_GATEWAY_CA_FILE')
    if gateway_ca is not None and (not Path(gateway_ca).is_absolute() or not Path(gateway_ca).is_file()):
        _fail('FORGE_GATEWAY_CA_FILE')
    return ProdConfig(public, db, roles, delivery, gateway, platform, policy, admin_dir, port, bind, level, smtp, gateway_ca, policy_key, connector_key, connector_fixtures, policy_retired)
