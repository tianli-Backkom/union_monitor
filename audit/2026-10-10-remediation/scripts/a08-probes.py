#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A08 整改复验探针：逐 workflow 按适用起点判定时间倒置。

以 audit/2026-10-10 对抗审查 A08 的同一组输入复跑反例：同 SHA 两条
workflow，一条可信精确触发 02:00 但 01:00 已结束（完成早于自身适用
起点），另一条合法 00:30 开始 03:00 结束。旧行为批次起点取全部精确
触发的最小值（00:30）且门禁只比对 workflow 自身 created_at，倒置被
辅助 workflow 掩盖，quality.passed=true。修复后每条 completed
workflow 都按自身适用起点（可信精确触发）逐条判定，掩盖不再可能；
冻结的基线、单条倒置与 as_of 越界邻例保持原判定。

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
        return {"passed": report["passed"], "errors": report["errors"]}
    except Exception as e:
        return {"passed": False, "exception": type(e).__name__ + ": " + str(e)}


def main():
    good = row(2)
    inverted = row(2, updated_at="2026-10-08T01:00:00Z")
    late = row(2, updated_at="2026-10-09T01:00:00Z")
    exact = row(2, trigger_at="2026-10-08T02:00:00Z", trigger_exact=True)
    bad = row(1, trigger_at="2026-10-08T02:00:00Z", trigger_exact=True,
              updated_at="2026-10-08T01:00:00Z")
    aux = row(1, id=2, trigger_at="2026-10-08T00:30:00Z", trigger_exact=True,
              updated_at="2026-10-08T03:00:00Z")

    cases = {
        # audit/2026-10-10/scripts/data-adversarial.py quality_cases（冻结邻例）
        "baseline-quality-control": ([good], {"passed": True}),
        "rerun-end-before-start": ([inverted], {"passed": False}),
        "completed-after-as-of": ([late], {"passed": False}),
        # 整改新增行为：合法精确触发不被误伤、无掩盖者的单条倒置同样被拒
        "exact-trigger-legal-passes": ([exact], {"passed": True}),
        "inverted-applicable-start-single": ([bad], {"passed": False}),
        # 冻结反例（A08 缺陷）
        "other-workflow-masks-inverted-applicable-start": ([bad, aux], {"passed": False}),
    }

    probes = {}
    checks = {}
    for name, (rows, expected) in cases.items():
        actual = gate(rows, payload(rows))
        probes[name] = {"expected": expected, "actual": actual}
        checks[name] = actual["passed"] == expected["passed"]

    report = {
        "finding": "A08 · P2 · 同SHA辅助workflow掩盖另一workflow时间倒置",
        "requirements": ["REQ-019"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic rows; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/data-adversarial.py quality_cases: the frozen A08 counterexample and its baseline neighbours keep their frozen verdicts; the masked inversion is now rejected per workflow.",
            "Pre-fix frozen evidence recorded passed=true for other-workflow-masks-inverted-applicable-start (the batch start, the minimum over exact triggers, masked the bad workflow); this probe asserts the fixed gate.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a08-applicable-start-gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
