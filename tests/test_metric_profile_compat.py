"""UDR-035-TC02: old-schema/metric-profile compatibility is explicit, never re-labelled.

A snapshot's ``metric_profile`` must resolve to a current profile; an old or
unknown id is rejected (or unavailable) rather than re-labelled to the current
definition, and a semantic change must bump the profile version. Duration
precision and unknown-not-zero are pinned in tests/test_monitor_duration.py.
"""
import unittest

from monitor import metrics as m
from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.report import validate_report

CATALOG = Catalog.load("catalog.json")


def context():
    return RunContext(run_id="run-1", code_sha="0" * 40,
                      cutoff_at="2026-10-09T23:30:00Z", project_ids=["ubs", "triton"])


def report_for(project_id, metric_profile):
    project = CATALOG.project(project_id)
    return {
        "run_id": "run-1", "project_id": project_id, "code_sha": "0" * 40,
        "collector": project["collector"], "metric_profile": metric_profile,
        "task_status": "success", "collection_status": "success", "validation_status": "passed",
        "exit_code": 0,
        "window": {"time_basis": project["window"]["time_basis"],
                   "start_at": "2026-09-09T23:30:00Z" if project_id == "ubs" else "2026-10-06T23:30:00Z",
                   "end_at": "2026-10-09T23:30:00Z"},
        "samples": {"prs": 0}, "data_mode": "fresh",
    }


class MetricProfileCompatTests(unittest.TestCase):
    def test_current_profile_resolves_and_is_not_relabelled(self):
        for project_id in ("ubs", "triton"):
            current = CATALOG.project(project_id)["metric_profile"]
            self.assertEqual(validate_report(report_for(project_id, current), context(), CATALOG), [])

    def test_old_unknown_profile_is_rejected_not_relabelled(self):
        for project_id in ("ubs", "triton"):
            errors = validate_report(
                report_for(project_id, "triton-commit-attempt-v0"), context(), CATALOG)
            self.assertTrue(any("metric_profile" in e for e in errors), errors)

    def test_catalog_profile_id_matches_the_metric_definition_version(self):
        # A semantic change must bump the profile id; the catalog id and the
        # metric's declared profile_version stay in lockstep.
        for project_id in ("ubs", "triton"):
            profile_id = CATALOG.project(project_id)["metric_profile"]
            for metric in m.profile_metrics(profile_id):
                self.assertEqual(metric["profile_version"], profile_id, metric["name"])

    def test_same_profile_id_yields_identical_definitions(self):
        self.assertEqual(m.profile_metrics("ubs-pr-representative-v1"),
                         m.profile_metrics("ubs-pr-representative-v1"))
        self.assertEqual(m.describe_profile("triton-commit-attempt-v1"),
                         m.describe_profile("triton-commit-attempt-v1"))


if __name__ == "__main__":
    unittest.main()