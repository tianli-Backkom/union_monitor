"""Contract tests for the project catalog (T-002, AC-002)."""

import json
import unittest
from pathlib import Path

from monitor.catalog import Catalog, CatalogError

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog.json"


def valid_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


class CatalogLoadingTests(unittest.TestCase):
    def test_shipped_catalog_loads_and_validates(self):
        catalog = Catalog.load(CATALOG_PATH)
        self.assertEqual(catalog.enabled_project_ids(), ["ubs", "triton"])

    def test_catalog_rejects_wrong_schema_version(self):
        data = valid_catalog()
        data["schema_version"] = 999
        with self.assertRaises(CatalogError):
            Catalog.from_dict(data)


class CatalogProjectReferencingTests(unittest.TestCase):
    def test_every_project_references_known_profiles(self):
        catalog = Catalog.load(CATALOG_PATH)
        for project in catalog.projects:
            self.assertIn(project["collector"], catalog.data["collectors"])
            self.assertIn(project["metric_profile"], catalog.data["metric_profiles"])
            self.assertIn(project["view_profile"], catalog.data["view_profiles"])

    def test_repository_ids_are_unique_within_a_project(self):
        catalog = Catalog.load(CATALOG_PATH)
        for project in catalog.projects:
            ids = [r["repository_id"] for r in project["repositories"]]
            self.assertEqual(len(ids), len(set(ids)), project["project_id"])

    def test_repository_ids_reference_known_source_instances(self):
        catalog = Catalog.load(CATALOG_PATH)
        for project in catalog.projects:
            for repo in project["repositories"]:
                instance = repo["repository_id"].split(":", 1)[0]
                self.assertIn(instance, catalog.data["source_instances"])

    def test_project_ids_are_unique(self):
        ids = [p["project_id"] for p in valid_catalog()["projects"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_source_instances_have_https_and_unique_base_urls(self):
        catalog = Catalog.load(CATALOG_PATH)
        instances = catalog.data["source_instances"]
        self.assertEqual(len(instances), len({v["base_url"] for v in instances.values()}))
        for value in instances.values():
            self.assertTrue(value["base_url"].startswith("https://"), value)
            self.assertTrue(value["provider"], value)


class CatalogValidationBehaviorTests(unittest.TestCase):
    def _minus(self, mutate):
        data = valid_catalog()
        mutate(data)
        return data

    def test_missing_target_branches_is_rejected(self):
        def mutate(data):
            data["projects"][0]["repositories"][0]["target_branches"] = []
        with self.assertRaises(CatalogError):
            Catalog.from_dict(self._minus(mutate))

    def test_project_without_repositories_is_rejected(self):
        def mutate(data):
            data["projects"][1]["repositories"] = []
        with self.assertRaises(CatalogError):
            Catalog.from_dict(self._minus(mutate))

    def test_unknown_project_id_raises(self):
        catalog = Catalog.load(CATALOG_PATH)
        with self.assertRaises(CatalogError):
            catalog.project("nope")

    def test_unknown_source_instance_raises(self):
        catalog = Catalog.load(CATALOG_PATH)
        with self.assertRaises(CatalogError):
            catalog.source_instance("nope")

    def test_duplicate_base_url_is_rejected(self):
        def mutate(data):
            data["source_instances"]["github"]["base_url"] = data["source_instances"]["gitcode"]["base_url"]
        with self.assertRaises(CatalogError):
            Catalog.from_dict(self._minus(mutate))


if __name__ == "__main__":
    unittest.main()