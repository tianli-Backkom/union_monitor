"""T-013: deployment verification and trusted rollback tests."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from monitor.rollback import rollback, should_rollback
from monitor.verify import mark_verified, verify_deployment


def release(release_id="rel-1", run_id="run-1", projects=None):
    return {
        "release_id": release_id,
        "run_id": run_id,
        "code_sha": "0" * 40,
        "cutoff_at": "2026-10-10T00:00:00Z",
        "release_status": "candidate",
        "projects": projects if projects is not None else {"ubs": {"data_mode": "fresh", "snapshot_sha256": "a" * 64}},
    }


class VerifyDeploymentTests(unittest.TestCase):
    def test_matching_deploy_is_verified(self):
        result = verify_deployment(release(), release())
        self.assertTrue(result["verified"])
        self.assertEqual(result["problems"], [])

    def test_identity_mismatch_is_flagged(self):
        result = verify_deployment(release(run_id="run-X"), release(run_id="run-1"))
        self.assertFalse(result["verified"])
        self.assertTrue(any("run_id mismatch" in p for p in result["problems"]))

    def test_missing_project_is_flagged(self):
        deployed = release(projects={})
        result = verify_deployment(deployed, release())
        self.assertFalse(result["verified"])
        self.assertTrue(any("ubs" in p for p in result["problems"]))

    def test_snapshot_mismatch_is_flagged(self):
        deployed = release(projects={"ubs": {"data_mode": "fresh", "snapshot_sha256": "b" * 64}})
        result = verify_deployment(deployed, release())
        self.assertFalse(result["verified"])
        self.assertTrue(any("snapshot mismatch" in p for p in result["problems"]))

    def test_non_object_deployed_is_a_problem(self):
        result = verify_deployment(None, release())
        self.assertFalse(result["verified"])

    def test_mark_verified_promotes_the_release(self):
        verified = mark_verified(release())
        self.assertEqual(verified["release_status"], "verified")
        self.assertEqual(verified["release_id"], "rel-1")


class RollbackTests(unittest.TestCase):
    def test_should_rollback_follows_verification(self):
        self.assertTrue(should_rollback({"verified": False}))
        self.assertFalse(should_rollback({"verified": True}))

    def test_rollback_points_at_the_trusted_baseline(self):
        baseline = release(release_id="rel-0", run_id="run-0")
        record = rollback("rel-1", baseline)
        self.assertEqual(record["action"], "rollback")
        self.assertEqual(record["failed_release_id"], "rel-1")
        self.assertEqual(record["active_release_id"], "rel-0")
        self.assertEqual(record["baseline_run_id"], "run-0")


class CliTests(unittest.TestCase):
    def test_cmd_verify_deployment_offline_returns_zero(self):
        from monitor.__main__ import cmd_verify_deployment
        with tempfile.TemporaryDirectory() as d:
            manifest = Path(d) / "manifest.json"
            manifest.write_text(json.dumps(release()), encoding="utf-8")
            deployed = Path(d) / "deployed.json"
            deployed.write_text(json.dumps(release()), encoding="utf-8")
            args = argparse.Namespace(manifest=str(manifest), url=None, deployed=str(deployed), out=None)
            self.assertEqual(cmd_verify_deployment(args), 0)

    def test_cmd_rollback_writes_the_record(self):
        from monitor.__main__ import cmd_rollback
        with tempfile.TemporaryDirectory() as d:
            baseline = Path(d) / "baseline.json"
            baseline.write_text(json.dumps(release(release_id="rel-0", run_id="run-0")), encoding="utf-8")
            out = Path(d) / "rollback.json"
            args = argparse.Namespace(failed_release="rel-1", baseline=str(baseline), reason=None, out=str(out))
            self.assertEqual(cmd_rollback(args), 0)
            record = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(record["active_release_id"], "rel-0")
            self.assertEqual(record["failed_release_id"], "rel-1")


if __name__ == "__main__":
    unittest.main()