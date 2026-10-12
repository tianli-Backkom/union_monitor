"""UDR-028: persistent verified baseline and atomic, non-force pointer promotion."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from monitor.baseline import (ArchiveMissingError, BaselineError, ConflictError,
                              ReleaseStore, promote_sequence)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle(release_id, content=b"v1", code_sha="0" * 40):
    manifest = {
        "release_id": release_id,
        "run_id": f"run-{release_id}",
        "code_sha": code_sha,
        "cutoff_at": "2026-10-10T00:00:00Z",
        "resources": {"data/snapshot.json": {"sha256": sha(content), "size": len(content)}},
    }
    return manifest, {"data/snapshot.json": content}


class ReleaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="baseline-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = ReleaseStore(self.tmp)

    def test_tc01_promote_then_cold_restore_from_immutable_archive(self):
        m1, f1 = bundle("rel-1", b"v1")
        m2, f2 = bundle("rel-2", b"v2")
        self.store.write_archive("rel-1", m1, f1)
        self.store.promote("rel-1")
        self.store.write_archive("rel-2", m2, f2)
        state = self.store.promote("rel-2", expected_previous={"current": "rel-1", "previous": None})
        self.assertEqual(state, {"current": "rel-2", "previous": "rel-1"})
        # Cold restore (no cache) returns the current archive bytes intact.
        manifest, files = self.store.cold_restore()
        self.assertEqual(manifest["release_id"], "rel-2")
        self.assertEqual(files["data/snapshot.json"], b"v2")
        self.assertEqual(self.store.verify_archive("rel-2"), [])

    def test_tc01_pointer_promotion_is_atomic_and_non_force(self):
        m1, f1 = bundle("rel-1")
        self.store.write_archive("rel-1", m1, f1)
        self.store.promote("rel-1")
        with self.assertRaises(ConflictError):
            # A stale expected state cannot overwrite a newer promotion.
            self.store.promote("rel-2", expected_previous={"current": "rel-9", "previous": None})
        self.assertEqual(self.store.pointer(), {"current": "rel-1", "previous": None})

    def test_tc02_unverified_candidate_is_never_archived_or_promoted(self):
        m, f = bundle("rel-1")
        with self.assertRaises(BaselineError):
            promote_sequence(self.store, "rel-1", m, f,
                             verify_fn=lambda rid, mf: {"verified": False})
        self.assertFalse(self.store.archive_dir("rel-1").exists())
        self.assertIsNone(self.store.pointer())

    def test_tc02_archive_is_immutable(self):
        m, f = bundle("rel-1")
        self.store.write_archive("rel-1", m, f)
        with self.assertRaises(BaselineError):
            self.store.write_archive("rel-1", m, {"data/snapshot.json": b"tampered"})

    def test_tc02_tampered_archive_fails_recheck(self):
        m, f = bundle("rel-1", b"v1")
        dest = self.store.write_archive("rel-1", m, f)
        (dest / "data/snapshot.json").write_bytes(b"tampered")
        problems = self.store.verify_archive("rel-1")
        self.assertTrue(any("sha256" in p for p in problems), problems)
        # A damaged current archive must not be promoted further.
        with self.assertRaises(BaselineError):
            self.store.promote("rel-1")

    def test_tc02_pointer_to_missing_archive_is_a_baseline_fault(self):
        self.store._write_pointer_atomic({"current": "rel-missing", "previous": None})
        with self.assertRaises(ArchiveMissingError):
            self.store.cold_restore()

    def test_promote_sequence_runs_verify_then_archive_then_promote(self):
        m1, f1 = bundle("rel-1")
        calls = []
        def verify(rid, mf):
            calls.append("verify")
            return {"verified": True}
        state = promote_sequence(self.store, "rel-1", m1, f1, verify_fn=verify)
        self.assertEqual(calls, ["verify"])
        self.assertEqual(state, {"current": "rel-1", "previous": None})
        self.assertEqual(self.store.verify_archive("rel-1"), [])


if __name__ == "__main__":
    unittest.main()