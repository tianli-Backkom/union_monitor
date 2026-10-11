"""Triton-Ascend GitHub Actions collector adapter (T-012).

Wraps ``triton.dashboard`` (repo root) behind a ``runner(repository, project,
context) -> dict`` seam. Unit tests inject a fake runner; the workflow uses the
default runner that drives ``triton.dashboard.collect`` and its real quality gate.
The single repository snapshot becomes the project snapshot (see
:func:`monitor.adapters.collect_repositories`).
"""

from __future__ import annotations

import json

from ..context import iso_utc, utc_time
from . import collect_repositories


def _default_runner(repository, project, context):
    """Drive ``triton.dashboard``. Network path (workflow only)."""
    try:
        from triton import dashboard as triton_dashboard
    except Exception as exc:  # pragma: no cover - exercised in the workflow, not unit tests
        raise RuntimeError(f"cannot import triton.dashboard: {exc}") from exc
    expected = 'github:' + triton_dashboard.REPO
    if repository['repository_id'] != expected:
        raise ValueError(f'collector does not support repository {repository["repository_id"]!r}; expected {expected!r}')
    # collect() already returns the payload and the actual observation time.
    return triton_dashboard.collect(
        hours=project['window']['hours'], as_of=iso_utc(context.cutoff_at),
    )


def validate_snapshot(repository, project, context, snapshot):
    """Validate saved source evidence, not just a claimed status in the payload."""
    from triton import dashboard, quality
    errors = []
    expected = repository['repository_id'].split(':', 1)[1]
    if snapshot.get('repo') != expected:
        errors.append('snapshot repository does not match the requested repository')
    window = context.window_for(project)
    for source_key, key in (('window_start', 'start_at'), ('window_end', 'end_at')):
        try:
            if utc_time(snapshot.get(source_key)) != utc_time(window[key]):
                errors.append(f'{source_key} does not match the frozen window')
        except (ValueError, TypeError, AttributeError):
            errors.append(f'{source_key} is missing or invalid')
    try:
        runs = json.loads((dashboard.EVIDENCE/'enriched-runs.json').read_text(encoding='utf-8'))
        if not isinstance(runs, list):
            raise ValueError('saved run evidence is not an array')
        report = quality.validate(runs, snapshot)
        errors.extend(report['errors'])
        return {'passed': not errors, 'errors': errors, 'warnings': report['warnings']}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append('quality evidence validation failed: ' + str(exc))
        return {'passed': False, 'errors': errors, 'warnings': []}


def collect(project, context, work_dir, *, runner=None, now=None):
    """Collect the Triton repository and return the partial collection report."""
    return collect_repositories(
        project, context, work_dir, runner=runner or _default_runner, now=now,
        validator=validate_snapshot,
    )
