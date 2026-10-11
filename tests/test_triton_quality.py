import copy,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from triton.dashboard import GitHub,build_batches,build_payload,collect,write_payload
from triton.quality import validate,fingerprint,verify_artifacts,verify_page

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
    def test_auxiliary_workflow_cannot_mask_inverted_applicable_start(self):
        bad=self.run_row(id=1,created_at="2026-09-22T00:00:00Z",trigger_at="2026-09-22T02:30:00Z",trigger_exact=True,updated_at="2026-09-22T01:00:00Z")
        aux=self.run_row(id=2,created_at="2026-09-22T00:00:00Z",trigger_at="2026-09-22T00:30:00Z",trigger_exact=True,updated_at="2026-09-22T03:00:00Z",
                         pr_evidence={"method":"m","run_id":2,"pr":7,"resolved_head_sha":"abc"})
        p=build_payload([bad,aux],"2026-09-22T00:00:00Z","2026-09-22T04:00:00Z","2026-09-22T04:00:00Z")
        self.assertEqual(len(p["batches"]),1)
        report=validate([bad,aux],p)
        self.assertFalse(report["passed"])
        self.assertTrue(any("applicable start" in e for e in report["errors"]))
    def test_legal_auxiliary_workflow_with_exact_triggers_still_passes(self):
        first=self.run_row(id=1,created_at="2026-09-22T00:00:00Z",trigger_at="2026-09-22T00:30:00Z",trigger_exact=True,updated_at="2026-09-22T01:00:00Z")
        aux=self.run_row(id=2,created_at="2026-09-22T00:00:00Z",trigger_at="2026-09-22T00:35:00Z",trigger_exact=True,updated_at="2026-09-22T03:00:00Z",
                         pr_evidence={"method":"m","run_id":2,"pr":7,"resolved_head_sha":"abc"})
        p=build_payload([first,aux],"2026-09-22T00:00:00Z","2026-09-22T04:00:00Z","2026-09-22T04:00:00Z")
        self.assertTrue(validate([first,aux],p)["passed"])
    def test_completed_workflow_with_missing_or_unparseable_timestamps_fails(self):
        self.assertFalse(validate([self.run_row(updated_at=None)],{"batches":[]})["passed"])
        self.assertFalse(validate([self.run_row(updated_at="not-a-timestamp")],{"batches":[]})["passed"])
    def test_unresolved_pr_is_a_warning_not_a_refresh_failure(self):
        row=self.run_row(pr=None,pr_url=None,base_branch=None,pr_title=None,
                         pr_evidence={"method":"unresolved","run_id":1,"error":"ambiguous"})
        p=build_payload([row],"2026-09-21T00:00:00Z","2026-09-23T00:00:00Z","2026-09-23T00:00:00Z")
        self.assertIsNone(p["batches"][0]["pr"])
        self.assertIn("未可靠关联 PR"," ".join(p["batches"][0]["missing"]))
        report=validate([row],p)
        self.assertTrue(report["passed"],report["errors"])
        self.assertTrue(any("unresolved" in w for w in report["warnings"]))
    def test_out_of_window_run_jobs_are_not_flagged_absent_from_payload(self):
        # A run whose batch starts before the display window is dropped from the
        # payload as association evidence only; its NPU jobs are legitimately
        # absent from the aggregated data, so they must not fail the gate.
        job={"id":7,"name":"integration-tests-ascend (linux-amd64-a5-2, py3.12)","status":"completed","conclusion":"success",
             "created_at":"2026-09-22T02:00:00Z","started_at":"2026-09-22T02:00:14Z","completed_at":"2026-09-22T02:05:00Z"}
        row=self.run_row(jobs=[job],created_at="2026-09-22T02:00:00Z",updated_at="2026-09-22T02:05:00Z")
        p=build_payload([row],"2026-09-23T00:00:00Z","2026-09-24T00:00:00Z","2026-09-24T00:00:00Z")
        self.assertEqual(len(p["batches"]),0)
        report=validate([row],p)
        self.assertTrue(report["passed"],report["errors"])
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


class PayloadContractTests(unittest.TestCase):
    def rerun_row(self, **overrides):
        row={"id":1,"event":"pull_request","head_sha":"abc","created_at":"2026-09-28T00:00:00Z",
             "run_started_at":"2026-09-28T02:00:00Z","updated_at":"2026-09-28T02:05:00Z","run_attempt":2,
             "status":"completed","conclusion":"success","jobs":[],"jobs_complete":True,"pr":23,"pr_title":"T",
             "pr_url":"https://github.com/triton-lang/triton-ascend/pull/23","base_branch":"main",
             "pr_evidence":{"method":"m","run_id":1,"pr":23,"resolved_head_sha":"abc"}}
        row.update(overrides); return row
    def payload(self,rows):
        return build_payload(rows,"2026-09-27T00:00:00Z","2026-09-29T00:00:00Z","2026-09-29T00:00:00Z")
    def test_valid_payload_passes(self):
        rows=[self.rerun_row()]
        self.assertTrue(validate(rows,self.payload(rows))["passed"])
    def test_missing_or_unparseable_window_end_fails_when_data_is_present(self):
        rows=[self.rerun_row()]
        for bad in (None,"not-a-date"):
            p=self.payload(rows); p["window_end"]=bad
            report=validate(rows,p)
            self.assertFalse(report["passed"],repr(bad))
            self.assertTrue(any("window_end" in e for e in report["errors"]),repr(bad))
    def test_illegal_completed_durations_fail(self):
        rows=[self.rerun_row()]
        for bad in (-1,None,True,"300",999):
            p=self.payload(rows); p["batches"][0]["duration_seconds"]=bad
            report=validate(rows,p)
            self.assertFalse(report["passed"],repr(bad))
            self.assertTrue(any("duration" in e for e in report["errors"]),repr(bad))
    def test_contradictory_summary_fails(self):
        rows=[self.rerun_row()]
        p=self.payload(rows); p["summary"]["valid"]=99; p["summary"]["p90"]=999
        report=validate(rows,p)
        self.assertFalse(report["passed"])
        self.assertTrue(any("summary" in e for e in report["errors"]))
    def test_running_batch_nan_duration_fails(self):
        row=self.rerun_row(status="in_progress",conclusion=None,updated_at="2026-09-28T02:30:00Z")
        p=self.payload([row]); p["batches"][0]["duration_seconds"]=float("nan")
        report=validate([row],p)
        self.assertFalse(report["passed"])
        self.assertTrue(any("observed span" in e for e in report["errors"]))
    def test_legal_zero_payload_stays_valid(self):
        self.assertTrue(validate([],{"batches":[]})["passed"])


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

    def test_declared_count_drift_between_pages_fails_instead_of_hiding_truncation(self):
        first={"workflow_runs":[{"id":i} for i in range(100)],"total_count":150}
        second={"workflow_runs":[],"total_count":100}
        with patch.object(GitHub, "get", side_effect=[(first,{}),(second,{})]):
            with self.assertRaises(RuntimeError) as ctx:
                GitHub().pages("/actions/runs", "workflow_runs")
            self.assertIn("total_count", str(ctx.exception))

    def test_records_without_id_fail_instead_of_double_counting_duplicates(self):
        page={"workflow_runs":[{"name":"same"} for _ in range(100)],"total_count":200}
        with patch.object(GitHub, "get", side_effect=[(page,{}),(page,{}),({"workflow_runs":[],"total_count":200},{})]):
            with self.assertRaises(RuntimeError) as ctx:
                GitHub().pages("/actions/runs", "workflow_runs")
            self.assertIn("'id'", str(ctx.exception))

    def test_bare_array_records_without_id_reject_duplicate_pages_by_content(self):
        first=[{"sha":format(i,"040x")} for i in range(100)]
        with patch.object(GitHub, "get", side_effect=[(first,{}),(first[:1],{})]):
            with self.assertRaises(RuntimeError) as ctx:
                GitHub().pages("/pulls/1/commits")
            self.assertIn("duplicate", str(ctx.exception))

    def test_bare_array_records_without_id_are_accepted_when_unique(self):
        first=[{"sha":format(i,"040x")} for i in range(100)]
        second=[{"sha":format(i,"040x")} for i in range(100,103)]
        with patch.object(GitHub, "get", side_effect=[(first,{}),(second,{})]):
            self.assertEqual(len(GitHub().pages("/pulls/1/commits")),103)

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


class ArtifactConsistencyTests(unittest.TestCase):
    """REQ-021 AC04: triton.json, the CSV export, the manifest and the build evidence must agree before upload."""
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix="triton-artifacts-"))
        self.addCleanup(shutil.rmtree,self.root,ignore_errors=True)
        self.data=self.root/"web"/"data";self.data.mkdir(parents=True)
        self.evidence=self.root/"evidence"/"triton";self.evidence.mkdir(parents=True)

    def payload(self):
        return {"repo":"triton-lang/triton-ascend","window_start":"2026-09-27T00:00:00Z","window_end":"2026-09-29T00:00:00Z",
                "collected_at":"2026-09-29T00:05:00Z","summary":{"prs":1,"batches":1,"valid":1},
                "batches":[{"id":"b1","pr":42,"title":"Improve compiler","sha":"abc123","base_branch":"main","kind":"initial",
                            "start_at":"2026-09-28T01:00:00Z","end_at":"2026-09-28T02:00:00Z","status":"success",
                            "duration_seconds":3600.0,"npu_queue_seconds":None,"approximate":True,
                            "start_source":"workflow_created","critical_workflow":"Integration Tests","missing":[],
                            "pr_url":"https://github.com/triton-lang/triton-ascend/pull/42",
                            "action_url":"https://github.com/triton-lang/triton-ascend/actions/runs/1"}]}

    def write_artifacts(self,payload):
        with patch("triton.dashboard.REPO_ROOT",self.root),patch("triton.dashboard.EVIDENCE",self.evidence):
            write_payload(payload)
        (self.data/"triton-manifest.json").write_text(
            json.dumps({"sha256":fingerprint(payload),"collected_at":payload["collected_at"]}),encoding="utf-8")

    def test_consistent_artifacts_pass_the_gate(self):
        payload=self.payload();self.write_artifacts(payload)
        self.assertEqual(verify_artifacts(self.data,self.evidence),[])

    def test_tampered_json_breaks_manifest_fingerprint_and_csv_row(self):
        payload=self.payload();self.write_artifacts(payload)
        payload["batches"][0]["duration_seconds"]=1.0
        (self.data/"triton.json").write_text(json.dumps(payload,ensure_ascii=False)+"\n",encoding="utf-8")
        problems=verify_artifacts(self.data,self.evidence)
        self.assertTrue(any("sha256" in p for p in problems),problems)
        self.assertTrue(any("duration_seconds" in p for p in problems),problems)

    def test_dropped_csv_row_fails_the_gate(self):
        payload=self.payload();self.write_artifacts(payload)
        lines=(self.data/"triton-batches.csv").read_text(encoding="utf-8-sig").splitlines()
        (self.data/"triton-batches.csv").write_text("\r\n".join(lines[:1])+"\r\n",encoding="utf-8-sig")
        problems=verify_artifacts(self.data,self.evidence)
        self.assertTrue(any("rows" in p for p in problems),problems)

    def test_collected_at_disagreement_fails_the_gate(self):
        payload=self.payload();self.write_artifacts(payload)
        manifest=json.loads((self.data/"triton-manifest.json").read_text(encoding="utf-8"))
        manifest["collected_at"]="2026-09-29T09:09:00Z"
        (self.data/"triton-manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        problems=verify_artifacts(self.data,self.evidence)
        self.assertTrue(any("collected_at" in p for p in problems),problems)

    def test_diverged_evidence_copy_fails_the_gate(self):
        payload=self.payload();self.write_artifacts(payload)
        payload["batches"][0]["title"]="A different title"
        (self.evidence/"dashboard-data.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        problems=verify_artifacts(self.data,self.evidence)
        self.assertTrue(any("dashboard-data.json" in p for p in problems),problems)

    def test_missing_evidence_copy_fails_the_gate(self):
        payload=self.payload();self.write_artifacts(payload)
        (self.evidence/"dashboard-data.json").unlink()
        problems=verify_artifacts(self.data,self.evidence)
        self.assertTrue(any("missing" in p for p in problems),problems)

    def test_main_gates_the_upload_on_artifact_consistency(self):
        source=(Path(__file__).resolve().parents[1]/"triton"/"dashboard.py").read_text(encoding="utf-8")
        self.assertIn("verify_artifacts(",source)
        self.assertLess(source.index('triton-manifest.json",{"sha256"'),source.index("verify_artifacts("),
                        "the gate must run after the manifest is written and before the run can succeed")
        self.assertIn("Artifact consistency gate failed",source)

    def test_live_artifacts_stay_consistent_when_present(self):
        root=Path(__file__).resolve().parents[1]
        data,evidence=root/"web"/"data",root/"evidence"/"triton"
        if not (data/"triton-manifest.json").exists():
            self.skipTest("no local Triton artifacts (collect first)")
        self.assertEqual(verify_artifacts(data,evidence),[])
