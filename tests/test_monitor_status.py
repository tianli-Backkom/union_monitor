"""Contract tests for the three independent status axes (T-008, P-008)."""

import unittest

from monitor.status import (
    Axes,
    Eligibility,
    Evidence,
    Execution,
    eligibility_for,
    is_terminal,
    normalize_execution_result,
)


class ExecutionNormalizationTests(unittest.TestCase):
    def test_clear_tokens_map_to_shared_vocabulary(self):
        self.assertEqual(normalize_execution_result("SUCCESS"), "success")
        self.assertEqual(normalize_execution_result("Failed"), "failure")
        self.assertEqual(normalize_execution_result("in_progress"), "running")
        self.assertEqual(normalize_execution_result("ABORTED"), "cancelled")

    def test_cancelled_is_never_rewritten_to_failure(self):
        self.assertEqual(normalize_execution_result("ABORTED"), "cancelled")
        self.assertEqual(normalize_execution_result("NOT_BUILT"), "cancelled")
        self.assertNotEqual(normalize_execution_result("ABORTED"), "failure")

    def test_unknown_tokens_and_none_become_unknown(self):
        self.assertEqual(normalize_execution_result(None), "unknown")
        self.assertEqual(normalize_execution_result("weird-token"), "unknown")

    def test_terminal_results_are_success_failure_cancelled(self):
        self.assertTrue(is_terminal("success"))
        self.assertTrue(is_terminal("failure"))
        self.assertTrue(is_terminal("cancelled"))
        self.assertFalse(is_terminal("running"))
        self.assertFalse(is_terminal("unknown"))


class AxisIndependenceTests(unittest.TestCase):
    def test_success_can_coexist_with_an_evidence_gap(self):
        axes = Axes(
            execution=Execution("success"),
            evidence=Evidence("missing", issues=("no terminal end evidence",)),
            eligibility={"e2e": eligibility_for("e2e", False, "no terminal end")},
        )
        self.assertEqual(axes.execution.result, "success")
        self.assertEqual(axes.evidence.state, "missing")
        self.assertEqual(axes.eligibility["e2e"].state, "excluded")

    def test_running_is_not_a_data_quality_failure(self):
        axes = Axes(
            execution=Execution("running"),
            evidence=Evidence("verified"),
            eligibility={},
        )
        self.assertEqual(axes.execution.result, "running")
        self.assertEqual(axes.evidence.state, "verified")

    def test_one_excluded_metric_does_not_drop_others(self):
        axes = Axes(
            execution=Execution("failure"),
            evidence=Evidence("verified"),
            eligibility={
                "e2e": eligibility_for("e2e", True),
                "queue": eligibility_for("queue", False, "queue item missing"),
                "total": eligibility_for("total", None),
            },
        )
        self.assertEqual(axes.eligibility["e2e"].state, "included")
        self.assertEqual(axes.eligibility["queue"].state, "excluded")
        self.assertEqual(axes.eligibility["total"].state, "unknown")

    def test_setting_one_axis_does_not_touch_another(self):
        axes = Axes(execution=Execution("cancelled"), evidence=Evidence("verified"))
        axes.execution = Execution("failure")
        self.assertEqual(axes.evidence.state, "verified")


class ValidationTests(unittest.TestCase):
    def test_invalid_enums_are_rejected(self):
        with self.assertRaises(ValueError):
            Execution("exploded")
        with self.assertRaises(ValueError):
            Evidence("fantasy")
        with self.assertRaises(ValueError):
            Eligibility("e2e", "maybe")

    def test_eligibility_requires_a_metric_name(self):
        with self.assertRaises(ValueError):
            Eligibility("", "included")


if __name__ == "__main__":
    unittest.main()