"""Disposable loopback developer composition, not the enterprise/native runtime.

Every credential is generated for a fresh owned database. No ambient DSN, Docker
login, identity shortcut, SMTP delivery or production configuration is adopted.
"""
from pathlib import Path
import argparse
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from threading import Event, Thread
from time import monotonic
from uuid import uuid4

FRONTEND_ORIGIN = "http://127.0.0.1:3319"
BACKEND_ORIGIN = "http://127.0.0.1:3320"
ROOT = Path(__file__).resolve().parents[2]
DOCKER = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
DOCKER_HOST = "npipe:////./pipe/docker_engine"
OS_ENVIRONMENT = ("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH", "PATHEXT")
WORKSPACE_NAME = re.compile(r"forge-owned-accounts-[a-f0-9]{32}")
CONTAINER_ID = re.compile(r"[a-f0-9]{64}")
MIGRATIONS = (
    "0001_bootstrap.sql", "0002_entra_identity_binding.sql",
    "0003_membership_authorization.sql", "0004_initial_admin_designation.sql",
    "0013_owned_account_enrollment.sql", "0014_owned_account_sessions.sql",
)
OWNERSHIP = "forge-owned-dev-accounts-v1"


class LocalFixtureError(RuntimeError):
    """Only finite nonsecret messages may cross the launcher boundary."""


def validate_repository(root):
    try:
        resolved = Path(root).resolve(strict=True)
    except (TypeError, ValueError, OSError):
        raise LocalFixtureError("INVALID_REPOSITORY") from None
    if resolved != ROOT or not (resolved / ".venv/Scripts/python.exe").is_file():
        raise LocalFixtureError("INVALID_REPOSITORY")
    if not all((resolved / "migrations" / name).is_file() for name in MIGRATIONS):
        raise LocalFixtureError("MISSING_REVIEWED_MIGRATION")
    return resolved


def validate_frontend_origin(origin):
    if origin != FRONTEND_ORIGIN:
        raise LocalFixtureError("INVALID_FRONTEND_ORIGIN")
    return origin


def isolated_environment(source):
    """Read OS plumbing by name; never copy or inspect ambient secret values."""
    return {key: source[key] for key in OS_ENVIRONMENT if key in source}


def reserve_backend_socket():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 3320))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except OSError:
        listener.close()
        raise LocalFixtureError("BACKEND_PORT_OCCUPIED") from None


def _owned_path(directory):
    path = Path(directory)
    if (path.is_symlink() or path.is_junction()
            or path.parent.resolve() != Path(tempfile.gettempdir()).resolve()
            or not WORKSPACE_NAME.fullmatch(path.name)):
        raise LocalFixtureError("INVALID_OWNED_DIRECTORY")
    return path.resolve()


# Set and read back a protected Windows DACL before any private material exists.
# Child files inherit only the current user's and SYSTEM's FullControl entries.
_ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$path = $env:FORGE_OWNED_FIXTURE_PATH
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [System.Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($user)
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($user, $system) | Select-Object -Unique) {
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $path -AclObject $acl
$actual = Get-Acl -LiteralPath $path
if (-not $actual.AreAccessRulesProtected) { throw 'Unprotected ACL' }
if ($actual.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $user.Value) { throw 'Wrong owner' }
$rules = @($actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
$allowed = @($user.Value, $system.Value) | Select-Object -Unique
if ($rules.Count -ne $allowed.Count) { throw 'Unexpected ACL entries' }
foreach ($rule in $rules) {
    if ($rule.IsInherited -or $rule.IdentityReference.Value -notin $allowed -or
        $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl' -or
        $rule.InheritanceFlags -ne 'ContainerInherit,ObjectInherit') { throw 'Unexpected ACL rule' }
}
"""


class PrivateWorkspace:
    def __init__(self, directory=None):
        if os.name != "nt":
            raise LocalFixtureError("WINDOWS_PRIVATE_ACL_REQUIRED")
        self.directory = _owned_path(directory or
            Path(tempfile.gettempdir()) / ("forge-owned-accounts-" + uuid4().hex))
        self.acl_verified = False
        self.directory.mkdir(exist_ok=False)
        try:
            environment = isolated_environment(os.environ)
            environment["FORGE_OWNED_FIXTURE_PATH"] = str(self.directory)
            powershell = Path(environment["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            result = subprocess.run(
                [str(powershell), "-NoProfile", "-NonInteractive", "-Command", _ACL_SCRIPT],
                env=environment, capture_output=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                raise LocalFixtureError("PRIVATE_ACL_VERIFICATION_FAILED")
            self.acl_verified = True
            self.write_json("ownership.json", {
                "kind": OWNERSHIP, "pid": os.getpid(), "repository": str(ROOT),
                "directory": str(self.directory),
            })
        except Exception:
            self.close()
            raise

    def write_json(self, name, document):
        if not self.acl_verified or name not in ("ownership.json", "context.json", "admin-credentials.json"):
            raise LocalFixtureError("PRIVATE_WRITE_NOT_AUTHORIZED")
        with (self.directory / name).open("x", encoding="utf-8") as output:
            json.dump(document, output, indent=2)
            output.write("\n")

    def close(self):
        if _owned_path(self.directory) != self.directory:
            raise LocalFixtureError("OWNED_DIRECTORY_CHANGED")
        if self.directory.exists():
            # Never follow a substituted descendant junction during recursive cleanup.
            for child in self.directory.rglob("*"):
                if child.is_symlink() or child.is_junction():
                    raise LocalFixtureError("OWNED_DIRECTORY_CHANGED")
            shutil.rmtree(self.directory)


class OwnedPostgres:
    def __init__(self, directory, image):
        if not re.fullmatch(r"postgres@sha256:[a-f0-9]{64}", image):
            raise LocalFixtureError("INVALID_PINNED_IMAGE")
        self.directory, self.image = Path(directory), image
        self.container_id = None
        self.container_name = None
        self.port = None
        self.password = secrets.token_urlsafe(32)
        self.environment = isolated_environment(os.environ)
        self.config = self.directory / "docker-config"

    def docker(self, *arguments, environment=None):
        return subprocess.run(
            [str(DOCKER), "--config", str(self.config), "--host", DOCKER_HOST, *arguments],
            env=environment or self.environment, capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def start(self, stopping):
        if not DOCKER.is_file():
            raise LocalFixtureError("LOCAL_DOCKER_UNAVAILABLE")
        self.config.mkdir()
        (self.config / "config.json").write_text("{}\n", encoding="utf-8")
        if self.docker("image", "inspect", self.image, "--format", "{{.Id}}").returncode:
            raise LocalFixtureError("CACHED_PINNED_IMAGE_REQUIRED")
        if stopping.is_set():
            raise LocalFixtureError("STOP_REQUESTED")
        environment = dict(self.environment, POSTGRES_PASSWORD=self.password)
        self.container_name = "forge-dev-accounts-" + uuid4().hex
        created = self.docker(
            "create", "--pull=never", "--name", self.container_name,
            "--publish", "127.0.0.1::5432", "--env", "POSTGRES_PASSWORD",
            "--env", "POSTGRES_DB=forge_dev", "--tmpfs", "/var/lib/postgresql/data:rw",
            self.image, environment=environment,
        )
        identifier = created.stdout.strip()
        if created.returncode or not CONTAINER_ID.fullmatch(identifier):
            raise LocalFixtureError("OWNED_DATABASE_CREATE_FAILED")
        self.container_id = identifier
        if self.docker("start", identifier).returncode:
            raise LocalFixtureError("OWNED_DATABASE_START_FAILED")
        inspected = self.docker("inspect", identifier, "--format", "{{json .}}")
        if inspected.returncode:
            raise LocalFixtureError("OWNED_DATABASE_INSPECTION_FAILED")
        document = json.loads(inspected.stdout)
        ports = document["NetworkSettings"]["Ports"]["5432/tcp"]
        if (document["Mounts"] or document["HostConfig"]["Tmpfs"] != {"/var/lib/postgresql/data": "rw"}
                or len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1"):
            raise LocalFixtureError("OWNED_DATABASE_ISOLATION_FAILED")
        self.port = int(ports[0]["HostPort"])
        import psycopg
        deadline = monotonic() + 30
        while monotonic() < deadline and not stopping.is_set():
            try:
                with psycopg.connect(**self.settings()) as connection:
                    if connection.execute("SHOW server_version_num").fetchone()[0][:2] != "17":
                        raise LocalFixtureError("POSTGRESQL_17_REQUIRED")
                return
            except psycopg.OperationalError:
                stopping.wait(.25)
        raise LocalFixtureError("OWNED_DATABASE_NOT_READY")

    def settings(self):
        return dict(host="127.0.0.1", port=self.port, dbname="forge_dev", user="postgres",
            password=self.password, autocommit=True, connect_timeout=2,
            options="-c statement_timeout=5000 -c lock_timeout=2000")

    def close(self):
        if self.container_id is None:
            if self.container_name is None:
                return
            if not re.fullmatch(r"forge-dev-accounts-[a-f0-9]{32}", self.container_name):
                raise LocalFixtureError("INVALID_OWNED_CONTAINER_NAME")
            recovered = self.docker("inspect", self.container_name, "--format", "{{.Id}}")
            if recovered.returncode == 1 and "No such object" in recovered.stderr:
                self.container_name = None
                return
            identifier = recovered.stdout.strip()
            if recovered.returncode or not CONTAINER_ID.fullmatch(identifier):
                raise LocalFixtureError("OWNED_DATABASE_CLEANUP_UNCONFIRMED")
            self.container_id = identifier
        identifier = self.container_id
        if not CONTAINER_ID.fullmatch(identifier):
            raise LocalFixtureError("INVALID_OWNED_CONTAINER_ID")
        removed = self.docker("rm", "--force", "--volumes", identifier)
        absent = self.docker("inspect", identifier)
        if removed.returncode or absent.returncode != 1 or "No such object" not in absent.stderr:
            raise LocalFixtureError("OWNED_DATABASE_CLEANUP_UNCONFIRMED")
        self.container_id = None
        self.container_name = None


def stop_session(directory):
    path = _owned_path(directory)
    try:
        marker = json.loads((path / "ownership.json").read_text("utf-8"))
    except (ValueError, OSError):
        raise LocalFixtureError("INVALID_OWNED_SESSION") from None
    if (marker.get("kind") != OWNERSHIP or marker.get("directory") != str(path)
            or marker.get("repository") != str(ROOT) or type(marker.get("pid")) is not int):
        raise LocalFixtureError("INVALID_OWNED_SESSION")
    (path / "stop.request").touch(exist_ok=True)
    deadline = monotonic() + 40
    while path.exists() and monotonic() < deadline:
        Event().wait(.1)
    if path.exists():
        raise LocalFixtureError("OWNED_SESSION_STOP_PENDING")


def install_and_seed(postgres, workspace, stopping):
    """Trusted installer only against this fresh disposable owned database."""
    import psycopg
    from psycopg import sql
    from forge.accounts import ACCOUNT_ISSUER, PasswordHasher
    credentials = {role: secrets.token_urlsafe(32) for role in
        ("forge_account_service", "forge_enrollment", "forge_runtime")}
    admin_password = secrets.token_urlsafe(32)
    encoded = PasswordHasher().hash(admin_password)
    account, organization, membership, department = (uuid4() for _ in range(4))
    with psycopg.connect(**postgres.settings()) as connection:
        if connection.execute("SELECT to_regnamespace('forge')").fetchone() != (None,):
            raise LocalFixtureError("FRESH_DATABASE_REQUIRED")
        for name in MIGRATIONS:
            if stopping.is_set():
                raise LocalFixtureError("STOP_REQUESTED")
            connection.execute((ROOT / "migrations" / name).read_text("utf-8"))
        for role, password in credentials.items():
            connection.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)))
        with connection.transaction():
            connection.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'forge',%s,%s)",
                (account, ACCOUNT_ISSUER, str(account)))
            connection.execute("INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) VALUES(%s,%s,%s,%s)",
                (account, "admin@forge.local.test", "Local fixture administrator", encoded))
            connection.execute("INSERT INTO forge.organizations VALUES(%s,%s,%s,true,1)",
                (organization, "forge-local-fixture", "Forge local fixture (disposable)"))
            connection.execute("INSERT INTO forge.configuration_revisions VALUES(%s,1)", (organization,))
            connection.execute("INSERT INTO forge.memberships(organization_id,id,identity_id,status) VALUES(%s,%s,%s,'active')",
                (organization, membership, account))
            connection.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')", (organization, membership))
            connection.execute("INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)",
                (organization, department, "Local fixture area"))
            connection.execute("INSERT INTO forge.membership_departments VALUES(%s,%s,%s)", (organization, membership, department))
    workspace.write_json("admin-credentials.json", {"email": "admin@forge.local.test", "password": admin_password})
    workspace.write_json("context.json", {
        "disposable_local_fixture": True, "enterprise_profile_configured": False,
        "backend_origin": BACKEND_ORIGIN, "frontend_origin": FRONTEND_ORIGIN,
        "organization_id": str(organization), "organization_name": "Forge local fixture (disposable)",
        "department_id": str(department), "department_name": "Local fixture area",
        "delivery_channel": "local_test_mailbox", "schema_profile": "0001-0004+0013-0014/PG17",
    })
    return credentials


def compose(postgres, workspace, credentials, pools, *, delivery_key=None, reuse_mailbox=False):
    """Real independent restricted pools; readiness must pass before dispatch."""
    from psycopg_pool import ConnectionPool
    from cryptography.fernet import Fernet
    from starlette.middleware.cors import CORSMiddleware
    from forge.account_api import create_account_app
    from forge.account_readiness import AccountReadiness
    from forge.account_sessions import SessionService, PostgresSessionStore
    from forge.account_store import PostgresEnrollmentStore
    from forge.invitations import InvitationService
    from forge.invitation_store import PostgresInvitationStore
    from forge.invitation_delivery import DeliveryCoordinator, PostgresDeliveryStore, LocalTestMailbox
    from forge.postgres import PostgresBootstrapReader
    from forge.authorization_store import PostgresAuthorizationReader
    for role in ("forge_account_service", "forge_enrollment", "forge_runtime"):
        settings = dict(postgres.settings(), user=role, password=credentials[role])
        pool = ConnectionPool(conninfo="", kwargs=settings, min_size=1, max_size=2,
            timeout=1, max_waiting=4, reconnect_timeout=1, open=False)
        pools.append(pool)
        pool.open(wait=True, timeout=5)
    account_pool, enrollment_pool, bootstrap_pool = pools
    readiness = AccountReadiness(account_pool, bootstrap_pool)
    if not readiness.check():
        raise LocalFixtureError("ACCOUNT_SCHEMA_ATTESTATION_FAILED")
    mailbox = workspace.directory / "mailbox"
    mailbox.mkdir(exist_ok=reuse_mailbox)
    app = create_account_app(
        sessions=SessionService(PostgresSessionStore(account_pool)),
        invitations=InvitationService(PostgresInvitationStore(enrollment_pool), PostgresEnrollmentStore(enrollment_pool)),
        delivery=DeliveryCoordinator(PostgresDeliveryStore(account_pool),
            LocalTestMailbox(mailbox, sender="forge@local.test"), origin=FRONTEND_ORIGIN,
            encryption_key=Fernet.generate_key() if delivery_key is None else delivery_key),
        bootstrap_reader=PostgresBootstrapReader(bootstrap_pool),
        authorization_reader=PostgresAuthorizationReader(bootstrap_pool), readiness=readiness,
    )
    app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_ORIGIN],
        allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False)
    return app


def _emit(document):
    print(json.dumps(document), flush=True)


def run_fixture(root, origin, stopping):
    validate_repository(root)
    validate_frontend_origin(origin)
    listener = reserve_backend_socket()  # Occupied port means no fixture is created.
    workspace = postgres = None
    pools = []
    try:
        workspace = PrivateWorkspace()
        _emit({"status": "starting", "session_directory": str(workspace.directory), "pid": os.getpid()})
        image = (ROOT / "scripts/postgres-image.txt").read_text("ascii").strip()
        postgres = OwnedPostgres(workspace.directory, image)
        postgres.start(stopping)
        credentials = install_and_seed(postgres, workspace, stopping)
        app = compose(postgres, workspace, credentials, pools)
        if stopping.is_set():
            raise LocalFixtureError("STOP_REQUESTED")
        import uvicorn
        config = uvicorn.Config(app, host="127.0.0.1", port=3320, access_log=False,
            log_config=None, timeout_graceful_shutdown=10)
        server = uvicorn.Server(config)
        identifier = postgres.container_id
        def observe_stop():
            while not stopping.wait(.1):
                if (workspace.directory / "stop.request").exists():
                    stopping.set()
            server.should_exit = True
        Thread(target=observe_stop, daemon=True).start()
        _emit({"status": "ready", "backend_origin": BACKEND_ORIGIN, "frontend_origin": FRONTEND_ORIGIN,
            "session_directory": str(workspace.directory), "context_file": str(workspace.directory / "context.json"),
            "credentials_file": str(workspace.directory / "admin-credentials.json"),
            "mailbox_directory": str(workspace.directory / "mailbox"), "container_id": identifier, "pid": os.getpid(),
            "disposable_local_fixture": True, "enterprise_profile_configured": False})
        server.run(sockets=[listener])
    finally:
        stopping.set()
        listener.close()
        cleanup_errors = []
        for pool in reversed(pools):
            try:
                pool.close(timeout=5)
            except Exception:
                cleanup_errors.append("POOL_CLEANUP_FAILED")
        if postgres is not None:
            try:
                postgres.close()
            except Exception:
                cleanup_errors.append("OWNED_DATABASE_CLEANUP_UNCONFIRMED")
        if workspace is not None and not cleanup_errors:
            workspace.close()
            _emit({"status": "stopped", "owned_container_absent": True, "private_workspace_absent": True})
        if cleanup_errors:
            # Keep the private ownership marker for precise manual recovery.
            raise LocalFixtureError("OWNED_CLEANUP_PENDING")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Disposable local Forge accounts; never production.")
    parser.add_argument("--repository", default=str(ROOT))
    parser.add_argument("--frontend-origin", default=FRONTEND_ORIGIN)
    parser.add_argument("--supervised", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--session-directory")
    args = parser.parse_args(argv)
    # Libpq must not consult ambient service/credential values in this process.
    if any(key.startswith("PG") for key in os.environ):
        _emit({"status": "failed", "code": "ISOLATED_CHILD_ENVIRONMENT_REQUIRED"})
        return 1
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "psycopg.pool"):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
    stopping = Event()
    if args.supervised:
        def supervise():
            sys.stdin.readline()  # Stop line or parent pipe EOF, including early startup.
            stopping.set()
        Thread(target=supervise, daemon=True).start()
    try:
        if args.stop:
            if not args.session_directory:
                raise LocalFixtureError("OWNED_SESSION_REQUIRED")
            validate_repository(args.repository)
            stop_session(args.session_directory)
        else:
            if args.session_directory:
                raise LocalFixtureError("EXISTING_SESSION_ADOPTION_FORBIDDEN")
            run_fixture(args.repository, args.frontend_origin, stopping)
        return 0
    except KeyboardInterrupt:
        return 0
    except LocalFixtureError as error:
        _emit({"status": "failed", "code": str(error)})
        return 0 if str(error) == "STOP_REQUESTED" else 1
    except Exception:
        _emit({"status": "failed", "code": "LOCAL_FIXTURE_FAILED"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
