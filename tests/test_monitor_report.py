"""Tests for the collection report contract and data-mode classification (T-012/T-013)."""

import unittest
from pathlib import Path

from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.report import (
    choose_data_mode,
    is_legal_zero,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")


def context(cutoff="2026-10-09T23:30:00Z"):
    return RunContext(
        run_id="synthetic-20261010-0730-attempt-1",
        code_sha="9aec47355689c243f3f8c35cab40fd275c0e8441",
        cutoff_at=cutoff,
        project_ids=["ubs", "triton"],
    )


def valid_fresh_report(project_id="ubs", hours=720):
    window = {
        "time_basis": "pr_created_at" if project_id == "ubs" else "batch_started_at",
        "start_at": "2026-09-09T23:30:00Z" if project_id == "ubs" else "2026-10-06T23:30:00Z",
        "end_at": "2026-10-09T23:30:00Z",
    }
    return {
        "run_id": "synthetic-20261010-0730-attempt-1",
        "project_id": project_id,
        "code_sha": "9aec47355689c243f3f8c35cab40fd275c0e8441",
        "collector": CATALOG.project(project_id)["collector"],
        "metric_profile": CATALOG.project(project_id)["metric_profile"],
        "task_status": "success",
        "collection_status": "success",
        "validation_status": "passed",
        "exit_code": 0,
        "window": window,
        "samples": {"prs": 0, "batches": 0},
        "data_mode": "fresh",
    }


class DataModeTests(unittest.TestCase):
    def test_success_with_fresh_bundle_is_fresh(self):
        self.assertEqual(choose_data_mode("success", has_fresh_bundle=True, has_trusted_fallback=False), "fresh")

    def test_partial_with_fresh_bundle_is_still_fresh(self):
        self.assertEqual(choose_data_mode("partial", has_fresh_bundle=True, has_trusted_fallback=False), "fresh")

    def test_failed_with_trusted_fallback_is_fallback(self):
        self.assertEqual(choose_data_mode("failed", has_fresh_bundle=False, has_trusted_fallback=True), "fallback")

    def test_failed_without_fallback_is_unavailable(self):
        self.assertEqual(choose_data_mode("failed", has_fresh_bundle=False, has_trusted_fallback=False), "unavailable")

    def test_thin_success_never_pretends_to_be_fresh(self):
        self.assertEqual(choose_data_mode("success", has_fresh_bundle=False, has_trusted_fallback=True), "fallback")
        self.assertEqual(choose_data_mode("success", has_fresh_bundle=False, has_trusted_fallback=False), "unavailable")

    def test_invalid_task_status_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_data_mode("exploded", has_fresh_bundle=True, has_trusted_fallback=False)


class ReportValidationTests(unittest.TestCase):
    def test_valid_fresh_report_has_no_errors(self):
        self.assertEqual(validate_report(valid_fresh_report(), context(), CATALOG), [])

    def test_run_id_mismatch_is_reported(self):
        report = valid_fresh_report()
        report["run_id"] = "other"
        errors = validate_report(report, context(), CATALOG)
        self.assertTrue(any("run_id" in e for e in errors))

    def test_code_sha_mismatch_is_reported(self):
        report = valid_fresh_report()
        report["code_sha"] = "deadbeef"
        self.assertTrue(any("code_sha" in e for e in validate_report(report, context(), CATALOG)))

    def test_unknown_project_is_reported(self):
        report = valid_fresh_report()
        report["project_id"] = "nope"
        self.assertTrue(any("unknown project" in e for e in validate_report(report, context(), CATALOG)))

    def test_collector_mismatch_is_reported(self):
        report = valid_fresh_report()
        report["collector"] = "wrong-v1"
        self.assertTrue(any("collector" in e for e in validate_report(report, context(), CATALOG)))

    def test_window_time_basis_mismatch_is_reported(self):
        report = valid_fresh_report()
        report["window"]["time_basis"] = "batch_started_at"
        self.assertTrue(any("time_basis" in e for e in validate_report(report, context(), CATALOG)))

    def test_fresh_end_at_must_equal_cutoff(self):
        report = valid_fresh_report()
        report["window"]["end_at"] = "2026-10-09T22:00:00Z"
        self.assertTrue(any("end_at must equal" in e for e in validate_report(report, context(), CATALOG)))

    def test_fresh_span_must_match_declared_hours(self):
        report = valid_fresh_report()
        report["window"]["start_at"] = "2026-10-01T23:30:00Z"  # only 8 days
        self.assertTrue(any("span" in e for e in validate_report(report, context(), CATALOG)))

    def test_fallback_window_must_precede_cutoff(self):
        report = valid_fresh_report()
        report["task_status"] = "failed"
        report["collection_status"] = "failed"
        report["validation_status"] = "failed"
        report["data_mode"] = "fallback"
        report["window"]["end_at"] = "2026-10-09T23:30:00Z"  # equals cutoff -> invalid
        self.assertTrue(any("fallback" in e for e in validate_report(report, context(), CATALOG)))

    def test_success_with_nonzero_exit_is_reported(self):
        report = valid_fresh_report()
        report["exit_code"] = 1
        self.assertTrue(any("exit_code" in e for e in validate_report(report, context(), CATALOG)))

    def test_invalid_task_status_is_reported(self):
        report = valid_fresh_report()
        report["task_status"] = "mostly-done"
        self.assertTrue(any("task_status" in e for e in validate_report(report, context(), CATALOG)))

    def test_triton_window_span_is_72h(self):
        report = valid_fresh_report(project_id="triton", hours=72)
        self.assertEqual(validate_report(report, context(), CATALOG), [])


class LegalZeroTests(unittest.TestCase):
    def test_collected_and_validated_zero_sample_is_legal(self):
        self.assertTrue(is_legal_zero(valid_fresh_report()))

    def test_unvalidated_zero_sample_is_not_legal(self):
        report = valid_fresh_report()
        report["validation_status"] = "failed"
        self.assertFalse(is_legal_zero(report))

    def test_missing_samples_object_is_not_legal_zero(self):
        report = valid_fresh_report()
        del report["samples"]
        self.assertFalse(is_legal_zero(report))


if __name__ == "__main__":
    unittest.main()