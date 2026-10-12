"""Unified run report: task/version/time axes with honest unknowns (UDR-032).

The report binds this round's run id/attempt, code SHA, cutoff, per-community
status and exit code, actual collection time, samples/gaps/errors and cache
source. The three axes (task result, data version, data time) are independent;
a missing report or missing metadata is ``unknown`` — never a zero and never a
silent ``failed``/``success``. An inconsistent report (wrong run/SHA/attribution/
snapshot) is rejected rather than trusted for display. Old-window data stays
viewable but is never mixed into this round's same-window aggregation, and a
reload reads only published data (no collection side effect).
"""

from __future__ import annotations

from .report import validate_report
from .status_view import project_status

UNKNOWN = "unknown"


def _unknown_axes(pid: str) -> dict:
    return {
        "project_id": pid,
        "task_result": {"task_status": UNKNOWN, "run_id": UNKNOWN, "code_sha": UNKNOWN,
                        "cutoff_at": UNKNOWN, "exit_code": UNKNOWN, "error": None},
        "data_version": {"data_mode": UNKNOWN, "snapshot_version": UNKNOWN,
                         "snapshot_sha256": UNKNOWN, "metric_profile": UNKNOWN},
        "data_time": {"collected_at": UNKNOWN, "window": UNKNOWN,
                      "published_at": UNKNOWN, "schedule_time": UNKNOWN},
    }


def _rejected(pid: str, problems: list[str]) -> dict:
    base = _unknown_axes(pid)
    base["rejected"] = True
    base["problems"] = problems
    return base


def _fresh_entry(report: dict) -> dict:
    return {
        "data_mode": report.get("data_mode", "fresh"),
        "snapshot_version": report.get("snapshot_version"),
        "snapshot_sha256": report.get("snapshot_sha256"),
        "metric_profile": report.get("metric_profile"),
        "collected_at": report.get("collected_at"),
        "window": report.get("window"),
    }


def build_run_report(context, catalog, reports, entries=None, *,
                     published_at: str | None = None,
                     schedule_time: str | None = None) -> dict:
    """Build the three-axis run report; read-only, no collection side effect.

    ``reports`` maps project id -> collection report (or ``None`` when missing);
    ``entries`` maps project id -> data-version/time entry for fallback/old data.
    """
    reports = reports or {}
    entries = entries or {}
    projects = {}
    for pid in catalog.enabled_project_ids():
        report = reports.get(pid)
        if report is None:
            projects[pid] = _unknown_axes(pid)
            continue
        problems = validate_report(report, context, catalog)
        if problems:
            projects[pid] = _rejected(pid, problems)
            continue
        entry = entries.get(pid) or _fresh_entry(report)
        projects[pid] = project_status(report, entry,
                                       published_at=published_at,
                                       schedule_time=schedule_time)
    return {
        "run_id": context.run_id,
        "code_sha": context.code_sha,
        "cutoff_at": context.as_dict()["cutoff_at"],
        "published_at": published_at,
        "projects": projects,
        "reload_read_only": True,  # a reload renders published data, never collects
    }