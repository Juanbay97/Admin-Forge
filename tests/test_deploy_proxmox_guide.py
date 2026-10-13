"""Static checks for docs/deploy-proxmox.md: the guide may only name scripts, services, secret files and settings that really exist in
deploy/ and scripts/, so it cannot drift from the stack it describes. Plain text assertions; nothing is started."""
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_artifacts import COMPOSE, ROOT, SECRET_FILES, concrete_domains, services, text

GUIDE = 'docs/deploy-proxmox.md'
DOMAIN = 'prometheonlab.com'  # confirmed by the owner for this guide; every other deploy artifact keeps reserved names only
# Build-time variables of the Windows installer (the client repository), named by the guide because the installer must be built for
# the control plane's origin. They are not settings of this stack.
CLIENT_BUILD_VARIABLES = {'FORGE_DEFAULT_CP_ORIGIN', 'FORGE_ALLOWED_ORIGINS'}
PACKAGE_NAMES = {'containerd.io'}  # an apt package of Docker's repository, not a host
# Created on the server by the operator or by the stack, so they cannot be checked into the repository.
CREATED_PATHS = {'deploy/.env', 'deploy/secrets', 'deploy/credentials', 'deploy/backups', 'deploy/downloads', 'deploy/gateway-ca'}
HEADINGS = ('## Quick path', '## Before you start', '## 1. Prepare the VM', '## 2. DNS and ports', '## 3. Install Docker',
            '## 4. Configure Forge', '## 5. Mail through Resend', '## 6. Start the stack', '## 7. First platform owner',
            '## 8. Connect OmniRoute', '## 9. Create the first company', '## 10. Publish the installer',
            '## 11. Install the client on another PC', '## Backups and restore', '## Upgrades', '## Troubleshooting', '## Checklist')


def known_settings():
    sources = ('deploy/.env.example', COMPOSE, 'deploy/Caddyfile', 'scripts/deploy-secrets.sh', 'deploy/backup/backup.sh')
    return {name for source in sources for name in re.findall(r'\bFORGE_[A-Z0-9_]*[A-Z0-9]\b', text(source))}


class Guide(unittest.TestCase):
    def setUp(self):
        self.doc = text(GUIDE)

    def test_it_leads_with_the_quick_path_and_follows_the_deployment_in_order(self):
        self.assertTrue(self.doc.startswith('# '))
        positions = [self.doc.find(heading + '\n') for heading in HEADINGS]
        self.assertNotIn(-1, positions, [heading for heading, position in zip(HEADINGS, positions) if position < 0])
        self.assertEqual(positions, sorted(positions))
        self.assertLess(self.doc.index('## Quick path'), self.doc.index('## Before you start'))

    def test_it_uses_the_confirmed_domain_and_no_other_production_name(self):
        for name in set(concrete_domains(self.doc)) - PACKAGE_NAMES:
            self.assertTrue(name == DOMAIN or name.endswith('.' + DOMAIN), name)
        for needle in ('forge.' + DOMAIN, 'ia.' + DOMAIN, 'FORGE_DOMAIN=forge.' + DOMAIN, 'FORGE_GATEWAY_ORIGINS=https://ia.' + DOMAIN):
            self.assertIn(needle, self.doc)
        self.assertIn('OmniRoute', self.doc)
        self.assertRegex(self.doc, r'(?i)host is configurable|any host name|choose another')

    def test_every_setting_it_names_exists_in_the_stack(self):
        named = set(re.findall(r'\bFORGE_[A-Z0-9_]*[A-Z0-9]\b', self.doc))
        self.assertTrue(named)
        self.assertEqual(sorted(named - known_settings() - CLIENT_BUILD_VARIABLES), [])
        for required in ('FORGE_DOMAIN', 'FORGE_TLS', 'FORGE_ACME_EMAIL', 'FORGE_SMTP_HOST', 'FORGE_SMTP_PORT', 'FORGE_SMTP_SECURITY',
                         'FORGE_SMTP_USER', 'FORGE_SMTP_FROM', 'FORGE_SMTP_PASSWORD_FILE', 'FORGE_GATEWAY_ORIGINS', 'FORGE_UID', 'FORGE_GID',
                         'FORGE_MIGRATE_SEED'):
            self.assertIn(required, self.doc)

    def test_every_path_it_names_exists_or_is_created_on_the_server(self):
        for path in set(re.findall(r'\b(?:deploy|scripts)/[A-Za-z0-9_./-]*[A-Za-z0-9_]', self.doc)):
            created = path.rstrip('/') in CREATED_PATHS or any(path.startswith(prefix + '/') for prefix in CREATED_PATHS)
            self.assertTrue(created or (ROOT / path).exists(), path)
        for name in set(re.findall(r'\bsecrets/([a-z_]+)\b', self.doc)):
            self.assertIn(name, SECRET_FILES)
        self.assertIn('deploy-secrets.sh', self.doc)

    def test_every_compose_service_and_command_it_runs_exists(self):
        names = set(services(text(COMPOSE)))
        shown = set(re.findall(r'(?:run --rm|exec(?: -T)?|logs(?: -f)?) ([a-z][a-z-]*)', self.doc)) - {'compose', 'run'}
        self.assertTrue({'platform', 'restore', 'backup', 'control-plane'} <= shown, shown)
        self.assertEqual(sorted(shown - names), [])
        self.assertIn('--profile tools run --rm platform bootstrap-owner', self.doc)
        self.assertIn('/opt/forge/backup.sh run-once', self.doc)
        self.assertIn('run-once', text('deploy/backup/backup.sh'))
        self.assertIn('bootstrap-owner', text('src/forge/platform_cli.py'))
        for flag in re.findall(r'(--(?:link-file|smtp|mailbox-dir|email|name))\b', self.doc):
            self.assertIn(flag, text('src/forge/platform_cli.py'))

    def test_mail_goes_through_resend_starttls_with_the_key_in_the_secret_file_and_never_in_the_guide(self):
        for needle in ('smtp.resend.com', 'FORGE_SMTP_PORT=587', 'FORGE_SMTP_SECURITY=starttls', 'FORGE_SMTP_USER=resend',
                       'secrets/smtp_password', 'SPF', 'DKIM', 'Amazon SES'):
            self.assertIn(needle, self.doc)
        self.assertNotRegex(self.doc, r'\bre_[A-Za-z0-9]{8,}')
        self.assertNotRegex(self.doc, r'(?i)(password|api[ _-]?key)\s*[:=]\s*[A-Za-z0-9+/]{12,}')

    def test_it_covers_the_whole_journey_from_a_bare_vm_to_a_working_client(self):
        for needle in ('qemu-guest-agent', 'snapshot', '80/tcp', '443/tcp', 'FORGE_TLS=acme', 'FORGE_TLS=internal', 'CGNAT',
                       'docker compose up -d --build --wait', '/status', 'bootstrap-owner', 'TOTP', 'recovery codes', '/admin/platform',
                       '/platform/keys', '/platform/companies/new', 'deploy/downloads/', 'latest.json', 'sha256sum', 'platforms',
                       'forge-install.json', '/CONFIG=', 'FORGE_DEFAULT_CP_ORIGIN', 'FORGE_ALLOWED_ORIGINS', 'prometheon-forge://join',
                       'vzdump', 'offline copy', 'restore', 'FORGE_MIGRATE_SEED=0', 'git pull', 'journalctl', 'Let\'s Encrypt'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.doc)

    def test_the_runbook_points_to_the_guide_without_naming_a_production_domain(self):
        runbook = text('docs/deploy.md')
        self.assertIn('deploy-proxmox.md', runbook)
        self.assertEqual(concrete_domains(runbook), [])

    def test_the_private_gateway_certificate_option_is_documented_where_the_gateway_is_connected(self):
        for document in (text(GUIDE), text('docs/deploy.md')):
            self.assertIn('FORGE_GATEWAY_CA_FILE=/run/gateway-ca/', document)
            self.assertIn('deploy/gateway-ca/', document)
            self.assertNotIn('the production compose passes no private CA through', document)

    def test_it_closes_with_a_checklist_the_reader_can_confirm(self):
        checklist = self.doc[self.doc.index('## Checklist'):]
        self.assertGreaterEqual(checklist.count('- [ ] '), 8)


if __name__ == '__main__':
    unittest.main()
