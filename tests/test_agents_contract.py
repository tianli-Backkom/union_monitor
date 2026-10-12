"""Keep the mandated GitHub submission workflow discoverable in AGENTS.md."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentsContractTests(unittest.TestCase):
    def setUp(self):
        self.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def test_gate_and_pull_request_workflow_are_mandated(self):
        self.assertIn("Dashboard quality gate", self.agents)
        self.assertIn("required_status_checks", self.agents)
        self.assertIn("required_pull_request_reviews", self.agents)
        self.assertIn("Pull Request", self.agents)

    def test_direct_main_push_and_protection_bypass_are_prohibited(self):
        self.assertIn("严禁移除或绕过 `main` 分支保护", self.agents)
        self.assertIn("不得直接推送到 `main`", self.agents)
        self.assertIn("门禁失败（红色）时", self.agents)
        self.assertIn("远端与本地只保留 `main` 一个分支", self.agents)


if __name__ == "__main__":
    unittest.main()