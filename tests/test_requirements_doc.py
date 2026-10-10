#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REQ-051 完整需求文档的版本与可追溯交付 — 测试。

覆盖三类：
1. 单元测试：Markdown 链接/REQ 提交主题/依赖行解析、依赖规则
   （不存在/自依赖/环/文档与模型不一致）；
2. 合成 git 树测试：先以 --delivering REQ-051 刷新验收台账，文档工具
   exit 0；非 REQ 业务提交、REQ-011 删 AC（最少 3 条不满足）、台账过期
   （delivering=REQ-050）、链接目标失效、保持需求挂接 F 来源均 exit 1；
3. 已提交证据冻结值测试：结构/分类/来源/总体验收与交付证据逐项一致。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

import test_acceptance as ta  # noqa: E402
import verify_requirements_doc as vrd  # noqa: E402

SCRIPT_VFA = REPO / "scripts" / "verify_acceptance.py"
SCRIPT_VRD = REPO / "scripts" / "verify_requirements_doc.py"
AUDIT = REPO / "audit" / "2026-10-09"


def run_vfa(tree: Path, delivering: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(SCRIPT_VFA),
            "--root",
            str(tree),
            "--delivering",
            delivering,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    return proc.returncode


def run_vrd(tree: Path, out: Path = None) -> int:
    cmd = [sys.executable, "-X", "utf8", str(SCRIPT_VRD), "--root", str(tree)]
    if out is not None:
        cmd += ["--output", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=300)
    return proc.returncode


def build_tree(base: Path, name: str, req_commits: int = 50) -> Path:
    """合成树：REQ-050 测试树基础上补冻结 final-delivery-verification.json。"""
    tree = base / name
    evidence = tree / "audit" / "2026-10-09" / "evidence"
    evidence.mkdir(parents=True)
    shutil.copy2(AUDIT / "requirements.md", evidence.parent / "requirements.md")
    for f in ("review-report.md", "coverage-matrix.md"):
        shutil.copy2(AUDIT / f, evidence.parent / f)
    shutil.copy2(AUDIT / "evidence" / "baseline-comparison.md", evidence / "baseline-comparison.md")
    for f in ta.EVIDENCE_JSONS:
        shutil.copy2(AUDIT / "evidence" / f, evidence / f)
    shutil.copy2(
        AUDIT / "evidence" / "final-delivery-verification.json",
        evidence / "final-delivery-verification.json",
    )
    fixtures = tree / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    shutil.copy2(
        REPO / "tests" / "fixtures" / "triton-audit-freeze.json",
        fixtures / "triton-audit-freeze.json",
    )
    (tree / "tests" / "test_dummy.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tree / "tests" / "dummy.test.cjs").write_text("require('node:test');\n", encoding="utf-8")
    ta._git_ok(tree, "init", "-q")
    ta._git_ok(tree, "config", "user.email", "t@example.com")
    ta._git_ok(tree, "config", "user.name", "tester")
    ta._git_ok(tree, "config", "commit.gpgsign", "false")
    ta._git_ok(tree, "add", "-A")
    ta._git_ok(tree, "commit", "-q", "-m", "审计基线：合成树")
    for i in range(1, req_commits + 1):
        ta._git_ok(tree, "commit", "-q", "--allow-empty", "-m", f"REQ-{i:03d}：测试主题")
    return tree


class UnitTests(unittest.TestCase):
    def test_re_md_link(self):
        line = (
            "- [审查报告](D:/ubs_core_monitor/audit/2026-10-09/review-report.md)"
            " 与 [GitHub](https://github.com/x)"
        )
        self.assertEqual(
            vrd.RE_MD_LINK.findall(line),
            [
                ("审查报告", "D:/ubs_core_monitor/audit/2026-10-09/review-report.md"),
                ("GitHub", "https://github.com/x"),
            ],
        )

    def test_re_req_subject(self):
        self.assertTrue(vrd.RE_REQ_SUBJECT.match("REQ-050：验收"))
        self.assertFalse(vrd.RE_REQ_SUBJECT.match("REQ-050: 半角冒号"))
        self.assertFalse(vrd.RE_REQ_SUBJECT.match("REQ-50：编号不足"))
        self.assertFalse(vrd.RE_REQ_SUBJECT.match("修复：REQ-050：非起始"))

    def test_parse_doc_dependencies(self):
        mini = (
            "### REQ-001 · 甲\n"
            "\n"
            "**优先级：** P1　**类型：** 整改\n"
            "\n"
            "**依赖：** REQ-002、REQ-003\n"
            "\n"
            "- **REQ-001-AC01：** a\n"
            "- **REQ-001-AC02：** b\n"
            "- **REQ-001-AC03：** c\n"
            "\n"
            "### REQ-002 · 乙\n"
            "\n"
            "**优先级：** P2　**类型：** 保持\n"
        )
        self.assertEqual(vrd.parse_doc_dependencies(mini), {1: [2, 3], 2: None})

    def test_check_dependencies_rules(self):
        def run(model, doc_deps):
            problems = []
            section = vrd.check_dependencies(model, doc_deps, problems)
            return problems, section

        problems, _ = run({"requirements": [{"id": "REQ-001", "dependencies": ["REQ-099"]}]}, {})
        self.assertTrue(any("依赖不存在的需求" in p for p in problems))
        problems, _ = run({"requirements": [{"id": "REQ-001", "dependencies": ["REQ-001"]}]}, {})
        self.assertTrue(any("依赖自身" in p for p in problems))
        problems, section = run(
            {
                "requirements": [
                    {"id": "REQ-001", "dependencies": ["REQ-002"]},
                    {"id": "REQ-002", "dependencies": ["REQ-001"]},
                ]
            },
            {},
        )
        self.assertTrue(any("环" in p for p in problems))
        self.assertFalse(section["acyclic"])
        problems, _ = run({"requirements": [{"id": "REQ-001", "dependencies": []}]}, {1: [2]})
        self.assertTrue(any("不一致" in p for p in problems))


class SyntheticTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="req051-"))
        cls.tree = build_tree(cls.tmp, "full")
        rc = run_vfa(cls.tree, "REQ-051")
        assert rc == 0, "合成树验收台账刷新失败"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _tamper(self, rel, mutate):
        path = self.tree / rel
        original = path.read_bytes()
        try:
            mutate(path)
            self.assertEqual(run_vrd(self.tree), 1)
        finally:
            path.write_bytes(original)

    def test_clean_run_exit_zero(self):
        out = self.tmp / "clean.json"
        self.assertEqual(run_vrd(self.tree, out), 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["overall"], {"status": "verified", "problems": []})
        self.assertEqual(report["structure"]["requirements"], 51)
        self.assertEqual(report["structure"]["acceptance_criteria"], 195)
        acc = report["overall_acceptance"]["acceptance"]
        self.assertEqual((acc["delivering"], acc["passed"], acc["unverified"]), ("REQ-051", 51, 0))

    def test_tamper_business_commit(self):
        stale = self.tmp / "biz"
        shutil.copytree(self.tree, stale, symlinks=True)
        try:
            (stale / "web").mkdir()
            (stale / "web" / "x.js").write_text("// t\n", encoding="utf-8")
            ta._git_ok(stale, "add", "-A")
            ta._git_ok(stale, "commit", "-q", "-m", "杂项：直接修改业务文件")
            self.assertEqual(run_vrd(stale), 1)
        finally:
            shutil.rmtree(stale, ignore_errors=True)

    def test_tamper_remove_min_ac(self):
        def mutate(path):
            kept = [
                ln
                for ln in path.read_bytes().split(b"\n")
                if not ln.startswith(b"- **REQ-011-AC03")
            ]
            path.write_bytes(b"\n".join(kept))

        self._tamper("audit/2026-10-09/requirements.md", mutate)

    def test_tamper_stale_acceptance_delivering(self):
        stale = self.tmp / "stale"
        shutil.copytree(self.tree, stale, symlinks=True)
        try:
            self.assertEqual(run_vfa(stale, "REQ-050"), 0)
            self.assertEqual(run_vrd(stale), 1)
        finally:
            shutil.rmtree(stale, ignore_errors=True)

    def test_tamper_link_target(self):
        def mutate(path):
            data = path.read_bytes()
            data = data.replace(
                b"D:/ubs_core_monitor/audit/2026-10-09/review-report.md",
                b"D:/ubs_core_monitor/audit/2026-10-09/missing-report.md",
                1,
            )
            path.write_bytes(data)

        self._tamper("audit/2026-10-09/requirements.md", mutate)

    def test_tamper_keep_with_findings(self):
        def mutate(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in data["requirements"]:
                if e["id"] == "REQ-041":
                    e["source_findings"] = ["F01"]
                    break
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        self._tamper("audit/2026-10-09/evidence/requirements-model.json", mutate)


class CommittedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (AUDIT / "evidence" / "requirements-doc-evidence.json").read_text(encoding="utf-8")
        )

    def test_structure_frozen(self):
        self.assertEqual(
            self.report["structure"],
            {
                "requirements": 51,
                "acceptance_criteria": 195,
                "min_acs": 3,
                "min_req": "REQ-011",
                "tracking_union": "REQ-001..REQ-050",
                "uncovered": [],
            },
        )

    def test_classification_frozen(self):
        c = self.report["classification"]
        self.assertEqual(c["type_counts"], {"整改": 37, "补证": 3, "保持": 9, "交付": 2})
        self.assertEqual(
            c["groups"],
            {
                "整改": [f"REQ-{i:03d}" for i in range(1, 38)],
                "补证": ["REQ-038", "REQ-039", "REQ-040"],
                "保持": [f"REQ-{i:03d}" for i in range(41, 50)],
                "交付": ["REQ-050", "REQ-051"],
            },
        )
        self.assertEqual(c["rules"]["rectification_with_findings"], 37)
        supplement = c["rules"]["supplement_unverified_rows"]
        self.assertEqual(sorted(supplement), ["REQ-038", "REQ-039", "REQ-040"])
        for rows in supplement.values():
            self.assertTrue(rows)
        self.assertTrue(any(r.startswith("P04") for r in supplement["REQ-039"]))
        self.assertEqual(
            c["dependencies"], {"doc_dep_lines": 28, "deps_total": 59, "acyclic": True}
        )

    def test_sources_frozen(self):
        s = self.report["sources"]
        self.assertEqual(len(s["source_sha256"]), 7)
        self.assertTrue(all(v["match"] for v in s["source_sha256"].values()))
        self.assertTrue(s["requirements_md_unchanged"])
        self.assertEqual(
            s["final_delivery"],
            {
                "history_commits": 1,
                "status": "passed",
                "findings": 19,
                "broken_local_links": [],
                "production_changed": [],
            },
        )
        self.assertEqual(
            s["business_attribution"], {"root_commit": "db0d98f", "commits": 35, "non_req": []}
        )
        links = s["links"]
        self.assertEqual(len(links["local_links"]), 7)
        self.assertTrue(all(v["ok"] for v in links["local_links"].values()))
        self.assertEqual(links["external_links"], 0)
        self.assertEqual(links["broken"], [])

    def test_overall_frozen(self):
        self.assertEqual(self.report["overall"], {"status": "verified", "problems": []})
        self.assertEqual(
            self.report["overall_acceptance"]["acceptance"],
            {
                "delivering": "REQ-051",
                "overall_status": "verified",
                "ledger": 51,
                "passed": 51,
                "unverified": 0,
                "acs": 195,
                "unverified_conclusions": 6,
            },
        )


if __name__ == "__main__":
    unittest.main()
