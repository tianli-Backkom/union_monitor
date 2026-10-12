"""UDR-024: unified production scheduling, shared cutoff and wait-for-all."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.orchestrate import TransientCollectError, retry_collect, run_round

ROOT = Path(__file__).resolve().parents[1]

RUN_ID = "synthetic-20261010-0730-attempt-1"
CODE_SHA = "9aec47355689c243f3f8c35cab40fd275c0e8441"
CUTOFF = "2026-10-09T23:30:00Z"


class VirtualClock:
    def __init__(self, start=0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def synthetic_catalog(with_third_disabled=True):
    projects = [
        {"project_id": "ubs", "display_name": "openEuler UBS", "enabled": True,
         "collector": "gitcode-jenkins-v1", "metric_profile": "ubs-pr-representative-v1",
         "view_profile": "pr-representative-v1",
         "window": {"time_basis": "pr_created_at", "hours": 720}, "timeout_minutes": 180,
         "repositories": [{"repository_id": f"gitcode:openeuler/r{i}", "target_branches": ["master"]}
                          for i in range(1, 10)]},
        {"project_id": "triton", "display_name": "Triton-Ascend", "enabled": True,
         "collector": "github-actions-v1", "metric_profile": "triton-commit-attempt-v1",
         "view_profile": "commit-attempt-v1",
         "window": {"time_basis": "batch_started_at", "hours": 72}, "timeout_minutes": 60,
         "repositories": [{"repository_id": "github:triton-lang/triton-ascend",
                           "target_branches": ["main", "main-dev"]}]},
    ]
    if with_third_disabled:
        projects.append({"project_id": "third", "display_name": "Third Community", "enabled": False,
                         "collector": "github-actions-v1", "metric_profile": "triton-commit-attempt-v1",
                         "view_profile": "commit-attempt-v1",
                         "window": {"time_basis": "batch_started_at", "hours": 25}, "timeout_minutes": 45,
                         "repositories": [{"repository_id": "github:example/other",
                                           "target_branches": ["main"]}]})
    return Catalog.from_dict({
        "schema_version": 1,
        "schedule": {"timezone": "Asia/Shanghai", "local_time": "07:30", "frequency": "daily"},
        "source_instances": {"gitcode": {"provider": "gitcode", "base_url": "https://gitcode.com"},
                             "github": {"provider": "github", "base_url": "https://github.com"}},
        "collectors": {"gitcode-jenkins-v1": {"entrypoint": "monitor.adapters.gitcode_jenkins", "cache_version": 1},
                       "github-actions-v1": {"entrypoint": "monitor.adapters.github_actions", "cache_version": 1}},
        "metric_profiles": {"ubs-pr-representative-v1": {"sample_unit": "pr_representative", "duration_unit": "ms"},
                            "triton-commit-attempt-v1": {"sample_unit": "commit_or_attempt_batch", "duration_unit": "ms"}},
        "view_profiles": {"pr-representative-v1": {"capabilities": ["repository_comparison", "csv"]},
                          "commit-attempt-v1": {"capabilities": ["batch_trend", "csv"]}},
        "projects": projects,
    })


def context():
    return RunContext(run_id=RUN_ID, code_sha=CODE_SHA, cutoff_at=CUTOFF,
                      project_ids=["ubs", "triton"])


def ok_report(pid):
    return {"project_id": pid, "task_status": "success", "collection_status": "success",
            "validation_status": "passed", "exit_code": 0, "run_id": RUN_ID, "code_sha": CODE_SHA,
            "collected_at": "2026-10-10T00:10:00Z"}


class UnifiedProductionTests(unittest.TestCase):
    def test_tc01_enabled_projects_only_and_single_collector_per_project(self):
        catalog = synthetic_catalog()
        calls = []
        collectors = {
            "ubs": lambda project, ctx, wd: calls.append("ubs") or ok_report("ubs"),
            "triton": lambda project, ctx, wd: calls.append("triton") or ok_report("triton"),
            "third": lambda project, ctx, wd: calls.append("third") or ok_report("third"),
        }
        clock = VirtualClock()
        reports, aggregate = run_round(catalog, context(), collectors=collectors,
                                       clock=clock, sleep=clock.sleep)
        # Exactly the two enabled projects; the nine UBS repos are one unit, and
        # the disabled third project is never collected.
        self.assertEqual(set(reports), {"ubs", "triton"})
        self.assertEqual(calls, ["ubs", "triton"])
        self.assertEqual(aggregate["cutoff_at"], CUTOFF)
        self.assertTrue(aggregate["all_terminal"])
        self.assertEqual(catalog.project("ubs")["window"]["hours"], 720)
        self.assertEqual(catalog.project("triton")["window"]["hours"], 72)
        self.assertEqual(catalog.project("third")["window"]["hours"], 25)  # not rounded to 24

    def test_tc01_single_production_schedule(self):
        catalog = synthetic_catalog()
        self.assertEqual(catalog.data["schedule"]["frequency"], "daily")
        # The production workflow is a single daily entry (legacy 30 23 cron).
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("30 23 * * *"), 1)

    def test_tc02_retry_budget_recovers_and_isolates_failures(self):
        catalog = synthetic_catalog()
        clock = VirtualClock()
        attempts = []

        def triton_collector(project, ctx, wd):
            def fn(attempt):
                attempts.append(attempt)
                if attempt < 3:
                    raise TransientCollectError("rate limited")
                return ok_report("triton")
            return retry_collect(fn, max_attempts=3, backoff=0.25, clock=clock, sleep=clock.sleep)

        reports, aggregate = run_round(
            catalog, context(),
            collectors={"ubs": lambda p, c, w: ok_report("ubs"), "triton": triton_collector},
            clock=clock, sleep=clock.sleep,
        )
        self.assertEqual(reports["ubs"]["task_status"], "success")
        self.assertEqual(reports["triton"]["task_status"], "success")
        self.assertEqual(attempts, [1, 2, 3])  # recovered on the 3rd attempt
        self.assertTrue(aggregate["all_terminal"])

    def test_tc02_persistent_failure_never_exceeds_max_attempts(self):
        clock = VirtualClock()
        attempts = []

        def fn(attempt):
            attempts.append(attempt)
            raise TransientCollectError("still limited")

        with self.assertRaises(TransientCollectError):
            retry_collect(fn, max_attempts=3, backoff=0.25, clock=clock, sleep=clock.sleep)
        self.assertEqual(attempts, [1, 2, 3])

    def test_tc02_project_deadline_is_config_driven_not_real_waiting(self):
        catalog = synthetic_catalog()
        clock = VirtualClock()

        def slow_collector(project, ctx, wd):
            clock.sleep(100 * 60)  # advance past the 60-minute triton deadline
            return ok_report("triton")

        reports, aggregate = run_round(
            catalog, context(),
            collectors={"ubs": lambda p, c, w: ok_report("ubs"), "triton": slow_collector},
            clock=clock, sleep=clock.sleep,
        )
        self.assertEqual(reports["triton"]["task_status"], "timeout")
        self.assertIn("deadline", reports["triton"]["error"])
        self.assertTrue(aggregate["all_terminal"])

    def test_tc02_precheck_failure_performs_no_collection(self):
        catalog = synthetic_catalog()
        calls = []

        def precheck():
            raise RuntimeError("pre-check failed: config fingerprint changed")

        reports, aggregate = run_round(
            catalog, context(),
            collectors={"ubs": lambda p, c, w: calls.append("ubs") or ok_report("ubs")},
            clock=VirtualClock(), sleep=lambda dt: None, precheck=precheck,
        )
        self.assertEqual(reports, {})


if __name__ == "__main__":
    unittest.main()