"""Isolated, network-free checks for Haseeb source-only artifact planning."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.release_planner import safe_system_path, source_only_update, changed_paths


class ReleasePlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Haseeb CI")
        self.git("config", "user.email", "ci@example.invalid")
        self.write("apps/audio_cutter/main.py", "print('unchanged app')")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.sha()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True, text=True, check=True, timeout=20,
        ).stdout.strip()

    def sha(self):
        return self.git("rev-parse", "HEAD")

    def write(self, path, value):
        path = self.repo / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def commit(self, path, content):
        self.write(path, content)
        self.git("add", "-A")
        self.git("commit", "-qm", "update")
        return self.sha()

    def test_only_known_system_sources_may_skip_bundle(self):
        self.assertTrue(safe_system_path("ops/windows/Sync-Haseeb.ps1"))
        self.assertTrue(safe_system_path("tools/release_planner.py"))
        self.assertTrue(safe_system_path("tests/test_release_planner.py"))
        self.assertFalse(safe_system_path("apps/audio_cutter/main.py"))
        self.assertFalse(safe_system_path("tools/haseeb.py"))
        self.assertFalse(safe_system_path("tools/prepare_audio_cutter.py"))
        self.assertFalse(safe_system_path(".github/workflows/build-windows.yml"))
        self.assertFalse(safe_system_path("shared/new_lib.py"))

    def test_actual_git_system_only_change_skips_artifact(self):
        current = self.commit("ops/windows/Sync-Haseeb.ps1", "change")
        self.assertEqual(changed_paths(self.repo, self.base, current),
                         ["ops/windows/Sync-Haseeb.ps1"])
        self.assertTrue(source_only_update(self.repo, self.base, current))

    def test_actual_git_app_change_requires_full_bundle(self):
        current = self.commit("apps/audio_cutter/main.py", "app changed")
        self.assertFalse(source_only_update(self.repo, self.base, current))

    def test_package_recipe_change_requires_bundle(self):
        current = self.commit("tools/haseeb.py", "new packaging code")
        self.assertFalse(source_only_update(self.repo, self.base, current))

    def test_unrecognized_new_module_requires_bundle(self):
        current = self.commit("shared/media_utils.py", "new shared module")
        self.assertFalse(source_only_update(self.repo, self.base, current))

    def test_invalid_or_divergent_shas_cannot_skip(self):
        current = self.commit("docs/PC_DEPLOYMENT.md", "new system docs")
        self.assertFalse(source_only_update(self.repo, "missing", current))
        self.assertFalse(source_only_update(self.repo, current, self.base))

    def test_mixed_system_and_app_diff_never_skips(self):
        self.write("docs/PC_DEPLOYMENT.md", "changed docs")
        self.write("apps/audio_cutter/main.py", "changed app")
        self.git("add", "-A")
        self.git("commit", "-qm", "mixed")
        self.assertFalse(source_only_update(self.repo, self.base, self.sha()))


if __name__ == "__main__":
    unittest.main()
