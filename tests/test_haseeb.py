import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

module_file = Path(__file__).resolve().parents[1] / "tools" / "haseeb.py"
spec = importlib.util.spec_from_file_location("haseeb", module_file)
haseeb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(haseeb)


class HaseebTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.app = self.home / "apps" / "demo"
        self.app.mkdir(parents=True)
        self.spec = {"id": "demo-app", "version": "1.0.0",
                     "name": "Demo", "entry_point": "main.py"}
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        (self.app / "main.py").write_text(
            "import sys\nif '--self-test' in sys.argv: print('PASS')\n", encoding="utf-8")

    def bundle(self):
        return haseeb.package(self.home / "apps", self.home / "dist")[0]

    def test_install_and_rollback(self):
        root = self.home / "installed"
        a = haseeb.deploy(root, self.bundle())
        self.assertEqual(a, haseeb.deploy(root, self.bundle()))
        self.spec["version"] = "1.0.1"
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        b = haseeb.deploy(root, self.bundle())
        self.assertNotEqual(a, b)
        self.assertEqual(a, haseeb.rollback(root, "demo-app"))

    def test_missing_checksum_fails(self):
        path = self.bundle()
        Path(str(path) + ".sha256").unlink()
        with self.assertRaisesRegex(ValueError, "Missing SHA"):
            haseeb.deploy(self.home / "install", path)

    def test_rejects_zip_escape(self):
        archive = self.home / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../escaped.txt", "content")
        Path(str(archive) + ".sha256").write_text(haseeb.sha256(archive), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP"):
            haseeb.deploy(self.home / "install", archive)
        self.assertFalse((self.home / "escaped.txt").exists())

    def test_smoke_failure_does_not_activate(self):
        (self.app / "main.py").write_text("raise RuntimeError('bad')\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Smoke test failed"):
            haseeb.deploy(self.home / "install", self.bundle())
        self.assertIsNone(haseeb.pointer(self.home / "install", "demo-app"))

    def make_secondary(self, version="2.0.0", script=None):
        secondary = self.home / "apps" / "other"
        secondary.mkdir(parents=True, exist_ok=True)
        obj = {"id": "other-app", "version": version, "name": "Other",
               "entry_point": "main.py"}
        (secondary / "app.json").write_text(json.dumps(obj), encoding="utf-8")
        (secondary / "main.py").write_text(
            script or "import sys\nif '--self-test' in sys.argv: print('PASS')\n",
            encoding="utf-8")

    def test_bundle_success_activates_all_apps(self):
        self.make_secondary()
        archives = haseeb.package(self.home / "apps", self.home / "dist")
        installed = self.home / "installed"
        records = haseeb.deploy_bundle(installed, archives)
        self.assertEqual({r["app_id"] for r in records}, {"demo-app", "other-app"})
        self.assertEqual(haseeb.pointer(installed, "demo-app")["version"], "1.0.0")
        self.assertEqual(haseeb.pointer(installed, "other-app")["version"], "2.0.0")
        # Idempotent re-deployment must preserve active pointers.
        self.assertEqual(records, haseeb.deploy_bundle(installed, archives))
        self.assertIsNone(haseeb.pointer(installed, "demo-app", "previous"))

    def test_bundle_invalid_second_app_preserves_existing_first(self):
        installed = self.home / "installed"
        original = haseeb.deploy(installed, self.bundle())
        self.spec["version"] = "1.0.1"
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        self.make_secondary(script="raise RuntimeError('bad secondary')\n")
        archives = haseeb.package(self.home / "apps", self.home / "dist")
        with self.assertRaisesRegex(RuntimeError, "Smoke test failed"):
            haseeb.deploy_bundle(installed, archives)
        self.assertEqual(haseeb.pointer(installed, "demo-app"), original)
        self.assertIsNone(haseeb.pointer(installed, "demo-app", "previous"))
        self.assertIsNone(haseeb.pointer(installed, "other-app"))

    def test_bundle_bad_checksum_preserves_every_app(self):
        self.make_secondary()
        archives = haseeb.package(self.home / "apps", self.home / "dist")
        Path(str(archives[-1]) + ".sha256").unlink()
        installed = self.home / "installed"
        with self.assertRaisesRegex(ValueError, "Missing SHA"):
            haseeb.deploy_bundle(installed, archives)
        self.assertIsNone(haseeb.pointer(installed, "demo-app"))
        self.assertIsNone(haseeb.pointer(installed, "other-app"))

    def test_bundle_activation_failure_restores_original_pointer_bytes(self):
        installed = self.home / "installed"
        original = haseeb.deploy(installed, self.bundle())
        before = (installed / "apps" / "demo-app" / "current.json").read_bytes()
        self.spec["version"] = "1.0.1"
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        self.make_secondary()
        archives = haseeb.package(self.home / "apps", self.home / "dist")
        real_save = haseeb.save
        errors = [0]

        def fail_on_second_app(path, value):
            if path.parent.name == "other-app" and path.name == "current.json" and not errors[0]:
                errors[0] += 1
                raise OSError("simulated pointer write failure")
            return real_save(path, value)

        with mock.patch.object(haseeb, "save", side_effect=fail_on_second_app):
            with self.assertRaisesRegex(OSError, "simulated pointer"):
                haseeb.deploy_bundle(installed, archives)
        self.assertEqual(haseeb.pointer(installed, "demo-app"), original)
        self.assertEqual(
            (installed / "apps" / "demo-app" / "current.json").read_bytes(), before)
        self.assertIsNone(haseeb.pointer(installed, "demo-app", "previous"))
        self.assertIsNone(haseeb.pointer(installed, "other-app"))

    def test_duplicate_app_in_bundle_is_rejected_before_activation(self):
        archive = self.bundle()
        installed = self.home / "installed"
        with self.assertRaisesRegex(ValueError, "Duplicate application"):
            haseeb.deploy_bundle(installed, [archive, archive])
        self.assertIsNone(haseeb.pointer(installed, "demo-app"))

    def test_rejects_unsafe_manifest(self):
        self.spec["entry_point"] = "../secret.py"
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        with self.assertRaises(ValueError):
            haseeb.manifest(self.app)


if __name__ == "__main__":
    unittest.main()
