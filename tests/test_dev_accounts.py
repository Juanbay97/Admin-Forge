"""Local developer lifecycle contracts and one real owned HTTP integration."""
from pathlib import Path
import json
import queue
import re
import threading
import time
import urllib.request
import urllib.error
from email import policy
from email.parser import BytesParser
import os
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from forge.dev_accounts import (
    FRONTEND_ORIGIN, BACKEND_ORIGIN, LocalFixtureError, OwnedPostgres,
    PrivateWorkspace, isolated_environment, reserve_backend_socket,
    stop_session, validate_frontend_origin, validate_repository,
)


class DevAccountContractTests(unittest.TestCase):
    def test_contract_repository_is_exact_and_existing(self):
        self.assertEqual(validate_repository(ROOT), ROOT.resolve())
        with TemporaryDirectory() as other:
            with self.assertRaises(LocalFixtureError):
                validate_repository(Path(other))
        with self.assertRaises(LocalFixtureError):
            validate_repository(ROOT / 'missing')

    def test_contract_frontend_origin_is_fixed_not_redirect_input(self):
        self.assertEqual(validate_frontend_origin(FRONTEND_ORIGIN), FRONTEND_ORIGIN)
        for invalid in ('http://127.0.0.1:3318', 'http://localhost:3319',
                        'https://evil.test', FRONTEND_ORIGIN+'/path',
                        FRONTEND_ORIGIN+'#secret', None):
            with self.subTest(origin=invalid), self.assertRaises(LocalFixtureError):
                validate_frontend_origin(invalid)

    def test_contract_environment_does_not_adopt_ambient_secrets(self):
        supplied = dict(SystemRoot='C:/Windows', PATH='safe-path', TEMP='safe-temp',
            PGSERVICE='private-marker', PGPASSWORD='private-marker',
            DOCKER_AUTH_CONFIG='private-marker', HTTP_PROXY='private-marker',
            AWS_SECRET_ACCESS_KEY='private-marker', FORGE_TOKEN='private-marker')
        isolated = isolated_environment(supplied)
        self.assertEqual(isolated['SystemRoot'], supplied['SystemRoot'])
        self.assertEqual(isolated['PATH'], supplied['PATH'])
        self.assertNotIn('private-marker', repr(isolated))
        self.assertNotIn('PGSERVICE', isolated)
        self.assertNotIn('PGPASSWORD', isolated)

    def test_contract_occupied_backend_port_refuses_without_reuse(self):
        first = reserve_backend_socket()
        try:
            self.assertEqual(first.getsockname(), ('127.0.0.1', 3320))
            with self.assertRaises(LocalFixtureError):
                reserve_backend_socket()
        finally:
            first.close()
        fresh = reserve_backend_socket()
        fresh.close()

    def test_contract_private_workspace_has_verified_acl_and_exact_cleanup(self):
        workspace = PrivateWorkspace()
        directory = workspace.directory
        self.assertTrue(workspace.acl_verified)
        self.assertTrue(directory.is_dir())
        self.assertRegex(directory.name, r'^forge-owned-accounts-[a-f0-9]{32}$')
        workspace.close()
        self.assertFalse(directory.exists())

    def test_contract_workspace_cannot_adopt_existing_arbitrary_folder(self):
        with TemporaryDirectory() as outside:
            with self.assertRaises(LocalFixtureError):
                PrivateWorkspace(Path(outside))
            self.assertTrue(Path(outside).is_dir())
            with self.assertRaises(LocalFixtureError):
                stop_session(Path(outside))
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_contract_container_cleanup_is_exact_id_and_verified(self):
        with TemporaryDirectory() as owned:
            postgres = OwnedPostgres(Path(owned), 'postgres@sha256:'+'a'*64)
            postgres.container_id = 'b'*64
            removed = subprocess.CompletedProcess([],0,stdout='',stderr='')
            absent = subprocess.CompletedProcess([],1,stdout='',stderr='Error: No such object: '+ 'b'*64)
            with patch('forge.dev_accounts.subprocess.run', side_effect=(removed,absent)) as run:
                postgres.close()
            self.assertIn('b'*64, run.call_args_list[0].args[0])
            self.assertIn('b'*64, run.call_args_list[1].args[0])
            self.assertNotIn('--all', repr(run.call_args_list))
            self.assertIsNone(postgres.container_id)

    def test_contract_invalid_container_identity_never_calls_docker(self):
        with TemporaryDirectory() as owned:
            postgres = OwnedPostgres(Path(owned), 'postgres@sha256:'+'a'*64)
            postgres.container_id = 'unowned-invalid'
            with patch('forge.dev_accounts.subprocess.run') as run:
                with self.assertRaises(LocalFixtureError):
                    postgres.close()
            run.assert_not_called()


POWERSHELL = Path("C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")
WRAPPER = ROOT / "scripts/dev-accounts.ps1"


def launch_wrapper(*arguments):
    return subprocess.Popen(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-File", str(WRAPPER), *arguments],
        cwd=ROOT, env=isolated_environment(os.environ), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class DevAccountWrapperTests(unittest.TestCase):
    def test_wrapper_rejects_wrong_origin_before_fixture(self):
        child = launch_wrapper("-FrontendOrigin", "https://untrusted.test")
        output, error = child.communicate(timeout=15)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("INVALID_FRONTEND_ORIGIN", error)
        self.assertNotIn('"status": "starting"', output)

    def test_wrapper_rejects_wrong_repository_before_fixture(self):
        with TemporaryDirectory() as outside:
            child = launch_wrapper("-RepositoryRoot", outside)
            output, error = child.communicate(timeout=15)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("INVALID_REPOSITORY", error)
        self.assertNotIn('"status": "starting"', output)

    def test_wrapper_occupied_port_never_creates_resources(self):
        held = reserve_backend_socket()
        try:
            child = launch_wrapper()
            output, error = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 1)
            self.assertIn("BACKEND_PORT_OCCUPIED", output)
            self.assertNotIn('"status": "starting"', output)
        finally:
            held.close()


@unittest.skipUnless(os.environ.get("FORGE_RUN_DEV_ACCOUNTS_INTEGRATION") == "1",
                     "Explicit one owned database/HTTP lifecycle run required.")
class DevAccountLifecycleTests(unittest.TestCase):
    def test_real_local_login_bootstrap_invitation_and_exact_shutdown(self):
        child = launch_wrapper()
        messages = queue.Queue()
        transcript = []  # Nonsecret launcher metadata only, never HTTP credentials.
        session = ready = None
        def collect():
            for line in child.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    messages.put({"status": "invalid_launcher_output"})
            messages.put({"status": "launcher_eof"})
        threading.Thread(target=collect, daemon=True).start()
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                message = messages.get(timeout=max(.1, deadline-time.monotonic()))
                transcript.append(message)
                if message.get("session_directory"):
                    session = Path(message["session_directory"])
                if message.get("status") == "ready":
                    ready = message
                    break
                self.assertNotIn(message.get("status"), ("failed", "launcher_eof", "invalid_launcher_output"),
                    "Local fixture did not reach ready; only nonsecret status was retained.")
            self.assertIsNotNone(ready, "Finite local startup deadline exceeded.")
            self.assertTrue(ready["disposable_local_fixture"])
            self.assertFalse(ready["enterprise_profile_configured"])
            context = json.loads(Path(ready["context_file"]).read_text("utf-8"))
            credentials = json.loads(Path(ready["credentials_file"]).read_text("utf-8"))
            self.assertNotIn("password", repr(context))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def request(path, body=None, token=None, origin=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                if origin:
                    headers["Origin"] = origin
                data = None if body is None else json.dumps(body).encode()
                req = urllib.request.Request(BACKEND_ORIGIN+path, data=data, headers=headers)
                try:
                    with opener.open(req, timeout=15) as response:
                        raw = response.read()
                        return response.status, json.loads(raw) if raw else None, response.headers
                except urllib.error.HTTPError as response:
                    raw = response.read()
                    return response.code, json.loads(raw) if raw else None, response.headers
            # The bound socket is reserved before readiness; wait only for serving.
            for _ in range(30):
                try:
                    health = request("/healthz")
                    break
                except OSError:
                    time.sleep(.1)
            self.assertEqual(health[0], 200)
            path = "/forge/v1/bootstrap?organization_id="+context["organization_id"]
            self.assertEqual(request(path)[0], 401)
            login = request("/forge/v1/accounts/login", credentials, origin=FRONTEND_ORIGIN)
            self.assertEqual(login[0], 200, "Real password login failed.")
            token = login[1]["access_token"]
            self.assertEqual(login[2].get("Access-Control-Allow-Origin"), FRONTEND_ORIGIN)
            bootstrap = request(path, token=token)
            self.assertEqual(bootstrap[0], 200, "Genuine session bootstrap failed.")
            self.assertNotIn(credentials["password"], json.dumps(bootstrap[1]))
            self.assertNotIn(token, json.dumps(bootstrap[1]))
            invitation = request("/forge/v1/accounts/invitations", {
                "organization_id": context["organization_id"], "department_id": context["department_id"],
                "email": "recipient@forge.local.test", "name": "Local recipient",
            }, token=token)
            self.assertEqual(invitation[0], 201, "Session-derived administrator invitation failed.")
            self.assertEqual(invitation[1]["delivery_state"], "delivered")
            self.assertEqual(invitation[1]["delivery_channel"], "local_test_mailbox")
            self.assertNotIn("capability", invitation[1])
            mailbox = Path(ready["mailbox_directory"])
            letters = list(mailbox.glob("*.eml"))
            self.assertEqual(len(letters), 1)
            self.assertEqual(mailbox.parent, session)
            message = BytesParser(policy=policy.default).parsebytes(letters[0].read_bytes())
            self.assertEqual(message["To"], "recipient@forge.local.test")
            plain = message.get_body(preferencelist=("plain",)).get_content()
            self.assertIn(FRONTEND_ORIGIN+"/onboarding#", plain)
            self.assertNotIn("/onboarding?", plain)
            self.assertEqual(request("/mailbox", token=token)[0], 404)
            self.assertIsNone(request(path, token=token, origin="https://evil.test")[2].get("Access-Control-Allow-Origin"))
            (session / "stop.request").touch()
            self.assertEqual(child.wait(timeout=45), 0, "Owned launcher shutdown failed.")
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    transcript.append(messages.get(timeout=.1))
                except queue.Empty:
                    pass
            self.assertTrue(any(item.get("status")=="stopped" and item.get("owned_container_absent")
                and item.get("private_workspace_absent") for item in transcript))
            self.assertFalse(session.exists())
            with TemporaryDirectory(prefix="forge-container-absence-") as probe:
                probe_config = Path(probe)
                (probe_config / "config.json").write_text("{}", encoding="utf-8")
                check = subprocess.run([
                    "C:/Program Files/Docker/Docker/resources/bin/docker.exe", "--config", str(probe_config),
                    "--host", "npipe:////./pipe/docker_engine", "inspect", ready["container_id"],
                ], env=isolated_environment(os.environ), capture_output=True, text=True, timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.assertEqual(check.returncode, 1)
                self.assertIn("No such object", check.stderr)
            available = reserve_backend_socket()
            available.close()
            print("Owned localhost lifecycle: health200/login200/bootstrap200/invite201/private-eml/exact-cleanup.")
            print("Nonsecret owned container ID:", ready["container_id"])
            print("Removed private fixture directory:", session)
        finally:
            if child.poll() is None:
                if session is not None and session.is_dir():
                    (session / "stop.request").touch(exist_ok=True)
                child.stdin.close()
                try:
                    child.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    self.fail("Owned child cleanup remains pending; no unrelated process was terminated.")
            child.stdout.close()
            child.stderr.close()
            if not child.stdin.closed:
                child.stdin.close()
