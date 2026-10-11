"""Explicit retained local demo. Never adopt ephemeral, remote or production data.

Create is fresh-only; resume is exact owned state only. Stop retains the container,
volume and private directory. No delete or reset exists. Gateway upgrade is explicit and stopped-owner only.
"""
from pathlib import Path
import argparse
import ctypes
import hashlib
import json
import logging
import msvcrt
import os
import re
import secrets
import subprocess
import sys
from threading import Event, Thread
from time import monotonic
from uuid import UUID, uuid4
from forge.dev_accounts import (
    ROOT, FRONTEND_ORIGIN, BACKEND_ORIGIN, MIGRATIONS, WORKSPACE_NAME,
    CONTAINER_ID, LocalFixtureError, OwnedPostgres, _ACL_SCRIPT, _emit,
    isolated_environment, reserve_backend_socket, validate_repository,
    install_and_seed, compose,
)

KIND = "forge-owned-durable-accounts-v1"
ROLES = ("forge_account_service", "forge_enrollment", "forge_runtime")
CAPABILITY = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def demos_root():
    if os.name != "nt":
        raise LocalFixtureError("WINDOWS_PRIVATE_ACL_REQUIRED")
    buffer = ctypes.create_unicode_buffer(32768)
    # Windows known LocalAppData folder: no ambient credentials or env fallback.
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer):
        raise LocalFixtureError("LOCAL_APPLICATION_DATA_UNAVAILABLE")
    # Explicit approved packaged-app data, also addressable outside Codex.
    # Retained across reboot, not promised across application uninstall.
    return (Path(buffer.value) / "Packages/OpenAI.Codex_2p2nqsd0c76g0"
        / "LocalCache/Local/PrometheonForge/demos").resolve()


DEMOS_ROOT = demos_root()


def validate_demo_directory(directory):
    path = Path(directory)
    if (not path.is_absolute() or not WORKSPACE_NAME.fullmatch(path.name)
            or path.parent != DEMOS_ROOT or path.is_symlink() or path.is_junction()):
        raise LocalFixtureError("INVALID_DURABLE_DIRECTORY")
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise LocalFixtureError("INVALID_DURABLE_DIRECTORY")
    if path.resolve() != path:
        raise LocalFixtureError("INVALID_DURABLE_DIRECTORY")
    return path


def validate_mount(document, volume):
    mounts = document.get("Mounts", [])
    if (len(mounts) != 1 or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != volume
            or mounts[0].get("Destination") != "/var/lib/postgresql/data"
            or mounts[0].get("RW") is not True
            or document.get("HostConfig", {}).get("Tmpfs")):
        raise LocalFixtureError("DURABLE_DATABASE_MOUNT_MISMATCH")


_ACL_VERIFY = """
$ErrorActionPreference = 'Stop'
$path = $env:FORGE_OWNED_FIXTURE_PATH
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$allowed = @($user.Value, $system.Value) | Select-Object -Unique
$root = Get-Acl -LiteralPath $path
if (-not $root.AreAccessRulesProtected) { throw 'Unprotected ACL' }
foreach ($target in @($path) + @(Get-ChildItem -LiteralPath $path -Recurse -Force | ForEach-Object FullName)) {
    $acl = Get-Acl -LiteralPath $target
    if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -ne $user.Value) { throw 'Wrong owner' }
    $rules = @($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne $allowed.Count) { throw 'Unexpected ACL entries' }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin $allowed -or
            $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl') { throw 'Unexpected ACL rule' }
    }
}
"""


def private_acl(path, *, create=False):
    if any(child.is_symlink() or child.is_junction() for child in path.rglob("*")):
        raise LocalFixtureError("DURABLE_DIRECTORY_CHANGED")
    environment = isolated_environment(os.environ)
    environment["FORGE_OWNED_FIXTURE_PATH"] = str(path)
    shell = Path(environment["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command",
        _ACL_SCRIPT if create else _ACL_VERIFY], env=environment, capture_output=True,
        timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise LocalFixtureError("PRIVATE_ACL_VERIFICATION_FAILED")


class DurableWorkspace:
    def __init__(self, directory, *, create=False):
        self.directory = validate_demo_directory(directory)
        if create:
            DEMOS_ROOT.mkdir(parents=True, exist_ok=True)
            self.directory.mkdir(exist_ok=False)
        elif not self.directory.is_dir():
            raise LocalFixtureError("DURABLE_DIRECTORY_MISSING")
        private_acl(self.directory, create=create)
        self.lock = None

    def acquire(self):
        handle = (self.directory / "instance.lock").open("a+b")
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            raise LocalFixtureError("DURABLE_INSTANCE_BUSY") from None
        self.lock = handle

    def close(self):
        if self.lock:
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            self.lock.close()
            self.lock = None

    def read(self, name):
        path = self.directory / name
        if path.is_symlink() or path.is_junction() or path.stat().st_size > 65536:
            raise LocalFixtureError("INVALID_PRIVATE_STATE")
        value = json.loads(path.read_text("utf-8"))
        if not isinstance(value, dict):
            raise LocalFixtureError("INVALID_PRIVATE_STATE")
        return value

    def save(self, name, document):
        if name not in {"ownership.json", "runtime-secrets.json", "run.json", "stop.request.json", "context.json", "gateway-secrets.json", "gateway-upgrade.json"}:
            raise LocalFixtureError("PRIVATE_WRITE_NOT_AUTHORIZED")
        target = self.directory / name
        temporary = self.directory / (".write-" + uuid4().hex)
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(document, output, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_json(self, name, document):
        # Used by the unchanged fresh seed helper; never called during resume.
        if name not in {"context.json", "admin-credentials.json"}:
            raise LocalFixtureError("PRIVATE_WRITE_NOT_AUTHORIZED")
        with (self.directory / name).open("x", encoding="utf-8") as output:
            json.dump(document, output, indent=2)
            output.write("\n")


def migration_hashes():
    return {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest()
        for name in MIGRATIONS}


def validated_state(workspace, *, ready=True):
    state = workspace.read("ownership.json")
    expected = {"version", "kind", "instance_id", "directory", "repository", "image",
        "migration_hashes", "container_name", "container_id", "volume_name", "phase"}
    if set(state) != expected:
        raise LocalFixtureError("INVALID_DURABLE_OWNERSHIP")
    try:
        identifier = UUID(state["instance_id"]).hex
    except (ValueError, TypeError, AttributeError):
        raise LocalFixtureError("INVALID_DURABLE_OWNERSHIP") from None
    image = (ROOT / "scripts/postgres-image.txt").read_text("ascii").strip()
    expected_hashes = migration_hashes()
    if state["migration_hashes"] != expected_hashes:
        from forge.dev_accounts_gateway import gateway_hashes,gateway_hashes_v1
        expected_hashes = gateway_hashes_v1() if state["migration_hashes"] == gateway_hashes_v1() else gateway_hashes()
    if (state["version"] != 1 or state["kind"] != KIND
            or state["directory"] != str(workspace.directory)
            or state["repository"] != str(ROOT)
            or workspace.directory.name != "forge-owned-accounts-" + identifier
            or state["container_name"] != "forge-durable-accounts-" + identifier
            or state["volume_name"] != "forge-durable-accounts-data-" + identifier
            or state["image"] != image or state["migration_hashes"] != expected_hashes
            or not re.fullmatch(r"postgres@sha256:[a-f0-9]{64}", image)):
        raise LocalFixtureError("INVALID_DURABLE_OWNERSHIP")
    if ready and (state["phase"] != "ready" or not CONTAINER_ID.fullmatch(state["container_id"] or "")):
        raise LocalFixtureError("DURABLE_INITIALIZATION_INCOMPLETE")
    return state


def validated_secrets(workspace):
    from cryptography.fernet import Fernet
    secret = workspace.read("runtime-secrets.json")
    if (set(secret) != {"postgres_password", "roles", "delivery_key"}
            or not isinstance(secret["roles"], dict) or set(secret["roles"]) != set(ROLES)
            or any(not isinstance(value, str) or not CAPABILITY.fullmatch(value)
                for value in [secret["postgres_password"], *secret["roles"].values()])):
        raise LocalFixtureError("INVALID_PRIVATE_STATE")
    try:
        Fernet(secret["delivery_key"].encode("ascii"))
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise LocalFixtureError("INVALID_PRIVATE_STATE") from None
    return secret


class RetainedPostgres(OwnedPostgres):
    def __init__(self, workspace, state, password):
        super().__init__(workspace.directory, state["image"])
        self.workspace, self.state = workspace, state
        self.password = password
        self.container_name = state["container_name"]
        self.container_id = state["container_id"]
        self.volume = state["volume_name"]
        self.labels = {"org.prometheon.forge.demo.kind": KIND,
            "org.prometheon.forge.demo.instance": state["instance_id"],
            "org.prometheon.forge.demo.repository": str(ROOT)}

    def inspect(self, kind, identifier):
        result = self.docker(kind, "inspect", identifier, "--format", "{{json .}}")
        if result.returncode:
            raise LocalFixtureError("DURABLE_RESOURCE_MISSING")
        return json.loads(result.stdout)

    def verify(self):
        volume = self.inspect("volume", self.volume)
        if (volume.get("Name") != self.volume or volume.get("Labels") != self.labels
                or volume.get("Driver") != "local" or volume.get("Options") not in (None, {})):
            raise LocalFixtureError("DURABLE_VOLUME_OWNERSHIP_MISMATCH")
        document = self.inspect("container", self.container_id)
        config, host = document["Config"], document["HostConfig"]
        if (document["Id"] != self.container_id or document["Name"] != "/" + self.container_name
                or config.get("Labels") != self.labels or config.get("Image") != self.image
                or host.get("Privileged") or host.get("Binds")
                or host.get("RestartPolicy", {}).get("Name") != "no"):
            raise LocalFixtureError("DURABLE_CONTAINER_OWNERSHIP_MISMATCH")
        bindings = host.get("PortBindings", {}).get("5432/tcp", [])
        if len(bindings) != 1 or bindings[0].get("HostIp") != "127.0.0.1":
            raise LocalFixtureError("DURABLE_DATABASE_ISOLATION_FAILED")
        validate_mount(document, self.volume)
        cached = self.docker("image", "inspect", self.image, "--format", "{{.Id}}")
        if cached.returncode or document.get("Image") != cached.stdout.strip():
            raise LocalFixtureError("CACHED_PINNED_IMAGE_REQUIRED")
        return document

    def create(self):
        self.config.mkdir(exist_ok=False)
        (self.config / "config.json").write_text("{}\n", encoding="utf-8")
        if self.docker("image", "inspect", self.image).returncode:
            raise LocalFixtureError("CACHED_PINNED_IMAGE_REQUIRED")
        for kind, name in (("volume", self.volume), ("container", self.container_name)):
            result = self.docker(kind, "inspect", name)
            if result.returncode != 1 or "no such" not in result.stderr.lower():
                raise LocalFixtureError("FRESH_DURABLE_RESOURCE_REQUIRED")
        labels = [argument for key, value in self.labels.items() for argument in ("--label", key + "=" + value)]
        volume = self.docker("volume", "create", *labels, self.volume)
        if volume.returncode or volume.stdout.strip() != self.volume:
            raise LocalFixtureError("DURABLE_VOLUME_CREATE_FAILED")
        environment = dict(self.environment, POSTGRES_PASSWORD=self.password)
        created = self.docker("create", "--pull=never", "--name", self.container_name,
            *labels, "--restart=no", "--publish", "127.0.0.1::5432", "--env", "POSTGRES_PASSWORD",
            "--env", "POSTGRES_DB=forge_dev", "--mount",
            "type=volume,source=" + self.volume + ",target=/var/lib/postgresql/data", self.image,
            environment=environment)
        identifier = created.stdout.strip()
        if created.returncode or not CONTAINER_ID.fullmatch(identifier):
            raise LocalFixtureError("DURABLE_DATABASE_CREATE_FAILED")
        self.container_id = identifier
        self.state["container_id"] = identifier
        self.workspace.save("ownership.json", self.state)
        self.verify()

    def start(self, stopping):
        if (self.config / "config.json").read_text("utf-8") != "{}\n":
            raise LocalFixtureError("INVALID_OWNED_DOCKER_CONFIG")
        self.verify()
        if self.docker("start", self.container_id).returncode:
            raise LocalFixtureError("DURABLE_DATABASE_START_FAILED")
        document = self.verify()
        ports = document["NetworkSettings"]["Ports"].get("5432/tcp") or []
        if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
            raise LocalFixtureError("DURABLE_DATABASE_ISOLATION_FAILED")
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
        raise LocalFixtureError("DURABLE_DATABASE_NOT_READY")

    def close(self):
        if self.container_id is None:
            return
        self.verify()  # Never stop an ID whose labels/mount/image have drifted.
        stopped = self.docker("stop", "--time", "10", self.container_id)
        if stopped.returncode or self.verify()["State"]["Running"]:
            raise LocalFixtureError("DURABLE_STOP_UNCONFIRMED")


def stop_demo(directory):
    workspace = DurableWorkspace(directory)
    state = validated_state(workspace)
    secret = validated_secrets(workspace)
    database = RetainedPostgres(workspace, state, secret["postgres_password"])
    database.verify()
    try:
        workspace.acquire()
    except LocalFixtureError as error:
        if str(error) != "DURABLE_INSTANCE_BUSY":
            raise
        running = workspace.read("run.json")
        workspace.save("stop.request.json", {"run_id": running["run_id"]})
        deadline = monotonic() + 40
        while monotonic() < deadline:
            current = workspace.read("run.json")
            if current.get("run_id") == running["run_id"] and current.get("status") == "stopped":
                _emit({"status": "stopped", "data_retained": True, "demo_directory": str(workspace.directory)})
                return
            Event().wait(.1)
        raise LocalFixtureError("DURABLE_STOP_PENDING")
    else:
        try:
            database.close()  # Owned container after crash/reboot; no PID adoption.
            _emit({"status": "stopped", "data_retained": True, "demo_directory": str(workspace.directory)})
        finally:
            workspace.close()


def run_demo(directory, *, create, stopping):
    validate_repository(ROOT)
    listener = reserve_backend_socket()  # No resources created if3320 is occupied.
    workspace = database = None
    pools = []
    run_id = uuid4().hex
    try:
        workspace = DurableWorkspace(directory, create=create)
        workspace.acquire()
        if create:
            instance = UUID(workspace.directory.name.removeprefix("forge-owned-accounts-"))
            image = (ROOT / "scripts/postgres-image.txt").read_text("ascii").strip()
            state = {"version": 1, "kind": KIND, "instance_id": str(instance),
                "directory": str(workspace.directory), "repository": str(ROOT), "image": image,
                "migration_hashes": migration_hashes(), "phase": "initializing",
                "container_name": "forge-durable-accounts-" + instance.hex, "container_id": None,
                "volume_name": "forge-durable-accounts-data-" + instance.hex}
            workspace.save("ownership.json", state)
            from cryptography.fernet import Fernet
            secret = {"postgres_password": secrets.token_urlsafe(32), "roles": {},
                "delivery_key": Fernet.generate_key().decode("ascii")}
            workspace.save("runtime-secrets.json", secret)
        else:
            state, secret = validated_state(workspace), validated_secrets(workspace)
            from forge.dev_accounts_gateway import admit_resume
            admit_resume(workspace,state)
        workspace.save("run.json", {"run_id": run_id, "status": "starting"})
        _emit({"status": "starting", "demo_directory": str(workspace.directory), "pid": os.getpid()})
        database = RetainedPostgres(workspace, state, secret["postgres_password"])
        if create:
            database.create()
        database.start(stopping)
        if create:
            secret["roles"] = install_and_seed(database, workspace, stopping)
            workspace.save("runtime-secrets.json", secret)
            context = workspace.read("context.json")
            context["persistent_local_demo"] = True
            workspace.save("context.json", context)
        from forge.dev_accounts_gateway import is_gateway_state,compose_gateway
        if not create and is_gateway_state(state):
            app = compose_gateway(database,workspace,secret,pools)
        else:
            app = compose(database, workspace, secret["roles"], pools,
                delivery_key=secret["delivery_key"].encode("ascii"), reuse_mailbox=not create)
        if create:
            state["phase"] = "ready"
            workspace.save("ownership.json", state)
        if stopping.is_set():
            raise LocalFixtureError("STOP_REQUESTED")
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=3320,
            access_log=False, log_config=None, timeout_graceful_shutdown=10))
        def observe_stop():
            while not stopping.wait(.1):
                signal = workspace.directory / "stop.request.json"
                if signal.exists() and workspace.read("stop.request.json").get("run_id") == run_id:
                    stopping.set()
            server.should_exit = True
        Thread(target=observe_stop, daemon=True).start()
        workspace.save("run.json", {"run_id": run_id, "status": "ready"})
        _emit({"status": "ready", "backend_origin": BACKEND_ORIGIN, "frontend_origin": FRONTEND_ORIGIN,
            "demo_directory": str(workspace.directory), "context_file": str(workspace.directory / "context.json"),
            "credentials_file": str(workspace.directory / "admin-credentials.json"),
            "mailbox_directory": str(workspace.directory / "mailbox"), "container_id": database.container_id,
            "volume_name": database.volume, "persistent_local_demo": True,
            "disposable_local_fixture": True, "enterprise_profile_configured": False, "pid": os.getpid()})
        server.run(sockets=[listener])
    finally:
        stopping.set()
        listener.close()
        error = False
        for pool in reversed(pools):
            try:
                pool.close(timeout=5)
            except Exception:
                error = True
        if database:
            try:
                database.close()
            except Exception:
                error = True
        if workspace and workspace.lock:
            try:
                workspace.save("run.json", {"run_id": run_id, "status": "stop_pending" if error else "stopped"})
            finally:
                workspace.close()
            _emit({"status": "stop_pending" if error else "stopped", "data_retained": True,
                "demo_directory": str(workspace.directory)})
        if error:
            raise LocalFixtureError("DURABLE_STOP_PENDING")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retained local Forge demo, never production")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--stop", action="store_true")
    mode.add_argument("--upgrade-gateway", action="store_true")
    parser.add_argument("--demo-directory")
    parser.add_argument("--supervised", action="store_true")
    args = parser.parse_args(argv)
    stopping = Event()
    if any(name.startswith("PG") for name in os.environ):
        _emit({"status": "failed", "code": "ISOLATED_CHILD_ENVIRONMENT_REQUIRED"})
        return 1
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "psycopg.pool"):
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate = [logging.NullHandler()], False
    if args.supervised and not args.upgrade_gateway:
        def supervise():
            sys.stdin.readline()
            stopping.set()
        Thread(target=supervise, daemon=True).start()
    try:
        if args.create:
            if args.demo_directory:
                raise LocalFixtureError("FRESH_DURABLE_DIRECTORY_REQUIRED")
            directory = DEMOS_ROOT / ("forge-owned-accounts-" + uuid4().hex)
        else:
            if not args.demo_directory:
                raise LocalFixtureError("EXPLICIT_DURABLE_DIRECTORY_REQUIRED")
            directory = args.demo_directory
        if args.stop:
            stop_demo(directory)
        elif args.upgrade_gateway:
            from forge.dev_accounts_gateway import upgrade_gateway
            upgrade_gateway(directory,stopping=stopping)
            _emit({"status":"upgraded","data_retained":True,"demo_directory":str(directory)})
        else:
            run_demo(directory, create=args.create, stopping=stopping)
        return 0
    except KeyboardInterrupt:
        return 0
    except LocalFixtureError as error:
        _emit({"status": "failed", "code": str(error)})
        return 1
    except Exception:
        _emit({"status": "failed", "code": "DURABLE_DEMO_UNAVAILABLE"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
