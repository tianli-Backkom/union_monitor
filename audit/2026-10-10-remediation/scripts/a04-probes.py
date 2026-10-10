#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A04 整改复验探针：采集入口枚举全部历史 attempt。

以 audit/2026-10-10 对抗审查 A04 的同一组输入复跑反例：发现查询返回
run_attempt=3 的单一 run 时，生产 collect() 必须枚举 attempt 1/2/3 并逐一
抓取其 jobs，历史 attempt 的身份与起点/完成证据保留且不继承当前 attempt
的运行字段；仅请求 attempts/3/jobs 得到 1 个批次的旧行为不得复现。

全部数据为进程内合成输入，不发起网络请求，不修改任何业务源码、测试、
冻结证据或真实快照。
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from triton import dashboard as d  # noqa: E402


def row(attempt=1, **kw):
    x = {"id": 1, "event": "pull_request", "head_sha": "abc",
         "created_at": "2026-10-08T00:00:00Z",
         "run_started_at": "2026-10-08T02:00:00Z",
         "updated_at": "2026-10-08T02:05:00Z",
         "run_attempt": attempt, "status": "completed", "conclusion": "success",
         "jobs_complete": True, "jobs": [],
         "pr": 23, "pr_url": "https://github.com/triton-lang/triton-ascend/pull/23",
         "pr_title": "Synthetic", "base_branch": "main", "trigger_at": None,
         "trigger_exact": False,
         "pr_evidence": {"method": "synthetic", "run_id": 1, "pr": 23,
                         "resolved_head_sha": "abc"}}
    x.update(kw)
    return x


class MemoryPath:
    def mkdir(self, *a, **kw): pass
    def __truediv__(self, other): return self
    def __str__(self): return "memory-only"
    def __fspath__(self): return "memory-only"


def make_api(source_rows, jobs_by_attempt):
    calls = []

    class API:
        def __init__(self): self.calls = 0

        def get(self, path):
            params = parse_qs(urlsplit(path).query)
            if "created" in params:
                lo, hi = params["created"][0].split("..")
                matches = [] if "event=pull_request_target" in path else [
                    x for x in source_rows
                    if d.dt(lo) <= d.dt(x["created_at"]) <= d.dt(hi)]
            else:
                matches = [] if "event=pull_request_target" in path else list(source_rows)
            return {"total_count": len(matches)}, {}

        def pages(self, path, field=None):
            calls.append(path)
            if field == "jobs":
                attempt = int(re.search(r"/attempts/(\d+)", path).group(1))
                return copy.deepcopy(jobs_by_attempt[attempt])
            if "event=pull_request_target" in path:
                return []
            params = parse_qs(urlsplit(path).query)
            if "created" in params:
                lo, hi = params["created"][0].split("..")
                return [copy.deepcopy(x) for x in source_rows
                        if d.dt(lo) <= d.dt(x["created_at"]) <= d.dt(hi)]
            return [copy.deepcopy(x) for x in source_rows]

    return API, calls


def resolve(self, x):
    return {k: x[k] for k in ("pr", "pr_url", "pr_title", "base_branch",
                              "head_sha", "pr_evidence")}


def run_collect(source_rows, jobs_by_attempt):
    api, calls = make_api(source_rows, jobs_by_attempt)
    with patch.object(d, "GitHub", api), \
         patch.object(d, "EVIDENCE", MemoryPath()), \
         patch.object(d, "_write_json", side_effect=lambda p, v: None), \
         patch("triton.pr_identity.PRResolver.resolve", resolve):
        payload = d.collect(72, "2026-10-09T00:00:00Z")
    return payload, calls


def main():
    # Case 1: the frozen adversarial shape — jobs carry only id/name.
    payload, calls = run_collect([row(3)], {n: [{"id": 100 + n, "name": "CPU"}]
                                            for n in (1, 2, 3)})
    frozen_shape = {
        "attempts": sorted(w["attempt"] for b in payload["batches"] for w in b["workflows"]),
        "job_calls": sorted(int(re.search(r"/attempts/(\d+)", c).group(1))
                            for c in calls if "/jobs" in c),
        "batches": len(payload["batches"]),
        "job_ids_per_attempt": {str(w["attempt"]): [j["id"] for j in w["jobs"]]
                                for b in payload["batches"] for w in b["workflows"]},
    }

    # Case 2: the real-data shape — each attempt's jobs carry full timing evidence.
    def job(job_id, created, completed, conclusion="success"):
        return {"id": job_id, "name": "build", "created_at": created,
                "started_at": created, "completed_at": completed,
                "status": "completed", "conclusion": conclusion}

    rich = row(3, run_started_at="2026-10-08T06:00:00Z",
               updated_at="2026-10-08T06:10:00Z")
    payload, calls = run_collect([rich], {
        1: [job(101, "2026-10-08T00:00:05Z", "2026-10-08T00:05:00Z")],
        2: [job(102, "2026-10-08T03:00:05Z", "2026-10-08T03:04:00Z", conclusion="failure")],
        3: [job(103, "2026-10-08T06:00:05Z", "2026-10-08T06:10:00Z")]})
    batches = {f'{b["kind"]}-{b["workflows"][0]["attempt"]}': b for b in payload["batches"]}
    rich_shape = {
        "attempts": sorted(w["attempt"] for b in payload["batches"] for w in b["workflows"]),
        "initial": {k: batches["initial-1"][k] for k in ("start_at", "duration_seconds", "status")},
        "rerun_2": {k: batches["rerun-2"][k] for k in ("start_at", "duration_seconds", "status")},
        "rerun_3": {k: batches["rerun-3"][k] for k in ("start_at", "duration_seconds", "status")},
    }

    checks = {
        "frozen_shape_enumerates_all_attempts": (
            frozen_shape["attempts"] == [1, 2, 3]
            and frozen_shape["job_calls"] == [1, 2, 3]
            and frozen_shape["batches"] == 3
            and frozen_shape["job_ids_per_attempt"] == {"1": [101], "2": [102], "3": [103]}),
        "rich_shape_derives_per_attempt_evidence": (
            rich_shape["attempts"] == [1, 2, 3]
            and rich_shape["initial"] == {"start_at": "2026-10-08T00:00:00Z",
                                          "duration_seconds": 300, "status": "success"}
            and rich_shape["rerun_2"] == {"start_at": "2026-10-08T03:00:05Z",
                                          "duration_seconds": 235, "status": "failure"}
            and rich_shape["rerun_3"] == {"start_at": "2026-10-08T06:00:00Z",
                                          "duration_seconds": 600, "status": "success"}),
    }
    report = {
        "finding": "A04 · P1 · 采集入口只获取最新attempt，遗漏历史attempt的jobs",
        "requirements": ["REQ-015"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": {"collector_enumerates_only_current_attempt_fixed": frozen_shape,
                   "per_attempt_timing_evidence": rich_shape},
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic rows; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/data-adversarial.py probe collector-still-enumerates-only-current-attempt: discovery returns one run at run_attempt=3, then production collect(72, as_of) runs with all I/O mocked.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a04-attempt-enumeration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
