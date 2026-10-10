"""Tests for the prepare/plan step (T-012)."""

import json
import tempfile
import unittest
from pathlib import Path

from monitor.catalog import Catalog
from monitor.plan import build_context, build_matrix, catalog_fingerprint, plan

ROOT = Path(__file__).resolve().parents[1]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.load(ROOT / "catalog.json")

    def test_context_matches_enabled_projects(self):
        context, matrix = plan(
            self.catalog,
            run_id="r-1",
            code_sha="abc",
            cutoff_at="2026-10-09T23:30:00Z",
        )
        self.assertEqual(context["project_ids"], self.catalog.enabled_project_ids())
        self.assertEqual(len(matrix["include"]), len(self.catalog.enabled_project_ids()))
        self.assertEqual(context["cutoff_at"], "2026-10-09T23:30:00Z")

    def test_matrix_covers_every_enabled_repository(self):
        _, matrix = plan(self.catalog, run_id="r-1", code_sha="abc", cutoff_at="2026-10-09T23:30:00Z")
        by_project = {row["project_id"]: set(row["repositories"]) for row in matrix["include"]}
        for project in self.catalog.enabled_projects():
            self.assertEqual(
                by_project[project["project_id"]],
                {r["repository_id"] for r in project["repositories"]},
            )

    def test_disabled_projects_are_excluded_from_matrix(self):
        data = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        data["projects"][1]["enabled"] = False
        catalog = Catalog.from_dict(data)
        _, matrix = plan(catalog, run_id="r-1", code_sha="abc", cutoff_at="2026-10-09T23:30:00Z")
        self.assertEqual([row["project_id"] for row in matrix["include"]], ["ubs"])

    def test_catalog_fingerprint_is_deterministic(self):
        data = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog_fingerprint(data), catalog_fingerprint(json.loads(json.dumps(data))))

    def test_catalog_fingerprint_changes_with_content(self):
        data = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        changed = json.loads(json.dumps(data))
        changed["projects"][0]["display_name"] = "renamed"
        self.assertNotEqual(catalog_fingerprint(data), catalog_fingerprint(changed))

    def test_context_carries_catalog_fingerprint(self):
        context = build_context(self.catalog, run_id="r-1", code_sha="abc", cutoff_at="2026-10-09T23:30:00Z")
        self.assertEqual(context["catalog_sha256"], catalog_fingerprint(self.catalog.data))


class PlanCliTests(unittest.TestCase):
    def test_plan_cli_writes_context_and_matrix(self):
        from monitor.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            ctx = Path(tmp) / "context.json"
            matrix = Path(tmp) / "matrix.json"
            code = main([
                "plan",
                "--catalog", str(ROOT / "catalog.json"),
                "--run-id", "synthetic-20261010-0730-attempt-1",
                "--code-sha", "9aec47355689c243f3f8c35cab40fd275c0e8441",
                "--cutoff", "2026-10-09T23:30:00Z",
                "--context-out", str(ctx),
                "--matrix-out", str(matrix),
            ])
            self.assertEqual(code, 0)
            context = json.loads(ctx.read_text(encoding="utf-8"))
            matrix_data = json.loads(matrix.read_text(encoding="utf-8"))
            self.assertEqual(context["run_id"], "synthetic-20261010-0730-attempt-1")
            self.assertEqual(context["cutoff_at"], "2026-10-09T23:30:00Z")
            self.assertEqual(sorted(row["project_id"] for row in matrix_data["include"]), ["triton", "ubs"])

    def test_plan_cli_rejects_missing_command(self):
        from monitor.__main__ import main
        self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()