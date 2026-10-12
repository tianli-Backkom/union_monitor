"""UDR-032-TC02: unified run report binding with honest unknowns and rejection."""
import unittest
from pathlib import Path

from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.run_report import build_run_report

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")

RUN_ID = "synthetic-20261010-0730-attempt-1"
CODE_SHA = "9aec47355689c243f3f8c35cab40fd275c0e8441"
CUTOFF = "2026-10-09T23:30:00Z"


def context():
    return RunContext(run_id=RUN_ID, code_sha=CODE_SHA, cutoff_at=CUTOFF,
                      project_ids=["ubs", "triton"])


def fresh_report(pid="ubs", hours=720):
    return {
        "run_id": RUN_ID, "project_id": pid, "code_sha": CODE_SHA,
        "collector": CATALOG.project(pid)["collector"],
        "metric_profile": CATALOG.project(pid)["metric_profile"],
        "task_status": "success", "collection_status": "success",
        "validation_status": "passed", "exit_code": 0,
        "window": {"time_basis": CATALOG.project(pid)["window"]["time_basis"],
                   "start_at": "2026-09-09T23:30:00Z" if pid == "ubs" else "2026-10-06T23:30:00Z",
                   "end_at": CUTOFF},
        "samples": {"prs": 0}, "data_mode": "fresh",
        "collected_at": "2026-10-10T00:10:00Z",
        "snapshot_version": "v1", "snapshot_sha256": "a" * 64,
    }


class RunReportTests(unittest.TestCase):
    def test_missing_report_is_unknown_not_failed_or_zero(self):
        report = build_run_report(context(), CATALOG, {"ubs": None, "triton": None})
        for pid in ("ubs", "triton"):
            project = report["projects"][pid]
            self.assertEqual(project["task_result"]["task_status"], "unknown")
            self.assertEqual(project["data_version"]["data_mode"], "unknown")
            self.assertEqual(project["data_time"]["collected_at"], "unknown")
        self.assertEqual(report["run_id"], RUN_ID)

    def test_inconsistent_report_is_rejected_not_trusted(self):
        bad = fresh_report("ubs")
        bad["run_id"] = "other-run"
        report = build_run_report(context(), CATALOG, {"ubs": bad, "triton": None})
        self.assertTrue(report["projects"]["ubs"]["rejected"])
        self.assertTrue(any("run_id" in p for p in report["projects"]["ubs"]["problems"]))

    def test_fresh_report_has_three_independent_axes(self):
        report = build_run_report(context(), CATALOG,
                                  {"ubs": fresh_report("ubs"), "triton": fresh_report("triton", 72)},
                                  published_at="2026-10-10T07:45:00Z",
                                  schedule_time="2026-10-10T07:30:00Z")
        ubs = report["projects"]["ubs"]
        self.assertEqual(ubs["task_result"]["task_status"], "success")
        self.assertEqual(ubs["data_version"]["data_mode"], "fresh")
        self.assertEqual(ubs["data_time"]["collected_at"], "2026-10-10T00:10:00Z")
        self.assertNotEqual(ubs["data_time"]["collected_at"], ubs["data_time"]["published_at"])

    def test_old_window_fallback_is_viewable_but_not_same_window(self):
        old_entry = {"data_mode": "fallback", "snapshot_version": "old-v3",
                     "snapshot_sha256": "b" * 64, "metric_profile": "ubs-pr-representative-v1",
                     "collected_at": "2026-09-10T00:10:00Z",
                     "window": {"time_basis": "pr_created_at",
                                "start_at": "2026-09-08T23:30:00Z", "end_at": "2026-09-09T23:30:00Z"}}
        failed = fresh_report("ubs")
        failed.update(task_status="failed", collection_status="failed",
                      validation_status="failed", exit_code=1)
        report = build_run_report(context(), CATALOG,
                                  {"ubs": failed, "triton": None},
                                  entries={"ubs": old_entry})
        ubs = report["projects"]["ubs"]
        self.assertEqual(ubs["task_result"]["task_status"], "failed")
        self.assertEqual(ubs["data_version"]["data_mode"], "fallback")
        # Old window stays before this round's cutoff; never same-window.
        self.assertLess(ubs["data_time"]["window"]["end_at"], CUTOFF)

    def test_reload_is_read_only(self):
        report = build_run_report(context(), CATALOG, {})
        self.assertTrue(report["reload_read_only"])


if __name__ == "__main__":
    unittest.main()