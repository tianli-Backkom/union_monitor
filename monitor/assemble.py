"""Assemble a candidate release manifest from project reports and baselines (T-013).

Fresh projects contribute their own snapshot references; a project whose round
failed or produced no acceptable data reuses the trusted baseline snapshot
(fallback) with its old window/collected time and a failed ``task_status``; a
failed project with no baseline is ``unavailable`` and carries no snapshot
reference. A release is publishable only when at least one project has fresh
data and every enabled project has an explicit result.
"""

from __future__ import annotations

from .catalog import Catalog
from .context import RunContext, iso_utc
from .report import TASK_STATUSES

RELEASE_STATUSES = frozenset({"candidate", "verified"})


def _fresh_entry(project: dict, report: dict) -> dict:
    return {
        "task_status": report.get("task_status", "success"),
        "data_mode": "fresh",
        "snapshot_version": report.get("snapshot_version"),
        "snapshot_path": report.get("snapshot_path"),
        "snapshot_sha256": report.get("snapshot_sha256"),
        "metric_profile": project["metric_profile"],
        "window": report.get("window"),
        "collected_at": report.get("collected_at"),
        "artifact": report.get("artifact"),
        "error": None,
    }


def _fallback_entry(project: dict, task_status: str, base: dict | None, error: str | None) -> dict:
    if base:
        entry = {
            "task_status": task_status,
            "data_mode": "fallback",
            "snapshot_version": base.get("snapshot_version"),
            "snapshot_path": base.get("snapshot_path"),
            "snapshot_sha256": base.get("snapshot_sha256"),
            "source_release_id": base.get("release_id"),
            "metric_profile": project["metric_profile"],
            "window": base.get("window"),
            "collected_at": base.get("collected_at"),
            "artifact": base.get("artifact"),
            "error": error,
        }
        entry = {k: v for k, v in entry.items() if v is not None}
        return entry
    return {
        "task_status": task_status,
        "data_mode": "unavailable",
        "metric_profile": project["metric_profile"],
        "error": error or "no trusted baseline and no acceptable fresh data",
    }


def _report_has_fresh_data(report: dict | None) -> bool:
    return bool(
        report
        and report.get("collection_status") == "success"
        and report.get("validation_status") == "passed"
        and report.get("snapshot_version")
        and report.get("snapshot_sha256")
    )


def assemble_release(
    catalog: Catalog,
    context: RunContext,
    reports: dict[str, dict | None],
    *,
    release_id: str,
    published_at: str,
    baseline: dict | None = None,
    baseline_release_id: str | None = None,
) -> dict:
    """Compose a candidate release manifest keyed by enabled project id."""
    baseline_projects = (baseline or {}).get("projects", {}) if baseline else {}
    projects: dict = {}
    for project in catalog.enabled_projects():
        pid = project["project_id"]
        report = reports.get(pid)
        if _report_has_fresh_data(report):
            projects[pid] = _fresh_entry(project, report)
            continue
        task_status = (report or {}).get("task_status") or "failed"
        if task_status not in TASK_STATUSES:
            task_status = "failed"
        base = baseline_projects.get(pid)
        error = (report or {}).get("error") if (report or {}).get("error") else None
        if report is None:
            error = "no collection report produced for this project"
        projects[pid] = _fallback_entry(project, task_status, base, error)

    return {
        "schema_version": 1,
        "release_id": release_id,
        "run_id": context.run_id,
        "code_sha": context.code_sha,
        "cutoff_at": iso_utc(context.cutoff_at),
        "published_at": published_at,
        "baseline_release_id": baseline_release_id,
        "release_status": "candidate",
        "projects": projects,
    }


def is_publishable(release: dict) -> bool:
    """Publishable iff >=1 project has fresh data and every project is explicit."""
    projects = list((release.get("projects") or {}).values())
    if not projects:
        return False
    has_fresh = any(p.get("data_mode") == "fresh" for p in projects)
    all_explicit = all(p.get("task_status") in TASK_STATUSES for p in projects)
    return has_fresh and all_explicit