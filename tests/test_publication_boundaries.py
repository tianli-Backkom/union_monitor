"""UDR-031: cache/source-evidence/public-resource and permission boundaries."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from monitor.baseline import ReleaseStore
from monitor.boundaries import (cache_key, scan_public_resources, sentinel_in,
                                whitelisted_public_path)

ROOT = Path(__file__).resolve().parents[1]


class CacheBoundaryTests(unittest.TestCase):
    def test_cache_key_is_isolated_per_community_collector_version(self):
        a = cache_key("gitcode", "gitcode-jenkins-v1", 1, "ubs")
        b = cache_key("github", "github-actions-v1", 1, "triton")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, cache_key("gitcode", "gitcode-jenkins-v1", 2, "ubs"))
        self.assertNotEqual(cache_key("github", "github-actions-v1", 1, "triton"),
                            cache_key("github", "github-actions-v1", 1, "other"))

    def test_history_restores_from_persistent_bundle_not_cache(self):
        tmp = Path(tempfile.mkdtemp(prefix="bounds-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        store = ReleaseStore(tmp)
        data = b"v"
        manifest = {"release_id": "rel-1", "release_status": "verified",
                    "resources": {"data/snapshot.json": {
                        "sha256": hashlib.sha256(data).hexdigest(), "size": 1}}}
        store.write_archive("rel-1", manifest, {"data/snapshot.json": data})
        store.promote("rel-1")
        # Simulate a corrupted short-term cache — recovery still uses the archive.
        cache = tmp / "cache"
        cache.mkdir()
        (cache / "snapshot.json").write_text("{corrupt", encoding="utf-8")
        restored_manifest, restored_files = store.cold_restore()
        self.assertEqual(restored_files["data/snapshot.json"], b"v")


class ResourceBoundaryTests(unittest.TestCase):
    def test_sentinel_is_detected_in_text_and_bytes(self):
        self.assertTrue(sentinel_in("resp SECRET_TOKEN here", "SECRET_TOKEN"))
        self.assertTrue(sentinel_in(b"resp SECRET_TOKEN here", "SECRET_TOKEN"))
        self.assertFalse(sentinel_in("clean response", "SECRET_TOKEN"))

    def test_public_whitelist_admits_display_data_only(self):
        for rel in ("data/snapshot.json", "data/catalog.json", "index.html",
                    "assets/app.js", "assets/app.css", "data/repos/ubs.csv"):
            self.assertTrue(whitelisted_public_path(rel), rel)

    def test_database_raw_cache_and_logs_are_never_public(self):
        for rel in ("data/efficiency.sqlite", "data/raw/evidence.log",
                    "cache/collector.db", "data/full-run.log", "data/snap.pkl"):
            self.assertFalse(whitelisted_public_path(rel), rel)

    def test_scan_flags_sentinel_and_non_whitelisted_resources(self):
        resources = {"data/snapshot.json": b'{"ok":1}',
                     "data/efficiency.sqlite": b"\x00",
                     "data/leak.json": b"key=SECRET_TOKEN"}
        problems = scan_public_resources(resources, resources, sentinel="SECRET_TOKEN")
        self.assertTrue(any("efficiency.sqlite" in p for p in problems), problems)
        self.assertTrue(any("sentinel" in p and "leak.json" in p for p in problems), problems)
        self.assertEqual(len(problems), 2)


class PermissionBoundaryTests(unittest.TestCase):
    def test_only_deploy_job_uses_github_pages_environment(self):
        text = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertEqual(text.count("environment:"), 1)
        self.assertEqual(text.count("name: github-pages"), 1)
        self.assertEqual(text.count("actions/deploy-pages@v4"), 1)
        # The collect/build job must not hold Pages/OIDC write permission.
        self.assertIn("contents: read", text)

    def test_secret_is_used_only_for_collection_request_not_output(self):
        text = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        # The token appears only in the Triton gating collect step environment.
        self.assertIn("GH_TOKEN: ${{ secrets.GH_TOKEN }}", text)
        self.assertNotIn("GH_TOKEN", text.replace("GH_TOKEN: ${{ secrets.GH_TOKEN }}", ""))


if __name__ == "__main__":
    unittest.main()