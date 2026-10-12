"""UDR-021-TC02: the unified ``python -m monitor collect`` entry exits non-zero
on honest failures and writes the located error, never a default success."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor import __main__ as cli
from monitor.context import RunContext
from triton import dashboard

ROOT = Path(__file__).resolve().parents[1]


def write_context(root: Path) -> str:
    ctx = RunContext(run_id="cli-exit-1", code_sha="e" * 40,
                     cutoff_at="2026-10-10T00:00:00Z")
    path = root / "context.json"
    path.write_text(json.dumps(ctx.as_dict()), encoding="utf-8")
    return str(path)


def run_collect(root: Path, project: str = "triton") -> int:
    return cli.main([
        "collect",
        "--catalog", str(ROOT / "catalog.json"),
        "--context", write_context(root),
        "--project", project,
        "--work-dir", str(root / "work"),
        "--report-out", str(root / "report.json"),
    ])


class UnifiedCollectCliExitTests(unittest.TestCase):
    def test_invalid_quality_evidence_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "enriched-runs.json").write_text(json.dumps([{
                "id": 1, "status": "completed", "jobs_complete": False, "jobs": [],
                "created_at": "2026-10-09T23:00:00Z", "updated_at": "2026-10-10T01:00:00Z",
            }]), encoding="utf-8")
            payload = dashboard.build_payload(
                [], "2026-10-07T00:00:00Z", "2026-10-10T00:00:00Z", "2026-10-10T00:10:00Z")
            with patch.object(dashboard, "collect", return_value=payload), \
                    patch.object(dashboard, "EVIDENCE", evidence):
                code = run_collect(root)
            self.assertEqual(code, 1)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["collection_status"], "failed")
            self.assertEqual(report["validation_status"], "failed")
            self.assertEqual(report["exit_code"], 1)
            self.assertTrue(report["errors"], report)
            self.assertTrue(any("incomplete job list" in e for e in report["errors"]), report)

    def test_success_collect_exits_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence"
            evidence.mkdir()
            # A legal empty window: zero runs, complete job lists, valid payload.
            (evidence / "enriched-runs.json").write_text("[]", encoding="utf-8")
            payload = dashboard.build_payload(
                [], "2026-10-07T00:00:00Z", "2026-10-10T00:00:00Z", "2026-10-10T00:10:00Z")
            with patch.object(dashboard, "collect", return_value=payload), \
                    patch.object(dashboard, "EVIDENCE", evidence):
                code = run_collect(root)
            self.assertEqual(code, 0)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["collection_status"], "success")
            self.assertEqual(report["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
