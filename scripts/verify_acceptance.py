#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REQ-050 · 需求验收记录与证据闭环 — 验收台账与证据闭环校验工具。

对 audit/2026-10-09/requirements.md 及其证据目录做结构化核验：
1. 解析 51 条需求（优先级/类型/验收标准），与冻结需求模型、审计期验收记录交叉核对；
2. 校验 F01–F19 与 5.1 追踪表、findings.json、模型 source_findings 三方一致，映射并集恰为
   REQ-001..REQ-037（37 条整改，19 组问题拆分不被误计成新增审查问题）；
3. 校验 5.2 通过/未验证结论映射完整，D10/P04 等未验证原因保留；
4. 校验 7 个来源文件 SHA-256 与第 7 节冻结表一致，238 项检查及其 29 项失败、
   2 项未验证记录不删除不改写，requirements.md 与审计基线提交一致；
5. 生成 51 条需求 + 195 条 AC 的验收台账：状态由证据链逐项推导（fail-closed），
   不由提交名称推断——每条已交付需求必须有交付提交、其提交触及的关联测试仍在
   tests/、证据文件（REQ-038..049）含实质核验内容而非仅顶层状态的空壳；
   证据状态非 verified（如 REQ-038 unverified、REQ-039 aligned）时如实保留未验证；
   本次交付（--delivering）需求在提交落地前如实记「本提交待落地」未验证；
6. 文档结构核验与业务交付完成度分别输出（delivery 段），未验证是如实状态而非
   核验失败；核验不以检查项通过比例声明来源准确率。

用法：
    python3 -X utf8 scripts/verify_acceptance.py [--root DIR] [--delivering REQ-050] [--output PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

BJT = timezone(timedelta(hours=8))

EXPECTED = {
    "requirements": 51,
    "acceptance_criteria": 195,
    "findings": 19,
    "type_counts": {"整改": 37, "补证": 3, "保持": 9, "交付": 2},
    "checks_total": 238,
    "checks_counts": {"passed": 207, "failed": 29, "unverified": 2},
    "unverified_ids": ["D10", "P04"],
    "unverified_conclusion_rows": 6,
}

# 补证/保持类需求 → (证据文件, 状态键路径, 冻结期望状态)
EVIDENCE_FILES = {
    38: ("artifact-verification.json", ("overall_status",), "unverified"),
    39: ("concurrency-evidence.json", ("overall", "status"), "aligned"),
    40: ("runtime-evidence.json", ("overall", "status"), "verified"),
    41: ("ubs-semantics-evidence.json", ("overall", "status"), "verified"),
    42: ("ubs-filtering-evidence.json", ("overall", "status"), "verified"),
    43: ("ubs-sorting-evidence.json", ("overall", "status"), "verified"),
    44: ("ubs-csv-evidence.json", ("overall", "status"), "verified"),
    45: ("ubs-detail-evidence.json", ("overall", "status"), "verified"),
    47: ("ubs-routes-evidence.json", ("overall", "status"), "verified"),
    48: ("interaction-evidence.json", ("overall", "status"), "verified"),
    49: ("freshness-evidence.json", ("overall", "status"), "verified"),
}
FIXTURE_46 = "tests/fixtures/triton-audit-freeze.json"

# 证据文件必须包含的实质核验内容键（缺失即空壳证据：仅剩顶层状态不构成验收证据）
EVIDENCE_DEPTH = {
    38: ("ac01_inventory", "ac02_comparisons", "ac03_rerun_impact", "ac04_deployment"),
    39: ("ac01_controlled_sequence", "ac03_run_history", "ac04_queue_max"),
    40: ("runs", "runtimes", "raw_audit_summary"),
    41: ("counts", "representative_recheck", "cross_repo", "frontend_cross_check"),
    42: ("combos", "trigger_dedup", "representative_invariance", "orphan_tracking"),
    43: ("pr_sorting", "repo_sorting", "pagination_model", "source_contracts"),
    44: ("repo_csv", "pr_csv", "batch_csv", "quality_csv", "csv_encoding"),
    45: ("detail_groups", "failed_wait", "drill_targets", "minute_exact"),
    47: ("router_matrix", "legacy_aliases", "views", "source_contracts"),
    48: ("time_rules", "views", "source_contracts"),
    49: ("freshness_slots", "source_contracts"),
}

SOURCE_FILES = [
    "review-report.md",
    "coverage-matrix.md",
    "evidence/findings.json",
    "evidence/all-checks.json",
    "evidence/data-audit.json",
    "evidence/deployment-audit.json",
    "evidence/baseline-comparison.md",
]

# 输入标注：特例需求优先，其余按类型组
INPUT_KINDS = {
    "整改": ["真实快照", "合成输入"],
    "保持": ["真实快照", "静态规则"],
    "交付": ["静态规则"],
    38: ["真实快照", "静态规则"],
    39: ["合成输入", "静态规则"],
    40: ["真实快照", "静态规则"],
    50: ["真实快照", "静态规则"],
}
INPUT_TEXT = {
    "整改": "整改后业务源码与测试套件（按交付规则以冻结审计快照与合成输入验证正常与边界路径；见该 REQ 提交）",
    "保持": "真实 web/data 快照与生产源码契约（独立镜像矩阵与基线回放）",
    "交付": "冻结需求文档与来源文件（文档结构、链接与 SHA-256 核验）",
    38: "冻结数据、审计导出、本地快照与构建清单交叉核对（可执行核对全部一致；D10 原始工件缺失如实标注未验证）",
    39: "文档化平台语义与受控并发序列（隔离合成验证；真实 pending 取消影响保留未验证）",
    40: "CI 工作流声明与目标运行时（Python 3.12/Node 22）本地实测记录（正式 CI 运行与真实部署记录未取得，真实部署类证据保留未验证）",
    50: "冻结审计记录（requirements.md、需求模型、验收记录、238 项检查、git 历史）结构化核验",
    "pending": "待交付",
}
ALL_KINDS = ["真实快照", "合成输入", "静态规则", "真实部署"]

RE_REQ_HEADER = re.compile(r"^### REQ-(\d{3}) · (.+)$")
RE_PRIORITY = re.compile(r"^\*\*优先级：\*\* P(\d)　\*\*类型：\*\* (整改|补证|保持|交付)$")
RE_AC = re.compile(r"^- \*\*REQ-(\d{3})-AC(\d{2})：\*\*")
RE_F_ROW = re.compile(r"^\|F(\d{2}) · [^|]+\|([^|]+)\|$")
RE_C_ROW = re.compile(r"^\| ([^|]+?) \| ([^|]+?) \|$")
RE_SHA_ROW = re.compile(r"^\|([^|]+)\|`([0-9a-f]{64})`\|$")
RE_GEN_TIME = re.compile(r"^文档生成时间：(\S+)（Asia/Shanghai）")
RE_REQ_REF = re.compile(r"REQ-(\d{3})(?:–REQ-(\d{3}))?")
RE_COMMIT = re.compile(r"^([0-9a-f]{40})\tREQ-(\d{3})：(.*)$")
RE_RATE_CLAIM = re.compile(
    r"(准确率|通过率)[^\n]{0,40}\d+(?:\.\d+)?%|\d+(?:\.\d+)?%[^\n]{0,20}(准确率|通过率)"
)


def _read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _git(root, *args):
    proc = subprocess.run(["git", "-C", root, *args], capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def expand_req_refs(cell):
    """把 'REQ-001、REQ-002' / 'REQ-042–REQ-045、REQ-047' 展开为编号列表。"""
    refs = []
    for m in RE_REQ_REF.finditer(cell):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        refs.extend(range(a, b + 1))
    return refs


def parse_requirements_doc(text):
    """解析需求文档 → {num: {title, priority, type, acs}}；返回 (reqs, problems)。"""
    reqs = {}
    problems = []
    current = None
    for line in text.splitlines():
        m = RE_REQ_HEADER.match(line)
        if m:
            num = int(m.group(1))
            reqs[num] = {"title": m.group(2).strip(), "priority": None, "type": None, "acs": []}
            current = num
            continue
        if current is None:
            continue
        m = RE_PRIORITY.match(line)
        if m:
            reqs[current]["priority"] = int(m.group(1))
            reqs[current]["type"] = m.group(2)
            continue
        m = RE_AC.match(line)
        if m:
            ac_req, ac_num = int(m.group(1)), int(m.group(2))
            if ac_req != current:
                problems.append(
                    f"AC 前缀与所属 REQ 不符：REQ-{ac_req:03d}-AC{ac_num:02d} 出现在 REQ-{current:03d} 块内"
                )
                continue
            reqs[current]["acs"].append(ac_num)
    return reqs, problems


def _section(text, start_marker, end_markers):
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if line.startswith(start_marker):
            start = i
            break
    if start is None:
        return []
    for j in range(start + 1, len(lines)):
        if any(lines[j].startswith(m) for m in end_markers):
            end = j
            break
    if end is None:
        end = len(lines)
    return lines[start:end]


def parse_findings_table(text):
    """5.1 原19组问题完整覆盖 → {F编号(int): [REQ nums]}。"""
    mapping = {}
    for line in _section(text, "### 5.1", ("### 5.2", "## 6")):
        m = RE_F_ROW.match(line)
        if m:
            mapping[int(m.group(1))] = expand_req_refs(m.group(2))
    return mapping


def parse_conclusions_table(text):
    """5.2 通过与未验证结论 → [(label, [REQ nums])]（仅保留含 REQ 引用的行）。"""
    rows = []
    for line in _section(text, "### 5.2", ("## 6",)):
        m = RE_C_ROW.match(line)
        if m:
            refs = expand_req_refs(m.group(2))
            if refs:
                rows.append((m.group(1).strip(), refs))
    return rows


def parse_sha_table(text):
    """第 7 节来源 SHA-256 表 → {path: sha}。"""
    table = {}
    for line in _section(text, "## 7", ()):
        m = RE_SHA_ROW.match(line)
        if m:
            table[m.group(1).strip()] = m.group(2)
    return table


def parse_generation_time(text):
    for line in text.splitlines():
        m = RE_GEN_TIME.match(line)
        if m:
            return m.group(1)
    return None


def conclusion_status(label):
    """5.2 结论行状态：含“未验证”或 D10 开头（缺证据）保留未验证，其余记通过。"""
    if "未验证" in label or label.startswith("D10"):
        return "未验证"
    return "通过"


def collect_commits(root):
    """git log → ({req_num: {hash, short, subject}}, 重复提交计数, 错误)。"""
    rc, out, err = _git(root, "log", "--format=%H%x09%s")
    if rc != 0:
        return {}, {}, f"git log 失败：{err.strip()}"
    commits = {}
    counts = {}
    for line in out.splitlines():
        m = RE_COMMIT.match(line)
        if not m:
            continue
        h, n, s = m.group(1), int(m.group(2)), m.group(3)
        counts[n] = counts.get(n, 0) + 1
        if n not in commits:  # 最新一次提交为准
            commits[n] = {"hash": h, "short": h[:7], "subject": s}
    return commits, {k: v for k, v in counts.items() if v > 1}, None


def collect_commit_tests(root):
    """git log --name-only → {req_num: 该 REQ 全部提交触及的 tests/ 文件并集}。

    关联测试是交付证据链的一环：REQ 提交引入的测试文件必须仍存在于 tests/。
    """
    rc, out, err = _git(root, "log", "--name-only", "--format=%H%x09%s")
    if rc != 0:
        return None, f"git log --name-only 失败：{err.strip()}"
    mapping = {}
    current = None
    for line in out.splitlines():
        if not line:
            continue
        if "\t" in line:
            m = RE_COMMIT.match(line)
            current = int(m.group(2)) if m else None
            continue
        if (
            current is not None
            and line.startswith("tests/")
            and (line.endswith(".py") or line.endswith(".cjs"))
        ):
            mapping.setdefault(current, set()).add(line)
    return mapping, None


def check_doc(doc_text, model, verification, problems):
    """解析需求文档并与冻结模型、审计期验收记录交叉核对。"""
    reqs, parse_problems = parse_requirements_doc(doc_text)
    problems.extend(parse_problems)
    section = {
        "requirements": len(reqs),
        "acceptance_criteria": sum(len(r["acs"]) for r in reqs.values()),
        "type_counts": {},
    }
    if len(reqs) != EXPECTED["requirements"]:
        problems.append(f"需求数量 {len(reqs)} ≠ {EXPECTED['requirements']}")
    if sorted(reqs) != list(range(1, EXPECTED["requirements"] + 1)):
        problems.append("REQ 编号不是 001..051 连续唯一")
    for num, r in sorted(reqs.items()):
        if r["priority"] is None or r["type"] is None:
            problems.append(f"REQ-{num:03d} 缺少优先级/类型行")
        if r["acs"] != list(range(1, len(r["acs"]) + 1)):
            problems.append(f"REQ-{num:03d} 的 AC 编号不连续或重复")
    type_counts = {}
    for r in reqs.values():
        if r["type"]:
            type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
    section["type_counts"] = type_counts
    if type_counts != EXPECTED["type_counts"]:
        problems.append(f"类型计数 {type_counts} ≠ {EXPECTED['type_counts']}")
    if section["acceptance_criteria"] != EXPECTED["acceptance_criteria"]:
        problems.append(f"验收标准总数 {section['acceptance_criteria']} ≠ {EXPECTED['acceptance_criteria']}")
    # 与冻结需求模型交叉核对
    model_reqs = model.get("requirements", [])
    model_by_num = {int(e["id"].split("-")[1]): e for e in model_reqs}
    section["model_version"] = model.get("version")
    section["model_requirements"] = len(model_reqs)
    if len(model_reqs) != EXPECTED["requirements"]:
        problems.append(f"需求模型条目 {len(model_reqs)} ≠ {EXPECTED['requirements']}")
    for num, r in sorted(reqs.items()):
        e = model_by_num.get(num)
        if e is None:
            problems.append(f"需求模型缺少 REQ-{num:03d}")
            continue
        if e.get("kind") != r["type"]:
            problems.append(f"REQ-{num:03d} 类型 {r['type']} 与模型 {e.get('kind')} 不一致")
        if str(e.get("priority", "")) != f"P{r['priority']}":
            problems.append(f"REQ-{num:03d} 优先级 P{r['priority']} 与模型 {e.get('priority')} 不一致")
        if re.sub(r"\s+", "", e.get("title", "")) != re.sub(r"\s+", "", r["title"]):
            problems.append(f"REQ-{num:03d} 标题与模型不一致")
    gen_time = parse_generation_time(doc_text)
    section["doc_generation_time"] = gen_time
    if gen_time != model.get("created_at"):
        problems.append(f"文档生成时间 {gen_time} 与模型 created_at {model.get('created_at')} 不一致")
    # 与审计期验收记录（冻结）交叉核对
    section["frozen_record"] = {
        "requirements": verification.get("requirements"),
        "acceptance_criteria": verification.get("acceptance_criteria"),
        "findings_covered": verification.get("findings_covered"),
        "type_counts": verification.get("type_counts"),
        "dependencies_acyclic": verification.get("dependencies_acyclic"),
        "audit_sources_unchanged": verification.get("audit_sources_unchanged"),
        "status": verification.get("status"),
        "warnings": verification.get("warnings", []),
        "errors": verification.get("errors", []),
        "note": "审计期文档生成校验的冻结记录（D:/ 链接与业务源码变化为其历史事实），保持原样不修改",
    }
    for key, want in (
        ("requirements", EXPECTED["requirements"]),
        ("acceptance_criteria", EXPECTED["acceptance_criteria"]),
        ("findings_covered", EXPECTED["findings"]),
    ):
        if verification.get(key) != want:
            problems.append(f"冻结验收记录 {key}={verification.get(key)} ≠ {want}")
    if verification.get("type_counts") != EXPECTED["type_counts"]:
        problems.append("冻结验收记录 type_counts 与期望不一致")
    if verification.get("dependencies_acyclic") is not True:
        problems.append("冻结验收记录 dependencies_acyclic 不是 True")
    if verification.get("audit_sources_unchanged") is not True:
        problems.append("冻结验收记录 audit_sources_unchanged 不是 True")
    return reqs, section


def check_findings_mapping(doc_text, findings, all_checks, model, problems):
    """F01–F19 与 5.1 追踪表、findings.json、模型 source_findings 三方一致。"""
    table = parse_findings_table(doc_text)
    check_ids = {c["id"] for c in all_checks["checks"]}
    fids = [f["id"] for f in findings]
    section = {
        "table_rows": len(table),
        "findings_json": len(findings),
        "check_ids_missing": [],
        "union_reqs": None,
        "model_inverted_match": False,
    }
    if len(table) != EXPECTED["findings"]:
        problems.append(f"5.1 追踪表行数 {len(table)} ≠ {EXPECTED['findings']}")
    if sorted(table) != list(range(1, EXPECTED["findings"] + 1)):
        problems.append("5.1 追踪表 F 编号不是 F01..F19 连续唯一")
    if sorted(fids) != [f"F{n:02d}" for n in range(1, EXPECTED["findings"] + 1)]:
        problems.append("findings.json 的 F 编号不是 F01..F19")
    if sorted(table) != sorted(int(f["id"][1:]) for f in findings):
        problems.append("5.1 追踪表与 findings.json 的 F 集合不一致")
    union = set()
    for fid, refs in sorted(table.items()):
        union.update(refs)
        for n in refs:
            if not (1 <= n <= 37):
                problems.append(f"F{fid:02d} 映射到非整改需求 REQ-{n:03d}")
    if union:
        section["union_reqs"] = f"REQ-{min(union):03d}..REQ-{max(union):03d}"
    if union != set(range(1, 38)):
        problems.append("5.1 追踪表映射并集 ≠ REQ-001..REQ-037（存在源问题遗漏或越界）")
    for f in findings:
        for cid in [c.strip() for c in f.get("check_ids", "").split(",") if c.strip()]:
            if cid not in check_ids:
                section["check_ids_missing"].append(f"{f['id']}:{cid}")
    if section["check_ids_missing"]:
        problems.append(f"检查 ID 在 238 项检查宇宙中缺失：{section['check_ids_missing'][:5]}")
    inverted = {}
    for e in model.get("requirements", []):
        for fid in e.get("source_findings", []):
            inverted.setdefault(int(fid[1:]), []).append(int(e["id"].split("-")[1]))
    mismatch = []
    for fid in sorted(set(inverted) | set(table)):
        if sorted(inverted.get(fid, [])) != sorted(table.get(fid, [])):
            mismatch.append(f"F{fid:02d}")
    if mismatch:
        problems.append(f"模型 source_findings 与 5.1 追踪表不一致：{mismatch}")
    section["model_inverted_match"] = not mismatch
    return table, section


def check_conclusions(doc_text, problems):
    """5.2 通过/未验证结论映射完整，未验证原因保留。"""
    rows = parse_conclusions_table(doc_text)
    section = {"rows": len(rows), "unverified": [], "passed": [], "d10_present": False, "p04_present": False}
    if len(rows) < 11:
        problems.append(f"5.2 结论表行数 {len(rows)} < 11")
    for label, refs in rows:
        status = conclusion_status(label)
        entry = {"label": label, "reqs": [f"REQ-{n:03d}" for n in refs], "status": status}
        if status == "未验证":
            section["unverified"].append(entry)
        else:
            section["passed"].append(entry)
        if not refs:
            problems.append(f"5.2 结论行未映射任何需求：{label}")
        for n in refs:
            if not (1 <= n <= 51):
                problems.append(f"5.2 结论行映射越界 REQ-{n:03d}：{label}")
        if label.startswith("D10"):
            section["d10_present"] = True
        if label.startswith("P04"):
            section["p04_present"] = True
    if not section["d10_present"]:
        problems.append("5.2 缺少 D10 未验证结论行")
    if not section["p04_present"]:
        problems.append("5.2 缺少 P04 未验证结论行")
    if len(section["unverified"]) != EXPECTED["unverified_conclusion_rows"]:
        problems.append(
            f"5.2 未验证结论行数 {len(section['unverified'])} ≠ {EXPECTED['unverified_conclusion_rows']}（未验证原因须保留）"
        )
    return section


def check_integrity(root, audit_dir, doc_text, all_checks, findings, problems):
    """来源 SHA-256、238 项检查不删除、证据文件状态、fixture 与测试套件存在。"""
    section = {
        "source_sha256": {},
        "all_checks": {},
        "findings": len(findings),
        "requirements_md_unchanged": False,
        "evidence_files": {},
        "fixture_46": None,
        "tests_inventory": {},
    }
    table = parse_sha_table(doc_text)
    if len(table) != len(SOURCE_FILES):
        problems.append(f"第 7 节来源 SHA 表行数 {len(table)} ≠ {len(SOURCE_FILES)}")
    for rel, want in sorted(table.items()):
        path = os.path.join(audit_dir, rel)
        if not os.path.isfile(path):
            section["source_sha256"][rel] = {"expected": want, "actual": None, "match": False}
            problems.append(f"来源文件缺失：{rel}")
            continue
        actual = _sha256_file(path)
        ok = actual == want
        section["source_sha256"][rel] = {"expected": want, "actual": actual, "match": ok}
        if not ok:
            problems.append(f"来源文件 SHA-256 不匹配：{rel}")
    checks = all_checks.get("checks", [])
    counts = all_checks.get("counts", {})
    failed = [c["id"] for c in checks if c["state"] == "failed"]
    unverified = sorted(c["id"] for c in checks if c["state"] == "unverified")
    section["all_checks"] = {
        "total": len(checks),
        "counts": counts,
        "failed_preserved": len(failed),
        "unverified_ids": unverified,
    }
    if len(checks) != EXPECTED["checks_total"]:
        problems.append(f"all-checks 条目 {len(checks)} ≠ {EXPECTED['checks_total']}")
    if counts != EXPECTED["checks_counts"]:
        problems.append(f"all-checks counts {counts} ≠ {EXPECTED['checks_counts']}")
    if sum(counts.values()) != len(checks):
        problems.append("all-checks counts 总和与条目数不一致")
    if len(failed) != EXPECTED["checks_counts"]["failed"]:
        problems.append(
            f"失败检查保留数 {len(failed)} ≠ {EXPECTED['checks_counts']['failed']}（记录不得删除或改写为通过）"
        )
    if unverified != EXPECTED["unverified_ids"]:
        problems.append(f"未验证检查 {unverified} ≠ {EXPECTED['unverified_ids']}")
    if len(findings) != EXPECTED["findings"]:
        problems.append(f"findings.json 条目 {len(findings)} ≠ {EXPECTED['findings']}")
    rel_md = os.path.relpath(os.path.join(audit_dir, "requirements.md"), root).replace(os.sep, "/")
    rc, out, _ = _git(root, "log", "--format=%H", "--", rel_md)
    hashes = [h for h in out.splitlines() if h]
    if rc != 0 or len(hashes) != 1:
        problems.append(f"requirements.md 的 git 历史不是单一基线提交（{len(hashes)} 条）")
    else:
        # 用 git 自身比对（含行尾归一化语义）；diff --quiet 退出 0 即与基线提交一致
        rc2, _, _ = _git(root, "diff", "--quiet", hashes[0], "--", rel_md)
        same = rc2 == 0
        section["requirements_md_unchanged"] = same
        if not same:
            problems.append("requirements.md 与审计基线提交内容不一致")
    for num, (fname, keys, want) in sorted(EVIDENCE_FILES.items()):
        path = os.path.join(audit_dir, "evidence", fname)
        entry = {"file": fname, "expected": want, "actual": None, "match": False}
        if not os.path.isfile(path):
            problems.append(f"REQ-{num:03d} 证据文件缺失：evidence/{fname}")
            section["evidence_files"][f"REQ-{num:03d}"] = entry
            continue
        data = _load_json(path)
        cur = data
        missing = False
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                missing = True
                break
            cur = cur[k]
        entry["actual"] = None if missing else cur
        entry["match"] = (not missing) and cur == want
        if not entry["match"]:
            problems.append(
                f"REQ-{num:03d} 证据文件状态 {entry['actual']!r} ≠ 冻结期望 {want!r}：evidence/{fname}"
            )
        section["evidence_files"][f"REQ-{num:03d}"] = entry
    fixture_path = os.path.join(root, FIXTURE_46)
    if os.path.isfile(fixture_path) and os.path.getsize(fixture_path) > 10000:
        section["fixture_46"] = {"file": FIXTURE_46, "bytes": os.path.getsize(fixture_path), "ok": True}
    else:
        section["fixture_46"] = {"file": FIXTURE_46, "ok": False}
        problems.append(f"REQ-046 冻结审计 fixture 缺失或过小：{FIXTURE_46}")
    tests_dir = os.path.join(root, "tests")
    py = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")] if os.path.isdir(tests_dir) else []
    cjs = [f for f in os.listdir(tests_dir) if f.endswith(".test.cjs")] if os.path.isdir(tests_dir) else []
    section["tests_inventory"] = {"python_test_files": len(py), "node_test_files": len(cjs)}
    if not py or not cjs:
        problems.append("tests/ 目录缺少 python 或 node 测试文件")
    return section


def _evidence_file_state(root, num):
    """读取证据文件 → (state, detail)：ok / truthful_unverified / invalid。"""
    fname, keys, _want = EVIDENCE_FILES[num]
    rel = f"evidence/{fname}"
    path = os.path.join(root, "audit", "2026-10-09", rel)
    if not os.path.isfile(path):
        return "invalid", f"证据文件缺失：{rel}"
    try:
        data = _load_json(path)
    except (OSError, ValueError) as exc:
        return "invalid", f"证据文件不可读（{exc}）：{rel}"
    if not isinstance(data, dict):
        return "invalid", f"证据文件不是 JSON 对象：{rel}"
    missing_depth = [k for k in EVIDENCE_DEPTH.get(num, ()) if k not in data]
    if missing_depth:
        return (
            "invalid",
            f"证据文件缺少实质核验内容（空壳证据，仅剩顶层状态不构成验收证据）：{rel} 缺 {missing_depth}",
        )
    cur = data
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return "invalid", f"证据文件缺少状态键 {'.'.join(keys)}：{rel}"
        cur = cur[k]
    if cur == "verified":
        return "ok", None
    return (
        "truthful_unverified",
        f"证据文件状态为 {cur!r}（原始/真实运行证据缺失，如实保留未验证，不放宽为通过）：{rel}",
    )


def build_ledger(reqs, commits, dup, delivering, problems, root=None):
    """生成 51 条需求 + 195 条 AC 的验收台账：状态由证据链推导，不由提交名推断。

    证据链（fail-closed，任一缺失即未验证）：
    1. 交付提交存在（--delivering 需求提交落地前如实记「本提交待落地」未验证）；
    2. 该 REQ 全部提交触及的测试文件仍存在于 tests/；
    3. 证据文件（REQ-038..049）含实质核验内容且状态为 verified
       （非 verified 的冻结证据如实保留未验证）。
    """
    root = os.path.abspath(root) if root else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    deliver_num = int(delivering.split("-")[1])
    commit_tests, git_err = collect_commit_tests(root)
    if git_err:
        problems.append(git_err)
        commit_tests = commit_tests or {}
    tests_dir = os.path.join(root, "tests")
    try:
        tests_present = set(os.listdir(tests_dir))
    except OSError:
        tests_present = set()
    ledger = []
    acs = []
    for num in sorted(reqs):
        r = reqs[num]
        commit = commits.get(num)
        req_tests = sorted(commit_tests.get(num, ()))
        entry = {
            "req": f"REQ-{num:03d}",
            "title": r["title"],
            "type": r["type"],
            "priority": f"P{r['priority']}" if r["priority"] is not None else None,
            "status": None,
            "version": commit["short"] if commit else None,
            "pending_commit": False,
            "input_kind": [],
            "input": None,
            "evidence": None,
            "unverified_reason": None,
        }
        status = reason = None
        if num > deliver_num:
            status = "未验证"
            reason = "待交付（验收工具与测试尚未提交）"
        elif commit is None:
            if num == deliver_num:
                status = "未验证"
                reason = "本提交待落地（证据先于提交产出，提交落地后复跑核验转为通过）"
                entry["pending_commit"] = True
            else:
                status = "失败"
                reason = "已在交付范围内但缺少对应提交"
                problems.append(f"REQ-{num:03d} 已在交付范围内但缺少对应提交")
        else:
            chain_problems = []
            missing_tests = [t for t in req_tests if os.path.basename(t) not in tests_present]
            if not req_tests:
                chain_problems.append("交付提交未触及任何 tests/ 测试文件（每次改动必须附带测试）")
            elif missing_tests:
                chain_problems.append(
                    "缺少关联测试文件：" + ", ".join(os.path.basename(t) for t in missing_tests)
                )
            if num in EVIDENCE_FILES:
                state, detail = _evidence_file_state(root, num)
                if state == "invalid":
                    chain_problems.append(detail)
                elif state == "truthful_unverified":
                    reason = detail
            if chain_problems:
                status = "未验证"
                reason = "；".join(chain_problems)
                for p in chain_problems:
                    problems.append(f"REQ-{num:03d} {p}")
            elif status is None:
                status = "通过" if reason is None else "未验证"
        entry["status"] = status
        entry["unverified_reason"] = reason if status != "通过" else None
        if num > deliver_num:
            entry["input_kind"] = []
            entry["input"] = INPUT_TEXT["pending"]
        elif num in INPUT_KINDS:
            entry["input_kind"] = list(INPUT_KINDS[num])
            entry["input"] = INPUT_TEXT[num]
        else:
            entry["input_kind"] = list(INPUT_KINDS.get(r["type"], []))
            entry["input"] = INPUT_TEXT.get(r["type"], "")
        parts = []
        if commit:
            parts.append(f"commit {commit['short']}")
        if req_tests:
            parts.append("tests(" + ", ".join(os.path.basename(t) for t in req_tests) + ")")
        if num in EVIDENCE_FILES:
            parts.append(f"evidence/{EVIDENCE_FILES[num][0]}")
        if num == 46:
            parts.append(FIXTURE_46)
        if num == 50:
            parts.append("scripts/verify_acceptance.py")
        if num == 51:
            parts.append("scripts/verify_requirements_doc.py")
        entry["evidence"] = " + ".join(parts) if parts else "待交付"
        ledger.append(entry)
        for k in sorted(r["acs"]):
            acs.append(
                {
                    "id": f"REQ-{num:03d}-AC{k:02d}",
                    "req": f"REQ-{num:03d}",
                    "status": entry["status"],
                    "version": entry["version"],
                    "input_kind": list(entry["input_kind"]),
                    "evidence": entry["evidence"],
                    "unverified_reason": entry["unverified_reason"],
                }
            )
    if len(ledger) != EXPECTED["requirements"] or len(acs) != EXPECTED["acceptance_criteria"]:
        problems.append(f"台账规模 {len(ledger)}/{len(acs)} ≠ 51/195")
    ledger_meta = {"duplicated_req_commits": {f"REQ-{k:03d}": v for k, v in sorted(dup.items())}}
    return ledger, acs, ledger_meta


def check_kinds_and_synthesis(root, doc_text, ledger, problems):
    """四类输入如实分别标注；不以检查项通过比例声明来源准确率。

    通过条目的输入类别必须属于四类；未在通过条目出现的类别如实列为
    「未获证据」（与台账未验证条目对应），不硬凑类别覆盖冒充证据存在。
    """
    kinds_used = set()
    for e in ledger:
        if e["status"] == "通过":
            kinds_used.update(e["input_kind"])
    unknown = sorted(kinds_used - set(ALL_KINDS))
    if unknown:
        problems.append(f"台账使用了未定义的输入类别：{unknown}")
    section = {
        "kind_coverage": sorted(kinds_used),
        "kinds_not_evidenced": sorted(set(ALL_KINDS) - kinds_used),
        "accuracy_rate_claimed": False,
        "no_rate_synthesis_rule_present": "不得以检查项通过比例声明来源准确率" in doc_text,
        "rate_claim_lines_in_doc": [],
        "rate_claim_lines_in_readme": [],
    }
    if not section["no_rate_synthesis_rule_present"]:
        problems.append("需求文档缺少“不得以检查项通过比例声明来源准确率”规则")
    section["rate_claim_lines_in_doc"] = [
        line.strip() for line in doc_text.splitlines() if RE_RATE_CLAIM.search(line)
    ]
    if section["rate_claim_lines_in_doc"]:
        problems.append(f"文档存在以百分比声明准确率/通过率的行：{section['rate_claim_lines_in_doc'][:3]}")
    readme_path = os.path.join(root, "README.md")
    if os.path.isfile(readme_path):
        readme = _read_text(readme_path)
        section["rate_claim_lines_in_readme"] = [
            line.strip() for line in readme.splitlines() if RE_RATE_CLAIM.search(line)
        ]
        if section["rate_claim_lines_in_readme"]:
            problems.append(
                f"README 存在以百分比声明准确率/通过率的行：{section['rate_claim_lines_in_readme'][:3]}"
            )
    return section


def build_report(args, audit_dir, sections, problems):
    counts = {}
    for e in sections["ledger"]:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    delivery = {
        "structural_verification": "verified" if not problems else "failed",
        "requirements": len(sections["ledger"]),
        "acceptance_criteria": len(sections["acs"]),
        "passed": counts.get("通过", 0),
        "unverified": counts.get("未验证", 0),
        "failed": counts.get("失败", 0),
        "unverified_reqs": [e["req"] for e in sections["ledger"] if e["status"] == "未验证"],
        "failed_reqs": [e["req"] for e in sections["ledger"] if e["status"] == "失败"],
        "kinds_not_evidenced": sections["kinds"]["kinds_not_evidenced"],
        "note": (
            "structural_verification 表示台账与证据链核验本身的结果；"
            "passed/unverified 表达业务交付完成度，未验证为如实保留的状态而非核验失败"
        ),
    }
    return {
        "requirement": "REQ-050 需求验收记录与证据闭环",
        "generated_at": datetime.now(BJT).isoformat(),
        "input": {
            "root": os.path.abspath(args.root),
            "delivering": args.delivering,
            "audit_dir": os.path.relpath(audit_dir, args.root).replace(os.sep, "/"),
        },
        "doc": sections["doc"],
        "findings_map": sections["findings"],
        "conclusions": sections["conclusions"],
        "integrity": sections["integrity"],
        "ledger": sections["ledger"],
        "acceptance_criteria": sections["acs"],
        "kinds": sections["kinds"],
        "ledger_meta": sections["ledger_meta"],
        "delivery": delivery,
        "overall": {"status": "verified" if not problems else "failed", "problems": problems},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="REQ-050 需求验收记录与证据闭环校验")
    ap.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="仓库根目录（默认：脚本所在仓库）",
    )
    ap.add_argument("--delivering", default="REQ-050", help="本次交付的需求编号（默认 REQ-050）")
    ap.add_argument("--output", default=None, help="证据输出路径（默认 audit/2026-10-09/evidence/acceptance-evidence.json）")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    audit_dir = os.path.join(root, "audit", "2026-10-09")
    m = re.fullmatch(r"REQ-(\d{3})", args.delivering)
    if not m or not (1 <= int(m.group(1)) <= 51):
        print("--delivering 格式须为 REQ-0NN（001..051）", file=sys.stderr)
        return 2
    problems = []
    doc_text = _read_text(os.path.join(audit_dir, "requirements.md"))
    model = _load_json(os.path.join(audit_dir, "evidence", "requirements-model.json"))
    verification = _load_json(os.path.join(audit_dir, "evidence", "requirements-verification.json"))
    all_checks = _load_json(os.path.join(audit_dir, "evidence", "all-checks.json"))
    findings = _load_json(os.path.join(audit_dir, "evidence", "findings.json"))
    reqs, doc_section = check_doc(doc_text, model, verification, problems)
    _, findings_section = check_findings_mapping(doc_text, findings, all_checks, model, problems)
    conclusions_section = check_conclusions(doc_text, problems)
    integrity_section = check_integrity(root, audit_dir, doc_text, all_checks, findings, problems)
    commits, dup, git_err = collect_commits(root)
    if git_err:
        problems.append(git_err)
    ledger, acs, ledger_meta = build_ledger(reqs, commits, dup, args.delivering, problems, root=root)
    kinds_section = check_kinds_and_synthesis(root, doc_text, ledger, problems)
    sections = {
        "doc": doc_section,
        "findings": findings_section,
        "conclusions": conclusions_section,
        "integrity": integrity_section,
        "ledger": ledger,
        "acs": acs,
        "kinds": kinds_section,
        "ledger_meta": ledger_meta,
    }
    report = build_report(args, audit_dir, sections, problems)
    output = args.output or os.path.join(audit_dir, "evidence", "acceptance-evidence.json")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(
        "[doc] 需求", doc_section["requirements"], "| AC", doc_section["acceptance_criteria"],
        "| 类型", doc_section["type_counts"],
    )
    print(
        "[findings] 5.1 行", findings_section["table_rows"],
        "| findings.json", findings_section["findings_json"],
        "| 并集", findings_section["union_reqs"],
        "| 缺失检查", len(findings_section["check_ids_missing"]),
    )
    print(
        "[conclusions] 行", conclusions_section["rows"],
        "| 未验证", len(conclusions_section["unverified"]),
        "| D10", conclusions_section["d10_present"],
        "| P04", conclusions_section["p04_present"],
    )
    sha_ok = sum(1 for v in integrity_section["source_sha256"].values() if v["match"])
    ev_ok = sum(1 for v in integrity_section["evidence_files"].values() if v["match"])
    print(
        "[integrity] 来源SHA", f"{sha_ok}/{len(integrity_section['source_sha256'])}",
        "| 检查", integrity_section["all_checks"]["total"], integrity_section["all_checks"]["counts"],
        "| 失败保留", integrity_section["all_checks"]["failed_preserved"],
        "| 证据文件", f"{ev_ok}/{len(EVIDENCE_FILES)}",
        "| requirements.md 未改", integrity_section["requirements_md_unchanged"],
    )
    status_counts = {}
    for e in ledger:
        status_counts[e["status"]] = status_counts.get(e["status"], 0) + 1
    print("[ledger] 需求", len(ledger), "| AC", len(acs), "| 状态", status_counts)
    unverified_reqs = [e["req"] for e in ledger if e["status"] == "未验证"]
    if unverified_reqs:
        print("[ledger] 未验证（如实保留）:", ", ".join(unverified_reqs))
    print(
        "[kinds] 覆盖", "+".join(kinds_section["kind_coverage"]),
        "| 未获证据", "+".join(kinds_section["kinds_not_evidenced"]) or "无",
        "| 准确率声明", kinds_section["accuracy_rate_claimed"],
    )
    print("[overall]", report["overall"]["status"])
    for p in problems:
        print("  -", p)
    print("[output]", os.path.relpath(output, root))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
