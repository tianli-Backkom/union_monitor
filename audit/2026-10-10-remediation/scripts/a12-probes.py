#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A12 整改复验探针：缺原始文件按未验证分类，不与审计失败混淆。

以 audit/2026-10-10 对抗审查 A12 的同一组输入复跑反例：
failure_report(FileNotFoundError("raw artifact unavailable"))——旧行为
overall_status=failed，缺证据与真实审计异常共用同一分类。修复后按
REQ-025-AC02 语义分类：缺文件（FileNotFoundError）或缺权限
（PermissionError）是已知缺证据情形，报告为 unverified；真实崩溃
（RuntimeError/AssertionError）保持 failed。两种分类都保留 error 与
受影响范围，checks_passed 恒为 False——未知不能变成通过；两个消费方
（validate.py、validate_multi.py）写报告后原样重抛，非通过退出与
发布保护不变。

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
from source_coverage import failure_report  # noqa: E402


def main():
    # 冻结反例：缺原始工件
    missing = failure_report(FileNotFoundError('raw artifact unavailable'))
    # 邻例：缺权限（REQ-025-AC02「仅缺权限或文件标未验证」）
    denied = failure_report(PermissionError('raw artifact unreadable'))
    # 邻例：真实崩溃保持 failed（REQ-025-AC03 保留错误与受影响范围）
    runtime = failure_report(RuntimeError('unexpected collector state'))
    assertion = failure_report(AssertionError('derived identity mismatch'))

    probes = {
        'missing_file_failure_classification': missing,
        'permission_denied_classification': denied,
        'runtime_crash_classification': runtime,
        'assertion_crash_classification': assertion,
    }
    checks = {
        'missing_file_unverified': bool(
            missing['overall_status'] == 'unverified'
            and missing['checks_passed'] is False
            and 'FileNotFoundError' in missing['error']
            and 'raw artifact unavailable' in missing['error']
            and missing['affected_scope']),
        'permission_denied_unverified': bool(
            denied['overall_status'] == 'unverified'
            and denied['checks_passed'] is False
            and denied['affected_scope']),
        'runtime_crash_stays_failed': bool(
            runtime['overall_status'] == 'failed'
            and runtime['checks_passed'] is False
            and 'RuntimeError' in runtime['error']
            and runtime['affected_scope']),
        'assertion_crash_stays_failed': bool(
            assertion['overall_status'] == 'failed'
            and assertion['checks_passed'] is False
            and assertion['affected_scope']),
        'unknown_never_becomes_pass': not any(
            r['checks_passed'] for r in (missing, denied, runtime, assertion)),
    }
    report = {
        "finding": "A12 · P2 · 缺原始文件被统一记为failed而非unverified",
        "requirements": ["REQ-025"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic exceptions; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/delivery-probes.py probes.missing_file_failure_classification with the same input (FileNotFoundError('raw artifact unavailable')); PermissionError and the two crash neighbours cover the REQ-025 AC02/AC03 classification edges.",
            "Pre-fix frozen evidence recorded overall_status=failed for the missing file; this probe asserts missing file/permission read as unverified while real crashes stay failed, and checks_passed stays False in every classification so unknown never becomes a pass.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a12-missing-evidence-classification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
