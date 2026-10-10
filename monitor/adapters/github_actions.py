"""Triton-Ascend GitHub Actions collector adapter (T-012).

Wraps ``triton.dashboard`` (repo root) behind a ``runner(repository, project,
context) -> dict`` seam. Unit tests inject a fake runner; the workflow uses the
default runner that drives ``triton.dashboard.collect`` + ``build_payload``.
The single repository snapshot becomes the project snapshot (see
:func:`monitor.adapters.collect_repositories`).
"""

from __future__ import annotations

from ..context import iso_utc
from . import collect_repositories


def _default_runner(repository, project, context):
    """Drive ``triton.dashboard``. Network path (workflow only)."""
    try:
        from triton import dashboard as triton_dashboard
    except Exception as exc:  # pragma: no cover - exercised in the workflow, not unit tests
        raise RuntimeError(f"cannot import triton.dashboard: {exc}") from exc
    win = context.window_for(project)
    start = win["start_at"]
    end = win["end_at"]
    hours = int(project["window"]["hours"])
    collected_at = iso_utc(context.cutoff_at)
    runs = triton_dashboard.collect(hours=hours, as_of=context.cutoff_at)
    return triton_dashboard.build_payload(
        runs,
        window_start=start,
        window_end=end,
        collected_at=collected_at,
    )


def collect(project, context, work_dir, *, runner=None, now=None):
    """Collect the Triton repository and return the partial collection report."""
    return collect_repositories(
        project, context, work_dir, runner=runner or _default_runner, now=now,
    )