"""Contract tests for stable ordering and pagination (T-006, P-006)."""

import unittest

from monitor.ordering import paginate, stable_sort


class StableSortTests(unittest.TestCase):
    def test_descending_puts_largest_first(self):
        rows = [{"id": "a", "v": 1}, {"id": "b", "v": 3}, {"id": "c", "v": 2}]
        out = stable_sort(rows, key=lambda r: r["v"], reverse=True)
        self.assertEqual([r["id"] for r in out], ["b", "c", "a"])

    def test_missing_values_always_sort_last_even_descending(self):
        rows = [{"id": "a", "v": 3}, {"id": "b", "v": None}, {"id": "c", "v": 1}]
        out = stable_sort(rows, key=lambda r: r["v"], reverse=True)
        self.assertEqual([r["id"] for r in out], ["a", "c", "b"])

    def test_real_zero_is_a_valid_value_not_missing(self):
        rows = [{"id": "a", "v": 0}, {"id": "b", "v": None}, {"id": "c", "v": 5}]
        out = stable_sort(rows, key=lambda r: r["v"], reverse=True)
        self.assertEqual([r["id"] for r in out], ["c", "a", "b"])

    def test_ties_break_by_stable_identity(self):
        rows = [{"id": "b", "v": 2}, {"id": "a", "v": 2}, {"id": "c", "v": 2}]
        out = stable_sort(rows, key=lambda r: r["v"], reverse=True, identity=lambda r: r["id"])
        self.assertEqual([r["id"] for r in out], ["a", "b", "c"])

    def test_input_is_not_mutated(self):
        rows = [{"id": "a", "v": 3}, {"id": "b", "v": 1}]
        stable_sort(rows, key=lambda r: r["v"], reverse=True)
        self.assertEqual([r["id"] for r in rows], ["a", "b"])


class PaginationTests(unittest.TestCase):
    def test_empty_list(self):
        result = paginate([], 1)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["pages"], 0)

    def test_page_slicing_defaults_to_15(self):
        rows = list(range(20))
        result = paginate(rows, 1)
        self.assertEqual(result["items"], list(range(15)))
        self.assertEqual(result["start"], 1)
        self.assertEqual(result["end"], 15)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["total"], 20)

    def test_last_page_is_short(self):
        rows = list(range(20))
        result = paginate(rows, 2)
        self.assertEqual(result["items"], list(range(15, 20)))
        self.assertEqual(result["start"], 16)
        self.assertEqual(result["end"], 20)

    def test_page_is_clamped(self):
        rows = list(range(20))
        self.assertEqual(paginate(rows, 99)["page"], 2)
        self.assertEqual(paginate(rows, 0)["page"], 1)

    def test_alternate_page_sizes(self):
        rows = list(range(31))
        self.assertEqual(paginate(rows, 1, page_size=30)["pages"], 2)
        self.assertEqual(paginate(rows, 2, page_size=30)["items"], [30])

    def test_pages_partition_the_sequence_exactly_once(self):
        rows = list(range(31))
        seen = []
        for page in range(1, 4):
            seen.extend(paginate(rows, page, page_size=15)["items"])
        self.assertEqual(seen, rows)
        self.assertEqual(len(seen), len(set(seen)))

    def test_negative_page_size_is_rejected(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 1, page_size=0)


if __name__ == "__main__":
    unittest.main()