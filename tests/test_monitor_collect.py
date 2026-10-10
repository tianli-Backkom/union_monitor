"""T-012: collect dispatch and honest collection-report building tests."""

import unittest
from pathlib import Path

from monitor.adapters import AdapterError, resolve
from monitor.catalog import Catalog
from monitor.collect import CollectError, build_report, collect_project
from monitor.context import RunContext

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")


def make_context():
    return RunContext(run_id="run-1", code_sha="0" * 40, cutoff_at="2026-10-10T00:00:00Z")


class ResolveAdapterTests(unittest.TestCase):
    def test_known_but_unimplemented_adapter_is_a_clear_error(self):
        # The catalog maps ubs -> monitor.adapters.gitcode_jenkins, which does
        # not exist yet; resolution must fail loudly, never silently.
        project = CATALOG.project("ubs")
        with self.assertRaises(AdapterError):
            resolve(CATALOG, project)

    def test_entrypoint_surfaces_the_catalog_path(self):
        from monitor.adapters import entrypoint
        self.assertEqual(entrypoint(CATALOG, CATALOG.project("ubs")), "monitor.adapters.gitcode_jenkins")


class CollectProjectTests(unittest.TestCase):
    def test_missing_adapter_yields_honest_failed_report(self):
        context = make_context()
        report = collect_project(CATALOG, context, "ubs", "/tmp/isolated",
                                 now=lambda: "2026-10-10T00:00:00Z")
        self.assertEqual(report["task_status"], "failed")
        self.assertEqual(report["collection_status"], "failed")
        self.assertEqual(report["validation_status"], "failed")
        self.assertEqual(report["exit_code"], 1)
        self.assertTrue(report["error"])
        self.assertIn(report["run_id"], "run-1")

    def test_injected_adapter_success_is_preserved(self):
        context = make_context()
        calls = []

        def adapter(project, ctx, work_dir):
            calls.append((project["project_id"], ctx.run_id, work_dir))
            return {
                "collection_status": "success",
                "collected_at": "2026-10-10T00:10:00Z",
                "window": {"time_basis": "pr_created_at",
                           "start_at": "2026-09-09T00:00:00Z",
                           "end_at": "2026-10-09T23:30:00Z"},
                "samples": {"prs": 0, "batches": 0, "valid_e2e_prs": 0},
                "coverage": {"repositories_expected": 9, "repositories_available": 9},
                "snapshot_version": "v1",
                "snapshot_sha256": "a" * 64,
            }

        report = collect_project(CATALOG, context, "ubs", "/tmp/w",
                                 adapter=adapter, now=lambda: "2026-10-10T00:20:00Z")
        self.assertEqual(report["task_status"], "success")
        self.assertEqual(report["collection_status"], "success")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["project_id"], "ubs")
        self.assertEqual(report["run_id"], "run-1")
        self.assertEqual(report["samples"]["prs"], 0)
        self.assertEqual(calls, [("ubs", "run-1", "/tmp/w")])

    def test_adapter_exception_maps_to_failed(self):
        context = make_context()

        def adapter(project, ctx, work_dir):
            raise RuntimeError("boom")

        report = collect_project(CATALOG, context, "ubs", "/tmp/w",
                                 adapter=adapter, now=lambda: "2026-10-10T00:00:00Z")
        self.assertEqual(report["task_status"], "failed")
        self.assertIn("boom", report["error"])

    def test_adapter_timeout_maps_to_timeout(self):
        context = make_context()

        def adapter(project, ctx, work_dir):
            raise TimeoutError("timed out")

        report = collect_project(CATALOG, context, "triton", "/tmp/w",
                                 adapter=adapter, now=lambda: "2026-10-10T00:00:00Z")
        self.assertEqual(report["task_status"], "timeout")
        self.assertIn("timed out", report["error"])

    def test_non_dict_adapter_result_is_failed(self):
        context = make_context()
        report = collect_project(CATALOG, context, "ubs", "/tmp/w",
                                 adapter=lambda p, c, w: "not-a-dict",
                                 now=lambda: "2026-10-10T00:00:00Z")
        self.assertEqual(report["task_status"], "failed")
        self.assertIn("str", report["error"])

    def test_unknown_project_raises(self):
        context = make_context()
        with self.assertRaises(CollectError):
            collect_project(CATALOG, context, "nope", "/tmp/w")


class BuildReportTests(unittest.TestCase):
    def test_partial_marks_failed(self):
        base = {"run_id": "r", "project_id": "p", "code_sha": "c", "collector": "x",
                "metric_profile": "m", "started_at": "s"}
        report = build_report(base, {"collection_status": "partial"}, "f")
        self.assertEqual(report["task_status"], "failed")
        self.assertEqual(report["collection_status"], "failed")
        self.assertEqual(report["exit_code"], 1)

    def test_identity_fields_cannot_be_overridden_by_adapter(self):
        base = {"run_id": "r", "project_id": "p", "code_sha": "c", "collector": "x",
                "metric_profile": "m", "started_at": "s"}
        report = build_report(base, {"collection_status": "success", "run_id": "ADULTERATED"}, "f")
        self.assertEqual(report["run_id"], "r")


if __name__ == "__main__":
    unittest.main()