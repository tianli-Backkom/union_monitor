"""P-013: per-project three-axis status view model.

The user-visible status separates three independent facts so no axis is ever
derived from another:

1. **task result** — this round's outcome (success/partial/failed/timeout/
   cancelled), run id, code sha, frozen cutoff, start/end, exit code, error;
2. **data version/mode** — snapshot identity, metric profile, fresh/fallback/
   unavailable, validation status;
3. **data time/freshness** — the *data's* ``collected_at`` and window, kept
   distinct from the publish time, plus the planned schedule.

A failed round that reuses old data keeps ``task_status=failed``,
``data_mode=fallback`` and the OLD ``collected_at``/``window`` — never
relabelled success and never presented as if freshly collected at publish time.
"""

from __future__ import annotations

TASK_STATUSES = ("success", "partial", "failed", "timeout", "cancelled")
DATA_MODES = ("fresh", "fallback", "unavailable")


def _norm_task(status):
    return status if status in TASK_STATUSES else "failed"


def _norm_mode(mode):
    return mode if mode in DATA_MODES else "unavailable"


def task_axis(report: dict | None) -> dict:
    """Axis 1: this round's task result."""
    report = report or {}
    window = report.get("window") or {}
    return {
        "task_status": _norm_task(report.get("task_status")),
        "run_id": report.get("run_id"),
        "code_sha": report.get("code_sha"),
        "cutoff_at": window.get("end_at"),
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "exit_code": report.get("exit_code"),
        "error": report.get("error"),
    }


def data_axis(entry: dict | None, report: dict | None = None) -> dict:
    """Axis 2: which data version/mode the project is actually showing."""
    entry = entry or {}
    report = report or {}
    return {
        "data_mode": _norm_mode(entry.get("data_mode")),
        "snapshot_version": entry.get("snapshot_version"),
        "snapshot_sha256": entry.get("snapshot_sha256"),
        "metric_profile": entry.get("metric_profile"),
        "validation_status": report.get("validation_status"),
        "source_release_id": entry.get("source_release_id"),
    }


def time_axis(
    entry: dict | None,
    *,
    published_at: str | None = None,
    schedule_time: str | None = None,
) -> dict:
    """Axis 3: the data's actual time, separate from when it was published."""
    entry = entry or {}
    collected_at = entry.get("collected_at")
    window = entry.get("window")
    delayed = None
    if schedule_time and published_at:
        delayed = published_at > schedule_time
    return {
        "collected_at": collected_at,
        "window": window,
        "published_at": published_at,
        "schedule_time": schedule_time,
        "delayed": delayed,
    }


def project_status(
    report: dict | None,
    entry: dict | None,
    *,
    published_at: str | None = None,
    schedule_time: str | None = None,
) -> dict:
    """Combine the three axes; entry carries the data-version/time facts."""
    return {
        "task_result": task_axis(report),
        "data_version": data_axis(entry, report),
        "data_time": time_axis(entry, published_at=published_at, schedule_time=schedule_time),
    }
