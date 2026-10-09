import copy,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from triton.dashboard import GitHub,build_batches,build_payload,collect
from triton.quality import validate,fingerprint,verify_page

class QualityTests(unittest.TestCase):
    def fixture(self):
        job={"id":7,"name":"integration-tests-ascend (linux-amd64-a5-2, py3.12)","status":"completed","conclusion":"success","created_at":"2026-09-28T01:00:00Z","started_at":"2026-09-28T01:00:14Z","completed_at":"2026-09-28T02:00:00Z"}
        run={"id":1,"pr":1,"head_sha":"abc","created_at":"2026-09-28T01:00:00Z","updated_at":"2026-09-28T02:00:00Z","status":"completed","conclusion":"success","jobs_complete":True,"jobs":[job]}
        runs=[run];p=build_payload(runs,"2026-09-27T00:00:00Z","2026-09-29T00:00:00Z","2026-09-29T00:00:00Z")
        return runs,p
    def test_valid(self):
        r,p=self.fixture();self.assertTrue(validate(r,p)['passed'])
    def test_zero_npu_is_valid(self):
        self.assertTrue(validate([],{'batches':[]})['passed'])
    def test_missing_timestamp(self):
        r,p=self.fixture();r[0]['jobs'][0]['created_at']=None
        self.assertFalse(validate(r,p)['passed'])
    def test_negative_timestamp(self):
        r,p=self.fixture();r[0]['jobs'][0]['started_at']='2026-09-28T00:00:00Z'
        p=build_payload(r,'2026-09-27T00:00:00Z','2026-09-29T00:00:00Z','2026-09-29T00:00:00Z')
        report=validate(r,p)
        self.assertTrue(report['passed'])
        self.assertTrue(report['warnings'])
        self.assertIsNone(p['batches'][0]['npu_queue_seconds'])
    def test_runner_rename(self):
        r,p=self.fixture();r[0]['jobs'][0]['name']='integration-tests-ascend (new-950, py3.12)'
        self.assertFalse(validate(r,p)['passed'])
    def test_lost_aggregation(self):
        r,p=self.fixture();p['batches'][0]['npu_jobs']=[]
        self.assertFalse(validate(r,p)['passed'])
    def test_wrong_maximum(self):
        r,p=self.fixture();p['batches'][0]['npu_queue_seconds']=0
        self.assertFalse(validate(r,p)['passed'])
    def test_pending_is_not_failed_measurement(self):
        r,p=self.fixture();j=r[0]['jobs'][0];j.update(status='queued',conclusion=None,started_at=None,completed_at=None)
        p=build_payload(r,'2026-09-27T00:00:00Z','2026-09-29T00:00:00Z','2026-09-29T00:00:00Z')
        self.assertTrue(validate(r,p)['passed'])
    def test_truncated_page(self):
        with patch.object(GitHub,'get',return_value=({'total_count':5,'jobs':[{'id':1}]},{})):
            with self.assertRaises(RuntimeError):GitHub().pages('/jobs','jobs')
    def test_published_old_data(self):
        r,p=self.fixture();manifest={'sha256':fingerprint(p)}
        html='<script id="data">'+json.dumps(p)+'</script>'
        self.assertEqual(verify_page(html,manifest),p)
        p['collected_at']='old'
        with self.assertRaises(ValueError):verify_page('<script id="data">'+json.dumps(p)+'</script>',manifest)


class WorkflowTimeGateTests(unittest.TestCase):
    def run_row(self, **overrides):
        row={"id":1,"event":"pull_request","head_sha":"abc","created_at":"2026-09-22T02:00:00Z","updated_at":"2026-09-22T02:05:00Z",
             "status":"completed","conclusion":"success","jobs":[],"jobs_complete":True,"pr":7,"pr_title":"T",
             "pr_url":"https://github.com/triton-lang/triton-ascend/pull/7","base_branch":"main",
             "pr_evidence":{"method":"m","run_id":1,"pr":7,"resolved_head_sha":"abc"}}
        row.update(overrides); return row
    def test_inverted_workflow_time_fails_the_gate_and_never_clamps_to_zero(self):
        row=self.run_row(updated_at="2026-09-22T01:00:00Z")
        batch=build_batches([row],"2026-09-22T03:00:00Z")[0]
        self.assertIsNone(batch["duration_seconds"])
        self.assertTrue(any("倒置" in m for m in batch["missing"]))
        self.assertFalse(validate([row],{"batches":[batch]})["passed"])
    def test_completed_workflow_with_missing_or_unparseable_timestamps_fails(self):
        self.assertFalse(validate([self.run_row(updated_at=None)],{"batches":[]})["passed"])
        self.assertFalse(validate([self.run_row(updated_at="not-a-timestamp")],{"batches":[]})["passed"])
    def test_completion_beyond_as_of_is_flagged(self):
        row=self.run_row(updated_at="2026-09-30T00:00:00Z")
        report=validate([row],{"batches":[],"window_end":"2026-09-29T00:00:00Z"})
        self.assertFalse(report["passed"])
        self.assertTrue(any("as-of" in e for e in report["errors"]))
    def test_running_batch_reports_only_the_observed_span_to_as_of(self):
        row=self.run_row(status="in_progress",conclusion=None,created_at="2026-09-28T10:00:00Z",updated_at="2026-09-28T10:30:00Z")
        p=build_payload([row],"2026-09-27T00:00:00Z","2026-09-28T12:00:00Z","2026-09-28T12:00:00Z")
        self.assertTrue(validate([row],p)["passed"])
        p["batches"][0]["duration_seconds"]+=100
        self.assertFalse(validate([row],p)["passed"])
    def test_completed_batch_without_end_time_warns_and_is_excluded(self):
        row=self.run_row(updated_at=None)
        p=build_payload([row],"2026-09-21T00:00:00Z","2026-09-23T00:00:00Z","2026-09-23T00:00:00Z")
        report=validate([row],p)
        self.assertTrue(report["warnings"])
        self.assertEqual(p["summary"]["valid"],0)
        self.assertEqual(len(p["batches"]),1)
    def test_skipped_and_unstarted_cancelled_jobs_are_not_missing_time(self):
        job={"id":7,"name":"integration-tests-ascend (linux-amd64-a5-2, py3.12)","status":"completed","conclusion":"success",
             "created_at":"2026-09-28T01:00:00Z","started_at":"2026-09-28T01:00:14Z","completed_at":"2026-09-28T02:00:00Z"}
        skipped={**job,"id":8,"conclusion":"skipped","started_at":None,"completed_at":None}
        cancelled={**job,"id":9,"conclusion":"cancelled","started_at":None,"completed_at":None}
        row=self.run_row(created_at="2026-09-28T01:00:00Z",updated_at="2026-09-28T02:00:00Z",jobs=[job,skipped,cancelled])
        p=build_payload([row],"2026-09-27T00:00:00Z","2026-09-29T00:00:00Z","2026-09-29T00:00:00Z")
        self.assertTrue(validate([row],p)["passed"])


class GitHubContractTests(unittest.TestCase):
    def test_missing_null_or_non_array_workflow_runs_fails_closed(self):
        for bad in ({}, {"workflow_runs": None}, {"workflow_runs": {"a": 1}}, {"workflow_runs": "oops"}, [], {"total_count": 3}):
            with patch.object(GitHub, "get", return_value=(bad, {})):
                with self.assertRaises(RuntimeError):
                    GitHub().pages("/actions/runs", "workflow_runs")

    def test_legal_empty_workflow_runs_is_zero_data_not_a_failure(self):
        with patch.object(GitHub, "get", return_value=({"workflow_runs": [], "total_count": 0}, {})):
            self.assertEqual(GitHub().pages("/actions/runs", "workflow_runs"), [])

    def test_duplicate_records_across_pages_fail_instead_of_double_counting(self):
        first={"workflow_runs":[{"id":i} for i in range(100)],"total_count":101}
        second={"workflow_runs":[{"id":1}],"total_count":101}
        with patch.object(GitHub, "get", side_effect=[(first,{}),(second,{})]):
            with self.assertRaises(RuntimeError) as ctx:
                GitHub().pages("/actions/runs", "workflow_runs")
            self.assertIn("duplicate", str(ctx.exception))

    def test_declared_count_mismatch_fails_instead_of_silent_truncation(self):
        response={"workflow_runs":[{"id":1},{"id":2}],"total_count":5}
        with patch.object(GitHub, "get", return_value=(response,{})):
            with self.assertRaises(RuntimeError) as ctx:
                GitHub().pages("/actions/runs", "workflow_runs")
            self.assertIn("total_count", str(ctx.exception))

    def test_bare_array_endpoints_reject_object_responses(self):
        with patch.object(GitHub, "get", return_value=({"message": "Bad credentials"}, {})):
            with self.assertRaises(RuntimeError):
                GitHub().pages("/pulls")

    def test_collect_contract_failure_names_source_without_credentials(self):
        def fake_get(self, url):
            if url.endswith("per_page=1"): return {"message": "Server Error"}, {}
            return {"workflow_runs": []}, {}
        tmp = Path(tempfile.mkdtemp(prefix="triton-contract-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with patch.object(GitHub, "get", fake_get), patch("triton.dashboard.EVIDENCE", tmp):
            with self.assertRaises(RuntimeError) as ctx:
                collect(hours=72, as_of="2026-09-28T12:00:00Z")
        message=str(ctx.exception)
        self.assertIn("/actions/runs", message)
        self.assertNotIn("Bearer", message)
        self.assertFalse((tmp / "enriched-runs.json").exists())
