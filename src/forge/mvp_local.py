"""Config-only MVP control-plane composition: ``python -m forge.mvp_local serve --config <file>``.

Everything comes from one explicit, strictly validated JSON file and the private secrets
file it names: no environment discovery, no fake identity, no implicit database. Any
missing, unknown or malformed field exits with a finite non-secret code before a single
port is bound. The legacy demo ports are refused and no other process is ever touched.
"""
import argparse
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
from threading import Event, Thread
from types import MappingProxyType
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

from forge.dev_accounts import LocalFixtureError
from forge.admin_mount import AdminBuildMissing, apply_guard, mount_admin
from forge.gateway_origins import OriginPolicy
from forge.mvp_profile import MVP_PROFILE

LOOPBACK = '127.0.0.1'
MVP_PORTS = MappingProxyType({'control_plane': 3410, 'client_ui': 3411, 'client_backend': 3412, 'fake_gateway': 3413})
FORBIDDEN_PORTS = frozenset({3319, 3320, 3331, 3332})
ROLES = ('forge_account_service', 'forge_enrollment', 'forge_runtime', 'forge_gateway_service',
         'forge_branding_service')
KEYS = ('version', 'profile', 'database', 'secrets_file', 'mailbox_dir', 'admin_dir', 'require_admin_build',
        'control_plane_port', 'client_origin', 'cors_origins', 'gateway_allowed_endpoints')
ORIGIN = re.compile(r'http://127\.0\.0\.1:(\d{1,5})')


class ConfigError(Exception):
    """The message is always a finite code, never a value from a file."""


def _fail(key):
    raise ConfigError('CONFIG_INVALID:' + key)


def _port(value):
    return type(value) is int and 1 <= value <= 65535 and value not in FORBIDDEN_PORTS


def _origin(value):
    match = ORIGIN.fullmatch(value) if type(value) is str else None
    return match is not None and _port(int(match.group(1)))


def _path(value):
    return type(value) is str and Path(value).is_absolute()


@dataclass(frozen=True)
class MvpConfig:
    database: dict
    secrets_file: str
    mailbox_dir: str
    admin_dir: str
    require_admin_build: bool
    control_plane_port: int
    client_origin: str
    cors_origins: tuple
    gateway_policy: OriginPolicy

    @property
    def admin_origin(self):
        return 'http://%s:%d' % (LOOPBACK, self.control_plane_port)

    @property
    def host(self):
        return '%s:%d' % (LOOPBACK, self.control_plane_port)


def load_config(path):
    try:
        values = json.loads(Path(path).read_text('utf-8'))
    except OSError:
        raise ConfigError('CONFIG_UNREADABLE') from None
    except ValueError:
        raise ConfigError('CONFIG_INVALID') from None
    if type(values) is not dict:
        raise ConfigError('CONFIG_INVALID')
    for key in KEYS:
        if key not in values:
            _fail(key)
    if set(values) != set(KEYS):
        _fail('unknown_key')
    database = values['database']
    if (type(values['version']) is not int or values['version'] != 1 or values['profile'] != MVP_PROFILE):
        _fail('version' if type(values['version']) is not int or values['version'] != 1 else 'profile')
    if (type(database) is not dict or set(database) != {'host', 'port', 'dbname'} or database['host'] != LOOPBACK
            or type(database['port']) is not int or not 1 <= database['port'] <= 65535
            or type(database['dbname']) is not str or not database['dbname']):
        _fail('database')
    for key in ('secrets_file', 'mailbox_dir', 'admin_dir'):
        if not _path(values[key]):
            _fail(key)
    if type(values['require_admin_build']) is not bool:
        _fail('require_admin_build')
    if not _port(values['control_plane_port']):
        _fail('control_plane_port')
    client, cors = values['client_origin'], values['cors_origins']
    if not _origin(client) or client == 'http://%s:%d' % (LOOPBACK, values['control_plane_port']):
        _fail('client_origin')
    if type(cors) is not list or not cors or not all(_origin(origin) for origin in cors):
        _fail('cors_origins')
    endpoints = values['gateway_allowed_endpoints']
    try:
        if type(endpoints) is not list or any(urlsplit(e).port in FORBIDDEN_PORTS for e in endpoints):
            raise ValueError
        policy = OriginPolicy(frozenset(endpoints), dev=True)
    except (ValueError, TypeError, AttributeError):
        _fail('gateway_allowed_endpoints')
    return MvpConfig(dict(database), values['secrets_file'], values['mailbox_dir'], values['admin_dir'],
                     values['require_admin_build'], values['control_plane_port'], client, tuple(dict.fromkeys(cors)), policy)


@dataclass(frozen=True)
class MvpSecrets:
    roles: dict = field(repr=False)
    delivery_key: bytes = field(repr=False)
    gateway_key: bytes = field(repr=False)


def load_secrets(path):
    try:
        values = json.loads(Path(path).read_text('utf-8'))
    except OSError:
        raise ConfigError('SECRETS_UNREADABLE') from None
    except ValueError:
        raise ConfigError('SECRETS_INVALID') from None
    try:
        roles = values['roles']
        if (set(values) != {'roles', 'delivery_key', 'gateway_key'} or set(roles) != set(ROLES)
                or any(type(password) is not str or not password for password in roles.values())
                or values['delivery_key'] == values['gateway_key']):
            raise ValueError
        keys = [values[name].encode('ascii') for name in ('delivery_key', 'gateway_key')]
        for key in keys:
            Fernet(key)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ConfigError('SECRETS_INVALID') from None
    return MvpSecrets(dict(roles), *keys)


def role_settings(config, secrets, role):
    """Every connection parameter is explicit, so libpq environment variables never apply."""
    return dict(host=config.database['host'], port=config.database['port'], dbname=config.database['dbname'],
                user=role, password=secrets.roles[role], autocommit=True, connect_timeout=2,
                options='-c statement_timeout=5000 -c lock_timeout=2000')


def assemble(app, config, readiness):
    """Status, admin mount and the loopback guard around an already composed application."""
    from forge.composition import add_status
    add_status(app, readiness, config.admin_dir)
    try:
        mount_admin(app, config.admin_dir, required=config.require_admin_build)
    except AdminBuildMissing:
        raise ConfigError('ADMIN_BUILD_MISSING') from None
    apply_guard(app, host=config.host, origins=(config.admin_origin, *config.cors_origins), cors_origins=config.cors_origins)
    return app


def compose(config, secrets, pools):
    """Real independent restricted pools; F26 readiness must pass before anything is served."""
    from forge import composition
    from forge.invitation_delivery import LocalTestMailbox
    owned = composition.open_pools(lambda role: role_settings(config, secrets, role), pools)
    readiness = composition.attest(owned)
    mailbox = Path(config.mailbox_dir)
    if not mailbox.is_dir():
        raise ConfigError('MAILBOX_MISSING')
    app = composition.build_app(
        owned, readiness=readiness, delivery_adapter=LocalTestMailbox(mailbox, sender='forge@local.test'),
        onboarding_origin=config.client_origin, delivery_key=secrets.delivery_key, gateway_key=secrets.gateway_key,
        gateway_policy=config.gateway_policy)
    return assemble(app, config, readiness)


def reserve_loopback_port(port):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((LOOPBACK, port))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError:
        listener.close()
        raise ConfigError('PORT_OCCUPIED') from None


def serve(config_path, *, compose_fn=compose, stopping=None, announce=None):
    stopping = Event() if stopping is None else stopping
    config = load_config(config_path)
    secrets = load_secrets(config.secrets_file)
    pools, listener = [], None
    try:
        app = compose_fn(config, secrets, pools)
        listener = reserve_loopback_port(config.control_plane_port)  # last: any earlier failure bound nothing
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(app, host=LOOPBACK, port=config.control_plane_port, access_log=False,
                                               log_config=None, timeout_graceful_shutdown=10))

        def watch():
            stopping.wait()
            server.should_exit = True
        Thread(target=watch, daemon=True).start()
        if announce is not None:
            announce(config)
        server.run(sockets=[listener])
    finally:
        stopping.set()
        if listener is not None:
            listener.close()
        for pool in reversed(pools):
            pool.close(timeout=5)


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage()


def main(argv=None):
    emit = lambda document: print(json.dumps(document), flush=True)
    try:
        parser = _Parser(prog='forge.mvp_local', description='Local Forge MVP control plane; never production.')
        commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
        commands.add_parser('serve').add_argument('--config', required=True)
        supervised = commands.add_parser('up')
        supervised.add_argument('--require-admin-build', action='store_true')
        supervised.add_argument('--supervised', action='store_true')
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except _Usage:
        emit({'status': 'failed', 'code': 'INVALID_ARGUMENTS'})
        return 2
    # libpq would consult PGSERVICE/PGOPTIONS-style variables even for explicit parameters: drop them all.
    for name in [name for name in os.environ if name.startswith('PG')]:
        del os.environ[name]
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'psycopg.pool'):
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate = [logging.NullHandler()], False
    try:
        if arguments.command == 'up':
            from forge.mvp_up import up
            stopping = Event()
            if arguments.supervised:
                # The launcher closes stdin (or writes a line) to request a clean stop.
                Thread(target=lambda: (sys.stdin.readline(), stopping.set()), daemon=True).start()
            up(stopping, require_admin_build=arguments.require_admin_build)
            return 0
        serve(arguments.config, announce=lambda config: emit({
            'status': 'ready', 'control_plane_origin': config.admin_origin, 'admin_url': config.admin_origin + '/admin/',
            'client_origin': config.client_origin}))
        return 0
    except KeyboardInterrupt:
        return 0
    except (ConfigError, LocalFixtureError) as error:
        emit({'status': 'failed', 'code': str(error)})
        return 1
    except Exception:
        emit({'status': 'failed', 'code': 'MVP_LOCAL_UNAVAILABLE'})
        return 1


if __name__ == '__main__':
    # Run the canonical module, not this __main__ copy: forge.mvp_up and forge.fake_gateway
    # import forge.mvp_local, and their ConfigError must be the class main() catches.
    from forge.mvp_local import main as canonical_main
    raise SystemExit(canonical_main())
