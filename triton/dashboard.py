#!/usr/bin/env python3
"""Collect Triton-Ascend PR checks and build a portable operations dashboard."""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .quality import CSV_FIELDS

REPO = "triton-lang/triton-ascend"
API = f"https://api.github.com/repos/{REPO}"
REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = REPO_ROOT / "evidence" / "triton"
UTC = timezone.utc
FOCUS_JOBS = {
    "linux-aarch64-a3-800i-4, py3.10": "a3-py310",
    "linux-aarch64-a3-800i-4, py3.11": "a3-py311",
    "linux-aarch64-a5-800i-4, py3.12": "a5-py312",
}


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def _duration_seconds(text):
    total = 0
    for amount, unit in __import__("re").findall(r"(\d+)\s*([hms])", text or ""):
        total += int(amount) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def extract_focus_job_links(source):
    """Find the three community-operations matrix jobs exposed by a run page."""
    import re
    found={}
    pattern=r'<a\b[^>]*href="([^"]*/actions/runs/(\d+)/job/(\d+)[^"]*)"[^>]*>\s*<strong>(.*?)</strong>'
    for href,run_id,job_id,label_html in re.findall(pattern,source,re.I|re.S):
        label=html.unescape(re.sub(r"<[^>]+>","",label_html)).strip()
        matched=next(((needle,key) for needle,key in FOCUS_JOBS.items() if needle in label),None)
        if not matched: continue
        url="https://github.com"+html.unescape(href).split("#",1)[0]
        found[int(job_id)]={"id":int(job_id),"run_id":int(run_id),"name":label,"key":matched[1],"url":url}
    return list(found.values())


def parse_job_header(source, run_created_at, as_of):
    """Derive job wait/execution timing from GitHub's public job header fragment."""
    import re
    text=html.unescape(re.sub(r"<[^>]+>"," ",source))
    text=" ".join(text.split()).lower()
    timestamp=re.search(r'datetime="([^"]+)"',source,re.I)
    duration=re.search(r'\bin\s+((?:\d+\s*[hms]\s*)+)',text,re.I)
    run_seconds=_duration_seconds(duration.group(1)) if duration else None
    completed_at=dt(timestamp.group(1)) if timestamp else None
    started_at=completed_at-timedelta(seconds=run_seconds) if completed_at and run_seconds is not None else None
    created_at=dt(run_created_at)
    if "queued" in text or "waiting" in text:
        status="queued";conclusion=None
    elif "in progress" in text:
        status="in_progress";conclusion=None
    else:
        status="completed" if completed_at else "unknown"
        conclusion="failure" if "failed" in text else "cancelled" if "cancel" in text else "success" if "succeeded" in text else None
    wait_seconds=max(0,(started_at-created_at).total_seconds()) if started_at and created_at else None
    if status in ("queued","in_progress") and created_at:
        wait_seconds=max(0,(dt(as_of)-created_at).total_seconds()) if status=="queued" else wait_seconds
    return {"status":status,"conclusion":conclusion,
            "started_at":iso(started_at) if started_at else None,"completed_at":iso(completed_at) if completed_at else None,
            "wait_seconds":wait_seconds,"run_seconds":run_seconds}


def parse_run_html(source):
    """Parse public Actions HTML. Used for PR linkage and job names without API quota."""
    import re
    clean=lambda value: html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()
    def first(pattern):
        match=re.search(pattern,source,re.I|re.S)
        return clean(match.group(1)) if match else None
    name=first(r'PageHeader-parentLink-label[^>]*>(.*?)</span>')
    title=first(r'class="markdown-title"[^>]*>(.*?)</span>')
    pr_match=re.search(r'href="/triton-lang/triton-ascend/pull/(\d+)"',source)
    at=first(r'<relative-time[^>]+datetime="([^"]+)"')
    label=(first(r'aria-label="([^"]+):\s*"') or "").lower()
    if "failure" in label: conclusion="failure"
    elif "cancel" in label: conclusion="cancelled"
    elif "success" in label: conclusion="success"
    else: conclusion=None
    status="completed" if conclusion else "in_progress"
    jobs=[]
    for block in re.findall(r'<streaming-graph-job\b.*?</streaming-graph-job>',source,re.I|re.S):
        job_name=first.__wrapped__(r'') if False else None
        match=re.search(r'data-target="streaming-graph-job.name"[^>]*>(.*?)</span>',block,re.I|re.S)
        if not match: continue
        job_name=clean(match.group(1))
        duration_match=re.search(r'flex-self-baseline[^>]*>(.*?)</div>',block,re.I|re.S)
        duration=_duration_seconds(clean(duration_match.group(1))) if duration_match else None
        failed="failure" in block.lower() or "color-fg-danger" in block.lower()
        jobs.append({"name":job_name,"status":"completed" if conclusion else "in_progress",
                     "conclusion":"failure" if failed else ("success" if conclusion else None),
                     "duration_seconds":duration,"steps":[]})
    return {"name":name,"pr":int(pr_match.group(1)) if pr_match else None,"pr_title":title,
            "created_at":at,"status":status,"conclusion":conclusion,"jobs":jobs}


def parse_pr_base_html(source):
    """Extract the PR merge target branch from GitHub's embedded page payload."""
    import re
    match=re.search(r'"baseBranch"\s*:\s*"([^"]+)"',source)
    return html.unescape(match.group(1)) if match else None


def extract_pr_base_ref(payload):
    """Read the target branch from GitHub's pull request API response."""
    return ((payload or {}).get("base") or {}).get("ref")


def merge_run_evidence(api_row, page_row):
    """Combine sources while retaining authoritative REST lifecycle fields."""
    merged={**api_row,**page_row}
    merged["status"]=api_row.get("status") or page_row.get("status")
    merged["conclusion"]=api_row.get("conclusion") if api_row.get("status")=="completed" else page_row.get("conclusion")
    merged["created_at"]=api_row.get("created_at") or page_row.get("created_at")
    merged["name"]=api_row.get("name") or page_row.get("name")
    return merged


def _job(row):
    start = dt(row.get("started_at"))
    end = dt(row.get("completed_at"))
    created = dt(row.get("created_at"))
    return {
        "id": row.get("id"), "name": row.get("name") or "未命名任务",
        "status": row.get("status"), "conclusion": row.get("conclusion"),
        "created_at": row.get("created_at"), "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"), "url": row.get("html_url"),
        "runner_name": row.get("runner_name"), "runner_label": row.get("runner_label"),
        "wait_seconds": (start-created).total_seconds() if start and created and start >= created else None,
        "measurement_error": "源时间戳异常：开始时间早于创建时间" if start and created and start < created else None,
        "run_seconds": max(0, (end-start).total_seconds()) if start and end else row.get("duration_seconds"),
        "failed_steps": [s.get("name") for s in row.get("steps", []) if s.get("conclusion") in ("failure", "timed_out", "action_required")],
    }


def focus_from_jobs(jobs):
    import re
    result=[]
    for raw in jobs:
        name=raw.get("name", "")
        chip=re.search(r"linux-(?:aarch64|amd64)-(a[35])-",name)
        py=re.search(r"py(3\.(?:10|11|12))",name)
        if chip and py:
            job=_job(raw)
            job["key"]=chip[1]+"-py"+py[1].replace(".","")
            result.append(job)
    return result


def _is_npu_job(job):
    import re
    identity=" ".join(str(job.get(key) or "") for key in ("name","runner_name","runner_label")).lower()
    return bool(re.search(r"linux-(?:aarch64|amd64)-a\d",identity) or "ascend950" in identity)


RERUN_LOOKBACK = timedelta(days=14)


def run_in_window(row, start, end):
    """A run belongs to the window when the current attempt started inside it
    (a rerun may target a run first created long before the window) or when the
    run itself was created inside it; fully out-of-window runs are association
    evidence only and never counted into the current window."""
    for field in ("run_started_at", "created_at"):
        value = dt(row.get(field))
        if value and start <= value <= end:
            return True
    return False


def build_batches(runs, as_of, window_start=None):
    """Group independently-triggered workflows by PR head SHA; keep reruns separate.

    Attempt identity is (run_id, run_attempt): attempt 1 rows join the initial
    PR+SHA batch together with auxiliary workflows, every later attempt is its
    own batch keyed by run and attempt, so history is never overwritten by the
    latest attempt and re-collecting an attempt never doubles it."""
    now = dt(as_of)
    unique = {}
    for row in sorted(runs,key=lambda r:r.get("created_at") or ""):
        unique[(row.get("id"), int(row.get("run_attempt") or 1))] = row
    groups = defaultdict(list)
    for row in unique.values():
        attempt = int(row.get("run_attempt") or 1)
        if attempt > 1:
            key = (row.get("pr"), row.get("head_sha"), "rerun", row.get("id"), attempt)
        else:
            # A pushed commit is the E2E identity. Auxiliary workflows may start much later,
            # but they still belong to the same PR head SHA and must not create extra dots.
            key = (row.get("pr"), row.get("head_sha"), "initial") if row.get("pr") else (None, row.get("head_sha"), "unresolved", row.get("id"), attempt)
        groups[key].append(row)
    batches = []
    for key, rows in groups.items():
        rows.sort(key=lambda r: r.get("created_at") or "")
        exact_times = [dt(r.get("trigger_at")) for r in rows if r.get("trigger_exact") and dt(r.get("trigger_at"))]
        if exact_times:
            # A trusted trigger event for this attempt wins over any derived start.
            exact = True; start = min(exact_times); start_source = "trigger_event"
        elif key[2] == "rerun":
            # The run's created_at is the FIRST attempt's start; using it here would bill
            # the gap between attempts to this rerun. Only the attempt's own start
            # (run_started_at) is provable for this attempt; without it E2E stays empty.
            attempt_starts = [dt(r.get("run_started_at")) for r in rows if dt(r.get("run_started_at"))]
            exact = False; start = min(attempt_starts) if attempt_starts else None
            start_source = "attempt_start" if start else None
        else:
            created_times = [dt(r.get("created_at")) for r in rows if dt(r.get("created_at"))]
            exact = False; start = min(created_times) if created_times else None
            start_source = "workflow_created" if start else None
        running = any(r.get("status") != "completed" for r in rows)
        ends = [dt(r.get("updated_at")) for r in rows if r.get("status") == "completed" and dt(r.get("updated_at"))]
        end = max(ends) if ends and not running else None
        conclusions = {r.get("conclusion") for r in rows}
        if running:
            status = "running"
        elif conclusions & {"failure", "timed_out", "action_required", "startup_failure"}:
            status = "failure"
        elif conclusions & {"cancelled", "stale"}:
            status = "cancelled"
        elif conclusions <= {"success", "skipped", "neutral", None}:
            status = "success"
        else:
            status = "unknown"
        # REQ-019: a completed batch without end evidence must not have its E2E
        # fabricated by measuring to as_of; only running batches observe to now.
        measured_end = end or (now if running else None)
        span = (measured_end - start).total_seconds() if start and measured_end else None
        # REQ-019: an inverted span is invalid evidence, never a clamped 0-second E2E.
        inverted = span is not None and span < 0
        duration = None if inverted else span
        critical = max(rows, key=lambda r: dt(r.get("updated_at")) or datetime.min.replace(tzinfo=UTC))
        action = next((r for r in rows if (r.get("name") or "").lower()=="integration tests"), critical)
        workflows = []
        focus_jobs=[]
        for r in rows:
            focus_jobs.extend(r.get("focus_jobs",[]))
            workflows.append({
                "id": r.get("id"), "name": r.get("name") or "未命名 workflow",
                "status": r.get("status"), "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"), "updated_at": r.get("updated_at"),
                "url": r.get("html_url"), "attempt": r.get("run_attempt") or 1,
                "jobs": [_job(j) for j in r.get("jobs", [])],
                "jobs_complete": bool(r.get("jobs_complete")),
                "event":r.get("event"), "pr":r.get("pr"), "pr_url":r.get("pr_url"), "head_sha":r.get("head_sha"), "pr_evidence":r.get("pr_evidence"),
            })
        first = rows[0]
        base_branch=next((r.get("base_branch") for r in rows if r.get("base_branch")),None)
        npu_jobs=[job for workflow in workflows for job in workflow["jobs"] if _is_npu_job(job)]
        npu_waits=[job["wait_seconds"] for job in npu_jobs if job.get("wait_seconds") is not None]
        npu_missing=any(r.get("jobs_complete") is False for r in rows) or any(j.get("wait_seconds") is None and j.get("conclusion")!="skipped" for j in npu_jobs)
        missing = []
        if inverted: missing.append("workflow 时间倒置，E2E 无效")
        if not running and start and end is None: missing.append("无完成时间证据，E2E 留空")
        if key[2] == "rerun" and start is None: missing.append("无本次 attempt 起点证据，E2E 留空")
        if any(not r.get("jobs_complete") for r in rows): missing.append("部分 workflow 的 job 明细未采集")
        if not first.get("pr"): missing.append("未可靠关联 PR")
        batches.append({
            "id": "-".join(str(x) for x in key if x is not None),
            "pr": first.get("pr"), "title": first.get("pr_title") or "标题未获取",
            "pr_url": first.get("pr_url"), "author": first.get("author"),
            "branch": first.get("branch"), "base_branch":base_branch or "未知目标分支", "sha": first.get("head_sha"),
            "kind": "rerun" if key[2] == "rerun" else "initial",
            "start_at": iso(start) if start else None, "end_at": iso(end) if end else None,
            "duration_seconds": duration, "status": status,
            "complete": status in ("success", "failure") and not missing,
            "approximate": start is not None and not exact, "start_source": start_source,
            "critical_workflow": critical.get("name"),
            "action_url": action.get("html_url"), "action_name": action.get("name") or "GitHub Actions",
            "workflows": workflows, "focus_jobs":focus_jobs, "npu_jobs":npu_jobs,
            "npu_data_missing": npu_missing, "npu_queue_seconds":max(npu_waits) if npu_waits and not npu_missing else None, "missing": missing,
        })
    batches.sort(key=lambda b: b["start_at"] or "")
    if window_start:
        # Out-of-window attempts are association evidence only: batches whose own
        # start falls before the display window are never counted into it.
        boundary = dt(window_start)
        batches = [b for b in batches if not b["start_at"] or dt(b["start_at"]) >= boundary]
    by_pr=defaultdict(list)
    for batch in batches: by_pr[batch.get("pr")].append(batch)
    for rows in by_pr.values():
        for index,batch in enumerate(rows,1):
            batch["e2e_index"]=index;batch["e2e_total"]=len(rows)
    return batches


class GitHub:
    def __init__(self):
        self.token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.calls = 0

    def get(self, url):
        target = url if url.startswith("https://") else API + url
        headers = {"Accept":"application/vnd.github+json", "User-Agent":"triton-gate-e2e-dashboard", "X-GitHub-Api-Version":"2022-11-28"}
        if self.token: headers["Authorization"] = "Bearer " + self.token
        for attempt in range(4):
            try:
                self.calls += 1
                with urllib.request.urlopen(urllib.request.Request(target, headers=headers), timeout=45) as response:
                    return json.load(response), dict(response.headers)
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429):
                    reset = int(exc.headers.get("X-RateLimit-Reset", "0"))
                    wait = reset - int(time.time()) + 2
                    if 0 < wait <= 60 and attempt < 3:
                        time.sleep(wait); continue
                    raise RuntimeError("GitHub API 配额不足。请设置 GH_TOKEN 后重新运行。") from None
                if exc.code >= 500 and attempt < 3:
                    time.sleep(2 ** attempt); continue
                raise

    def pages(self, path, field=None, limit=None):
        out=[]; page=1; expected=None; seen=set()
        while True:
            sep="&" if "?" in path else "?"
            data,_=self.get(f"{path}{sep}per_page=100&page={page}")
            if field is not None:
                # REQ-018: a missing, null or non-array list field is a contract
                # failure that fails the refresh; it is never a legal empty page.
                if not isinstance(data, dict) or not isinstance(data.get(field), list):
                    raise RuntimeError(f"{path}: page {page} response has no usable '{field}' array")
                rows=data[field]
            else:
                rows=data
                if not isinstance(rows, list):
                    raise RuntimeError(f"{path}: page {page} response is not a JSON array")
            declared=data.get("total_count") if isinstance(data, dict) else None
            if isinstance(declared,int): expected=declared
            for row in rows:
                if not isinstance(row, dict): raise RuntimeError(f"{path}: page {page} contains a non-object record")
                identity=row.get("id")
                if identity is not None:
                    if identity in seen: raise RuntimeError(f"{path}: duplicate record id={identity} across pages")
                    seen.add(identity)
            if len(rows)<100 and expected is not None and len(out)+len(rows)!=expected:
                raise RuntimeError(f"{path}: pagination incomplete: total_count={expected}, received {len(out)+len(rows)}")
            out.extend(rows)
            if len(rows)<100 or (limit and len(out)>=limit): return out[:limit] if limit else out
            page += 1


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def augment_focus_jobs(runs, as_of):
    """Fetch public header fragments for the three requested NPU matrix jobs."""
    links={}
    run_by_id={int(r["id"]):r for r in runs}
    for run_id,row in run_by_id.items():
        page=EVIDENCE/"run-pages"/f"{run_id}.html"
        if not page.exists(): continue
        for job in extract_focus_job_links(page.read_text(encoding="utf-8")):
            links[job["id"]]=job
    def fetch(job):
        cache=EVIDENCE/"job-headers"/f"{job['id']}.html"
        if cache.exists(): source=cache.read_text(encoding="utf-8")
        else:
            url=f"https://github.com/{REPO}/runs/{job['id']}/header"
            request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 triton-gate-e2e","X-Requested-With":"XMLHttpRequest"})
            with urllib.request.urlopen(request,timeout=45) as response: source=response.read().decode("utf-8","replace")
            cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(source,encoding="utf-8")
        run=run_by_id.get(job["run_id"],{})
        return {**job,**parse_job_header(source,run.get("created_at"),as_of)}
    by_run=defaultdict(list)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures={pool.submit(fetch,job):job for job in links.values()}
        for index,future in enumerate(as_completed(futures),1):
            try:
                job=future.result();by_run[job["run_id"]].append(job)
            except Exception as exc:
                job=futures[future];by_run[job["run_id"]].append({**job,"status":"unknown","wait_seconds":None,"run_seconds":None,"error":str(exc)})
            if index%50==0: print(f"focus jobs {index}/{len(links)}",flush=True)
    for run in runs: run["focus_jobs"]=sorted(by_run.get(int(run["id"]),[]),key=lambda j:j["key"])
    return runs


def augment_base_branches(runs, fetch_missing=False, api=None):
    """Attach each PR's merge target branch, preferring API evidence and cached PR pages."""
    by_pr={}
    for row in runs:
        for pr in row.get("pull_requests") or []:
            ref=(pr.get("base") or {}).get("ref")
            if ref and row.get("pr"): by_pr[row["pr"]]=ref
    prs={row.get("pr") for row in runs if row.get("pr")}
    def resolve(pr):
        if api is not None:
            try:
                payload,_=api.get(f"/pulls/{pr}")
                return pr,extract_pr_base_ref(payload)
            except Exception:
                # Missing branch metadata must not abort the full dashboard refresh.
                return pr,None
        cache=EVIDENCE/"pr-pages"/f"{pr}.html"
        if cache.exists(): source=cache.read_text(encoding="utf-8")
        elif fetch_missing:
            request=urllib.request.Request(f"https://github.com/{REPO}/pull/{pr}",headers={"User-Agent":"Mozilla/5.0 triton-gate-e2e"})
            try:
                with urllib.request.urlopen(request,timeout=45) as response: source=response.read().decode("utf-8","replace")
            except urllib.error.HTTPError as exc:
                if exc.code in (403,429): return pr,None
                raise
            cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(source,encoding="utf-8")
        else: return pr,None
        return pr,parse_pr_base_html(source)
    unresolved=[pr for pr in prs if pr not in by_pr]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for pr,ref in pool.map(resolve,unresolved):
            if ref: by_pr[pr]=ref
    for row in runs: row["base_branch"]=by_pr.get(row.get("pr"),row.get("base_branch"))
    return runs


def collect(hours=72, as_of=None):
    api=GitHub(); end=dt(as_of) if as_of else datetime.now(UTC).replace(microsecond=0); start=end-timedelta(hours=hours)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    # Query the two native PR event types separately; recursively split intervals to avoid GitHub's 1,000-result cap.
    # A rerun may target a run first created before the window, so discovery reaches
    # RERUN_LOOKBACK further back; run_in_window() then keeps only runs whose current
    # attempt actually acted inside the display window.
    fetch_start=start-RERUN_LOOKBACK
    runs=[]
    def interval(a,b,event):
        created=urllib.parse.quote(f"{iso(a)}..{iso(b)}", safe="")
        path=f"/actions/runs?event={event}&created={created}"
        first,_=api.get(path+"&per_page=1")
        if not isinstance(first, dict) or not isinstance(first.get("total_count"), int):
            raise RuntimeError(f"{path}: response has no usable total_count")
        if first["total_count"]>1000:
            mid=a+(b-a)/2; interval(a,mid,event); interval(mid+timedelta(seconds=1),b,event); return
        runs.extend(api.pages(path,"workflow_runs"))
    for event in ("pull_request","pull_request_target"):
        interval(fetch_start,end,event)
    unique={(r["id"], r.get("run_attempt") or 1):r for r in runs}
    runs=[r for r in unique.values() if run_in_window(r,start,end)]
    _write_json(EVIDENCE/"runs.json", {"collected_at":iso(datetime.now(UTC)),"window_start":iso(start),"fetch_window_start":iso(fetch_start),"window_end":iso(end),"runs":runs})

    # PRs from forks can have empty run.pull_requests and commit/pulls responses.
    from .pr_identity import PRResolver
    resolver=PRResolver(api,EVIDENCE/"pr-associations")
    enriched=[]
    association_errors=[]
    for index,r in enumerate(runs,1):
        row=dict(r)
        try:
            row.update(resolver.resolve(r))
        except Exception as exc:
            association_errors.append({"run_id":r["id"],"url":r.get("html_url"),"error":str(exc)})
            continue
        row.update(author=(r.get("actor") or {}).get("login"),branch=r.get("head_branch"),
                   trigger_at=None,trigger_exact=False)
        try:
            jobs=api.pages(f"/actions/runs/{r['id']}/attempts/{r.get('run_attempt') or 1}/jobs","jobs")
            row.update(jobs=jobs,jobs_complete=True)
            _write_json(EVIDENCE/"jobs"/f"{r['id']}-{r.get('run_attempt') or 1}.json",jobs)
        except Exception as exc:
            row.update(jobs=[],jobs_complete=False,jobs_error=str(exc))
        row["focus_jobs"]=focus_from_jobs(row["jobs"])
        enriched.append(row)
        if index%50==0: print(f"REST jobs {index}/{len(runs)}",flush=True)
    failed_jobs=[r for r in enriched if not r.get("jobs_complete")]
    if failed_jobs:
        _write_json(EVIDENCE/"collection-errors.json", failed_jobs)
        raise RuntimeError(f"{len(failed_jobs)} workflow job lists could not be collected; refusing to publish incomplete refresh")
    if association_errors:
        _write_json(EVIDENCE/"pr-association-errors.json",association_errors)
        raise RuntimeError(f"{len(association_errors)} runs have unresolved PR identities; refusing to publish. See pr-association-errors.json")

    _write_json(EVIDENCE/"enriched-runs.json", enriched)
    return build_payload(enriched, iso(start), iso(end), iso(datetime.now(UTC)), api.calls)


def valid_seconds(value):
    """A valid duration is a finite, non-negative raw number; missing, null,
    numeric strings, NaN, infinities and negatives never become an implicit 0."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def summary_of(batches, calls=0):
    """Summary statistics count only success/failure batches with valid durations
    (REQ-017); running and cancelled batches keep observed values but never
    join the completed-sample statistics."""
    complete = [b for b in batches if b["status"] in ("success", "failure") and valid_seconds(b["duration_seconds"])]
    values = [b["duration_seconds"] for b in complete]
    return {"prs": len({b["pr"] for b in batches if b["pr"]}), "batches": len(batches),
            "valid": len(complete), "median": percentile(values, .5), "p90": percentile(values, .9),
            "approximate": sum(bool(b["approximate"]) for b in batches), "incomplete": sum(bool(b["missing"]) for b in batches),
            "api_calls": calls}


def build_payload(runs, window_start, window_end, collected_at, calls=0):
    for row in runs:
        if row.get("conclusion") in ("skipped","neutral"): row["jobs_complete"]=True
    batches=build_batches(runs, window_end, window_start)
    return {"repo":REPO,"window_start":window_start,"window_end":window_end,"collected_at":collected_at,
            "batches":batches,"summary":summary_of(batches,calls)}


def export_csv(payload):
    path=REPO_ROOT/"web"/"data"/"triton-batches.csv"
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=CSV_FIELDS);w.writeheader()
        for b in payload["batches"]: w.writerow({k:"; ".join(b[k]) if k=="missing" else b.get(k) for k in CSV_FIELDS})


def write_payload(payload):
    data_dir=REPO_ROOT/"web"/"data"
    data_dir.mkdir(parents=True,exist_ok=True)
    (data_dir/"triton.json").write_text(json.dumps(payload,ensure_ascii=False)+"\n",encoding="utf-8")
    export_csv(payload); _write_json(EVIDENCE/"dashboard-data.json",payload)


def main():
    p=argparse.ArgumentParser(description="Collect and build the Triton-Ascend 72-hour PR gate dashboard")
    p.add_argument("--hours",type=int,default=72);p.add_argument("--as-of");p.add_argument("--from-evidence",action="store_true")
    p.add_argument("--refresh-focus",action="store_true",help="Fetch requested A3/A5 job timing from saved run pages")
    args=p.parse_args()
    if args.from_evidence:
        meta=json.loads((EVIDENCE/"runs.json").read_text(encoding="utf-8")); runs=json.loads((EVIDENCE/"enriched-runs.json").read_text(encoding="utf-8"))
        runs=augment_base_branches(runs,fetch_missing=False)
        if args.refresh_focus:
            runs=augment_focus_jobs(runs,meta["window_end"]);_write_json(EVIDENCE/"enriched-runs.json",runs)
        payload=build_payload(runs,meta["window_start"],meta["window_end"],meta["collected_at"])
    else: payload=collect(args.hours,args.as_of)
    from .quality import fingerprint, validate, verify_artifacts
    report=validate(runs if args.from_evidence else json.loads((EVIDENCE/"enriched-runs.json").read_text(encoding="utf-8")),payload)
    _write_json(EVIDENCE/"quality-report.json",report)
    if not report["passed"]:
        raise RuntimeError("Data quality gate failed: "+"; ".join(report["errors"][:10]))
    write_payload(payload)
    _write_json(REPO_ROOT/"web"/"data"/"triton-manifest.json",{"sha256":fingerprint(payload),"collected_at":payload["collected_at"],**report})
    problems=verify_artifacts(REPO_ROOT/"web"/"data",EVIDENCE)
    if problems: raise RuntimeError("Artifact consistency gate failed: "+"; ".join(problems[:10]))
    print(f"Generated web/data/triton.json with {len(payload['batches'])} batches")


if __name__=="__main__": main()
