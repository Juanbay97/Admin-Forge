"""Opt-in end-to-end proof: the real compose stack on the local Docker daemon (FORGE_DOCKER_SMOKE=1).

It builds the image, starts PostgreSQL + migrations + control plane + Caddy (internal CA, loopback ports) and
removes every container, volume, network and image it created. Run: FORGE_DOCKER_SMOKE=1 python -m unittest tests.test_deploy_smoke
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh')


@unittest.skipUnless(os.environ.get('FORGE_DOCKER_SMOKE') == '1' and POWERSHELL, 'set FORGE_DOCKER_SMOKE=1 (needs Docker and PowerShell)')
class DeploySmoke(unittest.TestCase):
    def test_the_stack_comes_up_is_proven_and_leaves_nothing_behind(self):
        result = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(ROOT/'scripts'/'deploy-smoke.ps1')],
                                capture_output=True, text=True, timeout=1800, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        for marker in ('PASS migrations applied', 'PASS status ready through caddy', 'PASS admin served',
                       'PASS tampered migration blocks control plane', 'PASS teardown left nothing'):
            self.assertIn(marker, result.stdout)


if __name__ == '__main__':
    unittest.main()
