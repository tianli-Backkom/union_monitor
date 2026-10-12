"""UDR-027: degraded release with trusted fallback and failure policies."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from monitor.assemble import is_publishable
from monitor.baseline import ReleaseStore
from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.release_policy import degraded_release

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")

RUN_ID = "synthetic-20261010-0730-attempt-1"
CODE_SHA = "9aec47355689c243f3f8c35cab40fd275c0e8441"
CUTOFF = "2026-10-09T23:30:00Z"


def context():
    return RunContext(run_id=RUN_ID, code_sha=CODE_SHA, cutoff_at=CUTOFF,
                      project_ids=["ubs", "triton"])


def windows():
    return {
        "ubs": {"time_basis": "pr_created_at", "start_at": "2026-09-09T23:30:00Z", "end_at": CUTOFF},
        "triton": {"time_basis": "batch_started_at", "start_at": "2026-10-06T23:30:00Z", "end_at": CUTOFF},
    }


def sha(data):
    return hashlib.sha256(data).hexdigest()


def report(pid, *, status="success", samples=None, **overrides):
    project = CATALOG.project(pid)
    value = {
        "run_id": RUN_ID, "project_id": pid, "code_sha": CODE_SHA,
        "collector": project["collector"], "metric_profile": project["metric_profile"],
        "task_status": status,
        "collection_status": "success" if status in ("success", "partial") else "failed",
        "validation_status": "passed" if status == "success" else "failed",
        "exit_code": 0, "window": windows()[pid], "collected_at": "2026-10-10T00:10:00Z",
        "samples": samples if samples is not None else {"prs": 2, "batches": 3},
        "snapshot_version": f"{pid}-20261010", "snapshot_path": f"data/projects/{pid}/snapshots/{pid}-20261010.json",
        "snapshot_sha256": sha(f"{pid}-fresh".encode()),
        "errors": [],
    }
    value.update(overrides)
    return value


def baseline_release(release_id="rel-0", release_status="verified"):
    return {
        "release_id": release_id,
        "release_status": release_status,
        "projects": {
            "ubs": {"task_status": "success", "data_mode": "fresh", "snapshot_version": "ubs-0",
                     "snapshot_path": "data/projects/ubs/snapshots/ubs-0.json",
                     "snapshot_sha256": sha(b"ubs0"), "metric_profile": "ubs-pr-representative-v1",
                     "collected_at": "2026-09-10T00:10:00Z",
                     "window": {"time_basis": "pr_created_at", "start_at": "2026-09-08T23:30:00Z", "end_at": "2026-09-09T23:30:00Z"}},
            "triton": {"task_status": "success", "data_mode": "fresh", "snapshot_version": "triton-0",
                        "snapshot_path": "data/projects/triton/snapshots/triton-0.json",
                        "snapshot_sha256": sha(b"triton0"), "metric_profile": "triton-commit-attempt-v1",
                        "collected_at": "2026-09-10T00:10:00Z",
                        "window": {"time_basis": "batch_started_at", "start_at": "2026-10-05T23:30:00Z", "end_at": "2026-10-08T23:30:00Z"}},
        },
        "resources": {
            "data/projects/ubs/snapshots/ubs-0.json": {"sha256": sha(b"ubs0"), "size": 4, "project": "ubs"},
            "data/projects/triton/snapshots/triton-0.json": {"sha256": sha(b"triton0"), "size": 7, "project": "triton"},
        },
    }


def baseline_files(manifest):
    return {rel: b"ubs0" if "ubs" in rel else b"triton0" for rel in manifest["resources"]}


class DegradedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="degraded-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def make_store(self, manifest):
        store = ReleaseStore(self.tmp)
        store.write_archive(manifest["release_id"], manifest, baseline_files(manifest))
        store.promote(manifest["release_id"])
        return store

    def test_success_is_fresh_and_legal_zero_is_fresh(self):
        release, block = degraded_release(
            None, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertIsNone(block)
        self.assertEqual(release["projects"]["ubs"]["data_mode"], "fresh")
        self.assertEqual(release["projects"]["triton"]["data_mode"], "fresh")
        # Legal zero is still fresh.
        zero = degraded_release(
            None, CATALOG, context(),
            {"ubs": report("ubs", samples={"prs": 0}), "triton": report("triton", samples={"batches": 0})},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )[0]
        self.assertEqual(zero["projects"]["ubs"]["data_mode"], "fresh")

    def test_failed_project_falls_back_keeping_old_window_and_failed_task(self):
        store = self.make_store(baseline_release())
        release, block = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertIsNone(block)
        triton = release["projects"]["triton"]
        self.assertEqual(triton["data_mode"], "fallback")
        self.assertEqual(triton["task_status"], "failed")
        # Old window/time are preserved, not rewritten to this round's cutoff.
        self.assertEqual(triton["window"]["end_at"], "2026-10-08T23:30:00Z")
        self.assertEqual(triton["collected_at"], "2026-09-10T00:10:00Z")
        self.assertTrue(is_publishable(release))

    def test_failed_project_without_baseline_is_unavailable(self):
        release, _ = degraded_release(
            None, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertEqual(release["projects"]["triton"]["data_mode"], "unavailable")

    def test_timeout_uses_fallback_not_success(self):
        store = self.make_store(baseline_release())
        release, _ = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="timeout")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        triton = release["projects"]["triton"]
        self.assertEqual(triton["data_mode"], "fallback")
        self.assertEqual(triton["task_status"], "timeout")

    def test_unreadable_fallback_is_downgraded_to_unavailable(self):
        manifest = baseline_release()
        manifest["projects"]["triton"]["snapshot_sha256"] = "f" * 64  # hash no longer matches archive
        store = self.make_store(manifest)
        release, _ = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertEqual(release["projects"]["triton"]["data_mode"], "unavailable")

    def test_all_failed_no_baseline_is_not_publishable(self):
        release, block = degraded_release(
            None, CATALOG, context(),
            {"ubs": None, "triton": None},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertIsNone(block)
        self.assertFalse(is_publishable(release))

    def test_all_failed_with_baseline_is_fallback_not_fresh(self):
        store = self.make_store(baseline_release())
        release, _ = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs", status="failed"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertFalse(any(p["data_mode"] == "fresh" for p in release["projects"].values()))
        self.assertFalse(is_publishable(release))

    def test_corrupt_baseline_blocks_even_with_fresh_project(self):
        manifest = baseline_release()
        store = self.make_store(manifest)
        # Destroy the archived resource so the pointer references a corrupt baseline.
        (store.archive_dir("rel-0") / "data/projects/triton/snapshots/triton-0.json").write_bytes(b"corrupt")
        release, block = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertIsNone(release)
        self.assertIn("baseline_fault", block)

    def test_non_verified_pointer_is_a_baseline_fault(self):
        store = self.make_store(baseline_release(release_status="candidate"))
        release, block = degraded_release(
            store, CATALOG, context(),
            {"ubs": report("ubs"), "triton": report("triton", status="failed")},
            release_id="rel-1", published_at="2026-10-10T00:30:00Z",
        )
        self.assertIsNone(release)
        self.assertIn("non-verified", block["baseline_fault"])


if __name__ == "__main__":
    unittest.main()