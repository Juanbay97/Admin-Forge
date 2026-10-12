"""Static policy tests for the deployment artifacts: image, secrets generator, compose, proxy, backup, runbook.

Plain text assertions (no YAML dependency): the files are the contract, so the rules are read from them.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from forge.mvp_local import ROLES

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r'@sha256:[0-9a-f]{64}\b')
SECRET_NAME = re.compile(r'(SECRET|PASSWORD|PASSWD|TOKEN|KEY|CREDENTIAL)', re.I)
SECRET_FILES = ('pg_superuser', *('role_' + role for role in ROLES), 'role_backup', 'delivery_key', 'gateway_key')


def text(relative):
    return (ROOT/relative).read_text('utf-8')


def dockerfile_stages(source):
    """Split a Dockerfile into ``(name, [instruction lines])`` stages; continuation lines are joined."""
    joined = re.sub(r'\\\r?\n', ' ', source)
    stages = []
    for line in joined.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        keyword, _, rest = line.partition(' ')
        if keyword.upper() == 'FROM':
            parts = rest.split()
            name = parts[parts.index('AS') + 1] if 'AS' in parts else None
            stages.append((name, [line]))
        elif stages:
            stages[-1][1].append(line)
    return stages


def dockerfile_violations(source):
    """Every policy breach in a Dockerfile, as short codes."""
    problems = []
    stages = dockerfile_stages(source)
    names = {name for name, _ in stages if name}
    for name, lines in stages:
        image = lines[0].split()[1]
        if image not in names and not DIGEST.search(image):
            problems.append('UNPINNED_IMAGE:' + image)
    for name, lines in stages:
        for line in lines:
            keyword, _, rest = line.partition(' ')
            if keyword.upper() in ('ARG', 'ENV') and SECRET_NAME.search(rest.split('=')[0].split()[0]):
                problems.append('SECRET_IN_IMAGE:' + rest.split('=')[0].split()[0])
    final = stages[-1][1] if stages else []
    users = [line.split()[1] for line in final if line.split()[0].upper() == 'USER']
    if not users or users[-1].split(':')[0] in ('root', '0'):
        problems.append('ROOT_USER')
    return problems


class DockerfilePolicy(unittest.TestCase):
    def test_real_dockerfile_passes_every_rule(self):
        self.assertEqual(dockerfile_violations(text('Dockerfile')), [])

    def test_the_policy_catches_each_breach(self):
        bad = ('FROM python:3.12-slim AS build\nENV DB_PASSWORD=hunter2\nARG API_TOKEN\n'
               'FROM build\nUSER root\n')
        self.assertEqual(dockerfile_violations(bad), [
            'UNPINNED_IMAGE:python:3.12-slim', 'SECRET_IN_IMAGE:DB_PASSWORD', 'SECRET_IN_IMAGE:API_TOKEN', 'ROOT_USER'])

    def test_a_pinned_non_root_image_is_clean(self):
        digest = '@sha256:' + 'a' * 64
        good = 'FROM python:3.12-slim%s AS build\nRUN true\nFROM build\nUSER 10001:10001\n' % digest
        self.assertEqual(dockerfile_violations(good), [])

    def test_the_stages_build_the_admin_spa_and_the_wheel_then_run_the_serve_command(self):
        stages = dockerfile_stages(text('Dockerfile'))
        self.assertGreaterEqual(len(stages), 3)
        source = text('Dockerfile')
        self.assertIn('npm ci', source)
        self.assertIn('npm run build', source)
        self.assertIn('migrations', source)
        self.assertRegex(source, r'ENTRYPOINT \["python", "-m", "forge\.serve_prod"\]')
        self.assertIn('USER 10001:10001', source)

    def test_nothing_secret_enters_the_build_context(self):
        ignored = text('.dockerignore').splitlines()
        for entry in ('.git', '.env', '.env.*', 'deploy/secrets', 'deploy/credentials', '**/node_modules',
                      '.venv', '.local'):
            self.assertIn(entry, ignored)
        self.assertNotRegex(text('Dockerfile'), r'COPY[^\n]*(secrets|\.env)')


def find_sh():
    found = shutil.which('sh')
    if found:
        return found
    for candidate in (r'C:\Program Files\Git\bin\sh.exe', r'C:\Program Files\Git\usr\bin\sh.exe'):
        if os.path.exists(candidate):
            return candidate
    return None


def run_generator(kind, directory):
    if kind == 'sh':
        command = [find_sh(), str(ROOT/'scripts'/'deploy-secrets.sh'), directory]
    else:
        command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                   str(ROOT/'scripts'/'deploy-secrets.ps1'), '-Directory', directory]
    return subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=ROOT)


def snapshot(directory):
    return {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in sorted(Path(directory).iterdir())}


class SecretsGeneratorContract:
    kind = None

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = str(Path(self.temporary.name)/'secrets')

    def test_first_run_writes_every_secret_with_valid_material(self):
        result = run_generator(self.kind, self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = {path.name for path in Path(self.directory).iterdir()}
        self.assertEqual(files, set(SECRET_FILES))
        values = {name: (Path(self.directory)/name).read_text('ascii').strip() for name in SECRET_FILES}
        self.assertEqual(len(set(values.values())), len(SECRET_FILES), 'every secret must be distinct')
        for name in ('delivery_key', 'gateway_key'):
            Fernet(values[name].encode('ascii'))  # raises when the key is not a valid Fernet key
        for name in SECRET_FILES:
            if name not in ('delivery_key', 'gateway_key'):
                self.assertRegex(values[name], r'[A-Za-z0-9]{32,}')
        for value in values.values():
            self.assertNotIn(value, result.stdout + result.stderr)  # secrets are never printed

    def test_second_run_changes_nothing_and_a_missing_file_is_filled_in(self):
        run_generator(self.kind, self.directory)
        before = snapshot(self.directory)
        again = run_generator(self.kind, self.directory)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(snapshot(self.directory), before)
        (Path(self.directory)/'role_backup').unlink()
        refill = run_generator(self.kind, self.directory)
        self.assertEqual(refill.returncode, 0, refill.stderr)
        after = snapshot(self.directory)
        self.assertEqual({name: after[name] for name in before if name != 'role_backup'},
                         {name: before[name] for name in before if name != 'role_backup'})
        self.assertIn('role_backup', after)


@unittest.skipUnless(find_sh(), 'a POSIX sh is required')
class ShellSecretsGenerator(SecretsGeneratorContract, unittest.TestCase):
    kind = 'sh'


@unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell is required')
class PowerShellSecretsGenerator(SecretsGeneratorContract, unittest.TestCase):
    kind = 'ps1'


class RepositoryHygiene(unittest.TestCase):
    def test_generated_secrets_and_the_local_environment_are_ignored(self):
        ignore = text('.gitignore').splitlines()
        for entry in ('deploy/secrets/', 'deploy/credentials/', 'deploy/downloads/*', '!deploy/downloads/.gitkeep',
                      '!deploy/.env.example'):
            self.assertIn(entry, ignore)


if __name__ == '__main__':
    unittest.main()
