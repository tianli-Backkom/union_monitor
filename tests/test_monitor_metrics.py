"""P-016: versioned metric definitions and structural completeness tests."""

import unittest

from monitor import metrics as m


class ProfileRegistryTests(unittest.TestCase):
    def test_both_catalog_profiles_have_definitions(self):
        self.assertEqual(
            set(m.profile_ids()),
            {"ubs-pr-representative-v1", "triton-commit-attempt-v1"},
        )

    def test_metrics_documentation_has_no_gaps(self):
        for profile_id in m.profile_ids():
            self.assertEqual(m.validate_profile(profile_id), [], profile_id)

    def test_every_metric_has_the_required_contract_fields(self):
        for profile_id in m.profile_ids():
            for metric in m.profile_metrics(profile_id):
                for field in m.REQUIRED_FIELDS:
                    self.assertTrue(metric.get(field), f"{profile_id}/{metric['name']} missing {field}")

    def test_documentation_renders_without_data(self):
        doc = m.describe_profile("ubs-pr-representative-v1")
        self.assertEqual(doc["profile_id"], "ubs-pr-representative-v1")
        self.assertEqual(doc["schema_version"], 1)
        self.assertTrue(doc["metrics"])

    def test_unknown_profile_is_a_clear_error(self):
        with self.assertRaises(KeyError):
            m.profile_metrics("nope")
        with self.assertRaises(KeyError):
            m.describe_profile("nope")
        self.assertEqual(m.validate_profile("nope"), ["unknown metric profile 'nope'"])