"""UDR-038-TC02: per-AC acceptance ledger — structure, honesty and evidence.

The committed ledger maps every UDR to its implementation status and the real
test file(s) that evidence it. A ``verified``/``implemented`` entry must name a
file that actually exists in the repository; a browser-gated entry must be
marked unverified and reference the blocker instead of claiming a pass. Missing
evidence is a structural failure, never a silent pass.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "audit" / "2026-10-12" / "udr-implementation-ledger.json"

IMPLEMENTED = {"已实现", "回归保持", "部分实现"}
UNVERIFIED_PREFIXES = ("未实现",)


class LedgerStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.requirements = cls.doc["requirements"]

    def test_38_requirements_complete_and_unique(self):
        ids = [r["id"] for r in self.requirements]
        self.assertEqual(ids, [f"UDR-{n:03d}" for n in range(1, 39)])
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_entry_has_status_evidence_and_note(self):
        for entry in self.requirements:
            with self.subTest(req=entry["id"]):
                self.assertIn(entry["status"],
                              {"已实现", "回归保持", "部分实现", "未实现-待浏览器验证"})
                self.assertIsInstance(entry["evidence"], list)
                self.assertTrue(entry["evidence"])
                self.assertTrue(entry["note"].strip())

    def test_policy_declares_browser_blocker(self):
        self.assertIn("ETIMEDOUT", self.doc["browser_blocker"])
        self.assertIn("@playwright/test", self.doc["browser_blocker"])
        self.assertIn("Chromium", self.doc["browser_blocker"])
        self.assertIn("unverified", self.doc["policy"])


class LedgerHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.requirements = cls.doc["requirements"]

    def test_implemented_entries_name_real_test_files(self):
        for entry in self.requirements:
            if entry["status"] in IMPLEMENTED:
                for rel in entry["evidence"]:
                    with self.subTest(req=entry["id"], file=rel):
                        self.assertTrue((ROOT / rel).is_file(), f"{rel} missing for {entry['id']}")

    def test_browser_gated_entries_are_honestly_unverified(self):
        browser_gated = [r for r in self.requirements
                         if r["status"] not in IMPLEMENTED]
        self.assertTrue(browser_gated)
        for entry in browser_gated:
            self.assertTrue(entry["status"].startswith("未实现"))
            self.assertIn("待浏览器验证", entry["status"])

    def test_all_new_release_modules_are_claimed_implemented_with_tests(self):
        implemented = {r["id"] for r in self.requirements if r["status"] == "已实现"}
        for module in ("UDR-024", "UDR-025", "UDR-026", "UDR-027", "UDR-028",
                       "UDR-029", "UDR-030", "UDR-031", "UDR-034"):
            self.assertIn(module, implemented, module)

    def test_udr005_and_udr001_frozen_evidence_stay_honest(self):
        by_id = {r["id"]: r for r in self.requirements}
        self.assertEqual(by_id["UDR-005"]["status"], "已实现")
        self.assertIn("887/885", by_id["UDR-005"]["note"])
        self.assertEqual(by_id["UDR-001"]["status"], "部分实现")
        self.assertIn("371/93", by_id["UDR-001"]["note"])


if __name__ == "__main__":
    unittest.main()