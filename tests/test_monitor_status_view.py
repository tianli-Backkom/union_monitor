"""P-013: three-axis status view model tests."""

import unittest

from monitor.status_view import data_axis, project_status, task_axis, time_axis


class TaskAxisTests(unittest.TestCase):
    def test_valid_status_preserved(self):
        axis = task_axis({"task_status": "partial", "run_id": "r1", "code_sha": "abc",
                          "window": {"end_at": "2026-10-09T23:30:00Z"},
                          "started_at": "s", "finished_at": "f", "exit_code": 1, "error": None})
        self.assertEqual(axis["task_status"], "partial")
        self.assertEqual(axis["cutoff_at"], "2026-10-09T23:30:00Z")
        self.assertEqual(axis["exit_code"], 1)

    def test_invalid_status_normalizes_to_failed(self):
        self.assertEqual(task_axis({"task_status": "bogus"})["task_status"], "failed")
        self.assertEqual(task_axis(None)["task_status"], "failed")


class DataAxisTests(unittest.TestCase):
    def test_fallback_carries_old_snapshot_identity(self):
        entry = {"data_mode": "fallback", "snapshot_version": "old-v3", "snapshot_sha256": "aa" * 32,
                 "metric_profile": "ubs-pr-representative-v1", "source_release_id": "r-old"}
        axis = data_axis(entry, {"validation_status": "passed"})
        self.assertEqual(axis["data_mode"], "fallback")
        self.assertEqual(axis["snapshot_version"], "old-v3")
        self.assertEqual(axis["validation_status"], "passed")

    def test_unknown_mode_normalizes_to_unavailable(self):
        self.assertEqual(data_axis({"data_mode": "weird"})["data_mode"], "unavailable")
        self.assertEqual(data_axis(None)["data_mode"], "unavailable")


class TimeAxisTests(unittest.TestCase):
    def test_data_time_is_distinct_from_publish_time(self):
        axis = time_axis({"collected_at": "2026-10-09T00:10:00Z"},
                         published_at="2026-10-10T07:45:00Z",
                         schedule_time="2026-10-10T07:30:00Z")
        self.assertEqual(axis["collected_at"], "2026-10-09T00:10:00Z")
        self.assertEqual(axis["published_at"], "2026-10-10T07:45:00Z")
        self.assertTrue(axis["delayed"])

    def test_delayed_is_none_without_schedule(self):
        axis = time_axis({"collected_at": "x"}, published_at="y")
        self.assertIsNone(axis["delayed"])


class ProjectStatusTests(unittest.TestCase):
    def test_failed_round_reuses_old_data_without_relabelling(self):
        # A failed round falls back to the old snapshot: failed + fallback + old time.
        report = {"task_status": "failed", "run_id": "run-2", "code_sha": "0" * 40,
                  "started_at": "2026-10-10T07:30:00Z", "finished_at": "2026-10-10T07:35:00Z",
                  "exit_code": 1, "error": "source down"}
        entry = {"data_mode": "fallback", "snapshot_version": "old-v3", "snapshot_sha256": "bb" * 32,
                 "collected_at": "2026-10-09T00:10:00Z",
                 "window": {"time_basis": "pr_created_at",
                            "start_at": "2026-09-09T00:00:00Z", "end_at": "2026-10-09T23:30:00Z"}}
        status = project_status(report, entry, published_at="2026-10-10T08:00:00Z",
                                schedule_time="2026-10-10T07:30:00Z")
        self.assertEqual(status["task_result"]["task_status"], "failed")
        self.assertEqual(status["data_version"]["data_mode"], "fallback")
        self.assertEqual(status["data_time"]["collected_at"], "2026-10-09T00:10:00Z")
        self.assertEqual(status["data_time"]["window"]["end_at"], "2026-10-09T23:30:00Z")
        # The old data time is never conflated with the publish time.
        self.assertNotEqual(status["data_time"]["collected_at"], status["data_time"]["published_at"])

    def test_unavailable_project_has_no_data_time(self):
        status = project_status({"task_status": "failed", "exit_code": 1},
                                {"data_mode": "unavailable", "error": "no baseline"},
                                published_at="2026-10-10T08:00:00Z")
        self.assertEqual(status["data_version"]["data_mode"], "unavailable")
        self.assertIsNone(status["data_time"]["collected_at"])


if __name__ == "__main__":
    unittest.main()