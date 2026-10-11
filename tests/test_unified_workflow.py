"""T-012: the unified shadow workflow keeps the legacy Pages deploy untouched.

The shadow run exercises ``python -m monitor plan/collect/assemble`` and uploads
comparable artifacts. It must NOT schedule itself daily (phase 2), must NOT
deploy to GitHub Pages, and must always reach assemble when prepare/checks are
clean even if a project collection failed.
"""

import re
import unittest
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML unavailable; fall back to text checks
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "unified-shadow.yml"


class UnifiedShadowWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_yaml_is_parseable_when_pyyaml_present(self):
        if yaml is None:
            self.skipTest("PyYAML not available")
        parsed = yaml.safe_load(self.workflow)
        self.assertIn("jobs", parsed)
        self.assertEqual(set(parsed["jobs"]), {"prepare", "checks", "collect", "assemble"})

    def test_shadow_is_manual_only_and_does_not_deploy_pages(self):
        self.assertRegex(self.workflow, r"(?m)^\s{2}workflow_dispatch:\s*$")
        self.assertNotIn("schedule:", self.workflow)
        self.assertNotIn("actions/deploy-pages", self.workflow)
        self.assertNotIn("actions/upload-pages-artifact", self.workflow)
        self.assertNotIn("configure-pages", self.workflow)

    def test_concurrency_group_is_the_shadow_not_production(self):
        self.assertRegex(self.workflow, r"(?ms)^concurrency:\s*\n\s+group: unified-dashboard-shadow\s*\n\s+cancel-in-progress: false")
        self.assertNotIn("unified-dashboard-production", self.workflow)

    def test_job_order_and_gates(self):
        self.assertRegex(self.workflow, r"(?m)^\s{2}collect:\s*\n\s{4}needs: \[prepare, checks\]")
        self.assertRegex(self.workflow, r"(?m)^\s{2}assemble:\s*\n\s{4}needs: \[prepare, checks, collect\]")
        self.assertIn("always() && !cancelled()", self.workflow)
        self.assertIn("needs.prepare.result == 'success'", self.workflow)
        self.assertIn("needs.checks.result == 'success'", self.workflow)

    def test_dynamic_matrix_parallelism_and_no_fast_fail(self):
        self.assertRegex(self.workflow, r"matrix: \${{ fromJSON\(needs\.prepare\.outputs\.matrix\) }}")
        self.assertIn("fail-fast: false", self.workflow)
        self.assertIn("max-parallel: 2", self.workflow)
        self.assertIn("timeout-minutes: ${{ matrix.timeout_minutes }}", self.workflow)

    def test_cli_stages_are_wired(self):
        for command in (
            "python -m monitor plan --catalog catalog.json",
            "python -m monitor collect \\",
            "python -m monitor assemble \\",
            "--report-out .shadow/work/${{ matrix.project_id }}/collection-report.json",
        ):
            self.assertIn(command, self.workflow)

    def test_collect_and_assemble_failures_are_not_mask_happy(self):
        # Project bundle upload and candidate upload run even on collect failure.
        self.assertRegex(self.workflow, r"(?ms)- name: Upload project bundle\s*\n\s+if: always\(\)")
        self.assertRegex(self.workflow, r"(?ms)- name: Upload candidate release\s*\n\s+if: always\(\)")
        self.assertNotIn("continue-on-error", self.workflow)

    def test_download_keeps_project_directories_and_checks_real_artifacts(self):
        self.assertNotIn('merge-multiple: true', self.workflow)
        self.assertIn('load_project_reports', self.workflow)
        self.assertNotIn("reports[rep.get('project_id')] = rep", self.workflow)

    def test_manual_shadow_declares_authenticated_collector_with_fallback(self):
        self.assertIn('GH_TOKEN: ${{ secrets.GH_TOKEN || github.token }}', self.workflow)

    def test_artifacts_are_scoped_to_attempt_for_safe_reruns(self):
        artifact_lines = [line for line in self.workflow.splitlines()
                          if ('name:' in line or 'pattern:' in line)
                          and any(prefix in line for prefix in ('shadow-context-', 'project-bundle-', 'shadow-candidate-'))]
        self.assertTrue(artifact_lines)
        for line in artifact_lines:
            self.assertIn('${{ github.run_attempt }}', line, 'reruns must not collide with or download earlier-attempt artifacts')


if __name__ == "__main__":
    unittest.main()
