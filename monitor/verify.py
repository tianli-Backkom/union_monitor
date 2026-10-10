"""Public deployment verification (T-013).

After the sole Pages deploy, the pipeline compares the published release
manifest against the candidate it intended to publish. A deploy is verified
only when the release identity (release/run/code), the project set, and the
per-project data versions all match — never by assuming the push succeeded.
"""

from __future__ import annotations

REQUIRED_IDENTITY_FIELDS = ("release_id", "run_id", "code_sha", "cutoff_at")


def verify_deployment(deployed: dict, expected: dict) -> dict:
    """Compare a deployed public manifest against the expected candidate.

    Returns ``{"verified": bool, "problems": [str]}``.
    """
    if not isinstance(deployed, dict):
        return {"verified": False, "problems": ["deployed manifest is not an object"]}
    problems: list[str] = []
    for field in REQUIRED_IDENTITY_FIELDS:
        if deployed.get(field) != expected.get(field):
            problems.append(
                f"{field} mismatch: deployed {deployed.get(field)!r}, expected {expected.get(field)!r}"
            )
    deployed_projects = deployed.get("projects") or {}
    expected_projects = expected.get("projects") or {}
    for pid, entry in expected_projects.items():
        if pid not in deployed_projects:
            problems.append(f"project {pid!r} missing from deployed manifest")
            continue
        deployed_entry = deployed_projects[pid]
        if deployed_entry.get("data_mode") != entry.get("data_mode"):
            problems.append(f"project {pid!r} data_mode mismatch")
        if deployed_entry.get("snapshot_sha256") != entry.get("snapshot_sha256"):
            problems.append(f"project {pid!r} snapshot mismatch")
    return {"verified": not problems, "problems": problems}


def mark_verified(release: dict) -> dict:
    """Promote a candidate release manifest to verified."""
    verified = dict(release)
    verified["release_status"] = "verified"
    return verified
