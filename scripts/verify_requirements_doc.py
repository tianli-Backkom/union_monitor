#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REQ-051 · 完整需求文档的版本与可追溯交付 — 校验工具。

对 audit/2026-10-09/requirements.md 做交付级核验：
1. 结构：51 个 REQ 编号连续唯一，每项至少 3 条带唯一编号的验收标准；
   5.1/5.2 追踪表并集覆盖 REQ-001..REQ-050（REQ-051 为文档交付自身，不入表）；
2. 分类：整改 37 / 补证 3 / 保持 9 / 交付 2；整改全部挂接 F01–F19 来源，
   保持与补证不来自任何 F 问题（补证映射 5.2 未验证结论而非已确认线上故障），
   依赖行与需求模型逐条一致、引用存在且无环；
3. 来源与不变性：7 个来源文件 SHA-256 与第 7 节冻结表一致；requirements.md 与
   final-delivery-verification.json 保持审计基线单一历史且结论不变；业务源码的
   全部基线后提交均归属 REQ-XXX（需求生成不改业务源码）；本地文档链接全部有效；
4. 总体验收：--delivering REQ-051 刷新后的验收台账如实反映交付完成度——
   结构核验通过、51 条需求/195 条 AC、无失败条目；冻结证据状态非 verified 的
   需求（缺原始证据/真实历史）保留未验证、不得放宽为通过；6 条未验证结论及
   D10/P04 标签保留。

用法（先刷新验收台账，再运行本工具）：
    python3 -X utf8 scripts/verify_acceptance.py --delivering REQ-051
    python3 -X utf8 scripts/verify_requirements_doc.py [--root DIR] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_acceptance as vfa

BJT = timezone(timedelta(hours=8))

MIN_ACS_PER_REQ = 3
DOC_REQUIREMENT = 51
BUSINESS_PREFIXES = ("web/", "data/", "triton/", ".github/")
BUSINESS_FILES = (
    "collect.py",
    "metrics.py",
    "repository_store.py",
    "serve.py",
    "source_coverage.py",
    "validate.py",
    "validate_bundle.py",
    "validate_multi.py",
)
FINAL_DELIVERY = "evidence/final-delivery-verification.json"
ACCEPTANCE_EVIDENCE = "evidence/acceptance-evidence.json"
LOCAL_LINK_PREFIX = "D:/ubs_core_monitor/"

RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
RE_REQ_SUBJECT = re.compile(r"^REQ-\d{3}：")
RE_DEP_LINE = re.compile(r"^\*\*依赖：\*\*\s*(.+)$")


def parse_doc_dependencies(md_text):
    """解析各 REQ 的「依赖：」行 → {num: [dep nums]}（无该行 → None）。"""
    deps = {}
    current = None
    for line in md_text.splitlines():
        m = vfa.RE_REQ_HEADER.match(line)
        if m:
            current = int(m.group(1))
            deps[current] = None
            continue
        if current is None:
            continue
        m = RE_DEP_LINE.match(line)
        if m:
            deps[current] = sorted(int(x) for x in re.findall(r"REQ-(\d{3})", m.group(1)))
    return deps


def check_dependencies(model, doc_deps, problems):
    """依赖：引用存在、无自依赖、无环，文档依赖行与模型逐条一致。"""
    req_ids = {int(e["id"].split("-")[1]) for e in model.get("requirements", [])}
    graph = {}
    for e in model.get("requirements", []):
        n = int(e["id"].split("-")[1])
        deps = []
        for d in e.get("dependencies", []):
            m = re.fullmatch(r"REQ-(\d{3})", d)
            if not m or int(m.group(1)) not in req_ids:
                problems.append(f"REQ-{n:03d} 依赖不存在的需求：{d}")
                continue
            dn = int(m.group(1))
            if dn == n:
                problems.append(f"REQ-{n:03d} 依赖自身")
                continue
            deps.append(dn)
        graph[n] = deps
    for n, doc_v in doc_deps.items():
        model_v = sorted(graph.get(n, []))
        if (doc_v or []) != model_v:
            problems.append(f"REQ-{n:03d} 依赖行 {doc_v} 与模型 {model_v} 不一致")
    color = {n: 0 for n in graph}
    cycles = []

    def visit(n):
        color[n] = 1
        for d in graph.get(n, []):
            if color.get(d) == 1:
                cycles.append(f"REQ-{n:03d}→REQ-{d:03d}")
            elif color.get(d) == 0:
                visit(d)
        color[n] = 2

    for n in sorted(graph):
        if color[n] == 0:
            visit(n)
    if cycles:
        problems.append(f"依赖图存在环：{cycles[:3]}")
    return {
        "doc_dep_lines": sum(1 for v in doc_deps.values() if v is not None),
        "deps_total": sum(len(v) for v in graph.values()),
        "acyclic": not cycles,
    }


def check_structure(md_text, reqs, problems):
    """AC01：编号连续唯一、每项至少 3 条 AC、追踪表覆盖全部源结论。"""
    section = {
        "requirements": len(reqs),
        "acceptance_criteria": 0,
        "min_acs": None,
        "min_req": None,
        "tracking_union": None,
        "uncovered": [],
    }
    if sorted(reqs) != list(range(1, vfa.EXPECTED["requirements"] + 1)):
        problems.append("REQ 编号不是 001..051 连续唯一")
    total = 0
    min_acs, min_req = None, None
    for num, r in sorted(reqs.items()):
        n = len(r["acs"])
        total += n
        if r["acs"] != list(range(1, n + 1)):
            problems.append(f"REQ-{num:03d} 的 AC 编号不连续或重复")
        if r["priority"] is None or r["type"] is None:
            problems.append(f"REQ-{num:03d} 缺少优先级/类型行")
        if min_acs is None or n < min_acs:
            min_acs, min_req = n, num
        if n < MIN_ACS_PER_REQ:
            problems.append(f"REQ-{num:03d} 验收标准数 {n} < {MIN_ACS_PER_REQ}")
    section["acceptance_criteria"] = total
    section["min_acs"] = min_acs
    section["min_req"] = f"REQ-{min_req:03d}" if min_req is not None else None
    if total != vfa.EXPECTED["acceptance_criteria"]:
        problems.append(f"验收标准总数 {total} ≠ {vfa.EXPECTED['acceptance_criteria']}")
    union = set()
    for refs in vfa.parse_findings_table(md_text).values():
        union.update(refs)
    for _, refs in vfa.parse_conclusions_table(md_text):
        union.update(refs)
    expected = set(range(1, DOC_REQUIREMENT))
    if union:
        section["tracking_union"] = f"REQ-{min(union):03d}..REQ-{max(union):03d}"
    section["uncovered"] = sorted(f"REQ-{n:03d}" for n in expected - union)
    if union != expected:
        problems.append(f"5.1/5.2 追踪表并集 ≠ REQ-001..REQ-050（缺失 {section['uncovered'][:5]}）")
    if DOC_REQUIREMENT in union:
        problems.append("REQ-051（文档交付自身）不应出现在源结论追踪表")
    return section


def check_classification(md_text, reqs, model, problems):
    """AC02：37/3/9/2 分类；整改挂接 F 来源；补证映射未验证结论而非线上故障。"""
    counts = {}
    groups = {"整改": [], "补证": [], "保持": [], "交付": []}
    for num, r in sorted(reqs.items()):
        t = r["type"]
        if t:
            counts[t] = counts.get(t, 0) + 1
            groups[t].append(num)
    section = {
        "type_counts": counts,
        "groups": {k: [f"REQ-{n:03d}" for n in v] for k, v in groups.items()},
        "rules": {},
        "dependencies": None,
    }
    if counts != vfa.EXPECTED["type_counts"]:
        problems.append(f"类型计数 {counts} ≠ {vfa.EXPECTED['type_counts']}")
    model_by_num = {int(e["id"].split("-")[1]): e for e in model.get("requirements", [])}
    findings_ids = {f"F{n:02d}" for n in range(1, vfa.EXPECTED["findings"] + 1)}
    table51 = vfa.parse_findings_table(md_text)
    rows52 = vfa.parse_conclusions_table(md_text)
    unverified_rows = [(l, r) for l, r in rows52 if vfa.conclusion_status(l) == "未验证"]
    in51 = set()
    for refs in table51.values():
        in51.update(refs)
    rectification_with_findings = 0
    for num in groups["整改"]:
        e = model_by_num.get(num)
        if e is None:
            problems.append(f"需求模型缺少 REQ-{num:03d}")
            continue
        sf = e.get("source_findings", [])
        if not sf:
            problems.append(f"整改需求 REQ-{num:03d} 未挂接 F 问题来源")
        else:
            rectification_with_findings += 1
            for fid in sf:
                if fid not in findings_ids:
                    problems.append(f"REQ-{num:03d} source_findings 越界：{fid}")
    for t in ("补证", "保持", "交付"):
        for num in groups[t]:
            e = model_by_num.get(num)
            if e is None:
                problems.append(f"需求模型缺少 REQ-{num:03d}")
                continue
            if e.get("source_findings"):
                problems.append(f"{t}需求 REQ-{num:03d} 不应挂接 F 问题来源：{e['source_findings']}")
    supplement_rows = {}
    for num in groups["补证"]:
        if num in in51:
            problems.append(f"补证需求 REQ-{num:03d} 不应出现在 5.1 问题追踪表")
        hits = [l for l, r in unverified_rows if num in r]
        supplement_rows[f"REQ-{num:03d}"] = hits
        if not hits:
            problems.append(f"补证需求 REQ-{num:03d} 未映射任何未验证结论（补证不是已确认线上故障）")
    section["rules"]["rectification_with_findings"] = rectification_with_findings
    section["rules"]["supplement_unverified_rows"] = supplement_rows
    for num in groups["保持"]:
        if not any(num in r for _, r in rows52):
            problems.append(f"保持需求 REQ-{num:03d} 未出现在 5.2 结论追踪表")
    section["dependencies"] = check_dependencies(model, parse_doc_dependencies(md_text), problems)
    return section


def check_business_attribution(root, problems):
    """业务源码的全部基线后提交均归属 REQ-XXX（需求生成不改业务源码）。"""
    rc, roots, _ = vfa._git(root, "rev-list", "--max-parents=0", "HEAD")
    lines = [h for h in roots.splitlines() if h]
    if rc != 0 or not lines:
        problems.append("无法确定仓库初始提交")
        return {"root_commit": None, "commits": 0, "non_req": []}
    root_hash = lines[0]
    pathspecs = list(BUSINESS_PREFIXES) + list(BUSINESS_FILES)
    rc, out, _ = vfa._git(root, "log", "--format=%H%x09%s", f"{root_hash}..HEAD", "--", *pathspecs)
    if rc != 0:
        problems.append("git log 业务路径失败")
        return {"root_commit": root_hash[:7], "commits": 0, "non_req": ["<git-error>"]}
    commits = []
    non_req = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        h, s = line.split("\t", 1)
        commits.append({"hash": h[:7], "subject": s})
        if not RE_REQ_SUBJECT.match(s):
            non_req.append(f"{h[:7]} {s}")
    if non_req:
        problems.append(f"业务源码存在不归属 REQ 的提交：{non_req[:5]}")
    return {"root_commit": root_hash[:7], "commits": len(commits), "non_req": non_req}


def check_links(md_text, root, problems):
    """本地文档链接（D:/ubs_core_monitor/...）全部有效。"""
    section = {"local_links": {}, "external_links": 0, "broken": []}
    for label, target in RE_MD_LINK.findall(md_text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            section["external_links"] += 1
            continue
        if target.startswith(LOCAL_LINK_PREFIX):
            rel = target[len(LOCAL_LINK_PREFIX):]
            path = os.path.join(root, rel.replace("/", os.sep))
            key = rel
        else:
            base = os.path.join(root, "audit", "2026-10-09")
            path = os.path.normpath(os.path.join(base, target))
            key = os.path.relpath(path, root).replace(os.sep, "/")
        ok = os.path.isfile(path)
        section["local_links"][key] = {"label": label, "ok": ok}
        if not ok:
            section["broken"].append(f"{label}→{target}")
    if section["broken"]:
        problems.append(f"本地文档链接失效：{section['broken']}")
    return section


def check_sources(root, audit_dir, md_text, problems):
    """AC03：来源 SHA-256、冻结记录不变、业务归属与本地链接。"""
    section = {
        "source_sha256": {},
        "requirements_md_unchanged": False,
        "final_delivery": None,
        "business_attribution": None,
        "links": None,
    }
    table = vfa.parse_sha_table(md_text)
    if len(table) != len(vfa.SOURCE_FILES):
        problems.append(f"第 7 节来源 SHA 表行数 {len(table)} ≠ {len(vfa.SOURCE_FILES)}")
    for rel, want in sorted(table.items()):
        path = os.path.join(audit_dir, rel)
        if not os.path.isfile(path):
            section["source_sha256"][rel] = {"expected": want, "actual": None, "match": False}
            problems.append(f"来源文件缺失：{rel}")
            continue
        actual = vfa._sha256_file(path)
        ok = actual == want
        section["source_sha256"][rel] = {"expected": want, "actual": actual, "match": ok}
        if not ok:
            problems.append(f"来源文件 SHA-256 不匹配：{rel}")
    rel_md = os.path.relpath(os.path.join(audit_dir, "requirements.md"), root).replace(os.sep, "/")
    rc, out, _ = vfa._git(root, "log", "--format=%H", "--", rel_md)
    hashes = [h for h in out.splitlines() if h]
    if rc != 0 or len(hashes) != 1:
        problems.append(f"requirements.md 的 git 历史不是单一基线提交（{len(hashes)} 条）")
    else:
        rc2, _, _ = vfa._git(root, "diff", "--quiet", hashes[0], "--", rel_md)
        section["requirements_md_unchanged"] = rc2 == 0
        if rc2 != 0:
            problems.append("requirements.md 与审计基线提交内容不一致")
    fd_path = os.path.join(audit_dir, FINAL_DELIVERY)
    if not os.path.isfile(fd_path):
        problems.append(f"final-delivery-verification.json 缺失：{FINAL_DELIVERY}")
    else:
        rel_fd = os.path.relpath(fd_path, root).replace(os.sep, "/")
        rc, out, _ = vfa._git(root, "log", "--format=%H", "--", rel_fd)
        fd_hashes = [h for h in out.splitlines() if h]
        fd = vfa._load_json(fd_path)
        section["final_delivery"] = {
            "history_commits": len(fd_hashes),
            "status": fd.get("status"),
            "findings": fd.get("findings"),
            "broken_local_links": fd.get("broken_local_links"),
            "production_changed": fd.get("production_changed"),
        }
        if len(fd_hashes) != 1:
            problems.append(
                f"final-delivery-verification.json 的 git 历史不是单一基线提交（{len(fd_hashes)} 条）"
            )
        if fd.get("status") != "passed":
            problems.append("冻结 final-delivery-verification.json status 不是 passed")
        if fd.get("broken_local_links"):
            problems.append("冻结 final-delivery-verification.json 记录了失效本地链接")
        if fd.get("production_changed"):
            problems.append("冻结 final-delivery-verification.json 记录了业务文件改动")
    section["business_attribution"] = check_business_attribution(root, problems)
    section["links"] = check_links(md_text, root, problems)
    return section


def check_overall(root, audit_dir, problems):
    """AC04：验收台账如实反映交付完成度——通过须有证据链，未验证如实保留。

    台账须由 verify_acceptance --delivering REQ-051 刷新：结构核验通过
    （overall verified）、51 条需求/195 条 AC、无失败条目；冻结证据状态非
    verified 的需求（REQ-038 unverified、REQ-039 aligned 等）必须保留未验证，
    不得放宽为通过；除该冻结未验证集合与「本提交待落地」的交付需求自身外，
    不允许其他未验证条目；6 条未验证结论及 D10/P04 标签保留
    （缺原始证据/真实历史不得记为完成）。
    """
    section = {"acceptance": None, "allowed_unverified": [], "extra_unverified": [], "relaxed_unverified": []}
    path = os.path.join(audit_dir, ACCEPTANCE_EVIDENCE)
    if not os.path.isfile(path):
        problems.append(
            f"验收台账证据缺失：{ACCEPTANCE_EVIDENCE}（先运行 verify_acceptance.py --delivering REQ-051）"
        )
        return section
    acc = vfa._load_json(path)
    ledger = acc.get("ledger", [])
    statuses = [e.get("status") for e in ledger]
    by_req = {e.get("req"): e for e in ledger}
    conclusions = acc.get("conclusions", {})
    allowed = sorted(
        f"REQ-{n:03d}" for n, (_f, _k, want) in vfa.EVIDENCE_FILES.items() if want != "verified"
    )
    unverified = [e.get("req") for e in ledger if e.get("status") == "未验证"]
    failed = [e.get("req") for e in ledger if e.get("status") == "失败"]
    section["allowed_unverified"] = allowed
    section["acceptance"] = {
        "delivering": acc.get("input", {}).get("delivering"),
        "overall_status": acc.get("overall", {}).get("status"),
        "ledger": len(ledger),
        "passed": statuses.count("通过"),
        "unverified": statuses.count("未验证"),
        "failed": statuses.count("失败"),
        "acs": len(acc.get("acceptance_criteria", [])),
        "unverified_conclusions": len(conclusions.get("unverified", [])),
        "delivery": acc.get("delivery"),
    }
    a = section["acceptance"]
    if a["delivering"] != "REQ-051":
        problems.append(f"验收台账 delivering={a['delivering']} ≠ REQ-051（需先刷新）")
    if a["overall_status"] != "verified":
        problems.append(f"验收台账 overall_status={a['overall_status']} 不是 verified")
    if a["ledger"] != vfa.EXPECTED["requirements"] or a["acs"] != vfa.EXPECTED["acceptance_criteria"]:
        problems.append(
            f"验收台账规模 {a['ledger']}/{a['acs']} ≠ 51/195"
        )
    if failed:
        problems.append(f"验收台账存在失败条目：{failed}")
    if a["passed"] + a["unverified"] + a["failed"] != vfa.EXPECTED["requirements"]:
        problems.append("验收台账 通过/未验证/失败 计数与需求总数不一致")
    section["relaxed_unverified"] = [r for r in allowed if r not in unverified]
    if section["relaxed_unverified"]:
        problems.append(
            f"冻结证据未验证的需求被放宽为通过：{section['relaxed_unverified']}（缺原始证据/真实历史不得记为完成）"
        )
    delivering_req = "REQ-051"
    extra = [r for r in unverified if r not in allowed]
    pending_ok = False
    if delivering_req in extra:
        e = by_req.get(delivering_req)
        if e and e.get("pending_commit"):
            pending_ok = True
    section["extra_unverified"] = [r for r in extra if not (r == delivering_req and pending_ok)]
    if section["extra_unverified"]:
        problems.append(
            f"允许范围之外的未验证条目：{section['extra_unverified']}（已交付需求须有完整证据链）"
        )
    for e in ledger:
        if e.get("status") == "通过" and not e.get("version"):
            problems.append(f"{e.get('req')} 标记通过但缺少版本（交付提交）")
        if e.get("status") == "未验证" and not e.get("unverified_reason"):
            problems.append(f"{e.get('req')} 未验证但缺少原因（如实状态须可追溯）")
    if a["unverified_conclusions"] != vfa.EXPECTED["unverified_conclusion_rows"]:
        problems.append(
            f"未验证结论保留数 {a['unverified_conclusions']} ≠ "
            f"{vfa.EXPECTED['unverified_conclusion_rows']}（缺原始证据/真实历史不得记为完成）"
        )
    labels = {e.get("label") for e in conclusions.get("unverified", [])}
    if not any(l.startswith("D10") for l in labels) or not any(l.startswith("P04") for l in labels):
        problems.append("未验证结论缺少 D10/P04 行")
    return section


def main(argv=None):
    ap = argparse.ArgumentParser(description="REQ-051 完整需求文档的版本与可追溯交付校验")
    ap.add_argument(
        "--root",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="仓库根目录（默认：脚本所在仓库）",
    )
    ap.add_argument(
        "--output",
        default=None,
        help="证据输出路径（默认 audit/2026-10-09/evidence/requirements-doc-evidence.json）",
    )
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    audit_dir = os.path.join(root, "audit", "2026-10-09")
    problems = []
    md_text = vfa._read_text(os.path.join(audit_dir, "requirements.md"))
    reqs, parse_problems = vfa.parse_requirements_doc(md_text)
    problems.extend(parse_problems)
    model = vfa._load_json(os.path.join(audit_dir, "evidence", "requirements-model.json"))
    structure = check_structure(md_text, reqs, problems)
    classification = check_classification(md_text, reqs, model, problems)
    sources = check_sources(root, audit_dir, md_text, problems)
    overall = check_overall(root, audit_dir, problems)
    report = {
        "requirement": "REQ-051 完整需求文档的版本与可追溯交付",
        "generated_at": datetime.now(BJT).isoformat(),
        "input": {"root": root, "audit_dir": os.path.relpath(audit_dir, root).replace(os.sep, "/")},
        "structure": structure,
        "classification": classification,
        "sources": sources,
        "overall_acceptance": overall,
        "overall": {"status": "verified" if not problems else "failed", "problems": problems},
    }
    output = args.output or os.path.join(audit_dir, "evidence", "requirements-doc-evidence.json")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(
        "[structure] 需求", structure["requirements"],
        "| AC", structure["acceptance_criteria"],
        "| 最少 AC", f"{structure['min_acs']}（{structure['min_req']}）",
        "| 追踪并集", structure["tracking_union"],
    )
    deps = classification["dependencies"]
    print(
        "[classification] 类型", classification["type_counts"],
        "| 整改挂接 F", classification["rules"]["rectification_with_findings"],
        "| 依赖", deps["deps_total"], "无环", deps["acyclic"],
    )
    sha_ok = sum(1 for v in sources["source_sha256"].values() if v["match"])
    links_ok = all(v["ok"] for v in sources["links"]["local_links"].values())
    biz = sources["business_attribution"]
    fd = sources["final_delivery"]
    print(
        "[sources] SHA", f"{sha_ok}/{len(sources['source_sha256'])}",
        "| 本地链接", len(sources["links"]["local_links"]), "有效", links_ok,
        "| 业务提交", biz["commits"], "非 REQ", len(biz["non_req"]),
        "| final-delivery", fd["status"] if fd else None,
    )
    acc = overall["acceptance"]
    print(
        "[acceptance] delivering", acc["delivering"] if acc else None,
        "| 台账通过", f"{acc['passed']}/{acc['ledger']}" if acc else None,
        "| 未验证结论保留", acc["unverified_conclusions"] if acc else None,
    )
    print("[overall]", report["overall"]["status"])
    for p in problems:
        print("  -", p)
    print("[output]", os.path.relpath(output, root))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
