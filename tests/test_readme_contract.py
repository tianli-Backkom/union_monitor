"""Keep the entry point and executable development instructions discoverable."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadmeContractTests(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_public_entry_is_the_merged_site_with_project_routes(self):
        for route in ("#workbench", "#ubs", "#triton"):
            self.assertTrue("https://tianli-backkom.github.io/union_monitor/" + route in self.readme,
                            f"missing public project entry: {route}")
        self.assertNotIn("https://<user>.github.io/<repo>/", self.readme)

    def test_triton_times_match_the_actual_production_cron(self):
        workflow = (ROOT / ".github" / "workflows" / "triton-refresh.yml").read_text(encoding="utf-8")
        cron = re.search(r'cron:\s*"(\d+) ([\d,]+) \* \* \*"', workflow)
        self.assertIsNotNone(cron)
        minute, hours = cron.groups()
        expected = "/".join(f"{(int(hour) + 8) % 24:02}:{int(minute):02}" for hour in hours.split(","))
        self.assertTrue(expected in self.readme, f"README must show the actual increment schedule: {expected}")

    def test_local_pr_checks_include_offline_data_and_real_chromium(self):
        for command in ("python -B scripts/devdata.py --offline",
                        "python -B -m unittest discover -s tests -v",
                        "node --test tests/*.test.cjs", "npm ci --ignore-scripts",
                        "npx playwright install --with-deps chromium", "npm run test:browser"):
            self.assertTrue(command in self.readme, f"missing local PR-gate command: {command}")
        self.assertIn("python -B -m scripts.published_health", self.readme)

    def test_relative_document_and_workflow_links_resolve(self):
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", self.readme)
        for target in links:
            if "://" in target or target.startswith("#"):
                continue
            with self.subTest(target=target):
                self.assertTrue((ROOT / target.split("#", 1)[0]).is_file())

    def test_unified_audit_requirements_are_discoverable(self):
        self.assertIn('docs/requirements/2026-10-12-unified-dashboard-audit-requirements.md', self.readme)
        self.assertIn('规格完整不代表业务验收通过', self.readme)


if __name__ == "__main__":
    unittest.main()
