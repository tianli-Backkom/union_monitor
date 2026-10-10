"""UBS GitCode/Jenkins PR gate collector adapter (T-012).

Wraps the read-only ``collect.py`` collector (repo root) behind a
``runner(repository, project, context) -> dict`` seam. Unit tests inject a fake
runner; the workflow uses the default runner that drives ``collect.py``'s
``run`` per repository. The nine repository snapshots aggregate into one
project snapshot (see :func:`monitor.adapters.collect_repositories`).
"""

from __future__ import annotations

from ..context import iso_utc
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

    hours = int(project["window"]["hours"])
    args = types.SimpleNamespace(
        days=max(1, round(hours / 24) or 1),
        until=iso_utc(context.cutoff_at),
        workers=4,
        refresh=True,
        offline=False,
        limit=0,
    )
    return ubs_collect.run(args, config)


def collect(project, context, work_dir, *, runner=None, now=None):
    """Collect every UBS repository and return the partial collection report."""
    return collect_repositories(
        project, context, work_dir, runner=runner or _default_runner, now=now,
    )