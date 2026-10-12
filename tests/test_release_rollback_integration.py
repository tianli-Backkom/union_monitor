"""UDR-030: real recovery deployment and post-rollback re-verification."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from monitor.baseline import ArchiveMissingError, BaselineError, ReleaseStore
from monitor.rollback import rollback_deploy


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle(release_id, content):
    return {
        "release_id": release_id,
        "run_id": f"run-{release_id}",
        "code_sha": "0" * 40,
        "cutoff_at": "2026-10-10T00:00:00Z",
        "resources": {"data/snapshot.json": {"sha256": sha(content), "size": len(content)}},
    }, {"data/snapshot.json": content}


class RollbackIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rollback-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = ReleaseStore(self.tmp)
        self.manifest_v1, self.files_v1 = bundle("rel-1", b"v1")
        self.store.write_archive("rel-1", self.manifest_v1, self.files_v1)
        self.store.promote("rel-1")

    def test_tc01_rollback_redeploys_archived_bundle_and_reverifies(self):
        deployed = []
        def deploy(rid, files):
            deployed.append((rid, files))
        def verify(rid, manifest):
            return {"verified": True, "release_id": rid}
        result = rollback_deploy(self.store, "rel-2", "rel-1",
                                 deploy_fn=deploy, verify_fn=verify,
                                 reason="candidate fingerprint mismatch")
        self.assertTrue(result["recovered"])
        self.assertEqual(result["active_release_id"], "rel-1")
        # The recovery used the immutable archive bytes, never re-collected.
        self.assertEqual(deployed, [("rel-1", self.files_v1)])
        self.assertEqual(deployed[0][1]["data/snapshot.json"], b"v1")

    def test_tc02_rollback_of_current_verified_release_is_refused(self):
        with self.assertRaises(BaselineError):
            rollback_deploy(self.store, "rel-1", "rel-1",
                            deploy_fn=lambda r, f: None, verify_fn=lambda r, m: {"verified": True})

    def test_tc02_nearer_verified_release_is_not_overwritten(self):
        self.store.write_archive("rel-3", *bundle("rel-3", b"v3"))
        self.store.promote("rel-3", expected_previous={"current": "rel-1", "previous": None})
        with self.assertRaisesRegex(BaselineError, "nearer verified"):
            rollback_deploy(self.store, "rel-2", "rel-1",
                            deploy_fn=lambda r, f: None, verify_fn=lambda r, m: {"verified": True})

    def test_tc02_missing_baseline_archive_is_a_fault(self):
        # The pointer still names rel-1, but its archive has been destroyed.
        shutil.rmtree(self.store.archive_dir("rel-1"))
        with self.assertRaises(ArchiveMissingError):
            rollback_deploy(self.store, "rel-2", "rel-1",
                            deploy_fn=lambda r, f: None, verify_fn=lambda r, m: {"verified": True})

    def test_tc02_failed_recovery_deploy_keeps_live_state_and_manual_entry(self):
        def deploy(rid, files):
            raise OSError("pages deploy refused")
        result = rollback_deploy(self.store, "rel-2", "rel-1",
                                 deploy_fn=deploy, verify_fn=lambda r, m: {"verified": True})
        self.assertFalse(result["recovered"])
        self.assertIn("manual_entry", result)
        self.assertEqual(result["active_release_id"], "rel-1")

    def test_tc02_failed_reverify_does_not_report_recovery(self):
        result = rollback_deploy(self.store, "rel-2", "rel-1",
                                 deploy_fn=lambda r, f: None,
                                 verify_fn=lambda r, m: {"verified": False, "problems": ["byte mismatch"]})
        self.assertFalse(result["recovered"])
        self.assertIn("manual_entry", result)
        self.assertIn("receipt", result)
        self.assertFalse(result["receipt"]["verified"])


if __name__ == "__main__":
    unittest.main()