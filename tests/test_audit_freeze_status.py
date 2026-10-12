"""UDR-001-TC02 / UDR-005-TC02: frozen audit evidence availability is honest.

The 2026-10-11 full enriched Triton evidence (371 records / 93 qualified batches
for UDR-001, and the per-identity 887/885 ledger for UDR-005) is not bundled.
A replay therefore records ``unverified`` instead of skipping the check or
substituting the legacy 66-batch freeze. This test pins that honest behaviour
so a future evidence drop must update the status and the replay together.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "tests" / "fixtures" / "audit-2026-10-11" / "status.json"
LEGACY_FREEZE = ROOT / "tests" / "fixtures" / "triton-audit-freeze.json"


class FrozenEvidenceStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_status_document_is_present_and_declares_unavailable(self):
        self.assertFalse(self.status["frozen_input"]["udr_001"]["available"])
        self.assertFalse(self.status["frozen_input"]["udr_005"]["available"])

    def test_unavailable_udr001_input_reports_unverified_not_passed(self):
        frozen = self.status["frozen_input"]["udr_001"]
        self.assertEqual(frozen["expected_records"], 371)
        self.assertEqual(frozen["expected_qualified_batches"], 93)
        # An unavailable replay must not be presented as a verified pass.
        self.assertIn("not bundled", frozen["note"])

    def test_legacy_66_batch_freeze_is_not_a_substitute(self):
        legacy = json.loads(LEGACY_FREEZE.read_text(encoding="utf-8"))
        # The legacy freeze is a different, smaller input and must never stand in
        # for the 371/93 replay.
        self.assertLess(legacy["summary"]["batches"], 93)
        self.assertIn("must not substitute", self.status["frozen_input"]["udr_001"]["note"])

    def test_udr005_gap_remains_unverified_until_evidence_arrives(self):
        frozen = self.status["frozen_input"]["udr_005"]
        self.assertEqual(frozen["manifest_runs"], 887)
        self.assertEqual(frozen["public_workflow_attempts"], 885)
        self.assertIn("unverified", frozen["note"])


if __name__ == "__main__":
    unittest.main()