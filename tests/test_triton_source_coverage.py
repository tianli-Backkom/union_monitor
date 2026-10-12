"""UDR-004-TC02: Triton full-source enumeration and independent-verification boundary.

The generic source-coverage model applies to Triton workflow/attempt identities:
the applicable denominator closes as verified + differences + missing; a
derived-only sample never upgrades to full-pass; and a historical PR
association without raw evidence stays unverified.
"""
import unittest

from source_coverage import SourceCategory, source_report


def attempt(run_id, n=1):
    return f"run:{run_id}:attempt:{n}"


class TritonSourceCoverageTests(unittest.TestCase):
    def test_five_identities_close_as_verified_difference_missing(self):
        category = SourceCategory("workflow_attempt_enumeration")
        ids = [attempt(i) for i in range(1, 6)]
        for i in ids:
            category.record_applicable(i)
        # 2 raw-verified consistent, 1 difference, 2 without evidence.
        category.record_verified(ids[0])
        category.record_verified(ids[1])
        category.record_difference(ids[2], "raw manifest runs(887) != derived(885)")
        result = category.result()
        self.assertEqual(result["applicable"], 5)
        self.assertEqual((result["verified_consistent"], result["differences"], result["missing_evidence"]),
                         (2, 1, 2))
        # The identity set is closed: every applicable identity lands in one bucket.
        self.assertEqual(result["applicable"],
                         result["verified_consistent"] + result["differences"] + result["missing_evidence"])
        self.assertEqual(result["status"], "differences_found")
        self.assertIn("887", result["difference_details"][0])

    def test_derived_sampling_never_upgrades_to_full_pass(self):
        # A 3-run / 11-job sample is derived-only re-computation, not raw-source
        # verification of the full set.
        category = SourceCategory("sampled_workflow_attempts")
        for run_id in (10, 20, 30):
            for n in (1, 2, 3):
                category.record_applicable(attempt(run_id, n))
        for run_id in (10, 20, 30):
            category.record_derived(attempt(run_id, 1))
            category.record_derived(attempt(run_id, 2))
            category.record_derived(attempt(run_id, 3))
        result = category.result()
        self.assertEqual(result["applicable"], 9)
        self.assertEqual(result["derived_consistent"], 9)
        self.assertEqual(result["verified_consistent"], 0)
        self.assertEqual(result["status"], "unverified")
        report = source_report({"sampled_workflow_attempts": category})
        self.assertEqual(report["status"], "unverified")

    def test_historical_pr_2513_association_stays_unverified(self):
        # The PR #2513 historical association lacks independent raw evidence and
        # must not be claimed verified by the source report.
        category = SourceCategory("pr_association")
        category.record_applicable("PR#2513")
        result = category.result()
        self.assertEqual(result["status"], "unverified")
        self.assertEqual((result["verified_consistent"], result["missing_evidence"]), (0, 1))
        self.assertEqual(result["missing"], ["PR#2513"])

    def test_full_verification_without_differences_is_verified(self):
        category = SourceCategory("workflow_attempt_enumeration")
        for run_id in (1, 2):
            category.record_applicable(attempt(run_id))
            category.record_verified(attempt(run_id))
        self.assertEqual(category.result()["status"], "verified")
        self.assertEqual(source_report({"workflow_attempt_enumeration": category})["status"], "verified")


if __name__ == "__main__":
    unittest.main()