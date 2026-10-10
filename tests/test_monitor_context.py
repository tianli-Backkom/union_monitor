"""Contract tests for the frozen run context (T-003, AC-003)."""

import unittest

from monitor.context import RunContext, iso_utc, utc_time


class RunContextTests(unittest.TestCase):
    def make_context(self, **overrides):
        values = dict(
            run_id="synthetic-20261010-0730-attempt-1",
            code_sha="9aec47355689c243f3f8c35cab40fd275c0e8441",
            cutoff_at="2026-10-09T23:30:00Z",
            scheduled_for="2026-10-10T07:30:00+08:00",
            started_at="2026-10-09T23:30:00Z",
            project_ids=["ubs", "triton"],
            artifact_root="artifacts/synthetic-20261010-0730-attempt-1",
        )
        values.update(overrides)
        return RunContext(**values)

    def test_window_spans_exactly_the_declared_hours(self):
        context = self.make_context()
        window = context.window(720)
        start = utc_time(window["start_at"])
        end = utc_time(window["end_at"])
        self.assertEqual((end - start).total_seconds(), 720 * 3600)

    def test_fresh_end_at_equals_cutoff(self):
        context = self.make_context(cutoff_at="2026-10-09T23:30:00Z")
        window = context.window(72)
        self.assertEqual(window["end_at"], "2026-10-09T23:30:00Z")

    def test_window_for_reads_time_basis_from_project(self):
        context = self.make_context()
        project = {
            "project_id": "ubs",
            "window": {"time_basis": "pr_created_at", "hours": 720},
        }
        window = context.window_for(project)
        self.assertEqual(window["time_basis"], "pr_created_at")
        self.assertEqual(window["end_at"], "2026-10-09T23:30:00Z")

    def test_cutoff_is_frozen_and_naive_times_are_rejected(self):
        with self.assertRaises(ValueError):
            self.make_context(cutoff_at="2026-10-09T23:30:00")  # no timezone

    def test_requires_run_id_and_code_sha(self):
        with self.assertRaises(ValueError):
            RunContext(run_id="", code_sha="abc", cutoff_at="2026-10-09T23:30:00Z")
        with self.assertRaises(ValueError):
            RunContext(run_id="r", code_sha="", cutoff_at="2026-10-09T23:30:00Z")

    def test_window_requires_positive_hours(self):
        context = self.make_context()
        with self.assertRaises(ValueError):
            context.window(0)

    def test_iso_utc_renders_z_suffix(self):
        from datetime import datetime, timezone
        value = datetime(2026, 10, 9, 23, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(iso_utc(value), "2026-10-09T23:30:00Z")


if __name__ == "__main__":
    unittest.main()