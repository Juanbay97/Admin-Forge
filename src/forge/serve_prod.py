"""Production control plane: ``python -m forge.serve_prod {migrate,serve,healthcheck}``.

Configured from environment variables and ``*_FILE`` secrets only (``forge.prod_config``); the
dev profile in ``forge.mvp_local`` is untouched and stays loopback-only.

* ``migrate`` is a one-shot job (``forge.migrate``); only it holds the database administrator
  credential, so the serving process never has DDL rights.
* ``serve`` opens the five restricted pools, requires the reviewed schema to be attested, then
  binds ``FORGE_BIND_HOST:FORGE_PORT`` last, so any earlier failure binds nothing. Every request
  is Host-checked against ``FORGE_PUBLIC_ORIGIN`` and logged as one JSON line.
* ``healthcheck`` exits 0 only when ``/status`` answers 200 ready (it sends the public Host).

Exactly one uvicorn worker runs, on purpose. The connection budget is sized for a single
process (two connections per service role), and the readiness cache and the rate-limit state
live in process memory; several workers would multiply the connection count and split that
state. Scaling out is unverified, so ``FORGE_WORKERS`` other than 1 is refused at load time.
"""
import http.client
import json
import logging
import os
from pathlib import Path
import socket
import sys
from threading import Event, Thread

from fastapi.responses import JSONResponse

from forge.admin_mount import AdminBuildMissing, apply_guard, mount_admin
from forge.logging_json import configure_logging, install_request_logging
from forge.migrate import main as migrate_main
from forge.mvp_local import ConfigError
from forge.prod_config import load_prod_config, strip_libpq_environment

COMMANDS = ('migrate', 'serve', 'healthcheck')
HEALTH_TIMEOUT = 3
_LOG = logging.getLogger('forge.serve')


def choose_delivery(config):
    """Production delivers by SMTP only. Without settings it fails closed: a silent local mailbox would lose invitations."""
    if config.smtp is None:
        raise ConfigError('CONFIG_INVALID:FORGE_SMTP_HOST')
    from forge.smtp_delivery import SmtpDelivery
    return SmtpDelivery(config.smtp)


def reserve_port(host, port):
    listener = socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError:
        listener.close()
        raise ConfigError('PORT_OCCUPIED') from None


def assemble_prod(app, config, readiness):
    """Health routes, admin mount, the trusted-host guard and request logging around the application."""
    from forge.composition import add_status

    @app.get('/livez', include_in_schema=False)
    def livez():
        return JSONResponse({'status': 'live'}, headers={'Cache-Control': 'no-store'})
    add_status(app, readiness, config.admin_dir)
    try:
        mount_admin(app, config.admin_dir, required=True)
    except AdminBuildMissing:
        raise ConfigError('ADMIN_BUILD_MISSING') from None
    apply_guard(app, hosts=config.trusted_hosts, origins=config.browser_origins, cors_origins=())
    install_request_logging(app)  # added last = outermost: a refused Host is logged too
    return app


def compose_prod(config, pools, *, pool_factory=None, readiness_factory=None, delivery=None):
    from forge import composition
    delivery = choose_delivery(config) if delivery is None else delivery  # before any pool: a misconfiguration binds nothing
    try:
        owned = composition.open_pools(config.role_settings, pools, pool_factory=pool_factory)
    except Exception:
        raise ConfigError('DB_UNAVAILABLE') from None  # the pools opened so far stay in ``pools`` to be closed
    readiness = composition.attest(owned, readiness_factory=readiness_factory)
    app = composition.build_app(
        owned, readiness=readiness, delivery_adapter=delivery,
        onboarding_origin=config.public_origin, delivery_key=config.delivery_key, gateway_key=config.gateway_key, platform_key=config.platform_key,
        gateway_policy=config.gateway_policy, gateway_ca_file=config.gateway_ca_file, policy_key=config.policy_key, policy_retired_keys=config.policy_retired_keys, policy_rotations=config.policy_rotations,
        connector_key=config.connector_key, connector_fixtures=config.connector_fixtures, public_origin=config.public_origin, installer_dir=config.installer_dir)
    return assemble_prod(app, config, readiness)


def serve(config, *, compose_fn=compose_prod, bind=reserve_port, stopping=None):
    stopping = Event() if stopping is None else stopping
    pools, listener = [], None
    try:
        app = compose_fn(config, pools)
        listener = bind(config.bind_host, config.port)  # last: any earlier failure bound nothing
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(app, host=config.bind_host, port=config.port, workers=1, access_log=False,
                                               log_config=None, timeout_graceful_shutdown=10))

        def watch():
            stopping.wait()
            server.should_exit = True
        Thread(target=watch, daemon=True).start()
        _LOG.info('listening', extra={'fields': {'port': config.port}})
        server.run(sockets=[listener])
    finally:
        stopping.set()
        if listener is not None:
            listener.close()
        for pool in reversed(pools):
            pool.close(timeout=5)
        _LOG.info('stopped')


def _fetch(host, port, authority, timeout):
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request('GET', '/status', headers={'Host': authority})
        response = connection.getresponse()
        return response.status, response.read(4096)
    finally:
        connection.close()


def healthcheck(config, *, fetch=_fetch):
    """True only for ``/status`` = 200 ready, asked on the bind address with the public Host header."""
    host = {'0.0.0.0': '127.0.0.1', '::': '::1'}.get(config.bind_host, config.bind_host)
    try:
        status, body = fetch(host, config.port, config.public_host, HEALTH_TIMEOUT)
        document = json.loads(body)
    except (OSError, ValueError, http.client.HTTPException):
        return False
    return status == 200 and type(document) is dict and document.get('status') == 'ready'


def main(argv=None, *, environ=None, serve_fn=serve, healthcheck_fn=healthcheck, migrate_fn=migrate_main,
         configure_fn=configure_logging):
    emit = lambda document: print(json.dumps(document), flush=True)
    arguments = list(sys.argv[1:] if argv is None else argv)
    command, rest = (arguments[0], arguments[1:]) if arguments else (None, [])
    if command not in COMMANDS or (command != 'migrate' and rest):
        emit({'status': 'failed', 'code': 'INVALID_ARGUMENTS'})
        return 2
    if environ is None:
        strip_libpq_environment(os.environ)  # libpq would consult PGSERVICE-style variables even for explicit parameters
        environ = os.environ
    if command == 'migrate':
        return migrate_fn(rest, environ=environ)
    try:
        config = load_prod_config(environ)
        if command == 'healthcheck':
            healthy = healthcheck_fn(config)
            if not healthy:
                emit({'status': 'unhealthy'})
            return 0 if healthy else 1
        configure_fn(sys.stdout, config.log_level)
        serve_fn(config)
        return 0
    except KeyboardInterrupt:
        return 0
    except ConfigError as error:
        emit({'status': 'failed', 'code': str(error)})
        return 1
    except Exception:
        emit({'status': 'failed', 'code': 'SERVE_PROD_UNAVAILABLE'})
        return 1


if __name__ == '__main__':
    # Run the canonical module, not this __main__ copy, so ConfigError is the class main() catches.
    from forge.serve_prod import main as canonical_main
    raise SystemExit(canonical_main())
