"""UDR-005: collection-to-public counting ledger (原始/唯一/公开/窗外/其他).

The ledger separates the raw returned row count, the unique (run_id, attempt)
identities, and the public workflow/attempt, out-of-window and other-exclusion
buckets. Every excluded identity must carry a traceable reason, tampering with
that reason is detected and named, and an unexplained gap stays unverified
instead of being guessed as "two missing" or "two legal exclusions".
"""
import unittest

from triton.coverage_ledger import (PUBLIC, OUT_OF_WINDOW, OTHER, UNACCOUNTED,
                                    build_ledger, verify_ledger)


def row(run_id, attempt=1):
    return {"id": run_id, "run_attempt": attempt}


class CoverageLedgerTests(unittest.TestCase):
    def _four_rows(self):
        # 4 raw rows: run 1 appears twice (duplicate), runs 2 and 3 once each.
        return [row(1), row(2), row(1), row(3)]

    def test_tc01_raw_unique_public_out_of_window_balance(self):
        ledger = build_ledger(
            self._four_rows(),
            public=[(1, 1), (2, 1)],
            out_of_window={(3, 1): "batch start before display window"},
        )
        self.assertEqual(ledger["raw_count"], 4)
        self.assertEqual(ledger["unique_count"], 3)
        self.assertEqual(ledger["duplicate_count"], 1)
        self.assertEqual(ledger["public_count"], 2)
        self.assertEqual(ledger["out_of_window_count"], 1)
        self.assertEqual(ledger["other_count"], 0)
        self.assertEqual(ledger["unaccounted_count"], 0)
        self.assertTrue(ledger["balanced"])
        self.assertTrue(ledger["verified"])
        # 4 = 3 + 1 and 3 = 2 + 1 + 0: mutually exclusive and complete.
        self.assertEqual(ledger["raw_count"], ledger["unique_count"] + ledger["duplicate_count"])
        self.assertEqual(ledger["unique_count"],
                         ledger["public_count"] + ledger["out_of_window_count"] + ledger["other_count"])
        self.assertEqual(verify_ledger(ledger), [])

    def test_tc01_entries_are_mutually_exclusive_and_documented(self):
        ledger = build_ledger(
            self._four_rows(),
            public=[(1, 1), (2, 1)],
            out_of_window={(3, 1): "batch start before display window"},
        )
        by_identity = {(e["run_id"], e["attempt"]): e for e in ledger["entries"]}
        self.assertEqual(by_identity[(1, 1)]["classification"], PUBLIC)
        self.assertIsNone(by_identity[(1, 1)]["reason"])
        self.assertEqual(by_identity[(3, 1)]["classification"], OUT_OF_WINDOW)
        self.assertEqual(by_identity[(3, 1)]["reason"], "batch start before display window")
        # Each unique identity appears exactly once across all buckets.
        classes = [e["classification"] for e in ledger["entries"]]
        self.assertEqual(sorted(classes), [OUT_OF_WINDOW, PUBLIC, PUBLIC])

    def test_tc01_deleting_an_exclusion_reason_is_named(self):
        ledger = build_ledger(
            self._four_rows(),
            public=[(1, 1), (2, 1)],
            out_of_window={(3, 1): "batch start before display window"},
        )
        for entry in ledger["entries"]:
            if entry["classification"] == OUT_OF_WINDOW:
                entry["reason"] = None
        problems = verify_ledger(ledger)
        self.assertTrue(any("run 3 attempt 1" in p and "reason" in p for p in problems), problems)

    def test_tc01_forging_an_exclusion_reason_is_named(self):
        ledger = build_ledger(
            self._four_rows(),
            public=[(1, 1), (2, 1)],
            out_of_window={(3, 1): "batch start before display window"},
        )
        # Forge: reclassify the out-of-window identity into `other` without it
        # being balanced — the out_of_window_count now disagrees with entries.
        for entry in ledger["entries"]:
            if entry["classification"] == OUT_OF_WINDOW:
                entry["classification"] = OTHER
                entry["reason"] = "forged reason"
        problems = verify_ledger(ledger)
        self.assertTrue(any("out_of_window_count" in p for p in problems), problems)
        self.assertTrue(any("other_count" in p for p in problems), problems)

    def test_overlapping_classification_is_rejected(self):
        with self.assertRaises(ValueError):
            build_ledger(
                self._four_rows(),
                public=[(1, 1), (2, 1)],
                out_of_window={(2, 1): "cannot be public and out-of-window"},
            )

    def test_unaccounted_identity_keeps_ledger_unverified_not_guessed(self):
        ledger = build_ledger(self._four_rows(), public=[(1, 1), (2, 1)])
        # Run 3 is absent from public/out_of_window/other -> unaccounted.
        self.assertEqual(ledger["unaccounted_count"], 1)
        self.assertEqual(ledger["balanced"], False)
        self.assertEqual(ledger["verified"], False)
        entry = next(e for e in ledger["entries"] if e["classification"] == UNACCOUNTED)
        self.assertEqual((entry["run_id"], entry["attempt"]), (3, 1))
        # No exclusion reason was invented for the gap.
        self.assertIsNone(entry["reason"])


class ManifestRunsLedgerTests(unittest.TestCase):
    """UDR-005-TC02: the 2026-10-11 manifest runs=887 vs public 885 gap.

    The full per-identity enriched evidence is not bundled here, so the ledger
    must keep the 2 unexplained identities ``unaccounted`` rather than guessing
    them as "two missing" or "two legal exclusions".
    """

    MANIFEST_RUNS = 887
    PUBLIC_WORKFLOW_ATTEMPTS = 885

    def test_missing_evidence_stays_unverified_not_hardcoded_difference(self):
        rows = [row(i) for i in range(1, self.MANIFEST_RUNS + 1)]
        public = [(i, 1) for i in range(1, self.PUBLIC_WORKFLOW_ATTEMPTS + 1)]
        ledger = build_ledger(rows, public=public)
        self.assertEqual(ledger["unique_count"], self.MANIFEST_RUNS)
        self.assertEqual(ledger["public_count"], self.PUBLIC_WORKFLOW_ATTEMPTS)
        self.assertEqual(ledger["unaccounted_count"], self.MANIFEST_RUNS - self.PUBLIC_WORKFLOW_ATTEMPTS)
        self.assertEqual(ledger["out_of_window_count"], 0)
        self.assertEqual(ledger["other_count"], 0)
        self.assertFalse(ledger["balanced"])
        self.assertFalse(ledger["verified"])
        # The gap is not hardcoded to a reason and the structure is internally honest.
        self.assertEqual(verify_ledger(ledger), [])

    def test_full_evidence_replay_closes_the_gap_with_reasons(self):
        # When per-identity evidence arrives, the same ledger becomes complete.
        gap = self.MANIFEST_RUNS - self.PUBLIC_WORKFLOW_ATTEMPTS
        rows = [row(i) for i in range(1, self.MANIFEST_RUNS + 1)]
        public = [(i, 1) for i in range(1, self.PUBLIC_WORKFLOW_ATTEMPTS + 1)]
        out_of_window = {(i, 1): "attempt started before the display window"
                         for i in range(self.PUBLIC_WORKFLOW_ATTEMPTS + 1, self.MANIFEST_RUNS + 1)}
        ledger = build_ledger(rows, public=public, out_of_window=out_of_window)
        self.assertEqual(ledger["unaccounted_count"], 0)
        self.assertEqual(ledger["out_of_window_count"], gap)
        self.assertTrue(ledger["balanced"])
        self.assertTrue(ledger["verified"])
        self.assertEqual(verify_ledger(ledger), [])


if __name__ == "__main__":
    unittest.main()