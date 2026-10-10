#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A07 整改复验探针：分页 total_count 以首页为准并要求记录身份。

以 audit/2026-10-10 对抗审查 A07 的同一组输入复跑反例：分页声明
total_count 由 150 变 100 且第二页为空时，旧行为返回 100 条且不拒绝
（截断被掩盖）；无 id 的重复页（两页各 100 条同名记录）旧行为返回
200 条且不拒绝（重复计数）。修复后两者必须明确失败；冻结的既有六个
分页契约用例（缺字段/null/非数组、合法零数据、有 id 重复页、缺页数
量不符）保持原判定；bare-array 提交列表（记录无 id）在唯一时仍被接
受，重复时按内容指纹拒绝。

全部数据为进程内合成输入，不发起网络请求，不修改任何业务源码、
测试、冻结证据或真实快照。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from triton import dashboard as d  # noqa: E402


def probe(responses, field="workflow_runs"):
    path = "/actions/runs" if field else "/pulls/1/commits"
    with patch.object(d.GitHub, "get", side_effect=[(x, {}) for x in responses]):
        try:
            return {"rejected": False, "count": len(d.GitHub().pages(path, field))}
        except Exception as e:
            return {"rejected": True, "error": str(e)}


def main():
    first = [{"id": i} for i in range(100)]
    no_id_page = [{"name": "same"}] * 100
    sha_page = [{"sha": format(i, "040x")} for i in range(100)]
    sha_tail = [{"sha": format(i, "040x")} for i in range(100, 103)]

    cases = {
        # audit/2026-10-10/scripts/data-adversarial.py pagination_cases（冻结用例）
        "workflow-schema-missing": ([{}], "workflow_runs", {"rejected": True}),
        "workflow-schema-null": ([{"workflow_runs": None}], "workflow_runs", {"rejected": True}),
        "workflow-schema-object": ([{"workflow_runs": {}}], "workflow_runs", {"rejected": True}),
        "legal-zero-page": ([{"total_count": 0, "workflow_runs": []}], "workflow_runs",
                            {"rejected": False, "count": 0}),
        "duplicate-page-id": ([{"total_count": 101, "workflow_runs": first},
                               {"total_count": 101, "workflow_runs": [{"id": 0}]}],
                              "workflow_runs", {"rejected": True}),
        "declared-count-missing-page": ([{"total_count": 101, "workflow_runs": first},
                                         {"total_count": 101, "workflow_runs": []}],
                                        "workflow_runs", {"rejected": True}),
        "declared-count-changes-hide-truncation": ([{"total_count": 150, "workflow_runs": first},
                                                    {"total_count": 100, "workflow_runs": []}],
                                                   "workflow_runs", {"rejected": True}),
        "duplicate-records-without-id": ([{"total_count": 200, "workflow_runs": no_id_page},
                                          {"total_count": 200, "workflow_runs": no_id_page},
                                          {"total_count": 200, "workflow_runs": []}],
                                         "workflow_runs", {"rejected": True}),
        # 整改新增行为：bare-array 提交列表（/pulls/{n}/commits 记录无 id）
        "bare-array-unique-commits-still-accepted": ([sha_page, sha_tail], None,
                                                     {"rejected": False, "count": 103}),
        "bare-array-duplicate-commits-rejected-by-content": ([sha_page, sha_page[:1]], None,
                                                             {"rejected": True}),
    }

    probes = {}
    checks = {}
    for name, (responses, field, expected) in cases.items():
        actual = probe(responses, field)
        probes[name] = {"expected": expected, "actual": actual}
        checks[name] = (actual["rejected"] == expected["rejected"]
                        and ("count" not in expected or actual.get("count") == expected["count"]))

    report = {
        "finding": "A07 · P2 · API分页数量漂移及无ID重复页未拒绝",
        "requirements": ["REQ-018"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic responses; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/data-adversarial.py pagination_cases: the six previously-passing contract probes keep their frozen verdicts and the two A07 defects (declared-count-changes-hide-truncation, duplicate-records-without-id) are now rejected.",
            "Pre-fix frozen evidence recorded rejected=False for the two A07 cases (100 and 200 records returned silently); this probe asserts the fixed contract.",
            "The bare-array cases cover /pulls/{n}/commits commit lists whose records carry no id: unique records stay accepted, duplicated content is rejected by content fingerprint.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a07-pagination-contract.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
