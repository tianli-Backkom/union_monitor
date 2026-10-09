import hashlib, json, os, shutil, tempfile, unittest, urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from triton.quality import fingerprint
from triton.verify_deployment import RETRIES, DeploymentMismatch, main as verify_main, run

SITE = "https://example.github.io/ubs_core_monitor"


class VerifyDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verify-deploy-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.triton_payload = {"repo": "triton-lang/triton-ascend", "collected_at": "2026-10-09T00:00:00Z",
                               "window_start": "2026-10-06T00:00:00Z", "window_end": "2026-10-09T00:00:00Z",
                               "batches": [], "summary": {}}
        self.triton_manifest = self.tmp / "triton-manifest.json"
        self.triton_manifest.write_text(json.dumps(
            {"sha256": fingerprint(self.triton_payload), "collected_at": self.triton_payload["collected_at"]}),
            encoding="utf-8")
        self.ubs_files = {"repositories.json": b'{"schema_version": 3, "repositories": []}',
                          "repos/ubs-engine.json": b'{"meta": {"repository": "openeuler/ubs-engine"}}',
                          "snapshot.json": b'{"compat": true}'}
        self.ubs_manifest = self.tmp / "ubs-manifest.json"
        self.ubs_manifest.write_text(json.dumps(
            {"schema": 1, "fingerprint": "sha256:" + "a" * 64, "generated_at": "2026-10-09T00:00:00+00:00",
             "files": {rel: hashlib.sha256(data).hexdigest() for rel, data in sorted(self.ubs_files.items())}}),
            encoding="utf-8")

    def publish(self, transient_failures=0, **overrides):
        """Serve this build's files at /data/*; overrides replace published entries."""
        files = {"triton.json": (json.dumps(self.triton_payload, ensure_ascii=False) + "\n").encode("utf-8"),
                 "triton-manifest.json": self.triton_manifest.read_bytes(),
                 "ubs-manifest.json": self.ubs_manifest.read_bytes()}
        files.update(self.ubs_files)
        files.update(overrides)
        calls, remaining = [], [transient_failures]

        def fake_fetch(url):
            calls.append(url)
            if remaining[0] > 0:
                remaining[0] -= 1
                raise urllib.error.URLError(f"connection reset: {url}")
            path = url.split("/data/", 1)[1]
            if path not in files:
                raise urllib.error.URLError(f"404 not found: {url}")
            return files[path]

        return fake_fetch, calls

    def test_success_verifies_the_real_triton_entry_and_records_the_run(self):
        # REQ-022 AC01/AC02/AC04: the real /data/triton.json entry is fetched and the
        # run record carries run ID, URL, verification time and both fingerprints.
        fake_fetch, calls = self.publish()
        summary = self.tmp / "summary.md"
        with patch("triton.verify_deployment.fetch", fake_fetch), \
             patch("triton.verify_deployment.time.sleep"), \
             patch.dict(os.environ, {"GITHUB_RUN_ID": "12345", "GITHUB_RUN_NUMBER": "67",
                                     "GITHUB_WORKFLOW": "Collect and deploy dashboard",
                                     "GITHUB_STEP_SUMMARY": str(summary)}):
            record = run(SITE, self.triton_manifest, self.ubs_manifest)
        self.assertIn(SITE + "/data/triton.json", calls, "must read the real /data/triton.json entry, not embedded HTML")
        self.assertIn(SITE + "/data/repositories.json", calls)
        self.assertIn(SITE + "/data/repos/ubs-engine.json", calls)
        self.assertIn(SITE + "/data/ubs-manifest.json", calls)
        self.assertEqual(record["run_id"], "12345")
        self.assertEqual(record["site"], SITE)
        self.assertEqual(record["triton"]["url"], SITE + "/data/triton.json")
        self.assertEqual(record["triton"]["fingerprint"], fingerprint(self.triton_payload))
        self.assertEqual(record["ubs"]["file_count"], 3)
        datetime.fromisoformat(record["verified_at"])
        summary_text = summary.read_text("utf-8")
        self.assertIn("12345", summary_text)
        self.assertIn(SITE + "/data/triton.json", summary_text)
        self.assertIn(fingerprint(self.triton_payload), summary_text)
        self.assertIn("sha256:" + "a" * 64, summary_text)

    def test_stale_triton_data_fails_naming_the_file_without_claiming_rollback(self):
        # REQ-022 AC03: stale published data fails after bounded retries, names the
        # inconsistent file in the run summary, and never claims a rollback.
        stale = dict(self.triton_payload, collected_at="old", batches=[{"id": "b1"}])
        fake_fetch, calls = self.publish(**{"triton.json": json.dumps(stale).encode("utf-8")})
        summary = self.tmp / "summary.md"
        with patch("triton.verify_deployment.fetch", fake_fetch), \
             patch("triton.verify_deployment.time.sleep"), \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            with self.assertRaises(DeploymentMismatch) as ctx:
                run(SITE, self.triton_manifest, self.ubs_manifest)
        message = str(ctx.exception)
        self.assertIn("triton.json", message)
        self.assertIn(SITE + "/data/triton.json", message)
        self.assertIn("no rollback", message)
        self.assertEqual(calls.count(SITE + "/data/triton.json"), RETRIES)
        summary_text = summary.read_text("utf-8")
        self.assertIn("不一致文件", summary_text)
        self.assertIn("- triton.json", summary_text)

    def test_tampered_ubs_index_and_snapshot_are_named_in_the_failure(self):
        # REQ-022 AC01/AC03: every tampered UBS file is named with its URL.
        fake_fetch, _ = self.publish(**{"repositories.json": b'{"tampered": true}',
                                        "repos/ubs-engine.json": b'{"meta": {"repository": "other/repo"}}'})
        summary = self.tmp / "summary.md"
        with patch("triton.verify_deployment.fetch", fake_fetch), \
             patch("triton.verify_deployment.time.sleep"), \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            with self.assertRaises(DeploymentMismatch) as ctx:
                run(SITE, self.triton_manifest, self.ubs_manifest)
        message = str(ctx.exception)
        self.assertIn("repositories.json", message)
        self.assertIn("repos/ubs-engine.json", message)
        summary_text = summary.read_text("utf-8")
        self.assertIn("- repositories.json", summary_text)
        self.assertIn("- repos/ubs-engine.json", summary_text)

    def test_stale_published_manifest_fails_naming_it(self):
        # REQ-022 AC01: the published manifests themselves must be this build's.
        fake_fetch, _ = self.publish(**{"ubs-manifest.json": b'{"stale": true}'})
        with patch("triton.verify_deployment.fetch", fake_fetch), \
             patch("triton.verify_deployment.time.sleep"), \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.tmp / "summary.md")}):
            with self.assertRaises(DeploymentMismatch) as ctx:
                run(SITE, self.triton_manifest, self.ubs_manifest)
        self.assertIn("ubs-manifest.json", str(ctx.exception))

    def test_transient_failures_retry_then_succeed(self):
        # REQ-022 AC03: retries are bounded and deployment propagation delays recover.
        fake_fetch, calls = self.publish(transient_failures=2)
        sleeps = []
        with patch("triton.verify_deployment.fetch", fake_fetch), \
             patch("triton.verify_deployment.time.sleep", lambda seconds: sleeps.append(seconds)), \
             patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.tmp / "unused-summary.md")}):
            record = run(SITE, self.triton_manifest, self.ubs_manifest)
        self.assertEqual(sleeps, [20, 20])
        self.assertEqual(calls.count(SITE + "/data/triton.json"), 3)
        self.assertEqual(record["triton"]["fingerprint"], fingerprint(self.triton_payload))

    def test_missing_local_manifest_fails_closed(self):
        # REQ-022 AC01: without this build's baseline the tool refuses to verify.
        with patch("sys.argv", ["verify_deployment", SITE,
                                "--triton-manifest", str(self.tmp / "missing.json"),
                                "--ubs-manifest", str(self.ubs_manifest)]):
            self.assertEqual(verify_main(), 1)

    def test_both_workflows_wire_post_deploy_verification(self):
        # REQ-022 (F12): both release workflows verify published data against this build.
        root = Path(__file__).resolve().parents[1]
        for name in ("pages.yml", "triton-refresh.yml"):
            text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("triton.verify_deployment", text, name)
            self.assertIn("deployment-manifests", text, name)
            self.assertIn("needs: deploy", text, name)
            self.assertIn("page_url: ${{ steps.deployment.outputs.page_url }}", text, name)
            self.assertIn("needs.deploy.outputs.page_url", text, name)


if __name__ == "__main__":
    unittest.main()
