"""The white-label smoke runner composes the real pieces in a safe order and stays inside what it owns."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT/'scripts'/'branding-smoke.ps1'
MVP_SMOKE = ROOT/'scripts'/'mvp-smoke.ps1'
RUNS = ("Invoke-Bounded $npx 'playwright test -c playwright.forge-branding-orgs.config.ts'",
        "Invoke-Bounded $npx 'playwright test -c playwright.config.ts branding.spec.ts'",
        "Invoke-Bounded $npx 'playwright test -c playwright.forge-branding.config.ts'")


class BrandingSmokeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SMOKE.is_file(), 'scripts/branding-smoke.ps1 is missing')
        self.text = SMOKE.read_text('utf-8')

    def test_it_composes_the_real_pieces_in_order(self):
        order = [self.text.index(piece) for piece in (
            "'run build'", 'forge.mvp_local up --supervised --require-admin-build', '--control-plane-origin',
            *RUNS, 'Stop-Child $clientProcess', 'Stop-Child $stack')]
        self.assertEqual(order, sorted(order))

    def test_the_read_only_seed_check_runs_before_anything_edits_the_seeded_brands(self):
        # The admin spec re-brands organization A and the gate spec saves both organizations through the API.
        orgs, admin, gate = (self.text.index(run) for run in RUNS)
        self.assertLess(orgs, admin)
        self.assertLess(admin, gate)
        self.assertEqual(len(re.findall(r'^    if \(\$result -eq 0\) \{', self.text, re.M)), 2,
                         'later steps run only after the previous one passed')

    def test_the_stack_is_the_seeded_one_and_the_client_gets_its_own_data_directory(self):
        self.assertIn('$env:FORGE_E2E_CLIENT_DATA = $clientData', self.text)
        self.assertIn('$env:FORGE_E2E_CREDENTIALS = $ready.credentials_file', self.text)
        self.assertIn('[Guid]::NewGuid()', self.text)
        self.assertIn('Remove-Item -LiteralPath $clientData', self.text)

    def test_the_run_must_leave_both_repositories_and_the_four_ports_as_it_found_them(self):
        self.assertIn('status --porcelain', self.text)
        for repository in ('(Get-TreeState $root)', '(Get-TreeState $client)'):
            self.assertEqual(self.text.count(repository), 2, repository)
        self.assertLess(self.text.index('$treeBefore ='), self.text.index("Invoke-Bounded $npm 'run build'"))
        self.assertIn('TREE_DIRTY', self.text)
        self.assertIn('@(3410, 3411, 3412, 3413)', self.text)
        self.assertIn('PORTS_NOT_FREED', self.text)

    def test_it_never_touches_the_retained_demo_or_unowned_processes(self):
        for port in ('3319', '3320', '3331', '3332'):
            self.assertNotIn(port, self.text)
        self.assertNotRegex(self.text, r'(?i)Stop-Process|taskkill(?:\.exe)?\s+/IM|Get-Process\s+-Name')
        self.assertIn('/PID', self.text)
        self.assertIn('owned_container_absent', self.text)
        self.assertIn('private_workspace_absent', self.text)

    def test_every_wait_is_bounded_and_secrets_are_never_printed(self):
        for name in ('BuildTimeoutSeconds', 'ClientStartTimeoutSeconds', 'StackStartTimeoutSeconds',
                     'AdminTestTimeoutSeconds', 'ClientTestTimeoutSeconds', 'GateTestTimeoutSeconds', 'StopTimeoutSeconds'):
            self.assertIn(name, self.text)
        self.assertNotRegex(self.text, r'(?i)(Get-Content|cat|type)\s+\$?\w*credentials')
        self.assertNotRegex(self.text, r'(?i)Write-(Output|Host)[^\n]*(password|gateway_key|access_token)')

    def test_the_mvp_smoke_runner_is_left_alone(self):
        # tasks.md: mvp-smoke.ps1 is not edited; this runner is its own script.
        self.assertTrue(MVP_SMOKE.is_file())
        self.assertNotIn('branding-smoke', MVP_SMOKE.read_text('utf-8'))  # the mvp smoke runs the branding e2e spec, never this runner
        self.assertIsNone(re.search(r'mvp-smoke:', self.text))


if __name__ == '__main__':
    unittest.main()
