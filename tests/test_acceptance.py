#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REQ-050 需求验收记录与证据闭环 — 测试。

覆盖四类：
1. 解析器单元测试：需求文档结构、REQ 引用展开（含区间）、F 映射表、结论表、
   SHA 表、结论状态分类、生成时间与“准确率百分比声明”正则、提交→测试映射、
   证据文件空壳检测；
2. 合成 git 树测试：干净树 exit 0（台账由证据链推导：49 通过 + 待交付如实未验证）；
   篡改 238 项检查宇宙（失败改写）、删除 F19、删除 AC 行、改动来源文件、
   改写证据状态（含把如实未验证放宽为通过）、清空证据详情（空壳证据）、
   删除关联测试文件均 exit 1；交付范围内缺 REQ 提交 exit 1；
   交付需求提交落地前如实记「本提交待落地」未验证；
3. 已提交证据冻结值测试：只断言跨 --delivering 刷新稳定的字段
   （49 通过 + REQ-038/039 如实未验证）。
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
import verify_acceptance as vfa  # noqa: E402

SCRIPT = REPO / "scripts" / "verify_acceptance.py"
AUDIT = REPO / "audit" / "2026-10-09"

EVIDENCE_JSONS = [
    "findings.json",
    "all-checks.json",
    "data-audit.json",
    "deployment-audit.json",
    "requirements-model.json",
    "requirements-verification.json",
    "artifact-verification.json",
    "concurrency-evidence.json",
    "runtime-evidence.json",
    "ubs-semantics-evidence.json",
    "ubs-filtering-evidence.json",
    "ubs-sorting-evidence.json",
    "ubs-csv-evidence.json",
    "ubs-detail-evidence.json",
    "ubs-routes-evidence.json",
    "interaction-evidence.json",
    "freshness-evidence.json",
]

MINI_DOC = (
    "### REQ-001 · 测试甲\n"
    "\n"
    "**优先级：** P1　**类型：** 整改\n"
    "\n"
    "- **REQ-001-AC01：** 标准1\n"
    "- **REQ-001-AC02：** 标准2\n"
    "- **REQ-001-AC03：** 标准3\n"
    "\n"
    "### REQ-002 · 测试乙\n"
    "\n"
    "**优先级：** P2　**类型：** 交付\n"
    "\n"
    "- **REQ-002-AC01：** 标准1\n"
    "- **REQ-001-AC02：** 前缀错位\n"
)

MINI_TABLES = (
    "### 5.1 原19组问题完整覆盖\n"
    "\n"
    "| 审查问题 | 对应独立需求 |\n"
    "|---|---|\n"
    "|F01 · 甲问题|REQ-001、REQ-002|\n"
    "|F02 · 乙问题|REQ-003|\n"
    "\n"
    "### 5.2 通过与未验证结论\n"
    "\n"
    "| 结论范围 | 对应需求 |\n"
    "|---|---|\n"
    "| D01–D09：一致性通过 | REQ-041、REQ-046 |\n"
    "| D10：缺原始来源 | REQ-023–REQ-025、REQ-038 |\n"
    "| P04：真实取消影响未验证 | REQ-039 |\n"
)


class ParserTests(unittest.TestCase):
    def test_parse_requirements_doc(self):
        reqs, problems = vfa.parse_requirements_doc(MINI_DOC)
        self.assertEqual(sorted(reqs), [1, 2])
        self.assertEqual(reqs[1]["title"], "测试甲")
        self.assertEqual(reqs[1]["priority"], 1)
        self.assertEqual(reqs[1]["type"], "整改")
        self.assertEqual(reqs[1]["acs"], [1, 2, 3])
        self.assertEqual(reqs[2]["priority"], 2)
        self.assertEqual(reqs[2]["type"], "交付")
        self.assertEqual(reqs[2]["acs"], [1])
        self.assertTrue(
            any("AC 前缀与所属 REQ 不符" in p and "REQ-001-AC02" in p for p in problems)
        )

    def test_expand_req_refs(self):
        self.assertEqual(vfa.expand_req_refs("REQ-001、REQ-002"), [1, 2])
        self.assertEqual(vfa.expand_req_refs("REQ-042–REQ-045、REQ-047"), [42, 43, 44, 45, 47])
        self.assertEqual(vfa.expand_req_refs("REQ-048、REQ-049及对应整改需求"), [48, 49])
        self.assertEqual(vfa.expand_req_refs("REQ-003"), [3])
        self.assertEqual(vfa.expand_req_refs("对应独立需求"), [])

    def test_parse_findings_table(self):
        self.assertEqual(vfa.parse_findings_table(MINI_TABLES), {1: [1, 2], 2: [3]})

    def test_parse_conclusions_table(self):
        rows = vfa.parse_conclusions_table(MINI_TABLES)
        self.assertEqual(
            rows,
            [
                ("D01–D09：一致性通过", [41, 46]),
                ("D10：缺原始来源", [23, 24, 25, 38]),
                ("P04：真实取消影响未验证", [39]),
            ],
        )

    def test_parse_sha_table(self):
        sha = "a" * 64
        text = f"## 7. 来源与版本\n\n| 来源文件 | SHA-256 |\n|---|---|\n|review-report.md|`{sha}`|\n"
        self.assertEqual(vfa.parse_sha_table(text), {"review-report.md": sha})

    def test_conclusion_status(self):
        self.assertEqual(vfa.conclusion_status("D10：缺原始来源"), "未验证")
        self.assertEqual(vfa.conclusion_status("真实缓存冷热/跨日更新影响未验证"), "未验证")
        self.assertEqual(vfa.conclusion_status("D01–D09：派生计算、身份和一致性通过"), "通过")
        self.assertEqual(vfa.conclusion_status("旧站继承和抽查范围的诚实说明"), "通过")

    def test_generation_time_and_rate_claim(self):
        line = "文档生成时间：2026-10-09T15:50:09.602805+08:00（Asia/Shanghai）。"
        self.assertEqual(vfa.parse_generation_time(line), "2026-10-09T15:50:09.602805+08:00")
        self.assertIsNone(vfa.parse_generation_time("其他行"))
        self.assertIsNotNone(vfa.RE_RATE_CLAIM.search("来源准确率 87%"))
        self.assertIsNotNone(vfa.RE_RATE_CLAIM.search("通过率 95.5%"))
        self.assertIsNone(vfa.RE_RATE_CLAIM.search("不得以检查项通过比例声明来源准确率"))

    def test_collect_commit_tests_maps_real_history(self):
        mapping, err = vfa.collect_commit_tests(REPO)
        self.assertIsNone(err)
        self.assertEqual(sorted(mapping), list(range(1, 52)))
        for num in range(1, 52):
            self.assertTrue(mapping[num], f"REQ-{num:03d} 提交未触及测试")
        self.assertIn("tests/test_acceptance.py", mapping[50])
        self.assertIn("tests/test_requirements_doc.py", mapping[51])

    def test_evidence_depth_keys_exist_in_frozen_files(self):
        for num, keys in vfa.EVIDENCE_DEPTH.items():
            fname = vfa.EVIDENCE_FILES[num][0]
            data = json.loads((AUDIT / "evidence" / fname).read_text(encoding="utf-8"))
            for k in keys:
                self.assertIn(k, data, f"{fname} 缺少实质核验键 {k}")

    def test_evidence_file_state_detects_hollow(self):
        state, detail = vfa._evidence_file_state(str(REPO), 41)
        self.assertEqual(state, "ok")
        hollow = Path(tempfile.mkdtemp(prefix="req050-hollow-"))
        try:
            audit = hollow / "audit" / "2026-10-09" / "evidence"
            audit.mkdir(parents=True)
            fname = vfa.EVIDENCE_FILES[41][0]
            (audit / fname).write_text(
                json.dumps({"overall": {"status": "verified"}}), encoding="utf-8"
            )
            state, detail = vfa._evidence_file_state(str(hollow), 41)
            self.assertEqual(state, "invalid")
            self.assertIn("空壳", detail)
        finally:
            shutil.rmtree(hollow, ignore_errors=True)


def _git_ok(tree, *args):
    proc = subprocess.run(["git", "-C", str(tree), *args], capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")


def build_tree(base: Path, name: str, req_commits: int, final_delivery: bool = False) -> Path:
    tree = base / name
    evidence = tree / "audit" / "2026-10-09" / "evidence"
    evidence.mkdir(parents=True)
    shutil.copy2(AUDIT / "requirements.md", evidence.parent / "requirements.md")
    for f in ("review-report.md", "coverage-matrix.md"):
        shutil.copy2(AUDIT / f, evidence.parent / f)
    shutil.copy2(AUDIT / "evidence" / "baseline-comparison.md", evidence / "baseline-comparison.md")
    for f in EVIDENCE_JSONS:
        shutil.copy2(AUDIT / "evidence" / f, evidence / f)
    if final_delivery:
        shutil.copy2(
            AUDIT / "evidence" / "final-delivery-verification.json",
            evidence / "final-delivery-verification.json",
        )
    fixtures = tree / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    shutil.copy2(REPO / "tests" / "fixtures" / "triton-audit-freeze.json", fixtures / "triton-audit-freeze.json")
    (tree / "tests" / "test_dummy.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    (tree / "tests" / "dummy.test.cjs").write_text("require('node:test');\n", encoding="utf-8")
    # 每个 REQ 提交必须触及其关联测试（镜像真实仓库的提交→测试映射）
    real_mapping, _ = vfa.collect_commit_tests(REPO)
    for num in range(1, req_commits + 1):
        for rel in sorted(real_mapping.get(num, ())):
            p = tree / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text("# stub\n", encoding="utf-8")
    _git_ok(tree, "init", "-q")
    _git_ok(tree, "config", "user.email", "t@example.com")
    _git_ok(tree, "config", "user.name", "tester")
    _git_ok(tree, "config", "commit.gpgsign", "false")
    _git_ok(tree, "add", "-A")
    _git_ok(tree, "commit", "-q", "-m", "审计基线：合成树")
    for i in range(1, req_commits + 1):
        for rel in sorted(real_mapping.get(i, ())):
            p = tree / rel
            p.write_text(p.read_text(encoding="utf-8") + f"# REQ-{i:03d}\n", encoding="utf-8")
        _git_ok(tree, "add", "-A")
        _git_ok(tree, "commit", "-q", "-m", f"REQ-{i:03d}：测试主题")
    return tree


def run_tool(tree: Path, out: Path, delivering: str = "REQ-050") -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(SCRIPT),
            "--root",
            str(tree),
            "--delivering",
            delivering,
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    return proc.returncode


class SyntheticTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="req050-"))
        cls.tree = build_tree(cls.tmp, "full", 49)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _tamper(self, rel, mutate):
        path = self.tree / rel
        original = path.read_bytes()
        try:
            mutate(path)
            out = self.tmp / "tamper.json"
            self.assertEqual(run_tool(self.tree, out), 1)
        finally:
            path.write_bytes(original)

    def test_clean_tree_exit_zero(self):
        out = self.tmp / "clean.json"
        self.assertEqual(run_tool(self.tree, out, delivering="REQ-050"), 0)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["overall"]["status"], "verified")
        self.assertEqual(len(report["ledger"]), 51)
        self.assertEqual(len(report["acceptance_criteria"]), 195)
        statuses = [e["status"] for e in report["ledger"]]
        # 49 个 REQ 提交：REQ-038/039 证据状态如实未验证，REQ-050 待落地，REQ-051 待交付
        self.assertEqual(
            (statuses.count("通过"), statuses.count("未验证"), statuses.count("失败")),
            (47, 4, 0),
        )
        by_req = {e["req"]: e for e in report["ledger"]}
        self.assertEqual(by_req["REQ-050"]["status"], "未验证")
        self.assertTrue(by_req["REQ-050"]["pending_commit"])
        self.assertIn("本提交待落地", by_req["REQ-050"]["unverified_reason"])
        self.assertEqual(by_req["REQ-051"]["status"], "未验证")
        self.assertIn("待交付", by_req["REQ-051"]["unverified_reason"])
        for e in report["ledger"]:
            if e["status"] == "通过":
                self.assertTrue(e["version"])
            elif e["status"] == "未验证":
                self.assertTrue(e["unverified_reason"])

    def test_delivering_pending_without_commit_exit_zero(self):
        pending = self.tmp / "pending"
        shutil.copytree(self.tree, pending, symlinks=True)
        try:
            _git_ok(pending, "reset", "-q", "--hard", "HEAD~1")  # 丢弃 REQ-049 提交
            out = self.tmp / "pending.json"
            self.assertEqual(run_tool(pending, out, delivering="REQ-049"), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            by_req = {e["req"]: e for e in report["ledger"]}
            self.assertEqual(by_req["REQ-049"]["status"], "未验证")
            self.assertTrue(by_req["REQ-049"]["pending_commit"])
            acs = report["acceptance_criteria"]
            self.assertNotIn(
                "通过", {a["status"] for a in acs if a["req"] == "REQ-049"}
            )
        finally:
            shutil.rmtree(pending, ignore_errors=True)

    def test_hollow_evidence_detail_rejected(self):
        path = self.tree / "audit" / "2026-10-09" / "evidence" / "freshness-evidence.json"
        original = path.read_bytes()
        try:
            # 空壳证据反例：仅保留顶层状态，其余核验内容全部清空
            path.write_text(
                json.dumps({"overall": {"status": "verified"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = self.tmp / "hollow.json"
            self.assertEqual(run_tool(self.tree, out, delivering="REQ-050"), 1)
            report = json.loads(out.read_text(encoding="utf-8"))
            by_req = {e["req"]: e for e in report["ledger"]}
            self.assertEqual(by_req["REQ-049"]["status"], "未验证")
            self.assertIn("空壳", by_req["REQ-049"]["unverified_reason"])
        finally:
            path.write_bytes(original)

    def test_missing_associated_tests_rejected(self):
        removed = self.tree / "tests" / "test_triton_quality.py"
        original = removed.read_bytes()
        try:
            removed.unlink()
            out = self.tmp / "notests.json"
            self.assertEqual(run_tool(self.tree, out, delivering="REQ-050"), 1)
            report = json.loads(out.read_text(encoding="utf-8"))
            by_req = {e["req"]: e for e in report["ledger"]}
            for req in ("REQ-018", "REQ-019"):
                self.assertEqual(by_req[req]["status"], "未验证")
                self.assertIn("缺少关联测试文件", by_req[req]["unverified_reason"])
        finally:
            removed.write_bytes(original)

    def test_tamper_flip_failed_check(self):
        def mutate(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            for c in data["checks"]:
                if c["state"] == "failed":
                    c["state"] = "passed"
                    break
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        self._tamper("audit/2026-10-09/evidence/all-checks.json", mutate)

    def test_tamper_drop_finding(self):
        def mutate(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            data[:] = [f for f in data if f["id"] != "F19"]
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        self._tamper("audit/2026-10-09/evidence/findings.json", mutate)

    def test_tamper_drop_ac_line(self):
        def mutate(path):
            kept = [
                ln
                for ln in path.read_bytes().split(b"\n")
                if not ln.startswith(b"- **REQ-051-AC04")
            ]
            path.write_bytes(b"\n".join(kept))

        self._tamper("audit/2026-10-09/requirements.md", mutate)

    def test_tamper_source_content(self):
        def mutate(path):
            path.write_bytes(path.read_bytes() + b"tamper\n")

        self._tamper("audit/2026-10-09/review-report.md", mutate)

    def test_tamper_evidence_status(self):
        def mutate(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["overall"]["status"] = "unverified"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        self._tamper("audit/2026-10-09/evidence/freshness-evidence.json", mutate)

    def test_tamper_artifact_status_relaxed(self):
        def mutate(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["overall_status"] = "verified"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        self._tamper("audit/2026-10-09/evidence/artifact-verification.json", mutate)

    def test_missing_req_commit_exit_one(self):
        partial = self.tmp / "partial"
        shutil.copytree(self.tree, partial, symlinks=True)
        _git_ok(partial, "reset", "-q", "--hard", "HEAD~1")
        out = self.tmp / "partial.json"
        try:
            self.assertEqual(run_tool(partial, out), 1)
        finally:
            shutil.rmtree(partial, ignore_errors=True)


class CommittedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (AUDIT / "evidence" / "acceptance-evidence.json").read_text(encoding="utf-8")
        )

    def test_overall_and_doc(self):
        self.assertEqual(self.report["overall"], {"status": "verified", "problems": []})
        doc = self.report["doc"]
        self.assertEqual(doc["requirements"], 51)
        self.assertEqual(doc["acceptance_criteria"], 195)
        self.assertEqual(doc["type_counts"], {"整改": 37, "补证": 3, "保持": 9, "交付": 2})
        self.assertEqual(doc["model_version"], "1.0")
        self.assertEqual(doc["model_requirements"], 51)
        frozen = doc["frozen_record"]
        self.assertEqual(frozen["requirements"], 51)
        self.assertEqual(frozen["acceptance_criteria"], 195)
        self.assertEqual(frozen["findings_covered"], 19)
        self.assertEqual(frozen["type_counts"], {"整改": 37, "补证": 3, "保持": 9, "交付": 2})
        self.assertTrue(frozen["dependencies_acyclic"])
        self.assertTrue(frozen["audit_sources_unchanged"])

    def test_findings_and_conclusions(self):
        fm = self.report["findings_map"]
        self.assertEqual(fm["table_rows"], 19)
        self.assertEqual(fm["findings_json"], 19)
        self.assertEqual(fm["union_reqs"], "REQ-001..REQ-037")
        self.assertEqual(fm["check_ids_missing"], [])
        self.assertTrue(fm["model_inverted_match"])
        c = self.report["conclusions"]
        self.assertEqual(c["rows"], 11)
        self.assertEqual(len(c["unverified"]), 6)
        self.assertTrue(c["d10_present"])
        self.assertTrue(c["p04_present"])
        labels = {e["label"] for e in c["unverified"]}
        self.assertIn("D10：缺原始来源、PR身份、queue和attempt证据", labels)
        self.assertIn("P04：真实pending取消及运行影响未验证", labels)
        for e in c["unverified"]:
            self.assertTrue(e["reqs"])

    def test_integrity(self):
        integ = self.report["integrity"]
        self.assertEqual(len(integ["source_sha256"]), 7)
        self.assertTrue(all(v["match"] for v in integ["source_sha256"].values()))
        ac = integ["all_checks"]
        self.assertEqual(ac["total"], 238)
        self.assertEqual(ac["counts"], {"passed": 207, "failed": 29, "unverified": 2})
        self.assertEqual(ac["failed_preserved"], 29)
        self.assertEqual(ac["unverified_ids"], ["D10", "P04"])
        self.assertEqual(integ["findings"], 19)
        self.assertTrue(integ["requirements_md_unchanged"])
        self.assertEqual(len(integ["evidence_files"]), 11)
        self.assertTrue(all(v["match"] for v in integ["evidence_files"].values()))
        self.assertTrue(integ["fixture_46"]["ok"])
        ev38 = integ["evidence_files"]["REQ-038"]
        self.assertEqual(ev38["expected"], "unverified")
        self.assertEqual(ev38["actual"], "unverified")

    def test_ledger_and_kinds(self):
        ledger = self.report["ledger"]
        acs = self.report["acceptance_criteria"]
        self.assertEqual(len(ledger), 51)
        self.assertEqual(len(acs), 195)
        statuses = [e["status"] for e in ledger]
        self.assertEqual(
            (statuses.count("通过"), statuses.count("未验证"), statuses.count("失败")),
            (49, 2, 0),
        )
        unverified = [e for e in ledger if e["status"] == "未验证"]
        self.assertEqual([e["req"] for e in unverified], ["REQ-038", "REQ-039"])
        for e in unverified:
            self.assertTrue(e["unverified_reason"])
            self.assertIn("如实保留未验证", e["unverified_reason"])
        for e in ledger:
            for key in (
                "req", "title", "type", "priority", "status", "version",
                "input_kind", "input", "evidence", "unverified_reason",
            ):
                self.assertIn(key, e)
            if e["status"] == "通过":
                self.assertTrue(e["version"])
        self.assertIn("duplicated_req_commits", self.report["ledger_meta"])
        kinds = self.report["kinds"]
        self.assertEqual(kinds["kind_coverage"], ["合成输入", "真实快照", "静态规则"])
        self.assertEqual(kinds["kinds_not_evidenced"], ["真实部署"])
        self.assertFalse(kinds["accuracy_rate_claimed"])
        self.assertTrue(kinds["no_rate_synthesis_rule_present"])
        self.assertEqual(kinds["rate_claim_lines_in_doc"], [])
        self.assertEqual(kinds["rate_claim_lines_in_readme"], [])

    def test_delivery_summary_separates_structure_from_completion(self):
        delivery = self.report["delivery"]
        self.assertEqual(
            (
                delivery["structural_verification"],
                delivery["requirements"],
                delivery["acceptance_criteria"],
                delivery["passed"],
                delivery["unverified"],
                delivery["failed"],
            ),
            ("verified", 51, 195, 49, 2, 0),
        )
        self.assertEqual(delivery["unverified_reqs"], ["REQ-038", "REQ-039"])
        self.assertEqual(delivery["failed_reqs"], [])
        self.assertEqual(delivery["kinds_not_evidenced"], ["真实部署"])


if __name__ == "__main__":
    unittest.main()
