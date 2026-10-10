"""Collection report and per-project release status contracts (T-012, T-013).

A report expresses collection, validation, exit code, sample counts, source
coverage, errors, cache source, window and file fingerprints separately; a legal
zero-sample success is not an interface-contract failure.

Per-project user-visible status combines three independent facts: ``task_status``
(this round), ``data_mode`` (fresh / fallback / unavailable) and time context
(planned / cutoff / collected / version-generated / deploy-verified). A failed
round that reuses old data stays ``task_status=failed`` with ``data_mode=fallback``
and keeps the old data time; it is never relabelled ``success``.
"""

from __future__ import annotations

from typing import Optional

from .catalog import Catalog, CatalogError
from .context import RunContext, utc_time

TASK_STATUSES = frozenset({"success", "partial", "failed", "timeout", "cancelled"})
COLLECTION_STATUSES = frozenset({"success", "failed"})
VALIDATION_STATUSES = frozenset({"passed", "failed"})
DATA_MODES = frozenset({"fresh", "fallback", "unavailable"})


def choose_data_mode(
    task_status: str,
    *,
    has_fresh_bundle: bool,
    has_trusted_fallback: bool,
) -> str:
    """Select fresh/fallback/unavailable from the round result and baselines.

    - at least one accepted project produces ``fresh``;
    - a failed/thin round with a trusted previous snapshot is ``fallback``;
    - no trusted previous snapshot is ``unavailable``.
    """
    if task_status not in TASK_STATUSES:
        raise ValueError(f"invalid task_status {task_status!r}")
    if has_fresh_bundle:
        return "fresh"
    if has_trusted_fallback:
        return "fallback"
    return "unavailable"


def classify_data_mode(task_status: str, has_fresh_bundle: bool, has_trusted_fallback: bool) -> str:
    return choose_data_mode(task_status, has_fresh_bundle=has_fresh_bundle, has_trusted_fallback=has_trusted_fallback)


def validate_report(report: dict, context: RunContext, catalog: Catalog) -> list[str]:
    """Return a list of contract violations (empty means structurally valid)."""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report must be an object"]

    for key in ("run_id", "code_sha", "project_id"):
        if not report.get(key):
            errors.append(f"report missing {key}")

    if report.get("run_id") and report["run_id"] != context.run_id:
        errors.append(f"run_id {report['run_id']!r} does not match context {context.run_id!r}")
    if report.get("code_sha") and report["code_sha"] != context.code_sha:
        errors.append("code_sha does not match the run context")

    project = None
    if report.get("project_id"):
        try:
            project = catalog.project(report["project_id"])
        except CatalogError:
            errors.append(f"unknown project_id {report['project_id']!r}")
    if project is None:
        return errors

    if report.get("collector") and report["collector"] != project["collector"]:
        errors.append(f"collector {report.get('collector')!r} does not match catalog {project['collector']!r}")
    if report.get("metric_profile") and report["metric_profile"] != project["metric_profile"]:
        errors.append(f"metric_profile {report.get('metric_profile')!r} does not match catalog {project['metric_profile']!r}")

    task_status = report.get("task_status")
    if task_status not in TASK_STATUSES:
        errors.append(f"invalid task_status {task_status!r}")
    if report.get("collection_status") not in COLLECTION_STATUSES:
        errors.append(f"invalid collection_status {report.get('collection_status')!r}")
    if report.get("validation_status") not in VALIDATION_STATUSES:
        errors.append(f"invalid validation_status {report.get('validation_status')!r}")

    if isinstance(report.get("exit_code"), int) and task_status == "success" and report["exit_code"] != 0:
        errors.append("successful report must have exit_code 0")

    window = report.get("window") or {}
    if window.get("time_basis") and window["time_basis"] != project["window"]["time_basis"]:
        errors.append(
            f"window time_basis {window['time_basis']!r} does not match catalog {project['window']['time_basis']!r}"
        )

    data_mode = report.get("data_mode", "fresh")
    if window.get("start_at") and window.get("end_at"):
        try:
            start, end = utc_time(window["start_at"]), utc_time(window["end_at"])
            span = (end - start).total_seconds()
            expected = project["window"]["hours"] * 3600
            if data_mode == "fresh":
                if end != context.cutoff_at:
                    errors.append("fresh window end_at must equal the run cutoff")
                if span != expected:
                    errors.append(
                        f"fresh window span {span}s does not match {project['window']['hours']}h"
                    )
            if data_mode == "fallback" and end >= context.cutoff_at:
                errors.append("fallback window must come from before this round's cutoff")
        except ValueError as exc:
            errors.append(f"invalid window timestamp: {exc}")

    samples = report.get("samples")
    if samples is not None and not isinstance(samples, dict):
        errors.append("samples must be an object")
    return errors


def is_legal_zero(report: dict) -> bool:
    """A successfully collected, validated report may carry zero samples."""
    return (
        report.get("collection_status") == "success"
        and report.get("validation_status") == "passed"
        and isinstance(report.get("samples"), dict)
    )