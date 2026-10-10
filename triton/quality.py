"""Fail closed on missing measurements; never require an arbitrary NPU count."""
import csv
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
                # REQ-019 (A08): inversion is judged per workflow against its own
                # applicable start — a proven exact trigger — because the batch
                # start is the minimum over all rows; a legal auxiliary workflow
                # on the same SHA must never mask another workflow completing
                # before the trigger that started it.
                applicable=stamp(run.get("trigger_at")) if run.get("trigger_exact") else None
                if not created or not updated:
                    errors.append(prefix+": completed workflow missing created_at/updated_at")
                elif updated<created:
                    errors.append(prefix+": completed workflow ends before its start")
                elif applicable is not None and updated<applicable:
                    errors.append(prefix+": completed workflow ends before its applicable start")
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


CSV_FIELDS=["pr","title","sha","base_branch","kind","start_at","end_at","status","duration_seconds","npu_queue_seconds","approximate","start_source","critical_workflow","missing","pr_url","action_url"]


def verify_artifacts(data_dir,evidence_dir=None):
    """Cross-check triton.json, the CSV export, the manifest and the build evidence (REQ-021 AC04).

    Returns a list of human-readable problems; an empty list means the artifacts
    agree on batch identity, statistics scope and collection time and may upload.
    """
    errors=[]
    payload=json.loads((data_dir/"triton.json").read_text(encoding="utf-8"))
    manifest=json.loads((data_dir/"triton-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("sha256")!=fingerprint(payload):
        errors.append("triton-manifest.json sha256 does not match web/data/triton.json")
    if manifest.get("collected_at")!=payload.get("collected_at"):
        errors.append(f"manifest collected_at {manifest.get('collected_at')!r} differs from the payload {payload.get('collected_at')!r}")
    batches=payload.get("batches",[])
    with (data_dir/"triton-batches.csv").open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        rows=list(reader)
        if reader.fieldnames!=CSV_FIELDS:
            errors.append(f"CSV header {reader.fieldnames!r} differs from the export contract")
    if len(rows)!=len(batches):
        errors.append(f"CSV carries {len(rows)} rows but triton.json has {len(batches)} batches")
    for position,(row,batch) in enumerate(zip(rows,batches)):
        for field in CSV_FIELDS:
            value=batch.get(field)
            if field=="missing" and isinstance(value,list): value="; ".join(value)
            expected="" if value is None else str(value)
            if (row.get(field) or "")!=expected:
                errors.append(f"CSV row {position} (PR {batch.get('pr')}/{batch.get('sha')}) field {field}: {row.get(field)!r} differs from {expected!r}")
                break
    if evidence_dir is not None:
        evidence=evidence_dir/"dashboard-data.json"
        if not evidence.exists():
            errors.append(f"{evidence} missing (the build-input evidence must ship with the artifacts)")
        elif json.loads(evidence.read_text(encoding="utf-8"))!=payload:
            errors.append("evidence dashboard-data.json differs from web/data/triton.json")
    return errors
