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


def rollback_deploy(
    store,
    failed_release_id: str,
    baseline_release_id: str,
    *,
    deploy_fn,
    verify_fn,
    reason: str | None = None,
) -> dict:
    """Execute a real recovery deployment and re-verify (UDR-030).

    The trusted baseline is loaded from the immutable archive — collection is
    never a rollback and no source request is made. The failed candidate must
    not already be the current verified release, and a nearer verified pointer
    must not be overwritten. Only a re-verification pass reports recovery;
    otherwise the live state is preserved with a manual-entry reason.
    """
    from .baseline import BaselineError

    pointer = store.pointer() or {}
    current = pointer.get("current")
    if failed_release_id == current:
        raise BaselineError(
            f"cannot rollback: {failed_release_id!r} is the current verified release"
        )
    if current != baseline_release_id:
        raise BaselineError(
            f"refusing to overwrite nearer verified release {current!r} with {baseline_release_id!r}"
        )
    # Load the trusted complete bundle from the immutable archive (no re-collect).
    manifest, files = store.read_archive(baseline_release_id)
    try:
        deploy_fn(baseline_release_id, files)
    except Exception as exc:
        return {
            "recovered": False,
            "failed_release_id": failed_release_id,
            "active_release_id": current,
            "reason": f"recovery deployment failed: {exc!r}",
            "manual_entry": "restore the trusted bundle manually and re-verify",
        }
    receipt = verify_fn(baseline_release_id, manifest)
    if not receipt.get("verified"):
        return {
            "recovered": False,
            "failed_release_id": failed_release_id,
            "active_release_id": current,
            "reason": "re-verification failed after recovery deployment",
            "manual_entry": "inspect the live site and the failed candidate",
            "receipt": receipt,
        }
    return {
        "recovered": True,
        "failed_release_id": failed_release_id,
        "active_release_id": baseline_release_id,
        "reason": reason or f"deployment verification failed for {failed_release_id}",
        "receipt": receipt,
    }