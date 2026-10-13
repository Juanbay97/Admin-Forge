"""Supervised local stack: owned PostgreSQL 17, full MVP schema, two-org seed, fake gateway, control plane.

Disposable by design: the container is tmpfs-backed and removed (ID read back) on stop, and the
private workspace holding the config, secrets and credentials is deleted with it. Ports are
prechecked before any resource exists; no other process is adopted, stopped or touched.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
from threading import Thread

from cryptography.fernet import Fernet
from psycopg import sql

from forge.dev_accounts import MIGRATIONS, ROOT, OwnedPostgres, PrivateWorkspace, validate_repository
from forge.mvp_local import ConfigError, MVP_PORTS, ROLES, reserve_loopback_port, serve
from forge.capability_signing import b64u
from forge.fake_gateway import MODELS as FAKE_MODELS
from forge.mvp_profile import MVP_ADDITIONS, MVP_PROFILE
from forge.platform_cli import bootstrap_owner, write_private_file
from forge.pool_seed import seed_gateway_pool
from forge.provisioning import MULTIUSER_SEED as MVP_SEED, provision, write_credentials

DATABASE = 'forge_dev'
OWNER_EMAIL, OWNER_NAME = 'owner@platform.test', 'Platform Owner'
INSTALLER = 'Forge-Setup-0.0.0-local.exe'


def stage_downloads(directory):
    """The local stack's installer hosting: a tiny stand-in file and the manifest a real release publishes (see forge.downloads_mount)."""
    directory = Path(directory)
    directory.mkdir()
    payload = b'MZ forge local installer stand-in\n'
    (directory/INSTALLER).write_bytes(payload)
    manifest = {'version': '0.0.0-local', 'released_at': '2026-01-01T00:00:00Z', 'platforms': {'windows': {
        'url': '/downloads/' + INSTALLER, 'sha256': hashlib.sha256(payload).hexdigest(), 'size_bytes': len(payload)}}}
    (directory/'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
ADMIN_BUILD = ROOT/'src'/'forge'/'web'/'admin'


def precheck_ports(ports):
    for port in ports:
        reserve_loopback_port(port).close()  # raises PORT_OCCUPIED; the port is released again at once


def install_schema(connection):
    """Fresh database only: the reviewed migrations, then LOGIN passwords for the five service roles."""
    if connection.execute("SELECT to_regnamespace('forge')").fetchone() != (None,):
        raise ConfigError('FRESH_DATABASE_REQUIRED')
    for name in (*MIGRATIONS, *MVP_ADDITIONS):
        connection.execute((ROOT/'migrations'/name).read_text('utf-8'))
    passwords = {role: secrets.token_urlsafe(32) for role in ROLES}
    for role, password in passwords.items():
        connection.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
    return passwords


def runtime_files(directory, *, database, passwords, delivery_key, gateway_key, platform_key, admin_dir, require_admin_build, policy_key=None, connector_key=None):
    """Write secrets.json and config.json (exclusive create) into the private workspace; return the config path."""
    directory = Path(directory)
    client = 'http://127.0.0.1:%d' % MVP_PORTS['client_ui']
    documents = (('secrets.json', {'roles': passwords, 'delivery_key': delivery_key, 'gateway_key': gateway_key,
                                  'platform_key': platform_key, **({} if policy_key is None else {'policy_key': policy_key}),
                                  **({} if connector_key is None else {'connector_key': connector_key})}),
                 ('config.json', {'version': 1, 'profile': MVP_PROFILE, 'database': database,
                                  'secrets_file': str(directory/'secrets.json'), 'mailbox_dir': str(directory/'mailbox'),
                                  'admin_dir': str(admin_dir), 'require_admin_build': require_admin_build,
                                  'control_plane_port': MVP_PORTS['control_plane'], 'client_origin': client,
                                  'cors_origins': [client],
                                  'gateway_allowed_endpoints': ['http://127.0.0.1:%d' % MVP_PORTS['fake_gateway']]}))
    for name, document in documents:
        with (directory/name).open('x', encoding='utf-8') as output:
            json.dump(document, output, indent=2)
            output.write('\n')
    return str(directory/'config.json')


def up(stopping, *, require_admin_build=False, emit=None):
    from forge.fake_gateway import FakeGatewayConfiguration, serve as serve_gateway
    emit = emit or (lambda document: print(json.dumps(document), flush=True))
    validate_repository(ROOT)
    precheck_ports((MVP_PORTS['control_plane'], MVP_PORTS['fake_gateway']))
    workspace = postgres = None
    failures = []
    try:
        workspace = PrivateWorkspace()
        emit({'status': 'starting', 'workspace': str(workspace.directory), 'pid': os.getpid()})
        postgres = OwnedPostgres(workspace.directory, (ROOT/'scripts/postgres-image.txt').read_text('ascii').strip())
        postgres.start(stopping)
        import psycopg
        credentials = workspace.directory/'credentials.json'
        gateway_secret = Fernet.generate_key()
        fake_origin = 'http://127.0.0.1:%d' % MVP_PORTS['fake_gateway']
        with psycopg.connect(**postgres.settings()) as connection:
            passwords = install_schema(connection)
            seeded = provision(connection, MVP_SEED, lambda created: write_credentials(credentials, created))
            # A company's key is the platform's: seed it the way the platform would assign it (see forge.pool_seed).
            seed_gateway_pool(connection, gateway_secret, fake_origin, seeded, FAKE_MODELS)
        (workspace.directory/'mailbox').mkdir()
        stage_downloads(workspace.directory/'downloads')
        owner_link = workspace.directory/'owner-link.txt'
        with psycopg.connect(**postgres.settings()) as connection:  # the platform owner's one-time set-password link, as the CLI issues it
            bootstrap_owner(connection, email=OWNER_EMAIL, name=OWNER_NAME, origin='http://127.0.0.1:%d' % MVP_PORTS['control_plane'],
                            ttl_seconds=3600, write_link=lambda link: write_private_file(owner_link, link))
        config_path = runtime_files(
            workspace.directory, database={'host': '127.0.0.1', 'port': postgres.port, 'dbname': DATABASE},
            passwords=passwords, delivery_key=Fernet.generate_key().decode('ascii'),
            gateway_key=gateway_secret.decode('ascii'), platform_key=Fernet.generate_key().decode('ascii'),
            policy_key=b64u(secrets.token_bytes(32)), connector_key=Fernet.generate_key().decode('ascii'), admin_dir=ADMIN_BUILD, require_admin_build=require_admin_build)

        def run_gateway():
            try:
                serve_gateway(FakeGatewayConfiguration(keys=tuple(item.gateway_key for item in seeded),
                                                       port=MVP_PORTS['fake_gateway']), stopping=stopping)
            except Exception as error:
                failures.append(error)
                stopping.set()
        gateway = Thread(target=run_gateway, daemon=True)
        gateway.start()
        try:
            serve(config_path, stopping=stopping, announce=lambda config: emit({
                'status': 'ready', 'control_plane_origin': config.admin_origin, 'admin_url': config.admin_origin + '/admin/',
                'admin_build': 'ready' if (ADMIN_BUILD/'index.html').is_file() else 'missing',
                'fake_gateway_origin': 'http://127.0.0.1:%d' % MVP_PORTS['fake_gateway'],
                'client_origin': config.client_origin, 'workspace': str(workspace.directory),
                'credentials_file': str(credentials), 'owner_link_file': str(owner_link), 'config_file': config_path, 'container_id': postgres.container_id}))
        finally:
            stopping.set()
            gateway.join(10)
        if failures:
            raise failures[0]
    finally:
        stopping.set()
        error = None
        if postgres is not None:
            try:
                postgres.close()
            except Exception:
                error = ConfigError('OWNED_CLEANUP_PENDING')  # keep the workspace for exact manual recovery
        if workspace is not None and error is None:
            workspace.close()
            emit({'status': 'stopped', 'owned_container_absent': True, 'private_workspace_absent': True})
        if error is not None:
            raise error
