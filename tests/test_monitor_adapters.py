"""T-012: real collector adapters (gitcode_jenkins / github_actions)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor.adapters import collect_repositories, resolve, write_snapshot
from monitor.adapters import gitcode_jenkins, github_actions
from monitor.catalog import Catalog
from monitor.context import RunContext
from triton import dashboard

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / "catalog.json")


def make_context():
    return RunContext(run_id="run-1", code_sha="0" * 40, cutoff_at="2026-10-10T00:00:00Z")


def runner_returning(payload):
    def run(repository, project, context):
        key = repository['repository_id'].split(':', 1)[1]
        if project['collector'] == 'gitcode-jenkins-v1':
            return {'meta': {'repository': key, 'branch':'master',
                            'start_ms':1791590400000-720*3600000, 'end_ms':1791590400000,
                            'collected_at':'2026-10-10T00:10:00Z', 'errors':[]}, 'prs':[]}
        return {'repo':key, 'window_start':'2026-10-07T00:00:00Z', 'window_end':'2026-10-10T00:00:00Z',
                'collected_at':'2026-10-10T00:10:00Z', 'batches':[],
                'summary':{'prs':0,'batches':0,'valid':0,'median':None,'p90':None,'approximate':0,'incomplete':0}}
    return run


def runner_failing_for(repo_ids):
    def run(repository, project, context):
        if repository["repository_id"] in repo_ids:
            raise RuntimeError(f"collector unavailable for {repository['repository_id']}")
        return runner_returning({})(repository, project, context)
    return run


class GitcodeAdapterTests(unittest.TestCase):
    def test_repo_key_strips_the_source_prefix(self):
        self.assertEqual(gitcode_jenkins.repo_key("gitcode:openeuler/ubs-engine"), "openeuler/ubs-engine")
        self.assertEqual(gitcode_jenkins.repo_key("openeuler/ubs-engine"), "openeuler/ubs-engine")

    def test_resolve_now_returns_the_real_adapter(self):
        fn = resolve(CATALOG, CATALOG.project("ubs"))
        self.assertEqual(fn.__module__, "monitor.adapters.gitcode_jenkins")
        self.assertTrue(callable(fn))

    def test_collect_aggregates_all_repositories(self):
        project = CATALOG.project("ubs")
        context = make_context()
        with tempfile.TemporaryDirectory() as work:
            report = gitcode_jenkins.collect(
                project, context, work,
                runner=runner_returning({}),
                now=lambda: "2026-10-10T00:10:00Z",
            )
            self.assertEqual(report["collection_status"], "success")
            self.assertEqual(report["task_status"], "success")
            self.assertEqual(report["collected_at"], "2026-10-10T00:10:00Z")
            self.assertEqual(report["window"]["time_basis"], "pr_created_at")
            self.assertEqual(report["window"]["start_at"], "2026-09-10T00:00:00Z")
            snapshot = json.loads((Path(work)/'ubs'/report["snapshot_path"]).read_text("utf-8"))
            self.assertEqual(len(snapshot["repositories"]), 9)
            self.assertEqual(snapshot["project_id"], "ubs")

    def test_partial_failure_keeps_the_round_honest(self):
        project = CATALOG.project("ubs")
        context = make_context()
        with tempfile.TemporaryDirectory() as work:
            report = gitcode_jenkins.collect(
                project, context, work,
                runner=runner_failing_for({"gitcode:openeuler/ubs-comm"}),
                now=lambda: "2026-10-10T00:10:00Z",
            )
            self.assertEqual(report["collection_status"], "failed")
            self.assertEqual(report["task_status"], "partial")
            self.assertEqual(report['validation_status'], 'failed')
            self.assertEqual(report['exit_code'], 1)
            self.assertEqual(len(report["errors"]), 1)
            snapshot = json.loads((Path(work)/'ubs'/report["snapshot_path"]).read_text("utf-8"))
            self.assertEqual(len(snapshot["repositories"]), 8)

    def test_no_repositories_collected_is_failed_not_fake_zero(self):
        project = CATALOG.project("ubs")
        context = make_context()

        def always_fail(repository, project, ctx):
            raise RuntimeError("down")

        with tempfile.TemporaryDirectory() as work:
            report = gitcode_jenkins.collect(
                project, context, work, runner=always_fail,
                now=lambda: "2026-10-10T00:10:00Z",
            )
            self.assertEqual(report["collection_status"], "failed")
            self.assertEqual(report["task_status"], "failed")
            self.assertTrue(report["errors"])


class GithubAdapterTests(unittest.TestCase):
    def test_resolve_returns_the_real_adapter(self):
        fn = resolve(CATALOG, CATALOG.project("triton"))
        self.assertEqual(fn.__module__, "monitor.adapters.github_actions")
        self.assertTrue(callable(fn))

    def test_collect_one_repository(self):
        project = CATALOG.project("triton")
        context = make_context()
        with tempfile.TemporaryDirectory() as work, patch.object(dashboard, 'EVIDENCE', Path(work)/'evidence'):
            dashboard.EVIDENCE.mkdir()
            (dashboard.EVIDENCE/'enriched-runs.json').write_text('[]', encoding='utf-8')
            report = github_actions.collect(
                project, context, work,
                runner=runner_returning({}),
                now=lambda: "2026-10-10T00:10:00Z",
            )
            self.assertEqual(report["collection_status"], "success")
            self.assertEqual(report["task_status"], "success")
            self.assertEqual(report["window"]["time_basis"], "batch_started_at")
            snapshot = json.loads((Path(work)/'triton'/report["snapshot_path"]).read_text("utf-8"))
            self.assertEqual(len(snapshot["repositories"]), 1)
            self.assertIn("github:triton-lang/triton-ascend", snapshot["repositories"])


class SnapshotArtifactTests(unittest.TestCase):
    def test_write_snapshot_returns_a_stable_sha256(self):
        with tempfile.TemporaryDirectory() as work:
            path, sha = write_snapshot(work, "ubs", {"a": 1})
            self.assertEqual(path.name, "snapshot.json")
            self.assertEqual(len(sha), 64)
            self.assertTrue(path.exists())

    def test_collect_repositories_without_repos_fails_honestly(self):
        project = {"project_id": "empty", "collector": "x", "window": {"hours": 24, "time_basis": "t"}}
        context = make_context()
        report = collect_repositories(
            project, context, "/tmp/irrelevant",
            runner=runner_returning({}), now=lambda: "2026-10-10T00:10:00Z",
        )
        self.assertEqual(report["collection_status"], "failed")
        self.assertEqual(report["task_status"], "failed")


if __name__ == "__main__":
    unittest.main()
