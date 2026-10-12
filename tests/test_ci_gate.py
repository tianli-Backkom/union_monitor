"""The required PR result must fail closed when a prerequisite did not pass."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_gate.py"
REQUIRED = {"python-tests", "frontend-tests", "collector-contracts", "workflow-lint"}


class RequiredGateTests(unittest.TestCase):
    def run_gate(self, results):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--results", json.dumps(results)],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_every_required_job_must_have_succeeded(self):
        result = self.run_gate({job: {"result": "success"} for job in REQUIRED})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failure_cancel_and_skip_never_become_green(self):
        for outcome in ("failure", "cancelled", "skipped", None):
            with self.subTest(outcome=outcome):
                results = {job: {"result": "success"} for job in REQUIRED}
                results["collector-contracts"]["result"] = outcome
                result = self.run_gate(results)
                self.assertEqual(result.returncode, 1)
                self.assertIn("collector-contracts", result.stdout + result.stderr)

    def test_missing_or_unexpected_job_is_not_an_acceptable_gate(self):
        results = {job: {"result": "success"} for job in REQUIRED}
        del results["workflow-lint"]
        self.assertEqual(self.run_gate(results).returncode, 1)
        results["replacement"] = {"result": "success"}
        self.assertEqual(self.run_gate(results).returncode, 1)

    def test_bad_json_is_an_explicit_failed_check(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--results", "{"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("JSON", result.stdout + result.stderr)


class PullRequestWorkflowTests(unittest.TestCase):
    def test_gate_covers_every_pr_and_runs_after_failed_dependencies(self):
        workflow = ROOT / ".github" / "workflows" / "pr-gate.yml"
        self.assertTrue(workflow.is_file())
        text = workflow.read_text("utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("merge_group:", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertNotIn("paths-ignore:", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("continue-on-error:", text)
        self.assertIn("contents: read", text)
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("name: Dashboard quality gate", text)
        self.assertIn("if: ${{ always() }}", text)
        self.assertIn("toJSON(needs)", text)
        self.assertIn("python scripts/ci_gate.py", text)
        for job in REQUIRED:
            self.assertIn(job + ":", text)


if __name__ == "__main__":
    unittest.main()
