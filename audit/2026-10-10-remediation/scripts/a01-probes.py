#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A01 整改复验探针：验收台账证据链推导。

以 audit/2026-10-10 对抗审查 A01 的同一组输入复跑四个反例，验证修复后
台账不再由提交名称推断全部通过：

1. erase_all_evidence_details（空壳证据）：证据文件仅剩顶层状态时，
   受影响需求必须转为未验证且工具报告问题；
2. remove_selected_test_files（隐藏关联测试）：交付提交触及的测试缺失时，
   对应需求必须转为未验证且工具报告问题；
3. omit_req051_commit（移除交付提交映射）：交付需求无提交时必须如实
   记「本提交待落地」未验证，不得自动通过；
4. truthful_unverified（如实未验证）：REQ-038/039 如实标未验证必须被
   REQ-051 总体校验接受；放宽 REQ-038 为通过必须被拒绝。

全部篡改仅在进程内存中生效，不修改任何业务源码、测试或冻结证据。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import verify_acceptance as va  # noqa: E402
import verify_requirements_doc as vd  # noqa: E402

HIDDEN_TESTS = [
    "test_acceptance.py",
    "test_artifact_verification.py",
    "test_concurrency_evidence.py",
    "test_runtime_evidence.py",
    "test_requirements_doc.py",
]


def build_acceptance():
    audit = str(ROOT / "audit" / "2026-10-09")
    root = str(ROOT)
    problems = []
    text = va._read_text(os.path.join(audit, "requirements.md"))
    model = va._load_json(os.path.join(audit, "evidence", "requirements-model.json"))
    verification = va._load_json(os.path.join(audit, "evidence", "requirements-verification.json"))
    checks = va._load_json(os.path.join(audit, "evidence", "all-checks.json"))
    findings = va._load_json(os.path.join(audit, "evidence", "findings.json"))
    reqs, doc = va.check_doc(text, model, verification, problems)
    _, findings_section = va.check_findings_mapping(text, findings, checks, model, problems)
    conclusions = va.check_conclusions(text, problems)
    integrity = va.check_integrity(root, audit, text, checks, findings, problems)
    commits, dup, error = va.collect_commits(root)
    if error:
        problems.append(error)
    ledger, acs, meta = va.build_ledger(reqs, commits, dup, "REQ-051", problems)
    kinds = va.check_kinds_and_synthesis(root, text, ledger, problems)
    return va.build_report(
        argparse.Namespace(root=root, delivering="REQ-051"),
        audit,
        {
            "doc": doc,
            "findings": findings_section,
            "conclusions": conclusions,
            "integrity": integrity,
            "ledger": ledger,
            "acs": acs,
            "kinds": kinds,
            "ledger_meta": meta,
        },
        problems,
    )


def summary(report):
    return {
        "overall": report["overall"]["status"],
        "req_statuses": dict(Counter(x["status"] for x in report["ledger"])),
        "ac_statuses": dict(Counter(x["status"] for x in report["acceptance_criteria"])),
        "unverified_reqs": [x["req"] for x in report["ledger"] if x["status"] == "未验证"],
    }


def main():
    load_json = va._load_json
    baseline = build_acceptance()

    evidence_by_file = {name: (keys, want) for name, keys, want in va.EVIDENCE_FILES.values()}

    def hollow_evidence(path):
        info = evidence_by_file.get(Path(path).name)
        if info:
            keys, want = info
            data = {}
            cur = data
            for key in keys[:-1]:
                cur[key] = {}
                cur = cur[key]
            cur[keys[-1]] = want
            return data
        return load_json(path)

    with patch.object(va, "_load_json", hollow_evidence):
        hollow = build_acceptance()

    listdir = os.listdir

    def hide_tests(path):
        names = listdir(path)
        if Path(path).resolve() == (ROOT / "tests").resolve():
            return [x for x in names if x not in HIDDEN_TESTS]
        return names

    with patch.object(os, "listdir", hide_tests):
        hidden = build_acceptance()

    collect = va.collect_commits

    def omit_req051(root):
        commits, dup, error = collect(root)
        commits = dict(commits)
        commits.pop(51, None)
        return commits, dup, error

    with patch.object(va, "collect_commits", omit_req051):
        without_commit = build_acceptance()

    def truthful(path):
        data = load_json(path)
        if Path(path).name == "acceptance-evidence.json":
            data = deepcopy(data)
            for entry in data["ledger"]:
                if entry["req"] in ("REQ-038", "REQ-039"):
                    entry["status"] = "未验证"
            for entry in data["acceptance_criteria"]:
                if entry["req"] in ("REQ-038", "REQ-039"):
                    entry["status"] = "未验证"
        return data

    truth_problems = []
    with patch.object(va, "_load_json", truthful):
        vd.check_overall(str(ROOT), str(ROOT / "audit" / "2026-10-09"), truth_problems)

    def relaxed(path):
        data = truthful(path)
        if Path(path).name == "acceptance-evidence.json":
            data = deepcopy(data)
            for entry in data["ledger"]:
                if entry["req"] == "REQ-038":
                    entry["status"] = "通过"
                    entry["unverified_reason"] = None
        return data

    relax_problems = []
    with patch.object(va, "_load_json", relaxed):
        vd.check_overall(str(ROOT), str(ROOT / "audit" / "2026-10-09"), relax_problems)

    req51 = next(x for x in without_commit["ledger"] if x["req"] == "REQ-051")
    hollow_unverified = {x["req"] for x in hollow["ledger"] if x["status"] == "未验证"}
    hidden_unverified = {x["req"] for x in hidden["ledger"] if x["status"] == "未验证"}
    probes = {
        "baseline": summary(baseline),
        "erase_all_evidence_details_keep_expected_status_only": {
            **summary(hollow),
            "expected_not_verified": sorted(hollow_unverified),
        },
        "remove_selected_test_files_from_inventory_in_memory": {
            **summary(hidden),
            "hidden_files": HIDDEN_TESTS,
            "expected_not_verified": sorted(hidden_unverified),
        },
        "omit_req051_commit_in_memory": {
            **summary(without_commit),
            "req051_status": req51["status"],
            "req051_pending_commit": req51["pending_commit"],
            "req051_reason": req51["unverified_reason"],
        },
        "truthful_unverified_req038_req039_accepted_by_req051": {
            "problems": truth_problems,
            "accepted": not truth_problems,
        },
        "relaxed_req038_rejected_by_req051": {
            "problems": relax_problems,
            "rejected": bool(relax_problems),
        },
    }
    checks = {
        "baseline_honest": baseline["overall"]["status"] == "verified"
        and probes["baseline"]["req_statuses"] == {"通过": 49, "未验证": 2}
        and probes["baseline"]["unverified_reqs"] == ["REQ-038", "REQ-039"],
        "hollow_evidence_not_verified": hollow["overall"]["status"] == "failed"
        and {"REQ-038", "REQ-039", "REQ-040", "REQ-041", "REQ-042", "REQ-043",
             "REQ-044", "REQ-045", "REQ-047", "REQ-048", "REQ-049"} <= hollow_unverified,
        "hidden_tests_not_verified": hidden["overall"]["status"] == "failed"
        and {"REQ-038", "REQ-039", "REQ-040", "REQ-050", "REQ-051"} <= hidden_unverified,
        "omitted_commit_pending_not_passed": req51["status"] == "未验证"
        and req51["pending_commit"] is True,
        "truthful_unverified_accepted": not truth_problems,
        "relaxed_unverified_rejected": bool(relax_problems),
    }
    report = {
        "finding": "A01 · P1 · 验收台账由提交名称推断全部AC通过",
        "requirements": ["REQ-050", "REQ-051"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": probes,
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All tampering is process-memory-only (unittest.mock.patch).",
            "No production source, test, frozen audit evidence, or snapshot was modified.",
            "Inputs mirror audit/2026-10-10/scripts/delivery-probes.py probes 1-3 plus the truthful/relaxed REQ-051 overall checks.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a01-acceptance-chain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
