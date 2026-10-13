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
SECRET_FILES = ('pg_superuser', *('role_' + role for role in ROLES), 'role_backup', 'delivery_key', 'gateway_key',
                'platform_key', 'policy_key', 'smtp_password')
# The SMTP relay password is chosen by the operator (a Resend/SES credential): the generator only creates the empty
# placeholder a Docker file secret needs, and an empty file is refused loudly if the operator forgot to fill it in.
OPERATOR_SECRETS = ('smtp_password',)


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
        generated = [name for name in SECRET_FILES if name not in OPERATOR_SECRETS]
        self.assertEqual(len({values[name] for name in generated}), len(generated), 'every secret must be distinct')
        for name in ('delivery_key', 'gateway_key', 'platform_key', 'policy_key'):
            Fernet(values[name].encode('ascii'))  # raises when the key is not a valid Fernet key
        for name in generated:
            if name not in ('delivery_key', 'gateway_key', 'platform_key', 'policy_key'):
                self.assertRegex(values[name], r'[A-Za-z0-9]{32,}')
        for name in OPERATOR_SECRETS:
            self.assertEqual((Path(self.directory)/name).read_bytes(), b'')  # a placeholder the operator fills in
        for value in filter(None, values.values()):
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


# ---------------------------------------------------------------------------------------------- compose + proxy

TOOL_HOSTS = {'caddyserver.com', 'docker.com', 'docker.io', 'letsencrypt.org', 'postgresql.org', 'resend.com',
              'amazonaws.com', 'github.com', 'mailpit.axllent.org', 'system.io'}  # system.io: .NET namespace in the .ps1
CONCRETE = re.compile(r'\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|app|ai|co|es|eu|cloud)\b', re.I)


def concrete_domains(source):
    """Fully qualified names that look like a real production domain (reserved test names and tool hosts excluded)."""
    found = []
    for match in CONCRETE.finditer(source):
        name = match.group(0).lower()
        if not any(name == host or name.endswith('.' + host) for host in TOOL_HOSTS):
            found.append(name)
    return found


def top_level(source, key):
    """The lines indented under a top-level ``key:`` mapping."""
    lines, inside, block = source.splitlines(), False, []
    for line in lines:
        if re.match(r'^[A-Za-z_-][\w-]*:', line):
            inside = line.split(':')[0] == key
            continue
        if inside:
            block.append(line)
    return '\n'.join(block)


def services(source):
    """``{service name: its block of text}`` from a compose file with two-space indentation."""
    result, current = {}, None
    for line in top_level(source, 'services').splitlines():
        header = re.match(r'^  ([A-Za-z][\w-]*):\s*$', line)
        if header:
            current = header.group(1)
            result[current] = []
        elif current is not None:
            result[current].append(line)
    return {name: '\n'.join(lines) for name, lines in result.items()}


def depends_on(block):
    """``{dependency: condition}`` from a service's ``depends_on`` mapping."""
    found, inside = {}, False
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if re.match(r'^    depends_on:\s*$', line):
            inside = True
        elif inside and re.match(r'^    \S', line):
            inside = False
        elif inside:
            name = re.match(r'^      ([\w-]+):\s*$', line)
            if name:
                condition = re.match(r'^\s+condition:\s*(\S+)', lines[index + 1])
                found[name.group(1)] = condition.group(1)
    return found


def env_keys(source, anchor='x-forge-env'):
    """Keys of a shared ``x-...`` environment mapping."""
    keys, inside = [], False
    for line in source.splitlines():
        if line.startswith(anchor + ':'):
            inside = True
        elif inside and re.match(r'^\S', line):
            break
        elif inside:
            match = re.match(r'^  ([A-Z][A-Z0-9_]*):', line)
            if match:
                keys.append(match.group(1))
    return keys


COMPOSE = 'deploy/compose.yml'


class ConcreteDomainDetector(unittest.TestCase):
    def test_a_production_looking_name_is_found_and_reserved_or_tool_names_are_not(self):
        self.assertEqual(concrete_domains('host forge.prometheonlab.com and smtp.resend.com and forge.example.test'),
                         ['forge.prometheonlab.com'])
        self.assertEqual(concrete_domains('server prometeonlab.com ; see https://caddyserver.com/docs'),
                         ['prometeonlab.com'])
        self.assertEqual(concrete_domains('FORGE_DOMAIN=localhost'), [])


class ComposePolicy(unittest.TestCase):
    def setUp(self):
        self.source = text(COMPOSE)
        self.services = services(self.source)

    def test_the_stack_has_the_four_core_services(self):
        self.assertTrue({'postgres', 'migrate', 'control-plane', 'caddy'} <= set(self.services))

    def test_only_caddy_publishes_host_ports(self):
        published = sorted(name for name, block in self.services.items() if re.search(r'^    ports:', block, re.M))
        self.assertEqual(published, ['caddy'])

    def test_every_service_is_hardened(self):
        for name, block in self.services.items():
            with self.subTest(service=name):
                self.assertRegex(block, r'(?m)^    read_only: true$')
                self.assertRegex(block, r'(?m)^    cap_drop:\n      - ALL$')
                self.assertRegex(block, r'(?m)^      - no-new-privileges:true$')

    def test_every_image_is_pinned_by_digest_or_built_here(self):
        for name, block in self.services.items():
            image = re.search(r'(?m)^    image: (\S+)$', block)
            with self.subTest(service=name):
                self.assertIsNotNone(image)
                if '${FORGE_IMAGE:-' in image.group(1):  # the control-plane image, built locally by one service
                    self.assertIn(name, ('control-plane', 'migrate', 'provision', 'platform'))
                elif name in ('backup', 'restore'):  # PostgreSQL client tools: the same pinned image as the database
                    self.assertEqual(image.group(1), re.search(r'(?m)^    image: (\S+)$', self.services['postgres']).group(1))
                else:
                    self.assertRegex(image.group(1), DIGEST)
        self.assertEqual(sum(1 for block in self.services.values() if re.search(r'(?m)^    build:', block)), 1)

    def test_postgres_digest_is_the_one_the_test_harness_pins(self):
        pinned = text('scripts/postgres-image.txt').strip()
        self.assertRegex(pinned, r'^postgres' + DIGEST.pattern + '$')
        self.assertIn(pinned, self.services['postgres'])

    def test_start_order_is_postgres_then_migrate_then_control_plane_then_caddy(self):
        self.assertEqual(depends_on(self.services['migrate']), {'postgres': 'service_healthy'})
        self.assertEqual(depends_on(self.services['control-plane']),
                         {'postgres': 'service_healthy', 'migrate': 'service_completed_successfully'})
        self.assertEqual(depends_on(self.services['caddy']), {'control-plane': 'service_healthy'})
        self.assertRegex(self.services['migrate'], r'(?m)^    restart: "no"$')

    def test_long_running_services_have_healthchecks(self):
        for name in ('postgres', 'control-plane', 'caddy'):
            with self.subTest(service=name):
                self.assertRegex(self.services[name], r'(?m)^    healthcheck:')
        self.assertIn('forge.serve_prod', self.services['control-plane'])
        self.assertIn('healthcheck', self.services['control-plane'])
        self.assertIn('-h 127.0.0.1', self.services['postgres'])  # TCP, so the init-time socket-only server is not "ready"

    def test_only_postgres_migrate_and_the_tools_profile_receive_the_database_administrator_secret(self):
        holders = sorted(name for name, block in self.services.items() if re.search(r'^      - pg_superuser$', block, re.M))
        self.assertEqual(holders, ['migrate', 'platform', 'postgres', 'provision', 'restore'])
        for name in ('provision', 'restore', 'platform'):
            self.assertRegex(self.services[name], r'(?m)^    profiles:\n      - tools$')  # never started by `up`

    def test_the_platform_tool_runs_the_bootstrap_cli_unprivileged_reaching_the_database_and_the_mail_relay(self):
        block = self.services['platform']
        self.assertRegex(block, r'(?m)^    profiles:\n      - tools$')  # never started by `up`
        self.assertIn('entrypoint: ["python", "-m", "forge.platform"]', block)
        self.assertIn('<<: [*forge-env, *forge-smtp]', block)
        self.assertIn('FORGE_DB_ADMIN_PASSWORD_FILE: /run/secrets/pg_superuser', block)
        self.assertRegex(block, r'(?m)^      - smtp_password$')
        self.assertRegex(block, r'(?m)^    user: "\$\{FORGE_UID:-10001\}:\$\{FORGE_GID:-10001\}"$')
        self.assertIn(':/credentials', block)  # the one-time link file lands where the operator can read it
        self.assertNotRegex(block, r'(?m)^    ports:')
        self.assertNotIn('network_mode', block)  # PostgreSQL by name on `data`, the relay through `edge`
        self.assertRegex(block, r'(?m)^      - data$')
        self.assertRegex(block, r'(?m)^      - edge$')
        self.assertNotRegex(block, r'(?m)^      - forge_')  # no service-role password is needed

    def test_secrets_are_docker_secrets_for_exactly_the_generated_files(self):
        declared = top_level(self.source, 'secrets')
        files = re.findall(r'(?m)^    file: \$\{FORGE_SECRETS_DIR:-\./secrets\}/(\S+)$', declared)
        self.assertEqual(sorted(files), sorted(SECRET_FILES))
        self.assertNotRegex(self.source, r'(?m)^[ \t]+[A-Z_]*(PASSWORD|KEY|SECRET)[A-Z_]*:[ \t]+(?!/run/secrets|\$\{)\S')

    def test_the_shared_environment_only_uses_keys_the_runtime_accepts(self):
        from forge.prod_config import KNOWN_KEYS
        keys = env_keys(self.source)
        self.assertGreaterEqual(len(keys), 8)
        self.assertEqual([key for key in keys if key not in KNOWN_KEYS], [])
        self.assertNotIn('FORGE_WORKERS', keys)  # one worker is the default and the only accepted value

    def test_smtp_is_configured_by_environment_and_one_optional_secret_for_the_control_plane_only(self):
        from forge.prod_config import KNOWN_KEYS
        keys = env_keys(self.source, 'x-forge-smtp')
        self.assertEqual(sorted(keys), sorted(['FORGE_SMTP_HOST', 'FORGE_SMTP_FROM', 'FORGE_SMTP_SECURITY', 'FORGE_SMTP_PORT',
                                               'FORGE_SMTP_USER', 'FORGE_SMTP_PASSWORD_FILE', 'FORGE_SMTP_CA_FILE']))
        self.assertEqual([key for key in keys if key not in KNOWN_KEYS], [])
        self.assertRegex(self.source, r'(?m)^  FORGE_SMTP_HOST: \$\{FORGE_SMTP_HOST:\?[^}]+\}$')  # required, like the domain
        self.assertRegex(self.source, r'(?m)^  FORGE_SMTP_SECURITY: \$\{FORGE_SMTP_SECURITY:-starttls\}$')
        self.assertRegex(self.source, r'(?m)^  FORGE_SMTP_PASSWORD_FILE:$')  # null: only present when .env sets it
        self.assertIn('smtp_password', self.services['control-plane'])
        self.assertIn('<<: [*forge-env, *forge-smtp]', self.services['control-plane'])
        self.assertNotIn('smtp_password', self.services['migrate'])  # the one-shot job never needs the relay
        self.assertNotIn('forge-smtp', self.services['migrate'])

    def test_the_public_origin_comes_from_the_domain_variables_alone(self):
        origin = re.search(r'(?m)^  FORGE_PUBLIC_ORIGIN: (.+)$', self.source).group(1)
        self.assertRegex(origin, r'^https://\$\{FORGE_DOMAIN:\?[^}]+\}\$\{FORGE_PORT_SUFFIX:-\}$')

    def test_no_artifact_outside_the_env_example_names_a_production_domain(self):
        for relative in (COMPOSE, 'Dockerfile', 'scripts/deploy-secrets.sh', 'scripts/deploy-secrets.ps1',
                         'deploy/Caddyfile'):
            with self.subTest(file=relative):
                self.assertEqual(concrete_domains(text(relative)), [])
        self.assertEqual(concrete_domains(text('deploy/.env.dev.example')), [])
        self.assertNotRegex(text('deploy/.env.example') + text(COMPOSE), r'(?i)prometh?eonlab\.(?!example)')

    def test_volumes_and_networks_isolate_the_database(self):
        self.assertIn('internal: true', top_level(self.source, 'networks'))
        for name in ('postgres', 'migrate'):
            self.assertNotIn('- edge', self.services[name])
        self.assertIn('- edge', self.services['caddy'])
        self.assertIn('- edge', self.services['control-plane'])


class CaddyfilePolicy(unittest.TestCase):
    def setUp(self):
        self.source = text('deploy/Caddyfile')

    def test_domain_and_tls_mode_are_selected_only_by_environment(self):
        self.assertIn('{$FORGE_DOMAIN}', self.source)
        self.assertIn('import tls_{$FORGE_TLS}', self.source)
        self.assertRegex(self.source, r'\(tls_internal\) \{\n\s+tls internal\n\}')
        self.assertRegex(self.source, r'\(tls_acme\) \{\n\s+tls \{\$FORGE_ACME_EMAIL\}\n\}')

    def test_the_control_plane_routes_are_proxied_and_everything_else_is_refused(self):
        self.assertRegex(self.source, r'@app path /admin /admin/\* /status /livez /forge/\*')
        self.assertIn('reverse_proxy control-plane:3410', self.source)
        self.assertRegex(self.source, r'handle \{\n\s+respond "Not found" 404\n\s+\}')

    def test_security_headers_are_added_but_the_application_csp_is_left_alone(self):
        for header in ('Strict-Transport-Security', 'X-Content-Type-Options nosniff', 'Referrer-Policy'):
            self.assertIn(header, self.source)
        self.assertNotIn('Content-Security-Policy', self.source)

    def test_downloads_are_served_read_only_without_listing_and_latest_json_is_never_cached(self):
        self.assertIn('handle_path /downloads/*', self.source)
        self.assertIn('root * /srv/downloads', self.source)
        self.assertNotIn('browse', self.source)
        self.assertRegex(self.source, r'@latest path /latest\.json\n\s+header @latest Cache-Control "no-cache"')
        self.assertIn('/srv/downloads:ro', text(COMPOSE))

    def test_an_unknown_host_is_answered_by_the_proxy_itself(self):
        self.assertRegex(self.source, r'(?m)^:443 \{\n(?:.*\n)*?\s+respond "Misdirected request" 421')


class EnvExample(unittest.TestCase):
    def test_every_setting_is_a_placeholder_with_a_reserved_domain(self):
        values = dict(line.split('=', 1) for line in text('deploy/.env.example').splitlines()
                      if line and not line.startswith('#'))
        self.assertEqual(values['FORGE_DOMAIN'], 'forge.example.test')
        self.assertEqual(values['FORGE_PORT_SUFFIX'], '')
        self.assertIn(values['FORGE_TLS'], ('acme', 'internal'))
        self.assertTrue({'FORGE_ACME_EMAIL', 'FORGE_GATEWAY_ORIGINS', 'FORGE_HTTP_PORT', 'FORGE_HTTPS_PORT', 'FORGE_SMTP_HOST',
                         'FORGE_SMTP_FROM', 'FORGE_SMTP_SECURITY', 'FORGE_SMTP_PORT'} <= set(values))
        self.assertTrue(values['FORGE_SMTP_FROM'].endswith('@example.test'))
        self.assertTrue(values['FORGE_SMTP_HOST'].endswith('.example.test'))
        self.assertTrue(values['FORGE_ACME_EMAIL'].endswith('@example.test'))
        for key, value in values.items():
            if key.endswith('_FILE'):  # a path to a Docker secret, never the secret itself
                self.assertRegex(value, r'^/run/secrets/[a-z_]+$')
            self.assertFalse(SECRET_NAME.search(key) and not key.endswith(('_DIR', '_FILE')) and value, key + ' must not carry a value')


@unittest.skipUnless(shutil.which('docker'), 'the docker CLI is required')
class ComposeConfigRendering(unittest.TestCase):
    """`docker compose config` is offline: it proves the file parses and leaks no secret value."""

    def test_the_rendered_configuration_succeeds_publishes_only_caddy_and_prints_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            secrets_dir = Path(directory)/'secrets'
            values = {}
            for name in SECRET_FILES:
                values[name] = 'v-%s-%s' % (name, hashlib.sha256(name.encode()).hexdigest()[:24])
                secrets_dir.mkdir(exist_ok=True)
                (secrets_dir/name).write_text(values[name] + '\n', 'utf-8')
            environment = {**os.environ, 'FORGE_DOMAIN': 'forge.example.test', 'FORGE_SECRETS_DIR': str(secrets_dir),
                           'FORGE_SMTP_HOST': 'smtp.resend.com', 'FORGE_SMTP_FROM': 'forge@example.test',
                           'FORGE_SMTP_USER': 'resend', 'FORGE_SMTP_PASSWORD_FILE': '/run/secrets/smtp_password'}
            result = subprocess.run(['docker', 'compose', '-p', 'forge-static-check', '-f', str(ROOT/COMPOSE), 'config'],
                                    capture_output=True, text=True, timeout=60, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, value in values.items():
            self.assertNotIn(value, result.stdout, name)
        self.assertEqual(len(re.findall(r'published:', result.stdout)), 3)  # 80/tcp, 443/tcp, 443/udp
        self.assertIn('FORGE_PUBLIC_ORIGIN: https://forge.example.test', result.stdout)


def run_sh(*arguments, environment=None):
    return subprocess.run([find_sh(), str(ROOT/'deploy'/'backup'/'backup.sh'), *arguments], capture_output=True, text=True,
                          timeout=60, env={**os.environ, **(environment or {})})


@unittest.skipUnless(find_sh(), 'a POSIX sh is required')
class BackupSchedule(unittest.TestCase):
    """`cron-match "<5-field cron>" "<minute hour day month weekday>"`: exit 0 when the moment is scheduled."""

    def matches(self, cron, now):
        return run_sh('cron-match', cron, now).returncode == 0

    def test_a_nightly_schedule_matches_only_its_minute(self):
        self.assertTrue(self.matches('30 2 * * *', '30 2 15 10 1'))
        self.assertFalse(self.matches('30 2 * * *', '31 2 15 10 1'))
        self.assertFalse(self.matches('30 2 * * *', '30 3 15 10 1'))

    def test_steps_ranges_and_lists_are_supported(self):
        self.assertTrue(self.matches('*/15 * * * *', '45 9 1 1 1'))
        self.assertFalse(self.matches('*/15 * * * *', '46 9 1 1 1'))
        self.assertTrue(self.matches('0 3 * * 1-5', '0 3 12 10 3'))
        self.assertFalse(self.matches('0 3 * * 1-5', '0 3 17 10 6'))
        self.assertTrue(self.matches('0,30 * * * *', '30 8 1 1 1'))
        self.assertFalse(self.matches('0,30 * * * *', '15 8 1 1 1'))

    def test_sunday_may_be_written_as_0_or_7(self):
        self.assertTrue(self.matches('0 0 * * 7', '0 0 18 10 0'))
        self.assertTrue(self.matches('0 0 * * 0', '0 0 18 10 0'))
        self.assertFalse(self.matches('0 0 * * 7', '0 0 19 10 1'))

    def test_a_malformed_schedule_is_refused_before_anything_runs(self):
        for bad in ('daily', '30 2 * *', '61 2 * * *', '* * * * * *', '*/0 * * * *'):
            with self.subTest(cron=bad):
                self.assertEqual(run_sh('cron-match', bad, '30 2 15 10 1').returncode, 2)


@unittest.skipUnless(find_sh(), 'a POSIX sh is required')
class BackupRetention(unittest.TestCase):
    def prune(self, directory, keep):
        return run_sh('prune', environment={'FORGE_BACKUP_DIR': directory, 'FORGE_BACKUP_KEEP': str(keep)})

    def make(self, directory, stamps):
        for stamp in stamps:
            (Path(directory)/('forge-%s.dump' % stamp)).write_bytes(b'dump')

    def test_only_the_newest_dumps_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make(directory, ['20261010T020000Z', '20261011T020000Z', '20261012T020000Z'])
            self.assertEqual(self.prune(directory, 2).returncode, 0)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()),
                             ['forge-20261011T020000Z.dump', 'forge-20261012T020000Z.dump'])

    def test_fewer_dumps_than_the_limit_are_all_kept_and_unrelated_files_are_never_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make(directory, ['20261012T020000Z'])
            (Path(directory)/'notes.txt').write_text('keep me', 'utf-8')
            self.assertEqual(self.prune(directory, 5).returncode, 0)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ['forge-20261012T020000Z.dump', 'notes.txt'])

    def test_a_non_numeric_limit_is_refused_and_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make(directory, ['20261012T020000Z', '20261011T020000Z'])
            self.assertEqual(self.prune(directory, 'x').returncode, 2)
            self.assertEqual(len(list(Path(directory).iterdir())), 2)


class BackupArtifacts(unittest.TestCase):
    def setUp(self):
        self.compose = text(COMPOSE)
        self.services = services(self.compose)
        self.script = text('deploy/backup/backup.sh')
        self.restore = text('deploy/backup/restore.sh')

    def test_the_backup_service_runs_unprivileged_with_only_its_own_secret_and_publishes_nothing(self):
        block = self.services['backup']
        self.assertRegex(block, r'(?m)^    secrets:\n      - backup_reader$')
        self.assertNotIn('pg_superuser', block)
        self.assertNotIn('ports:', block)
        self.assertRegex(block, r'(?m)^    user: "\$\{FORGE_UID:-10001\}:\$\{FORGE_GID:-10001\}"$')
        self.assertIn('FORGE_BACKUP_CRON: ${FORGE_BACKUP_CRON:-30 2 * * *}', block)
        self.assertIn('FORGE_BACKUP_KEEP: ${FORGE_BACKUP_KEEP:-14}', block)
        self.assertEqual(depends_on(block), {'postgres': 'service_healthy'})
        self.assertIn('${FORGE_BACKUPS_DIR:-./backups}:/backups', block)

    def test_the_restore_tool_is_a_tools_profile_service_that_never_publishes_or_runs_by_default(self):
        block = self.services['restore']
        self.assertIn('/opt/forge/restore.sh', block)
        self.assertNotIn('ports:', block)
        self.assertIn('/backups:ro', block)

    def test_the_dump_is_custom_format_taken_with_a_read_only_role_and_never_includes_secret_files(self):
        self.assertIn('pg_dump --format=custom', self.script)
        self.assertIn('pg_restore --list', self.script)  # a dump is verified before it counts
        self.assertNotIn('roles', self.script.split('set -eu')[1])  # roles come from the migrations, never from a dump
        for forbidden in ('deploy/secrets', '.env', 'tar ', 'pg_superuser'):
            self.assertNotIn(forbidden, self.script)
        self.assertNotRegex(self.script, r'(?m)^\s*(echo|printf)[^\n]*(PGPASSWORD|password)')

    def test_the_backup_role_is_created_once_with_read_everything_but_write_nothing(self):
        sql = text('deploy/postgres/initdb/10-backup-reader-role.sql')
        self.assertIn('CREATE ROLE backup_reader LOGIN NOSUPERUSER', sql)
        self.assertIn('BYPASSRLS', sql)
        self.assertIn('GRANT pg_read_all_data TO backup_reader', sql)
        self.assertIn('GRANT CONNECT ON DATABASE :"DBNAME" TO backup_reader', sql)  # CONNECT is revoked from PUBLIC
        self.assertIn('`cat /run/secrets/backup_reader`', sql)  # read from the secret file, not from argv
        postgres = self.services['postgres']
        self.assertIn('- backup_reader', postgres)
        self.assertIn('./postgres/initdb:/docker-entrypoint-initdb.d:ro', postgres)

    def test_the_backup_role_name_stays_outside_the_attested_forge_role_family(self):
        # The schema attestation fingerprints every role LIKE 'forge_%' (and its memberships): a role named
        # forge_<anything> would change the fingerprint and make `migrate` report SCHEMA_FINGERPRINT_MISMATCH.
        sql = text('deploy/postgres/initdb/10-backup-reader-role.sql')
        role = re.search(r'CREATE ROLE (\w+)', sql).group(1)
        self.assertFalse(re.match(r'^forge.', role), role)
        self.assertEqual(role, 'backup_reader')
    def test_restore_loads_data_only_into_a_migrated_empty_database_in_one_transaction(self):
        # The schema attestation hashes deparsed expressions that a dump/restore round trip rewrites, so the schema
        # must always be the one migrate built; only rows are restored.
        for needle in ('TARGET_NOT_EMPTY', 'SCHEMA_VERSION_MISMATCH', '--data-only', '--disable-triggers',
                       '--exclude-schema=forge_ops', '--single-transaction', '--exit-on-error', 'pg_restore --list',
                       'forge_ops.schema_migrations'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.restore)
        self.assertNotIn('.roles.sql', self.restore)

    def test_the_env_template_documents_the_backup_settings(self):
        template = text('deploy/.env.example')
        for key in ('FORGE_BACKUP_CRON=', 'FORGE_BACKUP_KEEP=', 'FORGE_BACKUPS_DIR=', 'FORGE_UID=', 'FORGE_GID='):
            self.assertIn(key, template)


class RunbookDocument(unittest.TestCase):
    def setUp(self):
        self.doc = text('docs/deploy.md')

    def test_the_email_section_documents_both_providers_domain_verification_and_failure_triage(self):
        section = self.doc[self.doc.index('## Email delivery (SMTP)'):self.doc.index('## First platform owner')]
        for needle in ('smtp.resend.com', 'FORGE_SMTP_PORT=465', 'FORGE_SMTP_SECURITY=tls', 'FORGE_SMTP_PORT=587',
                       'FORGE_SMTP_USER=resend', 'email-smtp.<region>.amazonaws.com', 'smtp_password', 'SPF', 'DKIM',
                       'FORGE_SMTP_FROM', 'delivery_state', 'SMTP_AUTH', 'SMTP_TLS', 'SMTP_STARTTLS_REQUIRED',
                       'SMTP_RECIPIENT', 'SMTP_TIMEOUT'):
            with self.subTest(needle=needle):
                self.assertIn(needle, section)
        self.assertRegex(section, r'(?i)verify (the|your) (sending )?domain')
        self.assertNotIn('re_', section)  # no provider API key, not even an example one

    def test_it_leads_with_the_quick_path_and_covers_every_operation(self):
        self.assertTrue(self.doc.startswith('# '))
        self.assertLess(self.doc.index('## Quick path'), self.doc.index('## Prerequisites'))
        for heading in ('## Prerequisites', '## DNS and firewall', '## Configuration and secrets',
                        '## Choose the TLS mode', '## Email delivery (SMTP)', '## First platform owner', '## Platform sign-in and companies',
                        '## Provision the first company',
                        '## Publish installers', '## Backup and restore', '## Upgrade and roll back', '## Logs',
                        '## Troubleshooting', '## Why one worker'):
            with self.subTest(heading=heading):
                self.assertIn(heading + '\n', self.doc)

    def test_the_first_owner_section_bootstraps_with_the_tools_service_and_explains_the_one_time_link(self):
        section = self.doc[self.doc.index('## First platform owner'):self.doc.index('## Provision the first company')]
        self.assertNotIn('Placeholder', section)
        for needle in ('run --rm platform bootstrap-owner', '--link-file /credentials/', '--smtp', 'single-use', 'forgot-password',
                       '--mailbox-dir', '"exists"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, section)

    def test_the_platform_section_documents_the_mandatory_second_factor_company_creation_suspension_and_audit(self):
        section = self.doc[self.doc.index('## Platform sign-in and companies'):self.doc.index('## Provision the first company')]
        for needle in ('/forge/v1/platform/', 'MFA_REQUIRED', '/forge/v1/platform/mfa/enroll', '/forge/v1/platform/login/mfa', 'recovery codes',
                       'MFA_LOCKED', '/forge/v1/platform/companies', 'COMPANY_CONFLICT', '/suspend', '/reactivate', '/branding',
                       '/forge/v1/platform/audit', 'append-only', 'absent from the published API contract'):
            with self.subTest(needle=needle):
                self.assertIn(needle, section)
        self.assertNotRegex(section, r'(?i)password\s*[:=]\s*\S{8,}')
        owner = self.doc[self.doc.index('## First platform owner'):self.doc.index('## Platform sign-in and companies')]
        self.assertIn('(#platform-sign-in-and-companies)', owner)

    def test_it_warns_that_losing_the_fernet_keys_is_unrecoverable_and_defines_the_offline_secrets_backup(self):
        section = self.doc[self.doc.index('## Backup and restore'):]
        self.assertRegex(section, r'(?i)losing[^\n]*delivery_key[^\n]*gateway_key[^\n]*unrecoverable')
        self.assertRegex(section, r'(?i)offline copy of `deploy/secrets/`')
        self.assertIn('restore.sh', section)
        self.assertIn('TARGET_NOT_EMPTY', section)

    def test_it_never_names_a_production_domain_and_uses_the_variables(self):
        self.assertEqual(concrete_domains(self.doc), [])
        self.assertIn('forge.example.test', self.doc)
        self.assertIn('FORGE_DOMAIN', self.doc)
        self.assertIn('FORGE_TLS=internal', self.doc)
        self.assertIn('FORGE_TLS=acme', self.doc)

    def test_every_command_it_shows_names_a_file_or_service_that_exists(self):
        for path in ('deploy/compose.yml', 'deploy/compose.dev.yml', 'scripts/deploy-secrets.sh',
                     'deploy/backup/restore.sh', 'scripts/deploy-smoke.ps1'):
            with self.subTest(path=path):
                self.assertTrue((ROOT/path).is_file())
        for service in ('provision', 'restore', 'backup', 'platform'):
            self.assertIn('run --rm %s' % service if service != 'backup' else 'exec backup', self.doc)


class SmokeInvitationPhase(unittest.TestCase):
    def test_the_smoke_provisions_logs_in_invites_and_reads_the_message_from_mailpit_with_a_working_link(self):
        script = text('scripts/deploy-smoke.ps1')
        for needle in ('/forge/v1/accounts/login', '/forge/v1/accounts/invitations', '/forge/v1/accounts/invitations/accept',
                       '/api/v1/messages', '/api/v1/message/', 'FORGE_MAILPIT_PORT', 'delivery_channel', "'smtp'",
                       'invitation email captured by Mailpit', 'the emailed link activates the account'):
            with self.subTest(needle=needle):
                self.assertIn(needle, script)


class SmokePlatformPhase(unittest.TestCase):
    def test_the_smoke_bootstraps_the_owner_enrols_totp_creates_a_company_and_proves_suspension_and_audit(self):
        script = text('scripts/deploy-smoke.ps1')
        for needle in ("'platform', 'bootstrap-owner'", "'--smtp'", 'Reset your Forge password', '/forge/v1/accounts/password-reset/consume',
                       '/forge/v1/platform/mfa/enroll', '/forge/v1/platform/login/mfa', '/forge/v1/platform/companies',
                       '/suspend', '/reactivate', '/forge/v1/platform/audit', 'Get-Totp', 'HMACSHA1',
                       'the owner link is single-use', 'a TOTP step was accepted twice', 'a taken company code was not a conflict',
                       'platform owner bootstrapped', 'company created by the owner', 'suspension denies the company and reactivation restores it'):
            with self.subTest(needle=needle):
                self.assertIn(needle, script)
        # The platform phase comes after the invitation proof and before the backups.
        order = [script.index(piece) for piece in ('the emailed link activates the account', 'platform owner bootstrapped', 'backup dump is valid')]
        self.assertEqual(order, sorted(order))


class SmokeTotpHelper(unittest.TestCase):
    def test_the_powershell_totp_helper_reproduces_the_rfc_6238_vectors(self):
        # A [byte] shifts as a byte in Windows PowerShell (255 -shl 8 is 0): this pins the widened arithmetic.
        import json
        import shutil
        import subprocess
        if not shutil.which('powershell.exe'):
            self.skipTest('needs Windows PowerShell')
        probe = (
            "$ast = [Management.Automation.Language.Parser]::ParseFile('" + str(ROOT/'scripts'/'deploy-smoke.ps1') + "', [ref]$null, [ref]$null);"
            "$ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-Totp' }, $true)"
            " | ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) };"
            "$secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';"
            "ConvertTo-Json -Compress @{ a = (Get-Totp $secret 0 59); b = (Get-Totp $secret 0 1111111109); c = (Get-Totp $secret 0 1234567890);"
            " d = (Get-Totp $secret 1 59); e = (Get-Totp $secret) }")
        done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', probe], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        values = json.loads(done.stdout)
        self.assertEqual((values['a'], values['b'], values['c']), ('287082', '081804', '005924'))
        self.assertNotEqual(values['d'], values['a'])  # a one-step offset moves the code
        self.assertRegex(values['e'], r'^[0-9]{6}$')


class SmokeGovernancePhase(unittest.TestCase):
    def test_the_smoke_seeds_the_catalog_verifies_a_signed_policy_and_proves_locks_audit_and_isolation(self):
        script = text('scripts/deploy-smoke.ps1')
        for needle in ("'forge.capability_seed', 'sync'", "'--entrypoint', 'python'", '/forge/v1/capabilities/effective', '/forge/v1/capabilities/keys',
                       '/forge/v1/capabilities/audit', 'forge.capability_signing', 'verify_document', 'blocked_attestation', 'forced_off', 'LOCKED',
                       '/capability-audit', 'a second seed run changes nothing', 'the signed policy verifies',
                       'a force-off lock beats the company administrator', 'governance: the catalog is seeded'):
            with self.subTest(needle=needle):
                self.assertIn(needle, script)
        order = [script.index(piece) for piece in ('usage is visible per company, model and total', 'governance: the catalog is seeded', 'backup dump is valid')]
        self.assertEqual(order, sorted(order))


class SmokeBackupPhase(unittest.TestCase):
    def test_the_smoke_proves_dump_retention_refusal_and_round_trip_and_checks_dumps_for_secrets(self):
        script = text('scripts/deploy-smoke.ps1')
        for needle in ('backup.sh', 'run-once', 'pg_restore --list', 'FORGE_BACKUP_KEEP', 'restore.sh', 'TARGET_NOT_EMPTY',
                       'backup dump is valid', 'retention keeps the newest', 'restore refuses a non-empty target',
                       'restore round trip', 'dumps contain no secret'):
            with self.subTest(needle=needle):
                self.assertIn(needle, script)


FORBIDDEN_HOST_PORTS = ('3319', '3320', '3331', '3332')


class DevOverlayPolicy(unittest.TestCase):
    def setUp(self):
        self.source = text('deploy/compose.dev.yml')
        self.services = services(self.source)

    def test_the_overlay_publishes_only_caddy_on_loopback_with_alternate_ports(self):
        self.assertEqual(sorted(name for name, block in self.services.items() if 'ports:' in block), ['caddy', 'mailpit'])
        block = self.services['caddy']
        self.assertIn('ports: !override', block)
        self.assertEqual(len(re.findall(r'- "127\.0\.0\.1:\$\{FORGE_HTTPS?_PORT:-(8080|8443)\}:(80|443)(/udp)?"', block)), 3)
        for port in FORBIDDEN_HOST_PORTS:
            self.assertNotIn(port, self.source)

    def test_the_overlay_defaults_to_the_internal_ca_and_never_to_a_concrete_domain(self):
        self.assertIn('FORGE_TLS: ${FORGE_TLS:-internal}', self.services['caddy'])
        self.assertEqual(concrete_domains(self.source), [])

    def test_the_overlay_does_not_weaken_the_existing_services(self):
        for name in ('caddy', 'control-plane', 'migrate', 'postgres'):
            for key in ('read_only', 'cap_drop', 'privileged', 'security_opt', 'cap_add'):
                self.assertNotIn(key, self.services.get(name, ''))
        self.assertNotIn('privileged', self.source)

    def test_mailpit_catches_mail_for_the_proof_on_loopback_with_a_pinned_image_and_full_hardening(self):
        block = self.services['mailpit']
        self.assertRegex(block, r'(?m)^    image: axllent/mailpit@sha256:[0-9a-f]{64}$')
        self.assertEqual(re.findall(r'- "(127\.0\.0\.1:[^"]+)"', block), ['127.0.0.1:${FORGE_MAILPIT_PORT:-8025}:8025'])
        self.assertRegex(block, r'(?m)^    read_only: true$')
        self.assertRegex(block, r'(?m)^    cap_drop:\n      - ALL$')
        self.assertRegex(block, r'(?m)^      - no-new-privileges:true$')
        self.assertIn('- edge', block)  # reachable from the control plane, but not on the database network
        self.assertNotIn('- data', block)
        self.assertRegex(block, r'(?m)^    healthcheck:')

    def test_the_dev_env_template_points_the_control_plane_at_mailpit_without_credentials(self):
        values = dict(line.split('=', 1) for line in text('deploy/.env.dev.example').splitlines() if line and not line.startswith('#'))
        self.assertEqual((values['FORGE_DOMAIN'], values['FORGE_TLS'], values['FORGE_PORT_SUFFIX']), ('localhost', 'internal', ':8443'))
        self.assertEqual((values['FORGE_SMTP_HOST'], values['FORGE_SMTP_SECURITY'], values['FORGE_SMTP_PORT']), ('mailpit', 'none', '1025'))
        self.assertTrue(values['FORGE_SMTP_FROM'].endswith('@example.test'))
        for key in ('FORGE_SMTP_USER', 'FORGE_SMTP_PASSWORD_FILE'):
            self.assertNotIn(key, values)  # cleartext relays never take credentials


class ProvisionTool(unittest.TestCase):
    def setUp(self):
        self.service = services(text(COMPOSE))['provision']
        self.script = text('deploy/tools/provision.sh')

    def test_it_shares_the_database_network_namespace_and_publishes_nothing(self):
        self.assertIn('network_mode: service:postgres', self.service)  # the operator CLI is loopback-only by design
        self.assertNotIn('ports:', self.service)
        self.assertRegex(self.service, r'(?m)^    user: "\$\{FORGE_UID:-10001\}:\$\{FORGE_GID:-10001\}"$')
        self.assertIn('/credentials', self.service)

    def test_the_operator_file_is_built_in_memory_storage_and_the_secret_is_never_printed(self):
        self.assertIn('/run/secrets/pg_superuser', self.script)
        self.assertIn('/tmp/operator.json', self.script)
        self.assertIn("'host': '127.0.0.1'", self.script)
        self.assertIn('umask 077', self.script)
        self.assertNotRegex(self.script, r'(?m)^\s*(echo|printf)[^\n]*(password|operator)')
        self.assertIn('rm -f "$operator"', self.script)
        self.assertIn('python -m forge.provision', self.script)

    def test_credentials_go_to_a_new_timestamped_file_so_nothing_is_overwritten(self):
        self.assertIn('/credentials/credentials-$(date', self.script)


class SmokeScript(unittest.TestCase):
    def setUp(self):
        self.script = text('scripts/deploy-smoke.ps1')

    def test_it_owns_a_prefixed_project_and_tears_everything_down(self):
        self.assertIn("'forge-smoke-'", self.script)
        self.assertIn("'down', '-v', '--remove-orphans'", self.script)
        self.assertIn('Assert-Gone', self.script)
        self.assertIn('finally', self.script)

    def test_it_never_uses_the_reserved_ports(self):
        for port in FORBIDDEN_HOST_PORTS:
            self.assertIn(port, self.script)  # listed in the guard that rejects them
        self.assertIn('Get-FreePort', self.script)

    def test_it_asserts_every_acceptance_criterion(self):
        for needle in ('forge_ops.schema_migrations', '--cacert', '/status', '/admin/', '/forge/v1/accounts/me',
                       'evil.test', '/downloads/latest.json', 'no-cache', 'forge.serve_prod', 'provision',
                       'MIGRATION_FAILED', 'compose config'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.script)

    def test_it_keeps_secrets_and_state_outside_the_repository(self):
        self.assertIn('$env:TEMP', self.script)
        self.assertIn('FORGE_SECRETS_DIR', self.script)
        self.assertNotIn('deploy/secrets', self.script)


def docker_ready():
    if not shutil.which('docker'):
        return False
    return subprocess.run(['docker', 'info'], capture_output=True, timeout=60).returncode == 0


@unittest.skipUnless(docker_ready(), 'a running Docker daemon is required')
class CaddyfileValidation(unittest.TestCase):
    """The pinned Caddy image parses the Caddyfile for both TLS modes and refuses an invalid one."""

    def validate(self, mode):
        digest = re.search(r'image: (caddy@sha256:[0-9a-f]{64})', text(COMPOSE)).group(1)
        return subprocess.run(
            ['docker', 'run', '--rm', '-e', 'FORGE_DOMAIN=forge.example.test', '-e', 'FORGE_TLS=' + mode,
             '-e', 'FORGE_ACME_EMAIL=admin@example.test', '-v', '%s:/etc/caddy/Caddyfile:ro' % (ROOT/'deploy'/'Caddyfile'),
             digest, 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'],
            capture_output=True, text=True, timeout=120)

    def test_both_modes_are_valid(self):
        for mode in ('internal', 'acme'):
            with self.subTest(mode=mode):
                self.assertEqual(self.validate(mode).returncode, 0)

    def test_an_unknown_mode_is_refused_with_a_clear_error(self):
        result = self.validate('bogus')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('tls_bogus', result.stderr)


if __name__ == '__main__':
    unittest.main()
