"""Fail closed on missing measurements; never require an arbitrary NPU count."""
import hashlib
import json
import re
from datetime import datetime


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def validate(runs, payload):
    errors=[]; warnings=[]
    try:
        as_of=stamp(payload.get("window_end"))
    except (ValueError,TypeError,AttributeError):
        as_of=None
    represented={j.get("id") for b in payload["batches"] for j in b.get("npu_jobs",[])}
    for run in runs:
        prefix=f"run {run.get('id')}"
        if run.get("event") in ("pull_request","pull_request_target"):
            proof=run.get("pr_evidence") or {}
            if not run.get("pr") or not run.get("pr_url") or not run.get("base_branch") or not run.get("pr_title"):
                errors.append(prefix+": missing PR identity or metadata")
            if proof.get("run_id")!=run.get("id") or not proof.get("method") or proof.get("pr")!=run.get("pr") or proof.get("resolved_head_sha")!=run.get("head_sha"):
                errors.append(prefix+": missing or inconsistent PR association evidence")
        if run.get("status")=="completed":
            try:
                created=stamp(run.get("created_at")); updated=stamp(run.get("updated_at"))
                if not created or not updated:
                    errors.append(prefix+": completed workflow missing created_at/updated_at")
                elif updated<created:
                    errors.append(prefix+": completed workflow ends before its start")
                elif as_of is not None and updated>as_of:
                    errors.append(prefix+": completion time beyond the as-of reference")
            except (ValueError,TypeError,AttributeError):
                errors.append(prefix+": invalid workflow timestamp")
        if not run.get("jobs_complete"):
            errors.append(prefix+": incomplete job list")
        for job in run.get("jobs", []):
            name=job.get("name", "")
            # Independent of the collector's runner-name matcher.
            candidate="integration-tests-ascend (" in name or bool(re.search(r"linux-(?:amd64|aarch64)-a[0-9]",name))
            if not candidate: continue
            if job.get("id") not in represented: errors.append(prefix+": NPU job absent from aggregated data")
            key=prefix+f" job {job.get('id')}: "
            from .dashboard import _is_npu_job, focus_from_jobs
            if not _is_npu_job(job): errors.append(key+"unrecognized NPU runner")
            if re.search(r"-a[35]-",name) and re.search(r"py3\.(10|11|12)",name) and not focus_from_jobs([job]):
                errors.append(key+"unrecognized focus job")
            if job.get("conclusion") in ("skipped","cancelled") and not job.get("started_at"): continue
            try:
                created=stamp(job.get("created_at")); started=stamp(job.get("started_at")); ended=stamp(job.get("completed_at"))
                if not created: errors.append(key+"missing created_at")
                if job.get("status")=="completed" and (not started or not ended): errors.append(key+"completed job missing timestamps")
                if started and created and started<created:
                    warnings.append(key+"source timestamps inverted; excluded from queue statistics")
                if ended and started and ended<started: errors.append(key+"negative execution time")
            except (ValueError,TypeError): errors.append(key+"invalid timestamp")
    for batch in payload["batches"]:
        for workflow in batch.get("workflows",[]):
            if workflow.get("event") in ("pull_request","pull_request_target"):
                if workflow.get("pr")!=batch.get("pr") or workflow.get("head_sha")!=batch.get("sha") or not batch.get("pr_url"):
                    errors.append(f"batch {batch['id']}: PR association lost during aggregation")
        jobs=batch.get("npu_jobs",[])
        values=[]
        for job in jobs:
            if job.get("wait_seconds") is None: continue
            try:
                actual=(stamp(job['started_at'])-stamp(job['created_at'])).total_seconds()
                if actual<0 or actual!=job['wait_seconds']: errors.append(f"batch {batch['id']}: queue mismatch")
                values.append(actual)
            except (KeyError,TypeError,ValueError): errors.append(f"batch {batch['id']}: invalid measurement")
        expected=max(values) if values and not batch.get("npu_data_missing") else None
        if batch.get("npu_queue_seconds")!=expected: errors.append(f"batch {batch['id']}: maximum mismatch")
        try:
            b_start=stamp(batch.get("start_at")); b_end=stamp(batch.get("end_at"))
        except (ValueError,TypeError,AttributeError):
            errors.append(f"batch {batch['id']}: invalid timestamp"); b_start=b_end=None
        if b_start and b_end and b_end<b_start:
            errors.append(f"batch {batch['id']}: end before start")
        if batch.get("status") in ("success","failure") and b_start and not b_end:
            warnings.append(f"batch {batch['id']}: no valid completion time; excluded from completed statistics")
        if batch.get("status")=="running" and b_start and as_of is not None:
            observed=(as_of-b_start).total_seconds()
            value=batch.get("duration_seconds")
            if not isinstance(value,(int,float)) or isinstance(value,bool) or abs(value-observed)>1:
                errors.append(f"batch {batch['id']}: running batch must report only the observed span to as_of")
    report={"passed":not errors,"errors":errors,"warnings":warnings,"runs":len(runs),"batches":len(payload['batches']),
            "npu_points":sum(b.get('npu_queue_seconds') is not None for b in payload['batches'])}
    return report


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",", ":")).encode()).hexdigest()


def verify_page(source, manifest):
    match=re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>',source,re.S)
    if not match: raise ValueError("Published page has no dashboard data")
    payload=json.loads(match[1])
    if fingerprint(payload)!=manifest['sha256']: raise ValueError("Published data differs from this build")
    return payload
