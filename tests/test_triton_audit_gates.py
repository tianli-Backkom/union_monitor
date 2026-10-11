"""Behavioral regression gates for the independently reproduced data defects."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from triton.dashboard import build_payload, summary_of, write_payload
from triton.quality import validate, verify_artifacts, fingerprint


def run_row(number=1, *, pr=7, attempt=1, created="2026-10-10T01:00:00Z", start=None):
    row = {
        "id": number, "pr": pr, "pr_title": "Example", "pr_url": "https://github.com/example/repo/pull/7" if pr else None,
        "base_branch": "main" if pr else None, "head_sha": "abc", "event": "pull_request",
        "run_attempt": attempt, "created_at": created, "run_started_at": start or created,
        "updated_at": "2026-10-10T01:10:00Z", "status": "completed", "conclusion": "failure",
        "jobs_complete": True,
        "jobs": [{"id": number * 10, "name": "integration-tests-ascend (linux-amd64-a5-2, py3.12)",
                  "status": "completed", "conclusion": "failure", "created_at": "2026-10-10T01:00:00Z",
                  "started_at": "2026-10-10T01:00:14Z", "completed_at": "2026-10-10T01:10:00Z"}],
        "pr_evidence": {"method": "explicit", "run_id": number, "pr": pr, "resolved_head_sha": "abc"},
    }
    if pr is None:
        row["pr_evidence"] = {"method": "unresolved", "run_id": number, "error": "historical commit not provable"}
    return row


def payload(rows, start="2026-10-10T00:00:00Z"):
    return build_payload(rows, start, "2026-10-11T00:00:00Z", "2026-10-11T00:01:00Z")


class DataQualificationTests(unittest.TestCase):
    def test_unresolved_measurements_survive_but_do_not_become_commit_e2e_samples(self):
        data = payload([run_row(), run_row(2, pr=None)])
        self.assertEqual(len(data["batches"]), 2)
        unknown = next(b for b in data["batches"] if b["pr"] is None)
        self.assertEqual(unknown["status"], "failure")
        self.assertEqual(unknown["duration_seconds"], 600)
        self.assertEqual(unknown["npu_queue_seconds"], 14)
        self.assertIs(unknown.get("e2e_sample_eligible"), False)
        self.assertEqual(unknown.get("e2e_exclusion_reason"), "unresolved_pr_batch_identity")
        self.assertEqual(data["summary"]["valid"], 1)
        self.assertEqual(data["summary"]["p90"], 600)

    def test_legacy_unresolved_rows_are_excluded_without_reclassifying_their_result(self):
        rows = [{"pr": 7, "status": "success", "duration_seconds": 600, "approximate": True, "missing": []},
                {"pr": None, "status": "failure", "duration_seconds": 10, "approximate": True, "missing": ["未可靠关联 PR"]}]
        self.assertEqual(summary_of(rows)["valid"], 1)
        self.assertEqual(summary_of(rows)["p90"], 600)
        self.assertEqual(rows[1]["status"], "failure")

    def test_unknown_runs_do_not_invent_one_pr_with_many_e2e_attempts(self):
        data = payload([run_row(1, pr=None), run_row(2, pr=None)])
        self.assertEqual([(b["e2e_index"], b["e2e_total"]) for b in data["batches"]], [(1, 1), (1, 1)])

    def test_csv_keeps_legacy_columns_and_qualifications_ship_separately(self):
        data = payload([run_row(), run_row(2, pr=None)])
        with tempfile.TemporaryDirectory() as tmp, patch("triton.dashboard.REPO_ROOT", Path(tmp)), patch("triton.dashboard.EVIDENCE", Path(tmp) / "evidence"):
            write_payload(data)
            directory = Path(tmp) / "web" / "data"
            with (directory / "triton-batches.csv").open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(rows[0]), 16)
            self.assertEqual(rows[1]["duration_seconds"], "600.0")
            self.assertTrue((directory / "triton-qualifications-v1.json").is_file())
            sidecar = json.loads((directory / "triton-qualifications-v1.json").read_text())
            self.assertEqual(sidecar["schema_version"], 1)
            self.assertEqual([b["e2e_sample_eligible"] for b in sidecar["batches"]], [True, False])

    def test_tampered_qualification_sidecar_cannot_pass_artifact_validation(self):
        data = payload([run_row(), run_row(2, pr=None)])
        with tempfile.TemporaryDirectory() as tmp, patch("triton.dashboard.REPO_ROOT", Path(tmp)), patch("triton.dashboard.EVIDENCE", Path(tmp) / "evidence"):
            write_payload(data)
            directory = Path(tmp) / "web" / "data"
            (directory / "triton-manifest.json").write_text(json.dumps({"sha256": fingerprint(data), "collected_at": data["collected_at"]}))
            self.assertEqual(verify_artifacts(directory), [])
            sidecar_path = directory / "triton-qualifications-v1.json"
            sidecar = json.loads(sidecar_path.read_text())
            sidecar["batches"][1]["e2e_sample_eligible"] = True
            sidecar_path.write_text(json.dumps(sidecar))
            self.assertTrue(any("qualification" in error for error in verify_artifacts(directory)))


class IndependentCoverageTests(unittest.TestCase):
    def test_deleting_the_entire_in_window_batch_cannot_exempt_its_npu_run(self):
        rows = [run_row()]
        data = payload(rows)
        data["batches"] = []
        data["summary"] = {"prs": 0, "batches": 0, "valid": 0, "median": None, "p90": None,
                           "approximate": 0, "incomplete": 0, "api_calls": 0}
        report = validate(rows, data)
        self.assertFalse(report["passed"], report)
        self.assertTrue(any("absent" in error for error in report["errors"]), report)

    def test_attempt_window_is_decided_from_its_own_start_not_first_creation(self):
        row = run_row(attempt=2, created="2026-10-01T00:00:00Z", start="2026-10-10T01:00:00Z")
        data = payload([row])
        self.assertTrue(validate([row], data)["passed"])
        data["batches"] = []
        data["summary"] = {"prs": 0, "batches": 0, "valid": 0, "median": None, "p90": None,
                           "approximate": 0, "incomplete": 0, "api_calls": 0}
        self.assertFalse(validate([row], data)["passed"])

    def test_outside_attempt_remains_legitimately_excluded(self):
        row = run_row(created="2026-10-09T01:00:00Z")
        data = payload([row])
        self.assertEqual(data["batches"], [])
        self.assertTrue(validate([row], data)["passed"])

    def test_exact_trigger_keeps_source_coverage_required_despite_older_auxiliary_creation(self):
        exact = run_row()
        exact.update(trigger_exact=True, trigger_at="2026-10-10T01:00:00Z")
        older_auxiliary = run_row(2, created="2026-10-09T22:00:00Z")
        data = payload([exact, older_auxiliary])
        self.assertEqual(len(data["batches"]), 1)
        data["batches"] = []
        data["summary"] = {"prs": 0, "batches": 0, "valid": 0, "median": None, "p90": None,
                           "approximate": 0, "incomplete": 0, "api_calls": 0}
        self.assertFalse(validate([exact, older_auxiliary], data)["passed"])


if __name__ == "__main__":
    unittest.main()
