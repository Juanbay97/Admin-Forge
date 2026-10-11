"""Cross-repo smoke contract: the client pin equals the control plane contract and the runner stays safe."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import contract

SMOKE = ROOT/'scripts'/'mvp-smoke.ps1'
DOCS = ROOT/'docs'/'mvp-local.md'
# The client lives beside the worktree directory in the monorepo checkout: <repo>/clients/openyak.
CLIENT = ROOT.parents[1]/'clients'/'openyak'
PIN = CLIENT/'contract'/'forge-contract.pin.json'


class ContractEqualityTests(unittest.TestCase):
    def setUp(self):
        if not PIN.is_file():
            self.skipTest('the client checkout is not next to this worktree')

    def test_client_pin_is_the_committed_control_plane_contract(self):
        committed = json.loads(contract.COMMITTED_PATH.read_text('utf-8'))
        pinned = json.loads(PIN.read_text('utf-8'))
        self.assertEqual(pinned, committed, 'regenerate the pin: copy contract/forge-mvp.contract.json to the client')
        self.assertEqual(contract.canonical_sha256(pinned), contract.canonical_sha256(committed))
        self.assertEqual(pinned['contract_version'], contract.CONTRACT_VERSION)

    def test_the_pin_is_independent_of_line_endings(self):
        raw = PIN.read_bytes()
        crlf = raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        self.assertEqual(contract.canonical_sha256(json.loads(crlf.decode('utf-8'))),
                         contract.canonical_sha256(json.loads(raw.decode('utf-8'))))


class SmokeRunnerTests(unittest.TestCase):
    def setUp(self):
        if not SMOKE.is_file():
            self.fail('scripts/mvp-smoke.ps1 is missing')
        self.text = SMOKE.read_text('utf-8')

    def test_it_composes_the_real_pieces_in_order(self):
        order = [self.text.index(piece) for piece in (
            'npm.cmd', 'forge.mvp_local up --supervised --require-admin-build', 'test:e2e',
            '--control-plane-origin', 'playwright.forge-managed-flow.config.ts')]
        self.assertEqual(order, sorted(order))

    def test_it_never_touches_the_retained_demo_or_unowned_processes(self):
        for port in ('3319', '3320', '3331', '3332'):
            self.assertNotIn(port, self.text)
        self.assertNotRegex(self.text, r'(?i)Stop-Process|taskkill(?:\.exe)?\s+/IM|Get-Process\s+-Name')
        self.assertIn('/PID', self.text)  # owned process trees only
        self.assertIn('owned_container_absent', self.text)
        self.assertIn('private_workspace_absent', self.text)

    def test_every_wait_is_bounded_and_secrets_are_never_printed(self):
        for name in ('BuildTimeoutSeconds', 'ClientStartTimeoutSeconds', 'StackStartTimeoutSeconds',
                     'AdminTestTimeoutSeconds', 'ClientTestTimeoutSeconds', 'StopTimeoutSeconds'):
            self.assertIn(name, self.text)
        self.assertNotRegex(self.text, r'(?i)(Get-Content|cat|type)\s+\$?\w*credentials')
        self.assertNotRegex(self.text, r'(?i)Write-(Output|Host)[^\n]*(password|gateway_key|access_token)')


class DocumentationTests(unittest.TestCase):
    def test_how_to_run_the_mvp_documents_the_exact_commands_without_secrets(self):
        text = DOCS.read_text('utf-8')
        self.assertIn('## Cómo ejecutar el MVP', text)
        for command in ('scripts\\mvp-local.ps1 -RequireAdminBuild', 'scripts\\mvp-smoke.ps1',
                        'scripts/forge-managed.mjs', '--control-plane-origin http://127.0.0.1:3410',
                        'http://127.0.0.1:3410/admin/', 'http://127.0.0.1:3411', 'credentials.json'):
            self.assertIn(command, text)
        self.assertNotRegex(text, r'(?i)password\s*[:=]\s*\S{8,}')
        self.assertIsNone(re.search(r'\b[A-Za-z0-9_-]{43}\b', text.split('## Cómo ejecutar el MVP', 1)[1]))


if __name__ == '__main__':
    unittest.main()
