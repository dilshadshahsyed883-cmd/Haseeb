"""System-only contract tests for safe rapid GitHub -> Windows pull updates.

These inspect the registered task's source configuration but never register,
run, or change a Windows scheduled task during CI.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYNC = (ROOT / "ops/windows/Sync-Haseeb.ps1").read_text(encoding="utf-8")
RUNNER = (ROOT / "ops/windows/Run-HaseebSync.ps1").read_text(encoding="utf-8")


class FastAutoDeployContracts(unittest.TestCase):
    def test_schedule_checks_every_two_minutes(self):
        self.assertIn('/SC MINUTE /MO 2 /TN "HaseebDesktopSync"', SYNC)
        self.assertNotIn('/SC HOURLY /TN "HaseebDesktopSync"', SYNC)

    def test_uses_existing_single_pc_logged_runner(self):
        self.assertIn('Run-HaseebSync.ps1', SYNC)
        self.assertIn('Local\\HaseebDesktopSync', RUNNER)
        self.assertIn('Start-Transcript', RUNNER)
        self.assertIn('Select-Object -Skip 720', RUNNER)

    def test_no_unverified_builds_or_partial_deploys(self):
        self.assertIn('$item.head_sha -eq $trustedSha', SYNC)
        self.assertIn('$item.conclusion -eq "success"', SYNC)
        self.assertIn('$item.status -eq "completed"', SYNC)
        self.assertIn('deploy-bundle --root $InstallRoot', SYNC)
        self.assertIn('Set-Content -Path $marker -Value ($runId)', SYNC)
        self.assertIn('if ($LASTEXITCODE -ne 0) { throw "Bundle deployment failed;', SYNC)

    def test_ci_not_ready_fallback_remains_strict(self):
        self.assertIn('head_sha=$trustedSha&per_page=100', SYNC)
        self.assertIn('runs?branch=main&per_page=100', SYNC)
        self.assertIn('Fallback confirmed successful Windows CI for exact main SHA.', SYNC)
        self.assertGreaterEqual(SYNC.count('$item.head_sha -eq $trustedSha'), 2)
        self.assertGreaterEqual(SYNC.count('$item.conclusion -eq "success"'), 2)
        self.assertGreaterEqual(SYNC.count('$item.head_branch -eq "main"'), 2)
        self.assertGreaterEqual(SYNC.count('$item.status -eq "completed"'), 2)

    def test_no_remote_shell_or_network_listener(self):
        self.assertNotIn('sshd', SYNC.lower())
        self.assertNotIn('netsh advfirewall', SYNC.lower())
        self.assertNotIn('/SC ONCE', SYNC)
        self.assertNotIn('Start-Process', SYNC)


if __name__ == "__main__":
    unittest.main()
