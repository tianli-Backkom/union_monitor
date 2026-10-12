"""UDR-026: assembler verifies real resources and emits a frozen complete bundle.

The assembler must never accept a report's self-declared success without
consulting the actual files. A fake-success report with the wrong identity,
wrong hash, missing snapshot, extra project or a missing runtime resource is
rejected before any deployable bundle exists; the frozen manifest's bytes,
sizes, ownership and version closure are independently recomputed.
"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from monitor.assemble import is_publishable
from monitor.bundle import (assemble_verified, build_site_manifest,
                            verify_fresh_reports, verify_site_manifest)
from monitor.catalog import Catalog
from monitor.context import RunContext
from monitor.public_verify import verify_public_resources

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


def write_file(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha(content)


def fresh_report(pid, snapshot_rel, snapshot_hash, snapshot_version, **overrides):
    project = CATALOG.project(pid)
    report = {
        "run_id": RUN_ID, "project_id": pid, "code_sha": CODE_SHA,
        "collector": project["collector"], "metric_profile": project["metric_profile"],
        "task_status": "success", "collection_status": "success", "validation_status": "passed",
        "exit_code": 0, "window": windows()[pid], "collected_at": "2026-10-10T00:10:00Z",
        "samples": {"prs": 12, "batches": 28},
        "snapshot_version": snapshot_version, "snapshot_path": snapshot_rel,
        "snapshot_sha256": snapshot_hash, "errors": [],
    }
    report.update(overrides)
    return report


UBS_SNAP = b'{"prs":[]}'
TRITON_SNAP = b'{"batches":[]}'
TRITON_CSV = b"pr,title,sha\n"
TRITON_SIDECAR = b'{"schema_version":1}'
INDEX_HTML = b"<!doctype html><html></html>"


def materialize(root):
    """Write every public resource and return consistent reports + resource_spec."""
    ubs_rel = "data/projects/ubs/snapshots/ubs-20261010.json"
    triton_rel = "data/projects/triton/snapshots/triton-20261010.json"
    ubs_sha = write_file(root, ubs_rel, UBS_SNAP)
    triton_sha = write_file(root, triton_rel, TRITON_SNAP)
    write_file(root, "data/projects/triton/triton-batches.csv", TRITON_CSV)
    write_file(root, "data/projects/triton/triton-qualifications-v1.json", TRITON_SIDECAR)
    write_file(root, "index.html", INDEX_HTML)
    reports = {
        "ubs": fresh_report("ubs", ubs_rel, ubs_sha, "ubs-20261010"),
        "triton": fresh_report("triton", triton_rel, triton_sha, "triton-20261010"),
    }
    resource_spec = {
        ubs_rel: {"project": "ubs", "snapshot_version": "ubs-20261010", "kind": "data"},
        triton_rel: {"project": "triton", "snapshot_version": "triton-20261010", "kind": "data"},
        "data/projects/triton/triton-batches.csv": {"project": "triton", "snapshot_version": "triton-20261010", "kind": "data"},
        "data/projects/triton/triton-qualifications-v1.json": {"project": "triton", "snapshot_version": "triton-20261010", "kind": "data"},
        "index.html": {"project": None, "kind": "runtime"},
    }
    return reports, resource_spec


class BundleAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="release-bundle-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "tree"
        self.root.mkdir()

    def test_assemble_verified_emits_complete_frozen_manifest(self):
        reports, spec = materialize(self.root)
        release, manifest = assemble_verified(
            CATALOG, context(), reports, self.root,
            release_id="rel-1", published_at="2026-10-10T00:30:00Z", resource_spec=spec,
        )
        self.assertTrue(is_publishable(release))
        self.assertEqual(manifest["release_id"], "rel-1")
        self.assertEqual(manifest["resources"]["index.html"]["kind"], "runtime")
        self.assertEqual(manifest["resources"]["index.html"]["sha256"], sha(INDEX_HTML))
        self.assertEqual(verify_site_manifest(manifest, self.root), [])

    def test_frozen_manifest_is_not_rewritten_by_verification(self):
        reports, spec = materialize(self.root)
        _, manifest = assemble_verified(
            CATALOG, context(), reports, self.root,
            release_id="rel-1", published_at="2026-10-10T00:30:00Z", resource_spec=spec,
        )
        before = json.dumps(manifest, sort_keys=True)
        verify_site_manifest(manifest, self.root)
        self.assertEqual(json.dumps(manifest, sort_keys=True), before)

    def test_fake_success_wrong_run_is_rejected(self):
        reports, spec = materialize(self.root)
        reports["ubs"]["run_id"] = "some-other-run"
        with self.assertRaisesRegex(RuntimeError, "run_id"):
            assemble_verified(CATALOG, context(), reports, self.root,
                              release_id="rel-1", published_at="2026-10-10T00:30:00Z",
                              resource_spec=spec)

    def test_fake_success_wrong_hash_is_rejected(self):
        reports, spec = materialize(self.root)
        reports["triton"]["snapshot_sha256"] = "f" * 64
        with self.assertRaisesRegex(RuntimeError, "sha256"):
            assemble_verified(CATALOG, context(), reports, self.root,
                              release_id="rel-1", published_at="2026-10-10T00:30:00Z",
                              resource_spec=spec)

    def test_fake_success_wrong_identity_and_config_is_rejected(self):
        # UDR-026-TC02: a bypassed loader must still reject wrong code SHA,
        # cutoff/window and collector/config before any deployable bundle.
        for mutation, field, value in (
            ("code_sha", "code_sha", "f" * 40),
            ("cutoff", "window", windows()["ubs"] | {"end_at": "2026-10-08T23:30:00Z"}),
            ("config", "collector", "some-other-collector"),
        ):
            with self.subTest(mutation=mutation):
                reports, spec = materialize(self.root)
                if mutation == "cutoff":
                    reports["ubs"]["window"] = value
                else:
                    reports["ubs"][field] = value
                with self.assertRaises(RuntimeError, msg=mutation):
                    assemble_verified(CATALOG, context(), reports, self.root,
                                      release_id="rel-1", published_at="2026-10-10T00:30:00Z",
                                      resource_spec=spec)

    def test_missing_snapshot_is_rejected(self):
        reports, spec = materialize(self.root)
        (self.root / "data/projects/ubs/snapshots/ubs-20261010.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            assemble_verified(CATALOG, context(), reports, self.root,
                              release_id="rel-1", published_at="2026-10-10T00:30:00Z",
                              resource_spec=spec)

    def test_extra_project_report_is_rejected(self):
        reports, spec = materialize(self.root)
        reports["unknown-project"] = fresh_report("ubs", "x", "a" * 64, "v")
        with self.assertRaisesRegex(RuntimeError, "unknown or disabled project"):
            assemble_verified(CATALOG, context(), reports, self.root,
                              release_id="rel-1", published_at="2026-10-10T00:30:00Z",
                              resource_spec=spec)

    def test_missing_runtime_resource_is_rejected(self):
        reports, spec = materialize(self.root)
        (self.root / "index.html").unlink()
        with self.assertRaisesRegex(RuntimeError, "index.html"):
            build_site_manifest({"release_id": "rel-1", "projects": {}}, self.root, resource_spec=spec)

    def test_version_mixing_is_flagged(self):
        reports, spec = materialize(self.root)
        release, manifest = assemble_verified(
            CATALOG, context(), reports, self.root,
            release_id="rel-1", published_at="2026-10-10T00:30:00Z", resource_spec=spec,
        )
        # Forge: the CSV claims a different snapshot version than the JSON.
        manifest["resources"]["data/projects/triton/triton-batches.csv"]["snapshot_version"] = "triton-20261009"
        problems = verify_site_manifest(manifest, self.root)
        self.assertTrue(any("mixes snapshot versions" in p and "triton" in p for p in problems), problems)


class FullPipelineTests(unittest.TestCase):
    def test_assemble_to_deploy_to_public_verify_receipt(self):
        with tempfile.TemporaryDirectory(prefix="release-pipeline-") as tmp:
            root = Path(tmp) / "tree"
            root.mkdir()
            reports, spec = materialize(root)
            release, manifest = assemble_verified(
                CATALOG, context(), reports, root,
                release_id="rel-1", published_at="2026-10-10T00:30:00Z", resource_spec=spec,
            )
            # Local bundle verification must pass before any deploy.
            self.assertEqual(verify_site_manifest(manifest, root), [])
            # Controlled deploy: copy the public tree to the Pages site.
            site = Path(tmp) / "site"
            shutil.copytree(root, site)
            # Public verification reads the deployed bytes and issues a receipt.
            def fetch(url):
                rel = url.split("https://site.example/", 1)[1]
                path = site / rel
                if not path.is_file():
                    raise FileNotFoundError(url)
                return path.read_bytes()
            receipt = verify_public_resources("https://site.example", manifest, fetch=fetch,
                                              verified_at="2026-10-10T01:00:00Z")
            self.assertTrue(receipt["verified"])
            self.assertEqual(receipt["release_id"], "rel-1")
            self.assertEqual(receipt["resources_checked"], len(manifest["resources"]))


if __name__ == "__main__":
    unittest.main()