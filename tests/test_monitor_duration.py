"""Contract tests for duration validity, percentile and display (T-009, P-009)."""

import math
import unittest

from monitor.duration import (
    format_minutes,
    format_observed,
    percentile_inc,
    seconds_to_ms,
    valid_duration,
)


class DurationValidityTests(unittest.TestCase):
    def test_finite_non_negative_numbers_are_valid(self):
        self.assertTrue(valid_duration(0))
        self.assertTrue(valid_duration(0.0))
        self.assertTrue(valid_duration(123.45))

    def test_real_zero_is_valid_and_distinct_from_unknown(self):
        self.assertTrue(valid_duration(0))
        self.assertFalse(valid_duration(None))

    def test_missing_and_unparseable_are_invalid(self):
        self.assertFalse(valid_duration(None))
        self.assertFalse(valid_duration("1200"))
        self.assertFalse(valid_duration([1, 2]))

    def test_bool_is_not_a_duration(self):
        self.assertFalse(valid_duration(True))
        self.assertFalse(valid_duration(False))

    def test_nan_infinity_and_negative_are_invalid(self):
        self.assertFalse(valid_duration(float("nan")))
        self.assertFalse(valid_duration(float("inf")))
        self.assertFalse(valid_duration(-1))


class UnitConversionTests(unittest.TestCase):
    def test_seconds_to_ms_is_exact(self):
        self.assertEqual(seconds_to_ms(1), 1000.0)
        self.assertEqual(seconds_to_ms(0.6), 600.0)

    def test_seconds_to_ms_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            seconds_to_ms("1")
        with self.assertRaises(ValueError):
            seconds_to_ms(True)


class PercentileTests(unittest.TestCase):
    def test_percentile_inc_linear_interpolation(self):
        self.assertEqual(percentile_inc([100, 200, 300], 0.9), 280.0)

    def test_empty_values_yield_none_not_zero(self):
        self.assertIsNone(percentile_inc([]))
        self.assertIsNone(percentile_inc([None, float("nan"), -1]))

    def test_single_sample_is_the_sample(self):
        self.assertEqual(percentile_inc([42], 0.9), 42.0)

    def test_real_zero_is_a_valid_sample(self):
        self.assertEqual(percentile_inc([0], 0.9), 0.0)


class FormattingTests(unittest.TestCase):
    def test_unknown_is_em_dash(self):
        self.assertEqual(format_minutes(None), "—")
        self.assertEqual(format_minutes(float("nan")), "—")
        self.assertEqual(format_minutes(-5), "—")

    def test_real_zero_renders_two_decimals(self):
        self.assertEqual(format_minutes(0), "0.00 min")

    def test_sub_centiminute_renders_less_than(self):
        self.assertEqual(format_minutes(599), "<0.01 min")
        self.assertEqual(format_minutes(1), "<0.01 min")

    def test_normal_value_renders_two_decimals_minutes(self):
        self.assertEqual(format_minutes(600), "0.01 min")
        self.assertEqual(format_minutes(60_000), "1.00 min")
        self.assertEqual(format_minutes(14 * 60_000), "14.00 min")

    def test_formatting_does_not_change_the_input(self):
        value = 599.5
        format_minutes(value)
        self.assertEqual(value, 599.5)


class ObservedFormattingTests(unittest.TestCase):
    def test_observed_is_not_a_terminal_value(self):
        self.assertEqual(format_observed(8.2 * 60_000, "2026-10-09T23:30:00Z"), "已观测 8.20 min · 截至 2026-10-09T23:30:00Z")

    def test_observed_without_as_of(self):
        self.assertEqual(format_observed(8.2 * 60_000), "已观测 8.20 min")


class Udr006BoundaryValueTests(unittest.TestCase):
    """UDR-006-TC02: named boundary values and legal-extreme retention.

    Legal zero stays zero, sub-centiminute values collapse to ``<0.01``,
    ``null``/inverted values are unknown (never zero), and a proven ~21.68-day
    UBS sample is retained rather than deleted for being "too long".
    """

    DAY_MS = 24 * 3600 * 1000
    EXTREME_MS = int(21.68 * DAY_MS)  # ≈ 21.68-day observed UBS sample

    def test_named_values_round_trip_without_mutation(self):
        self.assertTrue(valid_duration(0))
        self.assertTrue(valid_duration(100))    # 100 ms is valid, renders sub-centiminute
        self.assertTrue(valid_duration(600))    # 600 ms is valid
        self.assertFalse(valid_duration(None))
        self.assertEqual(format_minutes(0), "0.00 min")
        self.assertEqual(format_minutes(100), "<0.01 min")
        self.assertEqual(format_minutes(600), "0.01 min")
        self.assertEqual(format_minutes(None), "—")

    def test_legal_extreme_duration_is_retained_not_deleted_as_outlier(self):
        self.assertTrue(valid_duration(self.EXTREME_MS))
        self.assertEqual(format_minutes(self.EXTREME_MS), "31219.20 min")

    def test_queue_inversion_negative_is_unknown_not_a_valid_value(self):
        self.assertFalse(valid_duration(-600))   # inverted start/end -> unknown
        self.assertEqual(format_minutes(-600), "—")

    def test_display_does_not_mutate_the_source_value(self):
        value = self.EXTREME_MS
        format_minutes(value)
        self.assertEqual(value, self.EXTREME_MS)


if __name__ == "__main__":
    unittest.main()