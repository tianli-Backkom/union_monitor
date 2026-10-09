import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "triton-refresh.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"

FALLBACK_URL = "https://tianli-backkom.github.io/ubs_core_monitor"


class TritonWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.pages = PAGES_WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_matches_beijing_refresh_slots(self):
        self.assertRegex(self.workflow, r"(?m)^\s{4}- cron: ['\"]0 0,5,10,12 \* \* \*['\"]$")
        self.assertEqual(self.workflow.count("cron:"), 1)
        self.assertRegex(self.workflow, r"(?m)^\s{2}workflow_dispatch:\s*$")
        # The incremental refresh must never trigger UBS collection or run on push.
        self.assertNotIn("collect.py", self.workflow)
        self.assertNotIn("push:", self.workflow)

    def test_permissions_match_daily_build(self):
        for permission in ("contents: read", "pages: write", "id-token: write"):
            self.assertEqual(self.workflow.count(permission), 1)
            self.assertIn(permission, self.pages)

    def test_queued_runs_never_cancel_the_daily_build(self):
        self.assertRegex(self.workflow, r"(?ms)^concurrency:\s*\n\s+group: pages\s*\n\s+cancel-in-progress: false")
        self.assertRegex(self.workflow, r"(?ms)^\s{2}deploy:\s*\n\s{4}needs: build\b")
        self.assertIn("name: github-pages", self.workflow)
        self.assertIn("uses: actions/deploy-pages@v4", self.workflow)

    def test_restore_fallback_collect_tests_upload_are_ordered(self):
        commands = [
            "uses: actions/cache/restore@v4",
            "SITE_FALLBACK_URL",
            "GH_TOKEN: ${{ github.token }}",
            "python -X utf8 -m triton.dashboard --hours 72",
            "python -m unittest discover -s tests",
            "node --test tests/*.test.cjs",
            "uses: actions/cache/save@v4",
            "uses: actions/upload-pages-artifact@v3",
        ]
        positions = [self.workflow.index(command) for command in commands]
        self.assertEqual(positions, sorted(positions))
        self.assertRegex(self.workflow, r"(?ms)uses: actions/upload-pages-artifact@v3\s+with:\s+path: web\s*$")

    def test_ensure_step_uses_fallback_site_and_fails_without_index(self):
        self.assertIn("确保 UBS 数据", self.workflow)
        self.assertIn(f"SITE_FALLBACK_URL: {FALLBACK_URL}", self.workflow)
        self.assertIn('"${SITE_FALLBACK_URL:-' + FALLBACK_URL + '}"', self.workflow)
        self.assertIn("curl -fsSL --retry 3 --retry-delay 5 --retry-all-errors", self.workflow)
        # No-deploy guard: a still-missing UBS index must fail the build.
        self.assertRegex(
            self.workflow,
            r"(?s)if \[ ! -s web/data/repositories\.json \]; then.*?exit 1",
        )

    def test_ensure_step_covers_index_snapshot_and_repos(self):
        self.assertIn("fetch web/data/repositories.json /data/repositories.json", self.workflow)
        self.assertIn("fetch data/snapshot.json /data/snapshot.json", self.workflow)
        self.assertIn('"/data/repos/$name.json"', self.workflow)

    def test_shares_rolling_cache_prefix_with_daily_build(self):
        for path in (
            "web/data",
            "data/repositories.json",
            "data/repos",
            "data/snapshot.json",
        ):
            self.assertRegex(self.workflow, rf"(?m)^\s+{re.escape(path)}\s*$")
        self.assertIn("${{ github.run_id }}", self.workflow)
        self.assertIn("restore-keys:", self.workflow)
        # The daily full build and this incremental workflow exchange caches
        # through the same "pages-data-" prefix (key and restore-keys).
        self.assertGreaterEqual(self.workflow.count("pages-data-"), 2)
        self.assertIn("pages-data-${{ runner.os }}-", self.workflow)
        self.assertIn("pages-data-", self.pages)


if __name__ == "__main__":
    unittest.main()
