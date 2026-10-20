import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
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

    def test_rejects_unsafe_manifest(self):
        self.spec["entry_point"] = "../secret.py"
        (self.app / "app.json").write_text(json.dumps(self.spec), encoding="utf-8")
        with self.assertRaises(ValueError):
            haseeb.manifest(self.app)


if __name__ == "__main__":
    unittest.main()
