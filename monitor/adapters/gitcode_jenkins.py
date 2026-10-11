"""UBS GitCode/Jenkins PR gate collector adapter (T-012).

Wraps the read-only ``collect.py`` collector (repo root) behind a
``runner(repository, project, context) -> dict`` seam. Unit tests inject a fake
runner; the workflow uses the default runner that drives ``collect.py``'s
``run`` per repository. The nine repository snapshots aggregate into one
project snapshot (see :func:`monitor.adapters.collect_repositories`).
"""

from __future__ import annotations

from ..context import iso_utc, utc_time
from . import collect_repositories


def repo_key(repository_id: str) -> str:
    """``gitcode:openeuler/ubs-engine`` -> ``openeuler/ubs-engine``."""
    return repository_id.split(":", 1)[1] if ":" in repository_id else repository_id


def _default_runner(repository, project, context):
    """Drive ``collect.py`` for one repository. Network path (workflow only)."""
    try:
        import collect as ubs_collect
    except Exception as exc:  # pragma: no cover - exercised in the workflow, not unit tests
        raise RuntimeError(f"cannot import collect.py: {exc}") from exc
    key = repo_key(repository["repository_id"])
    config = next((c for c in ubs_collect.CONFIG if c["repository"] == key), None)
    if config is None:
        raise ValueError(f"no collect.py config for repository {key}")
    import types

    hours = project["window"]["hours"]
    if hours % 24 or repository['target_branches'] != ['master']:
        raise ValueError('legacy collector requires whole-day windows and the master target branch')
    args = types.SimpleNamespace(
        days=int(hours / 24),
        until=iso_utc(context.cutoff_at),
        workers=4,
        refresh=True,
        offline=False,
        limit=0,
    )
    return ubs_collect.run(args, config)


def validate_snapshot(repository, project, context, snapshot):
    """Check the legacy source contract; this is not a full raw-source audit."""
    errors = []
    meta = snapshot.get('meta') or {}
    expected = repo_key(repository['repository_id'])
    if meta.get('repository') != expected:
        errors.append('snapshot repository does not match the requested repository')
    if meta.get('branch') not in repository['target_branches']:
        errors.append('snapshot target branch does not match the requested branches')
    window = context.window_for(project)
    for key, timestamp in (('start_ms', 'start_at'), ('end_ms', 'end_at')):
        if meta.get(key) != round(utc_time(window[timestamp]).timestamp()*1000):
            errors.append(f'{key} does not match the frozen window')
    for issue in meta.get('errors') or []:
        errors.append(str(issue.get('reason', issue)) if isinstance(issue, dict) else str(issue))
    prs = snapshot.get('prs')
    if not isinstance(prs, list):
        errors.append('snapshot prs is not an array')
    else:
        seen = set()
        for pr in prs:
            if not isinstance(pr, dict) or pr.get('repository') != expected or not isinstance(pr.get('number'), int):
                errors.append('PR identity is missing or belongs to another repository')
                continue
            if pr['number'] in seen:
                errors.append('duplicate PR identity')
            seen.add(pr['number'])
            if not isinstance(pr.get('events'), list) or not isinstance(pr.get('batches'), list):
                errors.append(f'PR {pr["number"]} has no usable events/batches arrays')
    return {'passed': not errors, 'errors': errors, 'warnings': []}


def collect(project, context, work_dir, *, runner=None, now=None):
    """Collect every UBS repository and return the partial collection report."""
    return collect_repositories(
        project, context, work_dir, runner=runner or _default_runner, now=now,
        validator=validate_snapshot,
    )
