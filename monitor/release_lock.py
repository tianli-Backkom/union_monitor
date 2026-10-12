"""Release concurrency: mutual exclusion, whole-round queueing and anti-old-overwrite (UDR-025).

One round covers every enabled project and awaits completion before the
aggregate. From trigger to promotion/rollback, a single non-reentrant release
lock serialises site writes. Pending rounds queue FIFO behind an in-flight
round (the in-flight round is never cancelled and later rounds never replace
each other). Before deploy or promotion the verified baseline is re-read, so an
older cutoff — or the same cutoff at a lower attempt — can never overwrite a
newer, already-verified release.
"""

from __future__ import annotations


class LockHeldError(RuntimeError):
    """A second writer tried to enter the release critical section."""


class ReleaseLock:
    """Non-reentrant mutual exclusion for deploy / promotion / rollback."""

    def __init__(self):
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> None:
        if self._held:
            raise LockHeldError("release lock is already held by another writer")
        self._held = True

    def release(self) -> None:
        if not self._held:
            raise RuntimeError("release lock is not held")
        self._held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def should_deploy(candidate_cutoff: str, candidate_attempt: int,
                  baseline_cutoff: str | None, baseline_attempt: int | None) -> tuple[bool, str | None]:
    """Decide whether a candidate may replace the current verified baseline.

    An older cutoff never deploys. An equal cutoff deploys only when it is an
    approved higher attempt of the same run; a lower or equal attempt does not.
    A newer cutoff always may.
    """
    if baseline_cutoff is None:
        return True, None
    if candidate_cutoff < baseline_cutoff:
        return False, "older cutoff cannot overwrite a newer baseline"
    if candidate_cutoff == baseline_cutoff:
        if (baseline_attempt or 0) >= (candidate_attempt or 0):
            return False, "same cutoff requires an approved higher attempt"
    return True, None


class RoundQueue:
    """Whole-round FIFO queue that never cancels the in-flight round.

    ``capacity`` models the platform's explicit pending bound: when set and
    full, a new submission is rejected rather than silently replacing a queued
    round.
    """

    def __init__(self, capacity: int | None = None):
        self.in_flight = None
        self._pending: list = []
        self.capacity = capacity

    def submit(self, round_id):
        if self.in_flight is None:
            self.in_flight = round_id
            return "running"
        if self.capacity is not None and len(self._pending) >= self.capacity:
            return "rejected"
        self._pending.append(round_id)
        return "queued"

    def finish(self):
        """Complete the in-flight round; promote the oldest queued round, if any."""
        self.in_flight = self._pending.pop(0) if self._pending else None
        return self.in_flight

    def pending(self) -> list:
        return list(self._pending)


def reconcile_deploy_state(public_release_id: str | None, pointer_current: str | None,
                           accepted_deploy_id: str | None) -> dict:
    """After a deploy was accepted then cancelled, reconcile public vs pointer.

    Returns ``{"status": ...}``. A deploy that is already live but not yet
    reflected in the verified pointer must be reconciled before the next round
    deploys; it must never be treated as "not deployed".
    """
    if accepted_deploy_id is None:
        return {"status": "clean", "reason": "no deploy was accepted"}
    if public_release_id == accepted_deploy_id and pointer_current != accepted_deploy_id:
        return {"status": "needs_reconcile", "public": public_release_id,
                "pointer": pointer_current, "accepted": accepted_deploy_id,
                "reason": "accepted deploy is live but the pointer is not yet reconciled"}
    if public_release_id != accepted_deploy_id and pointer_current == accepted_deploy_id:
        return {"status": "needs_reconcile", "public": public_release_id,
                "pointer": pointer_current, "accepted": accepted_deploy_id,
                "reason": "pointer advanced but the public site does not reflect it"}
    return {"status": "clean", "public": public_release_id,
            "pointer": pointer_current, "accepted": accepted_deploy_id}