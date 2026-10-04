"""Explicit local runtime/status composition; authentication is not enrollment."""
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from ipaddress import ip_address
import os
import re
from threading import Lock
from time import monotonic

from fastapi import Request
from fastapi.responses import Response
import psycopg
from psycopg import pq
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool
from starlette.concurrency import run_in_threadpool

from forge.api import create_app
from forge.entra import EntraConfiguration, EntraTokenValidator
from forge.postgres import PostgresBootstrapReader, PostgresReadinessProbe

STORAGE_UNAVAILABLE = "Runtime storage unavailable."
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; "
       "object-src 'none'")
HEADERS = {"Cache-Control": "no-store", "Content-Security-Policy": CSP,
           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


def _reject_pg_environment():
    # Inspect names only, never values. Do not clear/modify a process-global env.
    # Recheck at connection creation too: configuration is not a one-time waiver.
    if any(name.upper().startswith("PG") for name in os.environ):
        raise ValueError("Explicit runtime configuration requires a clean PG environment.")


@dataclass(frozen=True, repr=False)
class LocalDatabaseConfiguration:
    """Complete local-only profile; credentials are supplied, never discovered.

    Numeric loopback forbids DNS/remote routes. SSL/GSS disabled is ONLY a local
    profile, not production security. Service/passfile/cert fallback is not allowed.
    The deployment provisions the exact restricted LOGIN role separately.
    """
    host: str
    port: int
    dbname: str
    password: str = field(repr=False)

    def __post_init__(self):
        try:
            address = ip_address(self.host) if isinstance(self.host, str) else None
        except ValueError:
            address = None
        if address is None or not address.is_loopback or str(address) != self.host:
            raise ValueError("Runtime database requires a canonical numeric loopback address.")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Runtime database port is invalid.")
        if (not isinstance(self.dbname, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", self.dbname) is None):
            raise ValueError("Runtime database name is invalid.")
        if (not isinstance(self.password, str) or not self.password
                or len(self.password) > 4096
                or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
                       for c in self.password)
                or len(self.password.encode("utf-8")) > 4096):
            raise ValueError("Runtime database password is invalid.")

    def connection_kwargs(self):
        _reject_pg_environment()
        # Actual bundled client is libpq18.4, not the server17 used in proof.
        # Fail closed on older unverified clients rather than dropping controls.
        if pq.version() < 180000:
            raise ValueError("Runtime requires a supported libpq client.")
        values = dict(host=self.host, hostaddr=self.host, port=self.port,
            dbname=self.dbname, user="forge_runtime", password=self.password,
            connect_timeout=2, sslmode="disable", gssencmode="disable",
            channel_binding="disable", sslcertmode="disable",
            require_auth="scram-sha-256", target_session_attrs="read-write",
            load_balance_hosts="disable", client_encoding="UTF8",
            application_name="forge-runtime",
            options="-c row_security=on -c search_path=pg_catalog,forge "
                    "-c statement_timeout=3000 -c lock_timeout=1000",
            autocommit=True)
        try:
            # Parse supplied options only: never PQconndefaults/get_defaults().
            make_conninfo(**{k: v for k, v in values.items() if k != "autocommit"})
        except Exception:
            raise ValueError("Runtime connection controls are unsupported.") from None
        return values


@dataclass(frozen=True, repr=False)
class RuntimeConfiguration:
    entra: EntraConfiguration
    database: LocalDatabaseConfiguration

    def __post_init__(self):
        if (type(self.entra) is not EntraConfiguration
                or type(self.database) is not LocalDatabaseConfiguration):
            raise ValueError("Runtime requires typed explicit configuration.")


class _RuntimeConnection(psycopg.Connection):
    """Redact both connection failures and pool connection repr, without log mutation."""

    @classmethod
    def connect(cls, *args, **kwargs):
        try:
            _reject_pg_environment()
            return super().connect(*args, **kwargs)
        except Exception:
            # Pool worker warnings render this exception. Never send raw libpq errors.
            raise psycopg.OperationalError(STORAGE_UNAVAILABLE) from None

    def rollback(self):
        try:
            return super().rollback()
        except Exception:
            raise psycopg.OperationalError(STORAGE_UNAVAILABLE) from None

    def __repr__(self):
        return "<Forge runtime connection>"


class _Runtime:
    """App-owned pool and bounded synchronous status cache; no user context."""
    def __init__(self, configuration, pool_factory, clock):
        self.configuration = configuration
        self.pool_factory = pool_factory
        self.clock = clock
        self.pool = None
        self.reader = None
        self.probe = None
        self.state = "checking" if configuration is not None else "not_configured"
        self.next_probe = 0.0
        self.lock = Lock()

    def start(self):
        if self.configuration is None:
            return
        try:
            self.pool = self.pool_factory(
                conninfo="", kwargs=self.configuration.database.connection_kwargs(),
                connection_class=_RuntimeConnection, name="forge-runtime",
                min_size=0, max_size=2, max_waiting=4, timeout=1,
                reconnect_timeout=1, num_workers=2, open=False)
            self.reader = PostgresBootstrapReader(self.pool)
            self.probe = PostgresReadinessProbe(self.pool)
            self.pool.open(wait=True, timeout=5)
            self.storage()
        except Exception:
            self.state = "unavailable"
            self.next_probe = self.clock() + 5
            self.close()

    def close(self):
        # Called off event loop. A failed startup cannot leave a live pool behind.
        # psycopg_pool.close waits boundedly and closes outstanding borrows on return.
        if self.pool is not None:
            try:
                self.pool.close(timeout=5)
            except Exception:
                raise RuntimeError(STORAGE_UNAVAILABLE) from None
        self.reader = None
        self.probe = None

    def read(self, identity, organization_id):
        if self.reader is None:
            raise RuntimeError(STORAGE_UNAVAILABLE)
        return self.reader.read(identity, organization_id)

    def storage(self):
        if self.configuration is None:
            return "not_configured"
        if self.clock() < self.next_probe:
            return self.state
        if not self.lock.acquire(blocking=False):
            return "checking"
        try:
            if self.clock() < self.next_probe:
                return self.state
            try:
                ready = self.probe is not None and self.probe.check() is True
            except Exception:
                ready = False
            self.state = "ready" if ready else "unavailable"
            # Completion-based cooldown also follows exceptions; no failed refresh flood.
            self.next_probe = self.clock() + 5
            return self.state
        finally:
            self.lock.release()

    def status(self):
        storage = self.storage()
        return dict(schema_version="1.0",
            runtime=("unconfigured" if self.configuration is None else storage),
            configuration="missing" if self.configuration is None else "provided",
            storage=storage,
            identity_provider=("not_configured" if self.configuration is None
                               else "configured_unverified"),
            onboarding="not_implemented", user_access="not_evaluated")


def create_runtime_app(configuration: RuntimeConfiguration | None = None, *,
                       _pool_factory=ConnectionPool,
                       _validator_factory=EntraTokenValidator,
                       _clock=monotonic):
    """Programmatic trusted composition; underscored seams are for isolated proof.

    None does not inspect env, construct adapters, connect or fetch. Explicit
    deployment config is not an authentication grant and is never served publicly.
    """
    if configuration is not None and type(configuration) is not RuntimeConfiguration:
        raise ValueError("Runtime requires typed explicit configuration.")
    if configuration is not None:
        configuration.database.connection_kwargs()  # Fail closed before pool work.
    runtime = _Runtime(configuration, _pool_factory, _clock)
    validator = _validator_factory(configuration.entra) if configuration is not None else None

    @asynccontextmanager
    async def lifespan(app):
        try:
            await run_in_threadpool(runtime.start)
            yield
        finally:
            await run_in_threadpool(runtime.close)

    app = create_app(token_validator=validator,
        bootstrap_reader=runtime if configuration is not None else None,
        lifespan=lifespan)
    app.state.runtime = runtime  # Trusted internal inspection, never a public serializer.

    @app.middleware("http")
    async def public_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(HEADERS)
        return response

    @app.get("/forge/v1/status", include_in_schema=False)
    def status():
        return runtime.status()

    # Fixed package resources, not a directory mount or user-selected path.
    def resource_handler(name, mime):
        def resource():
            try:
                content = files("forge").joinpath("web", name).read_bytes()
                return Response(content, media_type=mime, headers=HEADERS)
            except Exception:
                return Response("Status resources unavailable.", status_code=503,
                                media_type="text/plain", headers=HEADERS)
        return resource

    for route, name, mime in (("/status", "status.html", "text/html"),
                              ("/status.css", "status.css", "text/css"),
                              ("/status.js", "status.js", "application/javascript")):
        app.add_api_route(route, resource_handler(name, mime), methods=["GET"],
                          include_in_schema=False)

    return app
