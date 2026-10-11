import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "triton-refresh.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"

FALLBACK_URL = "https://tianli-backkom.github.io/union_monitor"


class TritonWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.pages = PAGES_WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_matches_beijing_refresh_slots(self):
        self.assertRegex(self.workflow, r"(?m)^\s{4}- cron: ['\"]0 0,4,8,10,12 \* \* \*['\"]$")
        self.assertEqual(self.workflow.count("cron:"), 1)
        self.assertRegex(self.workflow, r"(?m)^\s{2}workflow_dispatch:\s*$")
        # The incremental refresh must never trigger UBS collection or run on push.
        self.assertNotIn("collect.py", self.workflow)
        self.assertNotIn("push:", self.workflow)

    def test_permissions_match_daily_build(self):
        for permission in ("contents: read", "pages: write", "id-token: write"):
            self.assertEqual(self.workflow.count(permission), 1)
            self.assertIn(permission, self.pages)

    def test_concurrency_protects_running_pending_replaced_by_platform_default(self):
        # REQ-039/P04: cancel-in-progress:false only protects the RUNNING
        # build. Pending runs follow the platform default (queue: single):
        # only the newest queued run per group is kept, earlier queued runs
        # are cancelled and replaced. The literal below declares the
        # protection; it must never be read as "queued runs never cancel".
        self.assertRegex(self.workflow, r"(?ms)^concurrency:\s*\n\s+group: pages\s*\n\s+cancel-in-progress: false")
        self.assertRegex(self.workflow, r"(?ms)^\s{2}deploy:\s*\n\s{4}needs: build\b")
        self.assertIn("name: github-pages", self.workflow)
        self.assertIn("uses: actions/deploy-pages@v4", self.workflow)

    def test_restore_fallback_collect_tests_upload_are_ordered(self):
        commands = [
            "uses: actions/cache/restore@v4",
            "SITE_FALLBACK_URL",
            "GH_TOKEN: ${{ secrets.GH_TOKEN }}",
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
        # REQ-012: the fallback also restores the published compat snapshot and
        # the shared bundle manifest, then mirrors the repo-root copies the
        # shared cache path set needs, logging every source.
        self.assertIn("fetch web/data/snapshot.json /data/snapshot.json", self.workflow)
        self.assertIn("fetch web/data/ubs-manifest.json /data/ubs-manifest.json", self.workflow)
        self.assertIn("cp web/data/snapshot.json data/snapshot.json", self.workflow)
        self.assertIn("cp web/data/repositories.json data/repositories.json", self.workflow)
        self.assertIn("[ensure-UBS-data] summary: cache=", self.workflow)

    def test_checkout_uses_full_history_for_commit_mapping_tests(self):
        for text in (self.workflow, self.pages):
            self.assertEqual(text.count("uses: actions/checkout@v4"), text.count("fetch-depth: 0"))
            self.assertRegex(text, r"(?ms)uses: actions/checkout@v4\s+with:\s+fetch-depth: 0")
    def test_shares_versioned_snapshot_cache_with_daily_build(self):
        for path in (
            "web/data/repositories.json",
            "web/data/repos",
            "web/data/snapshot.json",
            "web/data/ubs-manifest.json",
            "data/repositories.json",
            "data/repos",
            "data/snapshot.json",
        ):
            self.assertRegex(self.workflow, rf"(?m)^\s+{re.escape(path)}\s*$")
        # REQ-012: the daily build and this incremental workflow exchange UBS
        # snapshots through the same versioned key family with the identical
        # path set; the unversioned legacy prefix is gone.
        self.assertIn("ubs-snapshots-v1-${{ runner.os }}-${{ github.run_id }}", self.workflow)
        self.assertIn("ubs-snapshots-v1-${{ runner.os }}-", self.workflow)
        self.assertIn("ubs-snapshots-v1-${{ runner.os }}-${{ github.run_id }}", self.pages)
        self.assertIn("ubs-snapshots-v1-${{ runner.os }}-", self.pages)
        self.assertNotIn("pages-data-", self.workflow)
        self.assertNotIn("pages-data-", self.pages)
        # The daily-only collection cache must not leak into this flow.
        self.assertNotIn("ubs-collection-", self.workflow)


if __name__ == "__main__":
    unittest.main()
