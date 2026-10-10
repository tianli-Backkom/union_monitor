"""Collect a single project and emit its collection report (T-012).

:func:`collect_project` resolves the project's adapter entrypoint, invokes it
with the frozen run context, and returns a complete collection report. Any
failure — a missing adapter, an adapter exception, or an invalid result — maps
to an honest ``failed``/``timeout`` report with a real exit code, never a fake
zero-sample success. A legal zero-sample success is the adapter's explicit
``collection_status == "success"``, not a silent default.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .adapters import AdapterError, resolve
from .catalog import Catalog, CatalogError
from .context import RunContext, iso_utc


class CollectError(Exception):
    """The project id is unknown or the collect step cannot proceed."""


def _now() -> str:
    return iso_utc(datetime.now(timezone.utc).replace(microsecond=0))


def _base(catalog, project: dict, context: RunContext, started_at: str) -> dict:
    return {
        "schema_version": 1,
        "run_id": context.run_id,
        "project_id": project["project_id"],
        "code_sha": context.code_sha,
        "collector": project["collector"],
        "metric_profile": project["metric_profile"],
        "started_at": started_at,
    }


def _fail(base: dict, status: str, error: str, finished_at: str) -> dict:
    return {
        **base,
        "task_status": status,
        "collection_status": "failed",
        "validation_status": "failed",
        "exit_code": 1,
        "finished_at": finished_at,
        "error": error,
        "errors": [error],
    }


def build_report(base: dict, result: dict, finished_at: str) -> dict:
    """Normalize an adapter result into a complete collection report."""
    report = dict(result or {})
    report.update(base)  # identity fields always come from the frozen context
    report["finished_at"] = finished_at

    collection_ok = report.get("collection_status") == "success"
    if collection_ok:
        report["collection_status"] = "success"
        report.setdefault("validation_status", "passed")
        report.setdefault("exit_code", 0)
    else:
        report["collection_status"] = "failed"
        report.setdefault("validation_status", "failed")
        report.setdefault("exit_code", 1)

    from .report import TASK_STATUSES

    if report.get("task_status") not in TASK_STATUSES:
        report["task_status"] = (
            "success" if collection_ok and report["validation_status"] == "passed" else "failed"
        )

    report.setdefault("errors", [])
    report.setdefault("warnings", [])
    return report


def collect_project(
    catalog: Catalog,
    context: RunContext,
    project_id: str,
    work_dir: str,
    *,
    adapter=None,
    now=None,
) -> dict:
    """Collect ``project_id`` and return its collection report.

    ``adapter`` and ``now`` are injectable for tests; ``now`` is a zero-arg
    callable returning an ISO-8601 UTC string.
    """
    clock = now or _now
    started_at = clock()

    try:
        project = catalog.project(project_id)
    except CatalogError as exc:
        raise CollectError(str(exc)) from exc

    base = _base(catalog, project, context, started_at)

    try:
        fn = adapter if adapter is not None else resolve(catalog, project)
    except AdapterError as exc:
        return _fail(base, "failed", str(exc), started_at)

    try:
        result = fn(project, context, work_dir)
    except AdapterError as exc:
        return _fail(base, "failed", str(exc), clock())
    except TimeoutError as exc:
        return _fail(base, "timeout", str(exc), clock())
    except Exception as exc:  # noqa: BLE001 - adapter contract: any error is a failure
        return _fail(base, "failed", repr(exc), clock())

    finished_at = clock()
    if not isinstance(result, dict):
        return _fail(base, "failed", f"adapter returned {type(result).__name__}, expected dict", finished_at)

    return build_report(base, result, finished_at)
