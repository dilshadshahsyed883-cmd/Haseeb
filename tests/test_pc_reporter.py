"""Deterministic local tests for Haseeb PC feedback (no GitHub network calls)."""
import json
import warnings
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import pc_reporter as report


class PCFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_success_is_durable_and_deduplicated(self):
        t = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertTrue(report.record(self.root, "success", "complete", "INSTALLED", "a" * 40, "123", now=t))
        self.assertFalse(report.record(self.root, "success", "complete", "INSTALLED", "a" * 40, "123", now=t))
        pending = list((self.root / "pending").glob("*.json"))
        self.assertEqual(len(pending), 1)
        payload = json.loads(pending[0].read_text())
        self.assertEqual(set(payload), report.FIELDS)
        self.assertNotIn("hostname", payload)
        self.assertNotIn("logs", payload)
        self.assertEqual(payload["status"], "success")

    def test_failure_deduplicated_per_day_and_commit(self):
        t = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertTrue(report.record(self.root, "failure", "ci", "CI_NOT_READY", "b" * 40, now=t))
        self.assertFalse(report.record(self.root, "failure", "ci", "CI_NOT_READY", "b" * 40, now=t))
        self.assertTrue(report.record(self.root, "failure", "ci", "CI_NOT_READY", "b" * 40, now=t + timedelta(days=1)))
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 2)

    def test_failed_dispatch_preserves_pending_for_retry(self):
        report.record(self.root, "failure", "artifact", "ARTIFACT_FAILED")
        self.assertEqual(report.flush(self.root, sender=lambda _: False), (0, 1))
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 1)
        self.assertEqual(report.flush(self.root, sender=lambda _: True), (1, 0))
        self.assertEqual(len(list((self.root / "pending").glob("*.json"))), 0)
        self.assertEqual(len(list((self.root / "sent").glob("*.json"))), 1)

    def test_sent_prevents_duplicate_requeue(self):
        t = datetime(2026, 10, 20, tzinfo=timezone.utc)
        report.record(self.root, "success", "complete", "INSTALLED", run_id="9", now=t)
        report.flush(self.root, sender=lambda _: True)
        self.assertFalse(report.record(self.root, "success", "complete", "INSTALLED", run_id="9", now=t))

    def test_reject_freeform_private_fields(self):
        payload = report.create_report("failure", "install", "INSTALL_FAILED")
        payload["computer_name"] = "private-pc"
        with self.assertRaises(ValueError):
            report.validate_report(payload)

    def test_reject_injection_and_inconsistent_results(self):
        payload = report.create_report("success", "complete", "INSTALLED")
        payload["commit_sha"] = "x\n## injected"
        with self.assertRaises(ValueError):
            report.validate_report(payload)
        payload = report.create_report("success", "complete", "INSTALLED")
        payload["error_code"] = "UNKNOWN_FAILURE"
        with self.assertRaises(ValueError):
            report.validate_report(payload)
        with self.assertRaises(ValueError):
            report.create_report("failure", "install", "INSTALL_FAILED", run_id="../../secrets")

    def test_reporter_compiles_without_python_syntax_warnings(self):
        source_path = Path(report.__file__)
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(source_path.read_text(encoding="utf-8"),
                    str(source_path), "exec")

    def test_summary_contains_only_allowlisted_values(self):
        payload = report.create_report("failure", "install", "INSTALL_FAILED", "a" * 40, "42")
        summary = report.render_summary(payload)
        self.assertIn("INSTALL_FAILED", summary)
        self.assertIn("PC-reported outcome", summary)
        self.assertNotIn("local path", summary.lower())

    def test_dispatch_export_and_validation(self):
        payload = report.create_report("success", "complete", "INSTALLED", "a" * 40, "1234")
        event = self.root / "github-event.json"
        event.write_text(json.dumps({"client_payload": payload}))
        out = self.root / "report.json"
        summary = self.root / "summary.md"
        report.export_dispatch(event, out, summary)
        self.assertEqual(json.loads(out.read_text()), payload)
        self.assertIn("SUCCESS", summary.read_text())
        event.write_text(json.dumps({"client_payload": {"status": "failure", "logs": "secret"}}))
        with self.assertRaises(ValueError):
            report.export_dispatch(event, out, summary)


if __name__ == "__main__":
    unittest.main()
