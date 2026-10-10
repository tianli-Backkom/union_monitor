#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A10 整改复验探针：来源覆盖按唯一适用身份记账。

以 audit/2026-10-10 对抗审查 A10 的同一组输入复跑反例：(1) 登记一个
适用对象后仅 record_derived——旧行为分母 1 而三项（已验证一致+差异+
缺证据）合计 0，派生桶游离于 REQ-023-AC02 恒等式之外；(2) 同一
identity 登记两次适用、仅一次 record_verified——旧行为分母被撑大到
2、missing 0 仍判 verified。修复后全部计数按唯一适用身份记账：重复
登记不重复计数、缺失清单不重复列出，派生自洽计入缺证据并保留
derived_consistent 属性；REQ-023/REQ-024 的冻结基线邻例（零覆盖、
三项恒等+差异优先、全派生未验证、完整覆盖、verified_absence 子计数）
保持原判定。

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
from source_coverage import SourceCategory, source_report  # noqa: E402


def ac02_sum(result):
    return result['verified_consistent'] + result['differences'] + result['missing_evidence']


def main():
    # 冻结反例 1：仅派生一致、无独立原始证据
    derived_cat = SourceCategory('queue_components')
    derived_cat.record_applicable('https://ci.example/job/x/1/')
    derived_cat.record_derived('https://ci.example/job/x/1/')
    derived = derived_cat.result()

    # 冻结反例 2：重复适用身份 + 单次验证
    duplicate_cat = SourceCategory('job_timing')
    duplicate_cat.record_applicable('job/1')
    duplicate_cat.record_applicable('job/1')
    duplicate_cat.record_verified('job/1')
    duplicate = duplicate_cat.result()

    # 重复身份且未验证：缺失清单不重复列出
    plain_cat = SourceCategory('job_timing')
    plain_cat.record_applicable('job/1')
    plain_cat.record_applicable('job/1')
    plain = plain_cat.result()

    # 邻例基线（冻结 REQ-023/REQ-024 基线形状）
    zero = SourceCategory('job_timing')
    for url in ['job/1/', 'job/2/']:
        zero.record_applicable(url)
    zero_result = zero.result()

    addup = SourceCategory('job_timing')
    for url in ['job/1/', 'job/2/', 'job/3/', 'job/4/', 'job/5/']:
        addup.record_applicable(url)
    for url in ['job/1/', 'job/2/', 'job/3/']:
        addup.record_verified(url)
    addup.record_difference('job/4/', 'raw waiting=9 != snapshot queue=1')
    addup_result = addup.result()

    all_derived_cat = SourceCategory('queue_components')
    for url in ['job/1/', 'job/2/']:
        all_derived_cat.record_applicable(url)
        all_derived_cat.record_derived(url)
    all_derived = source_report({'queue_components': all_derived_cat})['categories']['queue_components']

    full = SourceCategory('job_timing')
    full.record_applicable('job/1/')
    full.record_verified('job/1/')
    full_result = full.result()

    absent = SourceCategory('queue_components')
    absent.record_applicable('job/1/')
    absent.record_verified_absence('job/1/')
    absent_result = absent.result()

    probes = {
        'derived_without_independent_raw': {
            'result': derived,
            'required_ac02_sum': ac02_sum(derived),
            'denominator': derived['applicable'],
        },
        'duplicate_source_identity': {
            'result': duplicate,
            'required_ac02_sum': ac02_sum(duplicate),
            'denominator': duplicate['applicable'],
        },
        'duplicate_unverified_identity': plain,
        'baseline_zero_coverage': zero_result,
        'baseline_counts_add_up': addup_result,
        'baseline_all_derived': all_derived,
        'baseline_full_coverage': full_result,
        'baseline_verified_absence': absent_result,
    }
    checks = {
        'derived_without_independent_raw': (
            derived['applicable'] == 1
            and ac02_sum(derived) == derived['applicable']
            and (derived['missing_evidence'], derived['derived_consistent']) == (1, 1)
            and derived['status'] == 'unverified'),
        'duplicate_source_identity': (
            duplicate['applicable'] == 1
            and ac02_sum(duplicate) == duplicate['applicable']
            and (duplicate['verified_consistent'], duplicate['missing_evidence']) == (1, 0)
            and duplicate['status'] == 'verified'),
        'duplicate_unverified_identity': (
            (plain['applicable'], plain['missing_evidence']) == (1, 1)
            and plain['missing'] == ['job/1']),
        'baseline_zero_coverage_unverified': (
            (zero_result['applicable'], zero_result['verified_consistent'],
             zero_result['differences'], zero_result['missing_evidence']) == (2, 0, 0, 2)
            and zero_result['status'] == 'unverified'),
        'baseline_counts_add_up': (
            ac02_sum(addup_result) == addup_result['applicable'] == 5
            and addup_result['status'] == 'differences_found'
            and addup_result['missing'] == ['job/5/']),
        'baseline_all_derived_unverified': (
            all_derived['status'] == 'unverified'
            and (all_derived['derived_consistent'], all_derived['missing_evidence']) == (2, 2)),
        'baseline_full_coverage_verified': (
            full_result['status'] == 'verified' and full_result['missing'] == []),
        'baseline_verified_absence_subcount': (
            absent_result['status'] == 'verified'
            and (absent_result['verified_consistent'], absent_result['verified_absent']) == (1, 1)),
    }
    report = {
        "finding": "A10 · P2 · 来源覆盖分母不满足要求，重复身份可误判verified",
        "requirements": ["REQ-023", "REQ-024"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All inputs are process-memory synthetic registrations; no network request, production source, test, frozen audit evidence, or real snapshot was modified.",
            "Mirrors audit/2026-10-10/scripts/delivery-probes.py probes.derived_without_independent_raw and probes.duplicate_source_identity with the same inputs; the REQ-023/REQ-024 baseline neighbours keep their frozen verdicts.",
            "Pre-fix frozen evidence recorded the derived case as denominator 1 with the AC02 three-term sum 0, and the duplicate case as denominator 2 with verified 1 / missing 0 while still status=verified; this probe asserts unique-identity accounting where derived-consistent counts as missing evidence with derived_consistent kept as an attribute.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a10-unique-identity-accounting.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
