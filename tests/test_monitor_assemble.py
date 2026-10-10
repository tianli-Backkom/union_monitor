"""Tests for the release assembler and publishability rule (T-013)."""

import json
import tempfile
import unittest
from pathlib import Path

from monitor.assemble import assemble_release, is_publishable
from monitor.catalog import Catalog
from monitor.context import RunContext

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")


def context():
    return RunContext(
        run_id="synthetic-20261010-0730-attempt-1",
        code_sha="9aec47355689c243f3f8c35cab40fd275c0e8441",
        cutoff_at="2026-10-09T23:30:00Z",
        project_ids=["ubs", "triton"],
    )


def windows():
    return {
        "ubs": {"time_basis": "pr_created_at", "start_at": "2026-09-09T23:30:00Z", "end_at": "2026-10-09T23:30:00Z"},
        "triton": {"time_basis": "batch_started_at", "start_at": "2026-10-06T23:30:00Z", "end_at": "2026-10-09T23:30:00Z"},
    }


def fresh_report(pid, task_status="success"):
    project = CATALOG.project(pid)
    return {
        "run_id": "synthetic-20261010-0730-attempt-1",
        "project_id": pid,
        "code_sha": "9aec47355689c243f3f8c35cab40fd275c0e8441",
        "collector": project["collector"],
        "metric_profile": project["metric_profile"],
        "task_status": task_status,
        "collection_status": "success",
        "validation_status": "passed",
        "exit_code": 0,
        "window": windows()[pid],
        "collected_at": "2026-10-10T00:10:00Z",
        "samples": {"prs": 12, "batches": 28},
        "snapshot_version": f"synthetic-{pid}-20261010",
        "snapshot_path": f"data/projects/{pid}/snapshots/synthetic-{pid}-20261010.json",
        "snapshot_sha256": "a" * 64,
        "artifact": f"project-bundle-{pid}-synthetic-20261010-0730-attempt-1",
        "errors": [],
    }


def baseline_release():
    return {
        "release_id": "synthetic-release-20261009-0830",
        "release_status": "verified",
        "projects": {
            "triton": {
                "task_status": "success",
                "data_mode": "fresh",
                "snapshot_version": "synthetic-triton-20261009",
                "snapshot_path": "data/projects/triton/snapshots/synthetic-triton-20261009.json",
                "snapshot_sha256": "b" * 64,
                "collected_at": "2026-10-09T00:10:00Z",
                "window": {"time_basis": "batch_started_at", "start_at": "2026-10-05T23:30:00Z", "end_at": "2026-10-08T23:30:00Z"},
            }
        },
    }


class AssembleTests(unittest.TestCase):
    def test_all_fresh_projects_produce_fresh_entries(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs"), "triton": fresh_report("triton")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertEqual(release["projects"]["ubs"]["data_mode"], "fresh")
        self.assertEqual(release["projects"]["triton"]["data_mode"], "fresh")
        self.assertEqual(release["projects"]["ubs"]["snapshot_sha256"], "a" * 64)

    def test_failed_project_falls_back_to_baseline_keeping_old_data(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs"), "triton": None},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
            baseline=baseline_release(), baseline_release_id="synthetic-release-20261009-0830",
        )
        triton = release["projects"]["triton"]
        self.assertEqual(triton["data_mode"], "fallback")
        self.assertEqual(triton["task_status"], "failed")
        self.assertEqual(triton["snapshot_sha256"], "b" * 64)
        self.assertEqual(triton["collected_at"], "2026-10-09T00:10:00Z")
        self.assertEqual(triton["window"]["end_at"], "2026-10-08T23:30:00Z")

    def test_failed_project_without_baseline_is_unavailable(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs"), "triton": None},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        triton = release["projects"]["triton"]
        self.assertEqual(triton["data_mode"], "unavailable")
        self.assertNotIn("snapshot_sha256", triton)

    def test_missing_report_has_an_explicit_error(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertTrue(release["projects"]["triton"]["error"])

    def test_partial_with_valid_data_stays_fresh(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs", task_status="partial"), "triton": fresh_report("triton")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertEqual(release["projects"]["ubs"]["data_mode"], "fresh")
        self.assertEqual(release["projects"]["ubs"]["task_status"], "partial")


class PublishabilityTests(unittest.TestCase):
    def test_at_least_one_fresh_and_all_explicit_is_publishable(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": fresh_report("ubs"), "triton": None},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
            baseline=baseline_release(),
        )
        self.assertTrue(is_publishable(release))

    def test_no_fresh_data_is_not_publishable(self):
        release = assemble_release(
            CATALOG, context(),
            {"ubs": None, "triton": None},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
            baseline=baseline_release(),
        )
        self.assertFalse(is_publishable(release))


class AssembleCliTests(unittest.TestCase):
    def test_assemble_cli_writes_a_manifest_with_publishable_flag(self):
        from monitor.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            inputs = Path(tmp) / "inputs.json"
            inputs.write_text(json.dumps({"projects": {"ubs": fresh_report("ubs"), "triton": None}}), encoding="utf-8")
            out = Path(tmp) / "release.json"
            code = main([
                "assemble",
                "--catalog", str(ROOT / "catalog.json"),
                "--context", self._context_file(tmp),
                "--inputs", str(inputs),
                "--release-id", "rel-1",
                "--published-at", "2026-10-10T00:30:00Z",
                "--out", str(out),
            ])
            self.assertEqual(code, 0)
            manifest = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(manifest["release_id"], "rel-1")
            self.assertIn("publishable", manifest)
            self.assertTrue(manifest["publishable"])

    def _context_file(self, tmp):
        path = Path(tmp) / "context.json"
        path.write_text(json.dumps(context().as_dict()), encoding="utf-8")
        return str(path)


if __name__ == "__main__":
    unittest.main()