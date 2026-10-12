"""UDR-025: release concurrency — mutual exclusion, FIFO queue, anti-old-overwrite."""
import unittest

from monitor.release_lock import (LockHeldError, ReleaseLock, RoundQueue,
                                  reconcile_deploy_state, should_deploy)


class ReleaseLockTests(unittest.TestCase):
    def test_lock_is_mutually_exclusive(self):
        lock = ReleaseLock()
        lock.acquire()
        with self.assertRaises(LockHeldError):
            lock.acquire()
        lock.release()
        lock.acquire()  # free again
        lock.release()

    def test_context_manager_releases(self):
        lock = ReleaseLock()
        with lock:
            self.assertTrue(lock.held)
        self.assertFalse(lock.held)

    def test_release_without_acquire_raises(self):
        lock = ReleaseLock()
        with self.assertRaises(RuntimeError):
            lock.release()


class ShouldDeployTests(unittest.TestCase):
    def test_newer_cutoff_may_deploy(self):
        allowed, reason = should_deploy("2026-10-10T00:00:00Z", 1, "2026-10-09T00:00:00Z", 1)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_older_cutoff_is_blocked(self):
        allowed, reason = should_deploy("2026-10-09T00:00:00Z", 1, "2026-10-10T00:00:00Z", 1)
        self.assertFalse(allowed)
        self.assertIn("older cutoff", reason)

    def test_same_cutoff_lower_attempt_is_blocked(self):
        allowed, reason = should_deploy("2026-10-10T00:00:00Z", 1, "2026-10-10T00:00:00Z", 2)
        self.assertFalse(allowed)
        self.assertIn("higher attempt", reason)

    def test_same_cutoff_higher_attempt_is_allowed(self):
        allowed, _ = should_deploy("2026-10-10T00:00:00Z", 3, "2026-10-10T00:00:00Z", 2)
        self.assertTrue(allowed)

    def test_no_baseline_is_first_run(self):
        allowed, _ = should_deploy("2026-10-10T00:00:00Z", 1, None, None)
        self.assertTrue(allowed)


class RoundQueueTests(unittest.TestCase):
    def test_in_flight_round_is_never_cancelled_and_later_rounds_queue_fifo(self):
        queue = RoundQueue()
        self.assertEqual(queue.submit("A"), "running")
        self.assertEqual(queue.submit("B"), "queued")
        self.assertEqual(queue.submit("C"), "queued")
        self.assertEqual(queue.in_flight, "A")  # A is still running, never replaced
        self.assertEqual(queue.pending(), ["B", "C"])  # FIFO, B not replaced by C
        self.assertEqual(queue.finish(), "B")
        self.assertEqual(queue.finish(), "C")
        self.assertIsNone(queue.finish())

    def test_capacity_rejects_without_replacing(self):
        queue = RoundQueue(capacity=1)
        queue.submit("A")
        queue.submit("B")
        self.assertEqual(queue.submit("C"), "rejected")
        self.assertEqual(queue.pending(), ["B"])  # C did not replace B


class ReconcileTests(unittest.TestCase):
    def test_no_accepted_deploy_is_clean(self):
        self.assertEqual(reconcile_deploy_state(None, None, None)["status"], "clean")

    def test_live_but_unreconciled_deploy_needs_reconcile(self):
        result = reconcile_deploy_state("rel-2", "rel-1", "rel-2")
        self.assertEqual(result["status"], "needs_reconcile")

    def test_pointer_ahead_of_site_needs_reconcile(self):
        result = reconcile_deploy_state("rel-1", "rel-2", "rel-2")
        self.assertEqual(result["status"], "needs_reconcile")

    def test_consistent_state_is_clean(self):
        result = reconcile_deploy_state("rel-2", "rel-2", "rel-2")
        self.assertEqual(result["status"], "clean")


if __name__ == "__main__":
    unittest.main()