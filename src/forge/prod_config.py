"""Production configuration: environment variables and ``*_FILE`` secret files only.

The dev profile (``forge.mvp_local``) stays loopback-only and file-configured; this module is
its production counterpart. Every failure is a finite non-secret ``CONFIG_INVALID:<KEY>`` code
raised before any port is bound or any pool opened; a value from the environment or from a
secret file is never echoed. ``PG*`` libpq variables are ignored here and removed from the
process by ``strip_libpq_environment`` so they can never steer a connection.
"""
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from forge.gateway_origins import canonical_origin, policy_from_env, ORIGINS_VARIABLE
from forge.mvp_local import ConfigError, FORBIDDEN_PORTS, ROLES, _fail

DEFAULT_PORT = 3410
DEFAULT_BIND_HOST = '0.0.0.0'
DEFAULT_ADMIN_DIR = str(Path(__file__).resolve().parent/'web'/'admin')
SSL_MODES = ('disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full')
_SECRETS = ('FORGE_DELIVERY_KEY', 'FORGE_GATEWAY_KEY', 'FORGE_DB_ADMIN_PASSWORD')
_PLAIN = ('FORGE_PUBLIC_ORIGIN', 'FORGE_DB_HOST', 'FORGE_DB_PORT', 'FORGE_DB_NAME', 'FORGE_DB_SSLMODE',
          'FORGE_DB_ADMIN_USER', 'FORGE_ROLE_PASSWORDS_DIR', 'FORGE_ADMIN_DIR', 'FORGE_PORT', 'FORGE_BIND_HOST',
          'FORGE_WORKERS', ORIGINS_VARIABLE)
# Later changes that add settings extend this tuple; any other FORGE_* name is a typo and refused.
KNOWN_KEYS = (*_PLAIN, *_SECRETS, *(name + '_FILE' for name in _SECRETS))
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
    gateway_policy: object
    admin_dir: str
    port: int = DEFAULT_PORT
    bind_host: str = DEFAULT_BIND_HOST

    @property
    def trusted_hosts(self):
        """The only Host header values accepted: derived from the public origin, nothing else."""
        parts = urlsplit(self.public_origin)
        if parts.port is None:
            return frozenset({parts.hostname})
        authority = '%s:%d' % (parts.hostname, parts.port)
        return frozenset({parts.hostname, authority}) if parts.port == 443 else frozenset({authority})

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
    return ProdConfig(public, db, roles, delivery, gateway, policy, admin_dir, port, bind)
