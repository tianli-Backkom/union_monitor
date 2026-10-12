"""UDR-002: cross-version PR identity recovery without double-counting.

Recovery may only use explicit run association or unique, credible
fork/branch/historical-SHA evidence. A run left unresolved for lack of such
evidence stays unresolved (never "recovered"); a source request failure
propagates instead of being re-labelled unknown; and when evidence later
completes, each run/attempt is recovered exactly once with a change record
preserving the previous unknown state.
"""
import unittest

from triton.dashboard import build_batches
from triton.pr_identity import PRResolver, association_error_kind, recover_identities
from test_triton_pr_identity import FakeAPI, action_run, pull


def unresolved_run(sha="a" * 40):
    run = action_run(sha=sha)
    run.update(pr=None, pr_url=None, pr_title=None, base_branch=None,
               pr_evidence={"method": "unresolved", "run_id": run["id"],
                            "error": "no unique credible evidence"})
    return run


class AssociationErrorKindTests(unittest.TestCase):
    def test_ordinary_unknown_is_unknown(self):
        self.assertEqual(association_error_kind(ValueError("ambiguous")), "unknown")

    def test_source_failure_is_not_unknown(self):
        self.assertEqual(association_error_kind(RuntimeError("rate limited")), "source_failure")
        self.assertEqual(association_error_kind(ConnectionError("offline")), "source_failure")


class PRIdentityRecoveryTests(unittest.TestCase):
    def test_missing_historical_sha_evidence_is_not_claimed_recovered(self):
        # PR #2513 shares fork/branch but its current head differs and no
        # historical commit proves the run's head_sha.
        run = unresolved_run()
        api = FakeAPI([pull(2513, "c" * 40)], commits={2513: []})
        records = recover_identities([run], PRResolver(api))
        self.assertEqual(records, [])
        self.assertIsNone(run.get("pr"))
        self.assertEqual(run["pr_evidence"]["method"], "unresolved")
        self.assertNotIn("recovery", run)

    def test_source_request_failure_propagates_instead_of_becoming_unknown(self):
        run = unresolved_run()
        api = FakeAPI([pull(2513)], failure=RuntimeError("rate limited"))
        with self.assertRaisesRegex(RuntimeError, "rate limited"):
            recover_identities([run], PRResolver(api))
        # The run still carries its honest unresolved gap, not a fake recovery.
        self.assertEqual(run["pr_evidence"]["method"], "unresolved")
        self.assertNotIn("recovery", run)

    def test_later_evidence_recovers_once_with_change_record(self):
        run = unresolved_run()
        # Evidence completes: the PR's commit history now proves the run's SHA.
        api = FakeAPI([pull(2513, "c" * 40)], commits={2513: ["a" * 40, "c" * 40]})
        records = recover_identities([run], PRResolver(api))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["run_id"], run["id"])
        self.assertEqual(records[0]["attempt"], 1)
        self.assertEqual(records[0]["pr"], 2513)
        self.assertEqual(records[0]["head_sha"], "a" * 40)
        self.assertEqual(records[0]["recovered_method"], "source_repository+branch+pr_commit_history")
        # Migration evidence preserves the previous unknown state.
        self.assertEqual(records[0]["previous"]["method"], "unresolved")
        self.assertEqual(run["pr"], 2513)
        self.assertEqual(run["head_sha"], "a" * 40)

    def test_recovered_run_is_counted_exactly_once(self):
        run = unresolved_run()
        api = FakeAPI([pull(2513, "c" * 40)], commits={2513: ["a" * 40, "c" * 40]})
        recover_identities([run], PRResolver(api))
        batches = build_batches([run], "2026-10-07T09:00:00Z")
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["pr"], 2513)
        workflows = batches[0]["workflows"]
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["attempt"], 1)

    def test_already_associated_runs_are_not_reprocessed(self):
        run = action_run()
        run["pr"] = 42
        run["pr_evidence"] = {"method": "run.pull_requests.head.sha", "run_id": run["id"],
                              "pr": 42, "resolved_head_sha": "a" * 40}
        api = FakeAPI([pull(42)])
        records = recover_identities([run], PRResolver(api))
        self.assertEqual(records, [])
        self.assertEqual(run["pr"], 42)


if __name__ == "__main__":
    unittest.main()
