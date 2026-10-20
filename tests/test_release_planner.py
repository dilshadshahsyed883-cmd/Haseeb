"""Isolated, network-free checks for Haseeb source-only artifact planning."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import json

from tools.release_planner import (
    safe_system_path, source_only_update, changed_paths, installed_apps_intact,
    verify_previous_run_response, previous_sha_for_run, evaluate,
)


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

    def test_windows_updater_keeps_app_install_marker_separate(self):
        base = Path(__file__).resolve().parents[1]
        sync = (base / "ops/windows/Sync-Haseeb.ps1").read_text(encoding="utf-8")
        status = (base / "ops/windows/Status-Haseeb.ps1").read_text(encoding="utf-8")
        self.assertIn("tools\\release_planner.py", sync)
        self.assertIn('last-successful-sha.txt', sync)
        self.assertIn('last-verified-source-run.txt', sync)
        self.assertIn('last-successful-run.txt', status)
        self.assertIn('last_verified_source_run', status)
        self.assertIn('if ($planResult -eq 0)', sync)
        self.assertIn('if ($planResult -ne 10)', sync)

    def test_legacy_run_only_accepts_exact_successful_haseeb_build(self):
        run_id = "39448858607"
        trusted_sha = "9a48aa1acfaa98d02ea983f4969973b4cb80fa2f"
        valid = {
            "id": 39448858607,
            "path": ".github/workflows/build-windows.yml",
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_sha": trusted_sha,
            "repository": {"full_name": "dilshadshahsyed883-cmd/Haseeb"},
            "head_repository": {"full_name": "dilshadshahsyed883-cmd/Haseeb"},
        }
        self.assertEqual(verify_previous_run_response(valid, run_id), trusted_sha)
        for field, replacement in (
            ("id", 39448858606),
            ("path", ".github/workflows/other.yml"),
            ("head_branch", "development"),
            ("event", "pull_request"),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("head_sha", "missing"),
            ("repository", {"full_name": "outsider/Haseeb"}),
            ("head_repository", {"full_name": "outsider/Haseeb"}),
        ):
            with self.subTest(field=field):
                alternate = dict(valid)
                alternate[field] = replacement
                self.assertIsNone(verify_previous_run_response(alternate, run_id))
        self.assertIsNone(verify_previous_run_response(valid, "not-a-run"))

    def test_legacy_lookup_is_read_only_and_returns_verified_sha(self):
        import subprocess as process
        run_id = "39448858607"
        expected = "9a48aa1acfaa98d02ea983f4969973b4cb80fa2f"
        doc = {
            "id": 39448858607,
            "path": ".github/workflows/build-windows.yml",
            "head_branch": "main", "event": "push",
            "status": "completed", "conclusion": "success",
            "head_sha": expected,
            "repository": {"full_name": "dilshadshahsyed883-cmd/Haseeb"},
            "head_repository": {"full_name": "dilshadshahsyed883-cmd/Haseeb"},
        }
        fake = process.CompletedProcess([], 0, json.dumps(doc), "")
        with mock.patch("tools.release_planner.subprocess.run", return_value=fake) as run:
            self.assertEqual(previous_sha_for_run(run_id), expected)
            self.assertEqual(run.call_args.args[0][:3],
                             ["gh", "api", "--method"])
        with mock.patch("tools.release_planner.subprocess.run",
                        return_value=process.CompletedProcess([], 1, "", "bad")):
            self.assertIsNone(previous_sha_for_run(run_id))

    def test_legacy_source_only_requires_present_installed_apps(self):
        self.write("apps/audio_cutter/app.json", json.dumps({
            "id": "audio-cutter", "version": "1.0.0", "entry_point": "main.py"
        }))
        self.git("add", "-A")
        self.git("commit", "-qm", "bundle recorded")
        prior = self.sha()
        current = self.commit("ops/windows/Sync-Haseeb.ps1", "new updater")
        root = self.repo / "installed"
        self.assertFalse(evaluate(self.repo, root, prior, current))
        active = root / "apps" / "audio-cutter" / "current.json"
        active.parent.mkdir(parents=True)
        release = root / "releases" / "audio-cutter" / "1.0.0-checksum"
        release.mkdir(parents=True)
        (release / "app.json").write_text(json.dumps({
            "id": "audio-cutter", "version": "1.0.0"
        }), encoding="utf-8")
        active.write_text(json.dumps({
            "app_id": "audio-cutter", "version": "1.0.0",
            "release": "releases/audio-cutter/1.0.0-checksum",
            "sha256": "f" * 64
        }), encoding="utf-8")
        self.assertTrue(installed_apps_intact(self.repo, root))
        self.assertTrue(evaluate(self.repo, root, prior, current))
        active.unlink()
        self.assertFalse(evaluate(self.repo, root, prior, current))

    def test_installed_app_path_cannot_escape_release_root(self):
        self.write("apps/audio_cutter/app.json", json.dumps({
            "id": "audio-cutter", "version": "1.0.0"
        }))
        root = self.repo / "installed"
        active = root / "apps" / "audio-cutter" / "current.json"
        active.parent.mkdir(parents=True)
        active.write_text(json.dumps({
            "app_id": "audio-cutter", "version": "1.0.0",
            "release": "../untrusted"
        }), encoding="utf-8")
        self.assertFalse(installed_apps_intact(self.repo, root))

    def test_windows_legacy_missing_sha_fallback_guard(self):
        sync = (Path(__file__).resolve().parents[1]
                / "ops/windows/Sync-Haseeb.ps1").read_text(encoding="utf-8")
        self.assertIn('Legacy app release has no SHA marker', sync)
        self.assertIn('"--previous-run-id", $previousRun', sync)
        self.assertIn('if ($planResult -eq 0)', sync)
        self.assertIn('if ($planResult -ne 10)', sync)

    def test_mixed_system_and_app_diff_never_skips(self):
        self.write("docs/PC_DEPLOYMENT.md", "changed docs")
        self.write("apps/audio_cutter/main.py", "changed app")
        self.git("add", "-A")
        self.git("commit", "-qm", "mixed")
        self.assertFalse(source_only_update(self.repo, self.base, self.sha()))


if __name__ == "__main__":
    unittest.main()
