"""Health checks detect overdue data without inventing scheduled successes."""
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from scripts.published_health import deadlines, check_freshness, inspect_site


def clock(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PublishedFreshnessTests(unittest.TestCase):
    def test_overnight_has_no_false_missed_morning_refresh(self):
        now = clock("2026-10-11T23:00:00+08:00")
        due = deadlines(now)
        self.assertEqual(due["triton"], clock("2026-10-11T20:00:00+08:00"))
        self.assertEqual(due["ubs"], clock("2026-10-11T07:30:00+08:00"))
        self.assertEqual(check_freshness({"ubs": "2026-10-11T03:00:00Z",
                                         "triton": "2026-10-11T12:54:59Z"}, now), [])

    def test_ongoing_run_gets_its_actual_timeout_and_delay_allowance(self):
        due = deadlines(clock("2026-10-11T08:30:00+08:00"))
        self.assertEqual(due["ubs"], clock("2026-10-10T07:30:00+08:00"))
        self.assertEqual(due["triton"], clock("2026-10-10T20:00:00+08:00"))

    def test_successful_noon_refresh_is_current_at_1430(self):
        due = deadlines(clock("2026-10-11T14:30:00+08:00"))
        self.assertEqual(due["triton"], clock("2026-10-11T12:00:00+08:00"))

    def test_missed_noon_refresh_reports_project_and_deadline(self):
        errors = check_freshness({"ubs": "2026-10-11T03:00:00Z",
                                  "triton": "2026-10-11T00:30:00Z"},
                                 clock("2026-10-11T14:30:00+08:00"))
        self.assertEqual(len(errors), 1)
        self.assertIn("triton", errors[0])

    def test_missing_naive_or_future_time_never_passes(self):
        now = clock("2026-10-11T14:30:00+08:00")
        for value in (None, "2026-10-11T13:00:00", "not-a-date", "2026-10-12T00:00:00Z"):
            with self.subTest(value=value):
                self.assertTrue(check_freshness({"ubs": "2026-10-11T03:00:00Z",
                                                 "triton": value}, now))


class PublishedHealthTests(unittest.TestCase):
    def inspect(self, status="success", collected_at="2026-10-11T03:00:00Z", problems=None, path="repos/a.json"):
        data = {
            "ubs-manifest.json": {"files": {path: "a" * 64}},
            "triton-manifest.json": {},
            "repositories.json": {"generated_at": "2026-10-11T03:00:00Z", "repositories": [
                {"name": "a", "status": status, "meta": {"collected_at": collected_at, "errors": []}}]},
            "triton.json": {"collected_at": "2026-10-11T12:30:00Z"},
        }
        def fetch(url):
            return json.dumps(data[url.rsplit("/", 1)[-1]]).encode()
        with patch("scripts.published_health.verify_deployment.fetch", side_effect=fetch), patch(
                "scripts.published_health.verify_deployment.check_all", return_value=({}, problems or [])):
            return inspect_site("https://example.test/monitor", clock("2026-10-11T23:00:00+08:00"))

    def test_healthy_check_does_not_invent_source_completeness(self):
        report = self.inspect()
        self.assertTrue(report["success"])
        self.assertEqual(report["scope"], "public integrity and freshness")

    def test_public_fingerprint_error_fails_health(self):
        self.assertFalse(self.inspect(problems=["triton fingerprint mismatch"])["success"])

    def test_index_timestamp_cannot_hide_failed_or_stale_repository(self):
        for kwargs in ({"status": "failed"}, {"collected_at": "2026-10-10T03:00:00Z"}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(self.inspect(**kwargs)["success"])

    def test_manifest_path_cannot_escape_public_directory(self):
        for path in ("../token", "/absolute", "https://elsewhere.test/data", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.inspect(path=path)

    def test_health_workflow_is_read_only_and_runs_after_refresh_grace(self):
        source = (Path(__file__).resolve().parents[1] / ".github/workflows/published-health.yml").read_text()
        for required in ("45 1,5,9,11,13 * * *", "0 3 * * *", "-m scripts.published_health", "contents: read", "always()"):
            self.assertIn(required, source)
        for forbidden in ("secrets.", "pages: write", "id-token: write", "deploy-pages", "triton.dashboard", "collect.py"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
