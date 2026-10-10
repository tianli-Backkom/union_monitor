"""Contract tests for stable identities (T-005)."""

import unittest

from monitor.identity import (
    batch_id_for_attempt,
    batch_id_for_commit,
    batch_id_for_trigger,
    pr_id,
    repository_id,
    split_repository_id,
    task_id,
)


class RepositoryIdentityTests(unittest.TestCase):
    def test_repository_id_is_case_preserved(self):
        self.assertEqual(repository_id("github", "OpenEuler", "UBS-Core"), "github:OpenEuler/UBS-Core")

    def test_repository_id_requires_all_parts(self):
        for args in (("", "owner", "repo"), ("id", "", "repo"), ("id", "owner", "")):
            with self.assertRaises(ValueError):
                repository_id(*args)

    def test_split_repository_id_round_trips(self):
        repo_id = repository_id("gitcode", "openeuler", "ubs-engine")
        self.assertEqual(split_repository_id(repo_id), ("gitcode", "openeuler", "ubs-engine"))

    def test_split_repo_rejects_malformed(self):
        for bad in ("nocolon", "no/slash", ":owner/repo", "id:owner", "id:owner/", "id:/repo", ":"):
            with self.assertRaises(ValueError):
                split_repository_id(bad)

    def test_same_name_repos_on_different_instances_do_not_collide(self):
        a = repository_id("gitcode", "openeuler", "ubs-engine")
        b = repository_id("github", "openeuler", "ubs-engine")
        self.assertNotEqual(a, b)

    def test_same_name_repos_in_different_orgs_do_not_collide(self):
        a = repository_id("github", "org-a", "repo")
        b = repository_id("github", "org-b", "repo")
        self.assertNotEqual(a, b)


class PRIdentityTests(unittest.TestCase):
    def test_pr_id_binds_source_instance_and_full_repository(self):
        self.assertEqual(pr_id("gitcode:openeuler/ubs-engine", 42), "gitcode:openeuler/ubs-engine#42")

    def test_same_number_prs_in_different_repos_do_not_collide(self):
        self.assertNotEqual(
            pr_id("gitcode:openeuler/ubs-engine", 42),
            pr_id("gitcode:openeuler/ubs-comm", 42),
        )

    def test_pr_number_must_be_positive(self):
        for bad in (0, -1, "42", None):
            with self.assertRaises(ValueError):
                pr_id("gitcode:openeuler/ubs-engine", bad)


class BatchIdentityTests(unittest.TestCase):
    def test_ubs_batch_identity_is_the_trigger_url(self):
        url = "https://openeulerjenkins.com/job/ubs/123/"
        self.assertEqual(batch_id_for_trigger(url), url)

    def test_ubs_batch_identity_rejects_empty(self):
        with self.assertRaises(ValueError):
            batch_id_for_trigger("")

    def test_triton_rerun_batch_identity_separates_attempts(self):
        run = "9876543210"
        self.assertEqual(batch_id_for_attempt(run, 1), "run:9876543210:attempt:1")
        self.assertEqual(batch_id_for_attempt(run, 2), "run:9876543210:attempt:2")
        self.assertNotEqual(batch_id_for_attempt(run, 1), batch_id_for_attempt(run, 2))

    def test_triton_first_commit_batch_identity_is_head_sha(self):
        self.assertEqual(batch_id_for_commit("abc123def"), "sha:abc123def")

    def test_task_identity_binds_batch_and_source_key(self):
        self.assertEqual(
            task_id("run:9:attempt:1", "job/42"),
            "run:9:attempt:1::task::job/42",
        )

    def test_identity_never_derives_from_title_or_position(self):
        # A bare title is not a valid identity input; only structured keys are.
        with self.assertRaises(ValueError):
            batch_id_for_trigger("")
        with self.assertRaises(ValueError):
            task_id("", "job/42")


if __name__ == "__main__":
    unittest.main()