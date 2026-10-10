import csv
import json
import re
import shutil
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from triton.dashboard import (
    GitHub,
    build_batches,
    build_payload,
    collect,
    dt,
    export_csv,
    extract_focus_job_links,
    extract_pr_base_ref,
    merge_run_evidence,
    parse_job_header,
    parse_pr_base_html,
    parse_run_html,
    percentile,
    run_in_window,
    summary_of,
)
from triton.quality import validate as quality_validate


def run(run_id, name, sha, created, updated, status="completed", conclusion="success", attempt=1, jobs=None):
    return {
        "id": run_id,
        "name": name,
        "head_sha": sha,
        "created_at": created,
        "updated_at": updated,
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "html_url": f"https://github.com/example/actions/runs/{run_id}",
        "jobs": jobs or [],
        "pr": 42,
        "pr_title": "Improve compiler",
        "pr_url": "https://github.com/example/pull/42",
        "trigger_at": "2026-09-22T00:00:00Z",
        "trigger_exact": True,
    }


class BatchAggregationTests(unittest.TestCase):
    def test_parallel_workflows_use_last_completion_not_sum(self):
        rows = [
            run(1, "Fast", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:11:00Z"),
            run(2, "Slow", "abc", "2026-09-22T00:02:00Z", "2026-09-22T00:31:00Z"),
        ]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["duration_seconds"], 31 * 60)
        self.assertEqual(batch["critical_workflow"], "Slow")

    def test_batch_exposes_focus_jobs_for_chart_cards(self):
        row = run(1, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:11:00Z")
        row["focus_jobs"] = [{"key":"a3-py310","name":"A3 py3.10","url":"https://github.com/job/1","wait_seconds":25,"run_seconds":838}]
        batch = build_batches([row], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["focus_jobs"][0]["key"], "a3-py310")
        self.assertEqual(batch["focus_jobs"][0]["wait_seconds"], 25)

    def test_running_batch_reports_elapsed_and_is_not_complete(self):
        rows = [run(1, "NPU", "abc", "2026-09-22T23:00:00Z", "2026-09-22T23:30:00Z", status="in_progress", conclusion=None)]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["status"], "running")
        self.assertEqual(batch["duration_seconds"], 24 * 60 * 60)
        self.assertFalse(batch["complete"])

    def test_failure_wins_over_success_for_completed_batch(self):
        rows = [
            run(1, "Lint", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:05:00Z"),
            run(2, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z", conclusion="failure"),
        ]
        self.assertEqual(build_batches(rows, "2026-09-23T00:00:00Z")[0]["status"], "failure")

    def test_rerun_is_kept_as_separate_batch(self):
        rows = [
            run(1, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z"),
            run(1, "Tests", "abc", "2026-09-22T01:01:00Z", "2026-09-22T01:08:00Z", attempt=2),
        ]
        batches = build_batches(rows, "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        self.assertEqual({b["kind"] for b in batches}, {"initial", "rerun"})

    def test_same_pr_and_sha_are_one_initial_e2e_even_when_workflows_arrive_late(self):
        first = run(1, "Title", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:02:00Z")
        second = run(2, "Title", "abc", "2026-09-22T03:01:00Z", "2026-09-22T03:02:00Z")
        second["trigger_at"] = "2026-09-22T03:00:00Z"
        batches = build_batches([first, second], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]["workflows"]), 2)

    def test_batch_exposes_actual_action_run_links(self):
        rows = [
            run(1, "Documentation", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:05:00Z"),
            run(2, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:08:00Z"),
        ]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["action_url"], "https://github.com/example/actions/runs/2")
        self.assertEqual(batch["action_name"], "Integration Tests")

    def test_batch_uses_longest_npu_job_queue_time(self):
        jobs = [
            {"id": 11, "name": "runner-preparation / prepare", "created_at": "2026-09-22T00:01:00Z", "started_at": "2026-09-22T00:01:03Z", "completed_at": "2026-09-22T00:01:05Z", "html_url": "https://github.com/job/11", "status": "completed", "conclusion": "success"},
            {"id": 12, "name": "integration-tests-ascend (linux-aarch64-a3-800i-4, py3.10)", "created_at": "2026-09-22T00:01:05Z", "started_at": "2026-09-22T00:01:45Z", "completed_at": "2026-09-22T00:06:00Z", "html_url": "https://github.com/job/12", "status": "completed", "conclusion": "success"},
            {"id": 13, "name": "integration-tests-ascend (linux-aarch64-a3-800i-4, py3.11)", "created_at": "2026-09-22T00:01:05Z", "started_at": "2026-09-22T00:02:15Z", "completed_at": "2026-09-22T00:07:00Z", "html_url": "https://github.com/job/13", "status": "completed", "conclusion": "success"},
        ]
        batch = build_batches([run(2, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:08:00Z", jobs=jobs)], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["npu_queue_seconds"], 70)
        self.assertEqual([job["id"] for job in batch["npu_jobs"]], [12, 13])

    def test_approximate_start_is_retained_and_marked(self):
        row = run(1, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z")
        row["trigger_at"] = None
        row["trigger_exact"] = False
        batch = build_batches([row], "2026-09-23T00:00:00Z")[0]
        self.assertTrue(batch["approximate"])
        self.assertEqual(batch["start_at"], "2026-09-22T00:01:00Z")
        self.assertNotIn("提交事件", " ".join(batch["missing"]))


class PercentileTests(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(percentile([10, 20, 30, 40], 0.9), 37)

    def test_empty_percentile_is_none(self):
        self.assertIsNone(percentile([], 0.9))


class HtmlEvidenceTests(unittest.TestCase):
    def test_pr_api_payload_extracts_merge_target_branch(self):
        self.assertEqual(extract_pr_base_ref({"base": {"ref": "release/3.3"}}), "release/3.3")
        self.assertIsNone(extract_pr_base_ref({}))

    def test_pr_page_parser_extracts_merge_target_branch(self):
        source = '<script type="application/json">{"pullRequest":{"baseBranch":"release/3.2.2","headBranch":"feature"}}</script>'
        self.assertEqual(parse_pr_base_html(source), "release/3.2.2")

    def test_run_page_parser_extracts_pr_status_and_jobs(self):
        source = '''
        <span class="PageHeader-parentLink-label"> Integration Tests</span>
        <svg aria-label="completed with failures: "></svg>
        <h1><span class="markdown-title">Fix compiler</span></h1>
        <a href="/triton-lang/triton-ascend/pull/42">#42</a>
        <relative-time datetime="2026-09-22T01:02:03Z"></relative-time>
        <streaming-graph-job><span data-target="streaming-graph-job.name">Build &amp; Test</span>
        <div class="flex-self-baseline text-small color-fg-muted flex-shrink-0 pl-1"> 2m 5s </div></streaming-graph-job>
        '''
        row = parse_run_html(source)
        self.assertEqual(row["name"], "Integration Tests")
        self.assertEqual(row["pr"], 42)
        self.assertEqual(row["conclusion"], "failure")
        self.assertEqual(row["created_at"], "2026-09-22T01:02:03Z")
        self.assertEqual(row["jobs"][0]["name"], "Build & Test")
        self.assertEqual(row["jobs"][0]["duration_seconds"], 125)

    def test_api_terminal_state_wins_when_html_label_is_ambiguous(self):
        api = {"id": 7, "name": "Label", "status": "completed", "conclusion": "skipped"}
        page = {"name": "Label", "status": "in_progress", "conclusion": None, "jobs": [], "pr": 42}
        merged = merge_run_evidence(api, page)
        self.assertEqual(merged["status"], "completed")
        self.assertEqual(merged["conclusion"], "skipped")

    def test_extracts_only_requested_matrix_jobs_with_direct_links(self):
        source = '''
        <a href="/triton-lang/triton-ascend/actions/runs/9/job/101#step:2:1"><strong>
        integration-tests-ascend / integration-tests-ascend (linux-aarch64-a3-800i-4, py3.10)
        </strong></a>
        <a href="/triton-lang/triton-ascend/actions/runs/9/job/102"><strong>
        integration-tests-ascend / integration-tests-ascend (linux-amd64-cpu-16, py3.11)
        </strong></a>
        '''
        jobs = extract_focus_job_links(source)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 101)
        self.assertEqual(jobs[0]["key"], "a3-py310")
        self.assertEqual(jobs[0]["url"], "https://github.com/triton-lang/triton-ascend/actions/runs/9/job/101")

    def test_job_header_derives_queue_and_execution_duration(self):
        source = '''<span>succeeded <relative-time datetime="2026-09-20T08:23:30Z"></relative-time> in 13m 58s</span>'''
        job = parse_job_header(source, "2026-09-20T08:09:07Z", "2026-09-20T09:00:00Z")
        self.assertEqual(job["run_seconds"], 838)
        self.assertEqual(job["wait_seconds"], 25)
        self.assertEqual(job["status"], "completed")


class AttemptIdentityTests(unittest.TestCase):
    """REQ-015: attempt identity, history retention and rerun window recognition."""

    def attempt_run(self, run_id, sha, created, started, updated, attempt=1, jobs=None, pr=42):
        row = run(run_id, "Integration Tests", sha, created, updated, attempt=attempt, jobs=jobs)
        row["run_started_at"] = started
        row["trigger_at"] = None
        row["trigger_exact"] = False
        row["pr"] = pr
        return row

    def job(self, job_id):
        return {"id": job_id, "name": f"job {job_id}", "created_at": "2026-09-22T02:00:00Z",
                "started_at": "2026-09-22T02:00:10Z", "completed_at": "2026-09-22T02:04:00Z",
                "status": "completed", "conclusion": "success"}

    def test_same_run_attempts_keep_both_identities_and_jobs(self):
        first = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T00:00:00Z",
                                 "2026-09-22T00:05:00Z", attempt=1, jobs=[self.job(11)])
        second = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z",
                                  "2026-09-22T02:05:00Z", attempt=2, jobs=[self.job(22)])
        batches = build_batches([first, second], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        by_kind = {batch["kind"]: batch for batch in batches}
        self.assertEqual([j["id"] for j in by_kind["initial"]["workflows"][0]["jobs"]], [11])
        self.assertEqual([j["id"] for j in by_kind["rerun"]["workflows"][0]["jobs"]], [22])
        self.assertEqual(by_kind["rerun"]["workflows"][0]["attempt"], 2)
        self.assertEqual({batch["e2e_total"] for batch in batches}, {2})

    def test_recollecting_the_same_attempt_never_doubles_it(self):
        first = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T00:00:00Z",
                                 "2026-09-22T00:05:00Z", attempt=1)
        second = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z",
                                  "2026-09-22T02:05:00Z", attempt=2)
        batches = build_batches([first, second, dict(first), dict(second)], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        for batch in batches:
            self.assertEqual(len(batch["workflows"]), 1)

    def test_rerun_e2e_spans_only_the_current_attempt(self):
        first = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T00:00:00Z",
                                 "2026-09-22T00:05:00Z", attempt=1)
        second = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z",
                                  "2026-09-22T02:05:00Z", attempt=2)
        batches = build_batches([first, second], "2026-09-22T03:00:00Z")
        rerun = next(batch for batch in batches if batch["kind"] == "rerun")
        self.assertEqual(rerun["duration_seconds"], 300)
        self.assertEqual(rerun["start_at"], "2026-09-22T02:00:00Z")
        self.assertEqual(rerun["start_source"], "attempt_start")
        self.assertTrue(rerun["approximate"])

    def test_rerun_without_attempt_start_leaves_e2e_empty(self):
        row = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", None,
                               "2026-09-22T02:05:00Z", attempt=2)
        batch = build_batches([row], "2026-09-22T03:00:00Z")[0]
        self.assertIsNone(batch["start_at"])
        self.assertIsNone(batch["duration_seconds"])
        self.assertIsNone(batch["start_source"])
        self.assertFalse(batch["approximate"])

    def test_window_recognition_keeps_only_current_window_attempts(self):
        first = self.attempt_run(1, "abc", "2026-09-20T00:00:00Z", "2026-09-20T00:00:00Z",
                                 "2026-09-20T00:05:00Z", attempt=1)
        second = self.attempt_run(1, "abc", "2026-09-20T00:00:00Z", "2026-09-26T10:00:00Z",
                                  "2026-09-26T10:05:00Z", attempt=2)
        payload = build_payload([first, second], "2026-09-25T00:00:00Z",
                                "2026-09-28T00:00:00Z", "2026-09-28T00:00:00Z")
        self.assertEqual([batch["kind"] for batch in payload["batches"]], ["rerun"])
        self.assertEqual(payload["batches"][0]["start_at"], "2026-09-26T10:00:00Z")
        self.assertEqual(payload["batches"][0]["e2e_index"], 1)

    def test_aux_workflows_join_initial_but_rerun_stays_separate(self):
        main = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T00:00:00Z",
                                "2026-09-22T00:10:00Z", jobs=[self.job(11)])
        aux = self.attempt_run(2, "abc", "2026-09-22T00:20:00Z", "2026-09-22T00:20:00Z",
                               "2026-09-22T00:25:00Z", jobs=[self.job(12)])
        rerun = self.attempt_run(1, "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z",
                                 "2026-09-22T02:05:00Z", attempt=2, jobs=[self.job(13)])
        batches = build_batches([main, aux, rerun], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        initial = next(batch for batch in batches if batch["kind"] == "initial")
        rerun_batch = next(batch for batch in batches if batch["kind"] == "rerun")
        self.assertEqual([workflow["id"] for workflow in initial["workflows"]], [1, 2])
        self.assertEqual(len(rerun_batch["workflows"]), 1)
        self.assertEqual([job["id"] for workflow in rerun_batch["workflows"]
                          for job in workflow["jobs"]], [13])

    def test_unresolved_runs_are_isolated_by_run_and_attempt(self):
        first = self.attempt_run(7, "abc", "2026-09-22T00:00:00Z", "2026-09-22T00:00:00Z",
                                 "2026-09-22T00:05:00Z", pr=None)
        second = self.attempt_run(7, "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:00:00Z",
                                  "2026-09-22T02:05:00Z", attempt=2, pr=None)
        batches = build_batches([first, second], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        self.assertEqual({batch["id"] for batch in batches}, {"abc-unresolved-7-1", "abc-rerun-7-2"})
        for batch in batches:
            self.assertIsNone(batch["pr"])
            self.assertIn("未可靠关联 PR", " ".join(batch["missing"]))


class RunWindowTests(unittest.TestCase):
    def test_run_in_window_uses_current_attempt_start(self):
        row = {"created_at": "2026-09-20T00:00:00Z", "run_started_at": "2026-09-26T10:00:00Z"}
        self.assertTrue(run_in_window(row, dt("2026-09-25T00:00:00Z"), dt("2026-09-28T00:00:00Z")))

    def test_run_fully_outside_window_is_excluded(self):
        row = {"created_at": "2026-09-20T00:00:00Z", "run_started_at": "2026-09-20T00:00:00Z"}
        self.assertFalse(run_in_window(row, dt("2026-09-25T00:00:00Z"), dt("2026-09-28T00:00:00Z")))

    def test_run_created_inside_window_is_included(self):
        row = {"created_at": "2026-09-26T00:00:00Z"}
        self.assertTrue(run_in_window(row, dt("2026-09-25T00:00:00Z"), dt("2026-09-28T00:00:00Z")))


class CollectWindowTests(unittest.TestCase):
    def test_collect_discovers_rerun_created_before_window(self):
        inside = {"id": 1, "name": "Integration Tests", "head_sha": "abc", "event": "pull_request",
                  "created_at": "2026-09-21T00:00:00Z", "run_started_at": "2026-09-26T10:00:00Z",
                  "updated_at": "2026-09-26T10:05:00Z", "status": "completed", "conclusion": "success",
                  "run_attempt": 2, "html_url": "https://github.com/example/actions/runs/1",
                  "actor": {"login": "dev"}, "head_branch": "feature"}
        outside = {**inside, "id": 2, "created_at": "2026-09-20T00:00:00Z",
                   "run_started_at": "2026-09-20T00:00:00Z", "updated_at": "2026-09-20T00:10:00Z",
                   "run_attempt": 1}
        paths = []

        def fake_get(self, url):
            paths.append(url)
            if url.endswith("per_page=1"):
                return {"total_count": 2, "workflow_runs": [inside, outside]}, {}
            if "/jobs" in url:
                return {"total_count": 0, "jobs": []}, {}
            return {"workflow_runs": [inside, outside]}, {}

        tmp = Path(tempfile.mkdtemp(prefix="triton-collect-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pr_fields = {"pr": 42, "pr_url": "https://github.com/triton-lang/triton-ascend/pull/42",
                     "pr_title": "Rerun", "base_branch": "main", "head_sha": "abc",
                     "pr_evidence": {"method": "run.pull_requests.head.sha", "run_id": 1,
                                     "pr": 42, "resolved_head_sha": "abc"}}
        with patch.object(GitHub, "get", fake_get), \
                patch("triton.pr_identity.PRResolver.resolve", return_value=pr_fields), \
                patch("triton.dashboard.EVIDENCE", tmp):
            payload = collect(hours=72, as_of="2026-09-28T12:00:00Z")
        created = next(p for p in paths if "created=" in p)
        range_raw = urllib.parse.unquote(created.split("created=")[1].split("&")[0])
        self.assertEqual(range_raw.split("..")[0], "2026-09-11T12:00:00Z")
        self.assertEqual([batch["kind"] for batch in payload["batches"]], ["rerun"])
        self.assertEqual(payload["batches"][0]["start_at"], "2026-09-26T10:00:00Z")


class AttemptEnumerationTests(unittest.TestCase):
    """REQ-015 AC01 (A04): collect() must enumerate every historical attempt."""

    def attempt_run(self, attempt):
        return {"id": 1, "name": "Integration Tests", "head_sha": "abc", "event": "pull_request",
                "created_at": "2026-10-08T00:00:00Z", "run_started_at": "2026-10-08T06:00:00Z",
                "updated_at": "2026-10-08T06:10:00Z", "status": "completed", "conclusion": "success",
                "run_attempt": attempt, "html_url": "https://github.com/example/actions/runs/1",
                "actor": {"login": "dev"}, "head_branch": "feature"}

    def collect_with(self, jobs_by_attempt):
        run = self.attempt_run(3)
        paths = []

        def fake_get(self_github, url):
            paths.append(url)
            if url.endswith("per_page=1"):
                return {"total_count": 1, "workflow_runs": [run]}, {}
            if "/jobs" in url:
                attempt = int(re.search(r"/attempts/(\d+)/jobs", url).group(1))
                jobs = jobs_by_attempt[attempt]
                return {"total_count": len(jobs), "jobs": jobs}, {}
            return {"total_count": 1, "workflow_runs": [run]}, {}

        tmp = Path(tempfile.mkdtemp(prefix="triton-attempts-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pr_fields = {"pr": 23, "pr_url": "https://github.com/triton-lang/triton-ascend/pull/23",
                     "pr_title": "Attempts", "base_branch": "main", "head_sha": "abc",
                     "pr_evidence": {"method": "synthetic", "run_id": 1, "pr": 23,
                                     "resolved_head_sha": "abc"}}
        with patch.object(GitHub, "get", fake_get), \
                patch("triton.pr_identity.PRResolver.resolve", return_value=pr_fields), \
                patch("triton.dashboard.EVIDENCE", tmp):
            payload = collect(hours=72, as_of="2026-10-09T00:00:00Z")
        return payload, paths, tmp

    def test_collect_enumerates_all_attempts_with_their_jobs(self):
        def job(job_id, created, completed, conclusion="success"):
            return {"id": job_id, "name": "build", "created_at": created,
                    "started_at": created, "completed_at": completed,
                    "status": "completed", "conclusion": conclusion}

        payload, paths, tmp = self.collect_with({
            1: [job(101, "2026-10-08T00:00:05Z", "2026-10-08T00:05:00Z")],
            2: [job(102, "2026-10-08T03:00:05Z", "2026-10-08T03:04:00Z", conclusion="failure")],
            3: [job(103, "2026-10-08T06:00:05Z", "2026-10-08T06:10:00Z")]})
        attempts = sorted(w["attempt"] for b in payload["batches"] for w in b["workflows"])
        self.assertEqual(attempts, [1, 2, 3])
        job_calls = sorted(re.search(r"/attempts/(\d+)/jobs", p).group(1)
                           for p in paths if "/jobs" in p)
        self.assertEqual(job_calls, ["1", "2", "3"])
        by_attempt = {w["attempt"]: w for b in payload["batches"] for w in b["workflows"]}
        self.assertEqual([j["id"] for j in by_attempt[1]["jobs"]], [101])
        self.assertEqual([j["id"] for j in by_attempt[2]["jobs"]], [102])
        self.assertEqual([j["id"] for j in by_attempt[3]["jobs"]], [103])
        initial = next(b for b in payload["batches"] if b["kind"] == "initial")
        self.assertEqual(initial["start_at"], "2026-10-08T00:00:00Z")
        self.assertEqual(initial["duration_seconds"], 300)
        reruns = {w["attempt"]: b for b in payload["batches"] if b["kind"] == "rerun"
                  for w in b["workflows"]}
        self.assertEqual(reruns[2]["start_at"], "2026-10-08T03:00:05Z")
        self.assertEqual(reruns[2]["duration_seconds"], 235)
        self.assertEqual(reruns[2]["status"], "failure")
        self.assertEqual(reruns[3]["start_at"], "2026-10-08T06:00:00Z")
        self.assertEqual(reruns[3]["duration_seconds"], 600)
        for attempt in (1, 2, 3):
            evidence = tmp / "jobs" / f"1-{attempt}.json"
            self.assertTrue(evidence.exists(), evidence)
            self.assertEqual([j["id"] for j in json.loads(evidence.read_text("utf-8"))],
                             [100 + attempt])
        enriched = json.loads((tmp / "enriched-runs.json").read_text("utf-8"))
        report = quality_validate(enriched, payload)
        self.assertTrue(report["passed"], report["errors"])

    def test_collect_keeps_attempt_identity_when_jobs_lack_timing(self):
        # The frozen adversarial probe's shape: jobs carry only id/name, so the
        # attempt rows keep their identity while E2E stays empty, never fabricated.
        payload, _, _ = self.collect_with({
            1: [{"id": 101, "name": "CPU"}],
            2: [{"id": 102, "name": "CPU"}],
            3: [{"id": 103, "name": "CPU"}]})
        attempts = sorted(w["attempt"] for b in payload["batches"] for w in b["workflows"])
        self.assertEqual(attempts, [1, 2, 3])
        by_attempt = {w["attempt"]: w for b in payload["batches"] for w in b["workflows"]}
        self.assertEqual([j["id"] for j in by_attempt[2]["jobs"]], [102])
        rerun2 = next(b for b in payload["batches"]
                      if b["kind"] == "rerun" and b["workflows"][0]["attempt"] == 2)
        self.assertIsNone(rerun2["start_at"])
        self.assertIsNone(rerun2["duration_seconds"])
        self.assertIn("无本次 attempt 起点证据", " ".join(rerun2["missing"]))


class SummaryValidityTests(unittest.TestCase):
    """REQ-017: missing and invalid durations never pollute counts or percentiles."""

    def batch(self, status, duration):
        return {"status": status, "duration_seconds": duration, "pr": 42, "approximate": False, "missing": []}

    def test_summary_counts_only_valid_completed_durations(self):
        batches = [
            self.batch("success", 600),
            self.batch("success", None),
            self.batch("failure", -1),
            self.batch("success", "300"),
            self.batch("cancelled", 1200),
            self.batch("running", 900),
        ]
        summary = summary_of(batches)
        self.assertEqual(summary["batches"], 6)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["median"], 600)
        self.assertEqual(summary["p90"], 600)

    def test_real_zero_is_a_valid_duration(self):
        summary = summary_of([self.batch("success", 0), self.batch("failure", 0)])
        self.assertEqual(summary["valid"], 2)
        self.assertEqual(summary["median"], 0)
        self.assertEqual(summary["p90"], 0)

    def test_summary_without_valid_samples_has_empty_statistics(self):
        summary = summary_of([self.batch("success", None), self.batch("failure", "")])
        self.assertEqual(summary["valid"], 0)
        self.assertIsNone(summary["median"])
        self.assertIsNone(summary["p90"])

    def test_build_payload_excludes_rerun_without_start_from_valid_count(self):
        row = run(1, "Integration Tests", "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:05:00Z", attempt=2)
        row["run_started_at"] = None
        row["trigger_at"] = None
        row["trigger_exact"] = False
        payload = build_payload([row], "2026-09-22T00:00:00Z", "2026-09-22T03:00:00Z", "2026-09-22T03:00:00Z")
        self.assertEqual(payload["batches"][0]["status"], "success")
        self.assertIsNone(payload["batches"][0]["duration_seconds"])
        self.assertEqual(payload["summary"]["valid"], 0)
        self.assertIsNone(payload["summary"]["p90"])

    def test_export_csv_distinguishes_zero_from_missing(self):
        payload = {"batches": [self.batch("success", 0), self.batch("success", None)]}
        tmp = Path(tempfile.mkdtemp(prefix="triton-csv-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "web" / "data").mkdir(parents=True)
        with patch("triton.dashboard.REPO_ROOT", tmp):
            export_csv(payload)
        with (tmp / "web" / "data" / "triton-batches.csv").open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["duration_seconds"] for row in rows], ["0", ""])


class RerunStartEvidenceTests(unittest.TestCase):
    """REQ-014: rerun E2E uses this attempt's provable start, never the original run creation."""

    def rerun(self, run_id, started, trigger_at=None, trigger_exact=False):
        row = run(run_id, "Integration Tests", "abc", "2026-09-22T00:00:00Z", "2026-09-22T02:05:00Z", attempt=2)
        row["run_started_at"] = started
        row["trigger_at"] = trigger_at
        row["trigger_exact"] = trigger_exact
        return row

    def test_trusted_trigger_spans_only_this_attempt(self):
        batch = build_batches([self.rerun(1, None, "2026-09-22T02:00:00Z", True)], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["duration_seconds"], 300)
        self.assertEqual(batch["start_at"], "2026-09-22T02:00:00Z")
        self.assertEqual(batch["start_source"], "trigger_event")
        self.assertFalse(batch["approximate"])

    def test_attempt_start_is_reported_as_approximate_span(self):
        batch = build_batches([self.rerun(1, "2026-09-22T02:00:00Z")], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["duration_seconds"], 300)
        self.assertEqual(batch["start_source"], "attempt_start")
        self.assertTrue(batch["approximate"])

    def test_missing_start_evidence_keeps_batch_visible_with_explicit_gap(self):
        row = self.rerun(1, None)
        payload = build_payload([row], "2026-09-22T00:00:00Z", "2026-09-22T03:00:00Z", "2026-09-22T03:00:00Z")
        batch = payload["batches"][0]
        self.assertIsNone(batch["start_at"])
        self.assertIsNone(batch["duration_seconds"])
        self.assertTrue(any("起点" in m for m in batch["missing"]))
        self.assertEqual(len(batch["workflows"]), 1)
        self.assertFalse(batch["complete"])
        self.assertEqual(payload["summary"]["valid"], 0)

    def test_csv_carries_the_same_start_source_and_approximate_flags(self):
        rows = [self.rerun(1, None, "2026-09-22T02:00:00Z", True), self.rerun(2, "2026-09-22T02:00:00Z")]
        payload = build_payload(rows, "2026-09-22T00:00:00Z", "2026-09-23T00:00:00Z", "2026-09-23T00:00:00Z")
        tmp = Path(tempfile.mkdtemp(prefix="triton-csv-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "web" / "data").mkdir(parents=True)
        with patch("triton.dashboard.REPO_ROOT", tmp):
            export_csv(payload)
        with (tmp / "web" / "data" / "triton-batches.csv").open(encoding="utf-8-sig") as handle:
            csv_rows = list(csv.DictReader(handle))
        by_source = {row["start_source"]: row for row in csv_rows}
        self.assertEqual(set(by_source), {"trigger_event", "attempt_start"})
        self.assertEqual(by_source["trigger_event"]["approximate"], "False")
        self.assertEqual(by_source["attempt_start"]["approximate"], "True")


if __name__ == "__main__":
    unittest.main()
