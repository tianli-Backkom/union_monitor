"""Unified production round orchestration (UDR-024).

A single production round orchestrates every enabled project from one frozen
run context: a pre-check runs first (a failure or cancellation performs no
collection/deploy side effect), then each project runs under its own
catalog-declared timeout with failure isolation, and the aggregate is built
only after all projects reach a terminal state. A virtual clock drives both the
per-project deadline and the retry budget so tests never wait real minutes.

The orchestration is community-agnostic: it iterates ``enabled_project_ids()``
and never branches on a hardcoded project id.
"""

from __future__ import annotations

from .context import iso_utc


class TransientCollectError(RuntimeError):
    """A transient collector failure (rate limit, 503) that may succeed on retry."""


def retry_collect(fn, *, max_attempts=3, backoff=0.25, clock, sleep, is_transient=None):
    """Run ``fn(attempt)`` under a transient-retry budget on the virtual clock.

    A transient failure sleeps ``backoff`` virtual seconds and retries, up to
    ``max_attempts`` total calls; a non-transient failure propagates immediately.
    """
    is_transient = is_transient or (lambda exc: isinstance(exc, TransientCollectError))
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(attempt)
        except Exception as exc:  # noqa: BLE001 - classify, then re-raise or retry
            if not is_transient(exc):
                raise
            last = exc
            if attempt < max_attempts:
                sleep(backoff)
    raise last


def _terminal(pid, event, status, detail):
    return {"project_id": pid, "task_status": status, "collection_status": "failed",
            "validation_status": "failed", "exit_code": 1, "error": f"{event}: {detail}", "errors": [detail]}


def run_round(catalog, context, *, collectors, clock, sleep,
              precheck=None, work_dir=None):
    """Run one production round and return ``(reports, aggregate)``.

    ``collectors`` maps project id -> ``fn(project, context, work_dir)->report``.
    The pre-check (when given) runs first; if it raises, no collector runs and
    the returned aggregate name the failure. Per-project deadlines come from the
    catalog ``timeout_minutes`` and are evaluated against the virtual clock.
    """
    if precheck is not None:
        try:
            precheck()  # a raise aborts before any collection side effect
        except Exception as exc:  # noqa: BLE001 - report, then stop the round
            return {}, {"run_id": context.run_id, "code_sha": context.code_sha,
                        "cutoff_at": iso_utc(context.cutoff_at), "projects": {},
                        "all_terminal": False, "precheck_failure": repr(exc)}
    start = clock()
    reports = {}
    for pid in catalog.enabled_project_ids():
        project = catalog.project(pid)
        deadline = start + project["timeout_minutes"] * 60
        fn = collectors.get(pid)
        if fn is None:
            reports[pid] = _terminal(pid, "no collector registered", "failed", "no collector registered")
            continue
        try:
            report = fn(project, context, work_dir)
            if not isinstance(report, dict):
                reports[pid] = _terminal(pid, "collector result", "failed",
                                         f"collector returned {type(report).__name__}, expected dict")
            elif clock() > deadline:
                reports[pid] = _terminal(pid, "deadline", "timeout",
                                         f"project exceeded its {project['timeout_minutes']}-minute deadline")
            else:
                reports[pid] = dict(report)
        except TimeoutError as exc:
            reports[pid] = _terminal(pid, "collector", "timeout", str(exc))
        except Exception as exc:  # noqa: BLE001 - isolate every project's failure
            reports[pid] = _terminal(pid, "collector", "failed", repr(exc))
    return reports, _aggregate(context, reports)


def _aggregate(context, reports):
    statuses = {pid: report.get("task_status") for pid, report in reports.items()}
    all_terminal = all(status in ("success", "partial", "failed", "timeout", "cancelled")
                       for status in statuses.values())
    return {
        "run_id": context.run_id,
        "code_sha": context.code_sha,
        "cutoff_at": iso_utc(context.cutoff_at),
        "projects": statuses,
        "all_terminal": all_terminal,
    }