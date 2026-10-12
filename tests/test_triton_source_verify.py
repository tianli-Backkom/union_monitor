"""UDR-004-TC01/TC02: the Triton full-source verification closes every category.

The independent verifier re-reads raw runs, job lists and PR association records
and reconciles them against the published payload. A raw identity absent from the
published output is a difference, a missing job list is missing evidence, and a
published PR without a raw association match stays unverified.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from triton.source_verify import (
    verify_enumeration,
    build_coverage_evidence,
    raw_identities,
    load_job_files,
    published_workflow_attempts,
    published_prs,
)


def run(row_id, attempt=1):
    return {"id": row_id, "run_attempt": attempt}


def workflow(row_id, attempt=1):
    return {"id": row_id, "attempt": attempt}


def batch(row_id, attempt, pr=None):
    b = {"id": f"run:{row_id}:attempt:{attempt}", "workflows": [workflow(row_id, attempt)]}
    if pr is not None:
        b["pr"] = pr
    return b


def write_job(jobs_dir, row_id, attempt=1, rows=None, corrupt=False):
    path = jobs_dir / f"{row_id}-{attempt}.json"
    if corrupt:
        path.write_text("{not json", encoding="utf-8")
    else:
        path.write_text(json.dumps([] if rows is None else rows), encoding="utf-8")
    return path


def write_pr(pr_dir, row_id, pr):
    path = pr_dir / f"{row_id}.json"
    path.write_text(
        json.dumps({"pr": pr, "pr_evidence": {"method": "source_repository+branch+head_sha"}}),
        encoding="utf-8",
    )


class EnumerationVerificationTests(unittest.TestCase):
    def test_fully_reconciled_enumeration_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            pr_dir = Path(tmp) / "pr"
            pr_dir.mkdir()
            runs = [run(1, 1), run(2, 1)]
            for r in runs:
                write_job(jobs_dir, r["id"], r["run_attempt"])
            payload = {"batches": [batch(1, 1, pr=100), batch(2, 1, pr=101)]}
            write_pr(pr_dir, 1, 100)
            write_pr(pr_dir, 2, 101)
            report = verify_enumeration(runs, jobs_dir, payload, pr_dir=pr_dir)
            self.assertEqual(report["status"], "verified")
            for category in ("workflow_attempt_enumeration", "job_enumeration", "pr_association"):
                self.assertEqual(report["categories"][category]["status"], "verified", category)
                self.assertEqual(report["categories"][category]["differences"], 0, category)
                self.assertEqual(report["categories"][category]["missing_evidence"], 0, category)

    def test_raw_run_absent_from_published_is_a_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            runs = [run(1, 1), run(2, 1)]
            for r in runs:
                write_job(jobs_dir, r["id"], r["run_attempt"])
            payload = {"batches": [batch(1, 1, pr=100)]}  # run 2 not published
            report = verify_enumeration(runs, jobs_dir, payload)
            cat = report["categories"]["workflow_attempt_enumeration"]
            self.assertEqual(cat["status"], "differences_found")
            self.assertEqual(cat["differences"], 1)
            self.assertIn("run 2 attempt 1", cat["difference_details"][0])

    def test_missing_job_file_is_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            runs = [run(1, 1), run(2, 1)]
            write_job(jobs_dir, 1, 1)  # run 2 has no job file
            payload = {"batches": [batch(1, 1), batch(2, 1)]}
            report = verify_enumeration(runs, jobs_dir, payload)
            cat = report["categories"]["job_enumeration"]
            self.assertEqual(cat["missing_evidence"], 1)
            self.assertEqual(cat["missing"], [(2, 1)])
            self.assertEqual(report["status"], "partial")

    def test_corrupt_job_file_is_a_difference_not_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            runs = [run(1, 1)]
            write_job(jobs_dir, 1, 1, corrupt=True)
            payload = {"batches": [batch(1, 1)]}
            report = verify_enumeration(runs, jobs_dir, payload)
            cat = report["categories"]["job_enumeration"]
            self.assertEqual(cat["differences"], 1)
            self.assertIn("unreadable", cat["difference_details"][0])

    def test_published_pr_without_raw_match_stays_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            pr_dir = Path(tmp) / "pr"
            pr_dir.mkdir()
            runs = [run(1, 1), run(2, 1)]
            for r in runs:
                write_job(jobs_dir, r["id"], r["run_attempt"])
            payload = {"batches": [batch(1, 1, pr=100), batch(2, 1, pr=2513)]}
            write_pr(pr_dir, 1, 100)  # PR 2513 has no raw resolved association
            report = verify_enumeration(runs, jobs_dir, payload, pr_dir=pr_dir)
            cat = report["categories"]["pr_association"]
            self.assertEqual(cat["missing_evidence"], 1)
            self.assertEqual(cat["missing"], [2513])
            self.assertNotEqual(cat["status"], "verified")

    def test_without_pr_dir_only_two_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            runs = [run(1, 1)]
            write_job(jobs_dir, 1, 1)
            payload = {"batches": [batch(1, 1, pr=100)]}
            report = verify_enumeration(runs, jobs_dir, payload)
            self.assertEqual(set(report["categories"]), {"workflow_attempt_enumeration", "job_enumeration"})
            self.assertEqual(report["status"], "verified")

    def test_helpers_dedupe_and_preserve_identity(self):
        self.assertEqual(raw_identities([run(1, 1), run(1, 1), run(1, 2)]), [(1, 1), (1, 2)])
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            write_job(jobs_dir, 7, 2, rows=[{"name": "x"}])
            self.assertEqual(list(load_job_files(jobs_dir)), [(7, 2)])
        payload = {"batches": [batch(1, 1), batch(1, 2)]}
        self.assertEqual(published_workflow_attempts(payload), {(1, 1), (1, 2)})
        self.assertEqual(published_prs({"batches": [batch(1, 1, pr=5), batch(2, 1)]}), {5})

    def test_evidence_block_records_raw_artifacts_and_window_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            pr_dir = Path(tmp) / "pr"
            pr_dir.mkdir()
            runs_json = {
                "window_start": "2026-10-09T07:43:33Z",
                "window_end": "2026-10-12T07:43:33Z",
                "collected_at": "2026-10-12T08:05:33Z",
                "runs": [run(1, 1), run(2, 1)],
            }
            for r in runs_json["runs"]:
                write_job(jobs_dir, r["id"], r["run_attempt"])
            payload = {
                "window_start": "2026-10-09T07:43:33Z",
                "window_end": "2026-10-12T07:43:33Z",
                "batches": [batch(1, 1, pr=100), batch(2, 1, pr=101)],
            }
            write_pr(pr_dir, 1, 100)
            write_pr(pr_dir, 2, 101)
            doc = build_coverage_evidence(runs_json, jobs_dir, payload, pr_dir=pr_dir)
            self.assertEqual(doc["status"], "verified")
            ev = doc["evidence"]
            self.assertTrue(ev["window_matches_payload"])
            self.assertEqual(ev["raw_run_count"], 2)
            self.assertEqual(ev["job_evidence_files"], 2)
            self.assertEqual(ev["pr_association_files"], 2)
            self.assertEqual(ev["published_batches"], 2)
            self.assertEqual(ev["published_prs"], 2)
            self.assertEqual(set(doc["categories"]), {"workflow_attempt_enumeration", "job_enumeration", "pr_association"})

    def test_evidence_window_mismatch_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            jobs_dir.mkdir()
            runs_json = {"window_start": "A", "window_end": "B", "runs": [run(1, 1)]}
            write_job(jobs_dir, 1, 1)
            payload = {"window_start": "C", "window_end": "D", "batches": [batch(1, 1)]}
            doc = build_coverage_evidence(runs_json, jobs_dir, payload)
            self.assertFalse(doc["evidence"]["window_matches_payload"])


if __name__ == "__main__":
    unittest.main()
