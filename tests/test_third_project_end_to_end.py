"""UDR-034: a third project joins by configuration through the real full chain."""
import copy
import json
import unittest
from pathlib import Path

from monitor.adapters import collect_repositories
from monitor.catalog import Catalog
from monitor.collect import build_report
from monitor.context import RunContext
from monitor.plan import build_matrix

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))

RUN_ID = "synthetic-20261010-0730-attempt-1"
CODE_SHA = "9aec47355689c243f3f8c35cab40fd275c0e8441"
CUTOFF = "2026-10-09T23:30:00Z"


def third_project_catalog(window_hours=25):
    data = copy.deepcopy(BASE)
    data["projects"].append({
        "project_id": "acme",
        "display_name": "Acme CI",
        "enabled": True,
        "collector": "github-actions-v1",
        "metric_profile": "triton-commit-attempt-v1",
        "view_profile": "commit-attempt-v1",
        "window": {"time_basis": "batch_started_at", "hours": window_hours},
        "timeout_minutes": 45,
        "repositories": [{"repository_id": "github:acme/eng-dashboard", "target_branches": ["release"]}],
    })
    return data


class ThirdProjectEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.from_dict(third_project_catalog())
        self.context = RunContext(run_id=RUN_ID, code_sha=CODE_SHA, cutoff_at=CUTOFF,
                                  project_ids=["ubs", "triton", "acme"])

    def test_tc01_window_not_rounded_and_data_attributed_to_third_repo(self):
        project = self.catalog.project("acme")
        self.assertEqual(project["window"]["hours"], 25)
        self.assertEqual(project["repositories"][0]["repository_id"], "github:acme/eng-dashboard")
        self.assertEqual(project["repositories"][0]["target_branches"], ["release"])

        def runner(repo, proj, ctx):
            self.assertEqual(repo["repository_id"], "github:acme/eng-dashboard")
            return {"collected_at": "2026-10-10T00:05:00Z", "repository": repo["repository_id"]}

        def validator(repo, proj, ctx, payload):
            self.assertEqual(payload["repository"], "github:acme/eng-dashboard")
            return {"passed": True, "errors": [], "warnings": []}

        partial = collect_repositories(project, self.context, str(ROOT / ".tmp-third"),
                                       runner=runner, validator=validator)
        report = build_report({"run_id": RUN_ID, "project_id": "acme", "code_sha": CODE_SHA,
                               "collector": "github-actions-v1",
                               "metric_profile": "triton-commit-attempt-v1"}, partial,
                              "2026-10-10T00:06:00Z")
        self.assertEqual(report["collection_status"], "success")
        # 25 hours is preserved verbatim — never rounded to 24.
        self.assertEqual(report["window"]["hours"], 25)
        self.assertLess(report["window"]["start_at"], CUTOFF)

    def test_tc01_matrix_and_no_community_branch_in_shared_flow(self):
        matrix = build_matrix(self.catalog)
        acme = [e for e in matrix["include"] if e["project_id"] == "acme"][0]
        self.assertEqual(acme["repositories"], ["github:acme/eng-dashboard"])
        self.assertEqual(acme["timeout_minutes"], 45)
        # The shared per-project flow must not branch on a hardcoded community id.
        source = (ROOT / "monitor" / "adapters" / "__init__.py").read_text(encoding="utf-8")
        collect_src = source[source.index("def collect_repositories"):]
        self.assertNotIn("triton", collect_src)
        self.assertNotIn("ubs", collect_src)

    def test_tc02_identity_isolation_for_same_name_repo_and_pr(self):
        from monitor.identity import pr_id, repository_id
        # Same repo name across source instances and orgs never collides.
        self.assertNotEqual(repository_id("github", "acme", "eng-dashboard"),
                            repository_id("gitcode", "acme", "eng-dashboard"))
        self.assertNotEqual(repository_id("github", "acme", "eng-dashboard"),
                            repository_id("github", "other", "eng-dashboard"))
        # Same PR number in different repos stays distinct.
        self.assertNotEqual(pr_id("github:acme/eng-dashboard", 7),
                            pr_id("gitcode:openeuler/ubs-engine", 7))

    def test_tc02_undeclared_capability_has_no_fake_filter(self):
        project = self.catalog.project("acme")
        capabilities = self.catalog.data["view_profiles"][project["view_profile"]]["capabilities"]
        # The third project reuses a commit-attempt profile and does not declare
        # NPU or lifecycle; those must not be synthesised as zero/fake filters.
        self.assertNotIn("pr_lifecycle", capabilities)
        self.assertNotIn("npu", [c.lower() for c in capabilities])


if __name__ == "__main__":
    unittest.main()