#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A11 整改复验探针：排队分项严格校验（布尔、负数、NaN、无穷）。

以 audit/2026-10-10 对抗审查 A11 的同一组输入复跑反例：对
waitingTimeMillis 分别注入 True、-12、NaN、Infinity（blocked=5、
buildable=3）——旧行为裸 isinstance(int,float) 全部接受并返回求和
结果与分项，布尔/负数/无穷经求和比对后可被判"已验证"。修复后三项
分项均要求有限、非 bool、非负：任一非法分项使 queue 保持未知
（REQ-024-AC02），不得作为有效排队秒数。冻结的邻例基线（合法
12/5/3 求和 20、真实 0 合法、缺失分项/字符串保持未知）保持原判定。

全部数据为进程内合成输入，不发起网络请求，不修改任何业务源码、
测试、冻结证据或真实快照。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from source_coverage import queue_from_raw  # noqa: E402


def main():
    # 冻结反例：waitingTimeMillis 注入布尔/负数/NaN/无穷
    invalid = []
    for label, value in [('boolean', True), ('negative', -12),
                         ('nan', float('nan')), ('infinity', float('inf'))]:
        queue, parts = queue_from_raw({'actions': [{'waitingTimeMillis': value,
                                                    'blockedTimeMillis': 5, 'buildableTimeMillis': 3}]})
        invalid.append({'input_kind': label, 'queue_returned': repr(queue),
                        'components_accepted': parts is not None})

    # 邻例：其余两键同样逐键把关
    per_key = {}
    for key, value in [('blockedTimeMillis', -1), ('buildableTimeMillis', float('inf'))]:
        row = {'waitingTimeMillis': 12, 'blockedTimeMillis': 3, key: value}
        per_key[key] = queue_from_raw({'actions': [row]})

    # 邻例基线（冻结 REQ-024 AC01/AC02 判定）
    valid = queue_from_raw({'actions': [{'waitingTimeMillis': 12, 'blockedTimeMillis': 5, 'buildableTimeMillis': 3}]})
    zero = queue_from_raw({'actions': [{'waitingTimeMillis': 0, 'blockedTimeMillis': 0, 'buildableTimeMillis': 0}]})
    missing = queue_from_raw({'actions': [{'waitingTimeMillis': 12}]})
    string = queue_from_raw({'actions': [{'waitingTimeMillis': 'x', 'blockedTimeMillis': 5, 'buildableTimeMillis': 3}]})
    empty = queue_from_raw({})

    probes = {
        'invalid_raw_queue_components': invalid,
        'per_key_gating': {key: {'queue': repr(q), 'components': 'dict' if p is not None else None}
                           for key, (q, p) in per_key.items()},
        'baseline_valid_recompute': {'queue': valid[0], 'components': valid[1]},
        'baseline_zero_is_legal': {'queue': zero[0], 'components': zero[1]},
        'baseline_missing_key_unknown': {'queue': missing[0], 'components': missing[1]},
        'baseline_string_unknown': {'queue': string[0], 'components': string[1]},
        'baseline_empty_unknown': {'queue': empty[0], 'components': empty[1]},
    }
    checks = {
        'boolean_rejected': invalid[0]['queue_returned'] == 'None' and invalid[0]['components_accepted'] is False,
        'negative_rejected': invalid[1]['queue_returned'] == 'None' and invalid[1]['components_accepted'] is False,
        'nan_rejected': invalid[2]['queue_returned'] == 'None' and invalid[2]['components_accepted'] is False,
        'infinity_rejected': invalid[3]['queue_returned'] == 'None' and invalid[3]['components_accepted'] is False,
        'per_key_gating': all(q is None and p is None for q, p in per_key.values()),
        'baseline_valid_recompute': valid == (20, {'waitingTimeMillis': 12, 'blockedTimeMillis': 5, 'buildableTimeMillis': 3}),
        'baseline_zero_is_legal': zero == (0, {'waitingTimeMillis': 0, 'blockedTimeMillis': 0, 'buildableTimeMillis': 0}),
        'baseline_missing_key_unknown': missing == (None, None),
        'baseline_string_unknown': string == (None, None),
        'baseline_empty_unknown': empty == (None, None),
    }
    report = {
        "finding": "A11 · P2 · 原始排队分项接受bool、负数和非有限数",
        "requirements": ["REQ-024"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic Jenkins records; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/delivery-probes.py probes.invalid_raw_queue_components with the same inputs (waitingTimeMillis injected with True/-12/NaN/Infinity, blocked=5, buildable=3); the REQ-024 AC01/AC02 baseline neighbours keep their frozen verdicts.",
            "Pre-fix frozen evidence recorded a summed queue value and accepted components for every injected input; this probe asserts each illegal component leaves queue unknown, while a real 0 stays a legal value distinct from missing.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a11-strict-queue-components.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
