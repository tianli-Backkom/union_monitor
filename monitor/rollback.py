"""Trusted rollback (T-013).

When deployment verification fails, the pipeline re-points the authoritative
verified-release pointer at the last trusted baseline. A rollback never edits
the failed candidate or its already-written reports; it records the rollback
decision and the baseline identity so the next round re-verifies against the
known-good release.
"""

from __future__ import annotations


def should_rollback(verification: dict) -> bool:
    return not bool(verification.get("verified", False))


def rollback(
    failed_release_id: str,
    baseline_release: dict,
    *,
    reason: str | None = None,
    schema_version: int = 1,
) -> dict:
    """Build the rollback record that points back to the trusted baseline."""
    return {
        "schema_version": schema_version,
        "action": "rollback",
        "failed_release_id": failed_release_id,
        "active_release_id": baseline_release.get("release_id"),
        "baseline_run_id": baseline_release.get("run_id"),
        "baseline_status": baseline_release.get("release_status"),
        "reason": reason or f"deployment verification failed for {failed_release_id}",
    }