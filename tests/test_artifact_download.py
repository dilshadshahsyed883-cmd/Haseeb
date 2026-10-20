"""Offline tests of bounded, logged, noninteractive artifact downloader."""
from pathlib import Path
import sys
import tempfile
import unittest

from tools.download_artifact import download


class ArtifactDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def script(self, contents):
        script = self.root / "fake_gh.py"
        script.write_text(contents, encoding="utf-8")
        return [sys.executable, str(script)]

    def test_success_with_checksum_file(self):
        fake = self.script(
            "import pathlib,sys\n"
            "args=sys.argv[1:]\n"
            "assert args[:3]==['run','download','39448858607']\n"
            "assert '--repo' in args and '--name' in args\n"
            "dest=pathlib.Path(args[args.index('--dir')+1])\n"
            "(dest/'app.zip').write_bytes(b'test')\n"
            "(dest/'app.zip.sha256').write_text('a'*64+'  app.zip\\n')\n"
        )
        output = self.root / "downloads" / "attempt"
        paths = download("39448858607", output, launcher=fake,
                         log_root=self.root / "logs", timeout_seconds=10,
                         heartbeat_seconds=0.2)
        self.assertEqual([p.name for p in paths], ["app.zip"])
        self.assertEqual(len(list((self.root / "logs").glob("artifact-*.log"))), 1)

    def test_timeout_kills_only_child(self):
        fake = self.script("import time\ntime.sleep(10)\n")
        with self.assertRaises(TimeoutError):
            download("39448858607", self.root / "downloads" / "second",
                     launcher=fake, log_root=self.root / "logs",
                     timeout_seconds=0.5, heartbeat_seconds=0.1)

    def test_failure_does_not_create_install_marker(self):
        fake = self.script("import sys\nsys.exit(2)\n")
        output = self.root / "downloads" / "attempt"
        with self.assertRaisesRegex(RuntimeError, "nonzero exit"):
            download("39448858607", output, launcher=fake,
                     log_root=self.root / "logs", timeout_seconds=10)
        self.assertFalse((self.root / "installed").exists())

    def test_existing_files_are_not_overwritten(self):
        output = self.root / "downloads" / "attempt"
        output.mkdir(parents=True)
        (output / "keep.txt").write_text("original")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            download("39448858607", output, launcher=["no-execution"],
                     log_root=self.root / "logs", timeout_seconds=10)
        self.assertEqual((output / "keep.txt").read_text(), "original")

    def test_missing_companion_rejected(self):
        fake = self.script(
            "import pathlib,sys\n"
            "dest=pathlib.Path(sys.argv[sys.argv.index('--dir')+1])\n"
            "(dest/'app.zip').write_bytes(b'test')\n"
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            download("39448858607", self.root / "downloads" / "attempt",
                     launcher=fake, log_root=self.root / "logs",
                     timeout_seconds=10)

    def test_untrusted_ids_rejected(self):
        for run_id in ("", "x", "234\n--repo=other", "../3944", "0" * 21):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                download(run_id, self.root / "downloads" / "attempt",
                         launcher=["no-execution"], log_root=self.root / "logs")

    def test_no_interactive_input_and_private_logs(self):
        fake = self.script(
            "import pathlib,sys\n"
            "assert sys.stdin.read()==''\n"
            "dest=pathlib.Path(sys.argv[sys.argv.index('--dir')+1])\n"
            "(dest/'x.zip').write_bytes(b'x')\n"
            "(dest/'x.zip.sha256').write_text('a'*64)\n"
        )
        self.assertEqual(
            len(download("39448858607", self.root / "downloads" / "attempt",
                         launcher=fake, log_root=self.root / "logs",
                         timeout_seconds=10)), 1)


if __name__ == "__main__":
    unittest.main()
