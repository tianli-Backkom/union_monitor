#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A09 整改复验探针：质量门禁独立重推 as_of、有效耗时与汇总契约。

以 audit/2026-10-10 对抗审查 A09 的同一组输入复跑反例：window_end
缺失或不可解析、完成样本 duration 为负数/null/布尔/字符串或与起止
不符、summary.valid/p90 被篡改、运行中批次 NaN 观测跨度——旧行为
均 quality.passed=true。修复后门禁在携带数据时强制要求可解析的
as_of 参照、按批次独立重算 summary 并逐键比对（api_calls 为采集遥
测、非批次派生，豁免），完成样本 duration 复用严格有限非负判断并
核对起止跨度，运行中批次拒绝 NaN/无穷；冻结的基线与 NPU 语义邻例
（源倒置 warning、未启动跳过/取消不误判）保持原判定。

全部数据为进程内合成输入，不发起网络请求，不修改任何业务源码、
测试、冻结证据或真实快照。
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from triton import dashboard as d  # noqa: E402
from triton.quality import validate  # noqa: E402


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
    if x["id"] != 1:
        x["pr_evidence"] = {**x["pr_evidence"], "run_id": x["id"]}
    return x


def payload(rows, end="2026-10-09T00:00:00Z", start="2026-10-07T00:00:00Z"):
    return d.build_payload(copy.deepcopy(rows), start, end, end)


def gate(rows, p):
    try:
        report = validate(rows, p)
        return {"passed": report["passed"], "errors": report["errors"],
                "warnings": len(report["warnings"])}
    except Exception as e:
        return {"passed": False, "exception": type(e).__name__ + ": " + str(e),
                "warnings": 0}


def main():
    good = row(2)
    gp = payload([good])

    cases = []
    # 冻结邻例（基线）
    cases.append(("baseline-quality-control", [good], copy.deepcopy(gp), {"passed": True}))
    # 冻结反例：as_of 参照缺失/不可解析
    for label, value in [("missing", None), ("invalid", "not-a-date")]:
        p = copy.deepcopy(gp); p["window_end"] = value
        cases.append((f"invalid-as-of-{label}", [good], p, {"passed": False}))
    # 冻结反例：完成样本非法 duration
    for label, value in [("negative", -1), ("null", None), ("bool", True),
                         ("string", "300"), ("wrong-span", 999)]:
        p = copy.deepcopy(gp); p["batches"][0]["duration_seconds"] = value
        cases.append((f"quality-duration-{label}", [good], p, {"passed": False}))
    # 冻结反例：矛盾 summary
    p = copy.deepcopy(gp); p["summary"]["valid"] = 99; p["summary"]["p90"] = 999
    cases.append(("quality-contradictory-summary", [good], p, {"passed": False}))
    # 冻结反例：运行中 NaN 观测跨度
    running = row(2, status="in_progress", conclusion=None, updated_at="2026-10-08T02:30:00Z")
    p = payload([running]); p["batches"][0]["duration_seconds"] = float("nan")
    cases.append(("running-nan-observed-span", [running], p, {"passed": False}))
    # 冻结邻例：NPU 语义（REQ-019-AC04）
    job = {"id": 8, "name": "integration-tests-ascend (linux-amd64-a5-2, py3.12)",
           "status": "completed", "conclusion": "success",
           "created_at": "2026-10-08T02:02:00Z", "started_at": "2026-10-08T02:01:00Z",
           "completed_at": "2026-10-08T02:04:00Z"}
    x = row(2, jobs=[copy.deepcopy(job)]); p = payload([x])
    cases.append(("npu-inverted-source-warning", [x], p,
                  {"passed": True, "warnings": 1, "queue": None}))
    for state in ["skipped", "cancelled"]:
        j = {**job, "conclusion": state, "started_at": None, "completed_at": None}
        x = row(2, jobs=[copy.deepcopy(j)]); p = payload([x])
        cases.append((f"npu-unstarted-{state}", [x], p, {"passed": True}))

    summary_cases = {"quality-contradictory-summary"} | {
        f"quality-duration-{l}" for l in ("negative", "null", "bool", "string", "wrong-span")}
    probes = {}
    checks = {}
    for name, rows, p, expected in cases:
        actual = gate(rows, p)
        if name == "npu-inverted-source-warning":
            actual = {**actual, "queue": p["batches"][0]["npu_queue_seconds"]}
        if name in summary_cases:
            actual = {**actual, "stored_summary": p["summary"],
                      "independent_summary": d.summary_of(p["batches"])}
        probes[name] = {"expected": expected, "actual": actual}
        checks[name] = all(actual.get(k) == v for k, v in expected.items())

    report = {
        "finding": "A09 · P2 · quality未核对as_of、有效耗时和汇总契约",
        "requirements": ["REQ-019"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic rows; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/data-adversarial.py quality_cases: the four A09 defect groups (invalid-as-of-*, quality-duration-*, quality-contradictory-summary, running-nan-observed-span) are now rejected; the baseline and REQ-019-AC04 NPU neighbours keep their frozen verdicts.",
            "Pre-fix frozen evidence recorded passed=true for every A09 case; this probe asserts the fixed gate re-derives the as-of reference, valid durations and the summary instead of trusting the stored copy.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a09-summary-duration-gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
