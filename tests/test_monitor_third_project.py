"""P-015: a third project joins by configuration only — no hardcoded branches."""

import copy
import json
import unittest
from pathlib import Path

from monitor.catalog import Catalog
from monitor.plan import build_matrix, plan

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


def third_project_catalog():
    data = copy.deepcopy(BASE)
    data["projects"].append(
        {
            "project_id": "acme",
            "display_name": "Acme CI",
            "enabled": True,
            "collector": "github-actions-v1",
            "metric_profile": "triton-commit-attempt-v1",
            "view_profile": "commit-attempt-v1",
            "window": {"time_basis": "batch_started_at", "hours": 96},
            "timeout_minutes": 45,
            "repositories": [
                {"repository_id": "github:acme/eng-dashboard", "target_branches": ["main"]}
            ],
        }
    )
    return data


class ThirdProjectCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.from_dict(third_project_catalog())

    def test_catalog_accepts_third_project(self):
        self.assertEqual(self.catalog.enabled_project_ids(), ["ubs", "triton", "acme"])
        self.assertEqual(self.catalog.repository_ids("acme"), ["github:acme/eng-dashboard"])

    def test_matrix_covers_third_project(self):
        matrix = build_matrix(self.catalog)
        self.assertEqual([e["project_id"] for e in matrix["include"]], ["ubs", "triton", "acme"])
        self.assertEqual(matrix["include"][2]["repositories"], ["github:acme/eng-dashboard"])
        self.assertEqual(matrix["include"][2]["timeout_minutes"], 45)

    def test_plan_freezes_context_for_all_three(self):
        context, matrix = plan(
            self.catalog,
            run_id="run-third",
            code_sha="0" * 40,
            cutoff_at="2026-10-10T00:00:00Z",
        )
        self.assertEqual(context["project_ids"], ["ubs", "triton", "acme"])
        self.assertEqual(len(matrix["include"]), 3)


if __name__ == "__main__":
    unittest.main()