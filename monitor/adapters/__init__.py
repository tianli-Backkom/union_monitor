"""Per-project collector adapters (T-012).

The catalog's ``collectors`` section maps each collector to an ``entrypoint``
(a ``module.submodule`` import path). :func:`resolve` imports that module and
returns its ``collect(project, context, work_dir) -> dict`` callable, which
returns a *partial* collection report:

* ``collection_status`` — ``"success"`` or ``"failed"``;
* on success: ``snapshot_version``, ``snapshot_sha256``, ``window``,
  ``collected_at`` and the written artifact path;
* optional ``validation_status``, ``errors``, ``warnings``.

A missing adapter module raises :class:`AdapterError`; the collect step then
records an honest ``failed`` report — it never fakes success.

:func:`collect_repositories` is the shared per-project orchestration both
adapters reuse: it runs each repository's collector, aggregates the results
into one project snapshot artifact, and shapes the partial report. A round with
zero usable repository results is an honest ``failed`` round.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..context import iso_utc, utc_time


class AdapterError(Exception):
    """A project's collector adapter cannot be located or invoked."""


def _default_now() -> str:
    return iso_utc(datetime.now(timezone.utc).replace(microsecond=0))


def entrypoint(catalog, project: dict) -> str:
    collector = project["collector"]
    collectors = catalog.data.get("collectors") or {}
    spec = collectors.get(collector)
    if not spec or not spec.get("entrypoint"):
        raise AdapterError(f"catalog collector {collector!r} has no entrypoint")
    return spec["entrypoint"]


def resolve(catalog, project: dict):
    """Import the adapter module and return its ``collect`` callable."""
    ep = entrypoint(catalog, project)
    try:
        module = importlib.import_module(ep)
    except ImportError as exc:
        raise AdapterError(f"adapter module {ep!r} unavailable: {exc}") from exc
    fn = getattr(module, "collect", None)
    if not callable(fn):
        raise AdapterError(f"{ep!r} exposes no collect()")
    return fn


def write_snapshot(work_dir, project_id: str, snapshot: dict):
    """Write a project snapshot artifact; return ``(path, sha256_hex)``."""
    out_dir = Path(work_dir) / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "snapshot.json"
    data = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def collect_repositories(project: dict, context, work_dir, *, runner, validator=None, now=None, schema_version: int = 3) -> dict:
    """Run each repository's collector and aggregate one project snapshot.

    ``runner(repository, project, context) -> dict`` is injected for tests; the
    adapters provide network-driving defaults. Returns a partial report that
    :func:`monitor.collect.build_report` normalizes.
    """
    clock = now or _default_now
    win = context.window_for(project)
    window = {
        "time_basis": win.get("time_basis"),
        "start_at": win["start_at"],
        "end_at": win["end_at"],
        "hours": project["window"]["hours"],
    }
    repos = project.get("repositories") or []
    failures: list = []
    snapshots: dict = {}
    warnings = []
    observations = []

    for repo in repos:
        try:
            payload = runner(repo, project, context)
            if not isinstance(payload, dict):
                raise ValueError('repository collector did not return an object')
            if validator is None:
                raise ValueError('no project quality validator was supplied')
            validation = validator(repo, project, context, payload)
            if not isinstance(validation, dict) or validation.get('passed') is not True:
                reasons = validation.get('errors') if isinstance(validation, dict) else None
                raise ValueError('; '.join(map(str, reasons or ['project quality validation failed'])))
            observed = payload.get('collected_at') or (payload.get('meta') or {}).get('collected_at')
            observations.append(utc_time(observed))
            warnings.extend(validation.get('warnings') or [])
            snapshots[repo["repository_id"]] = payload
        except Exception as exc:  # noqa: BLE001 - a failed repo is recorded, not fatal
            failures.append({"repository_id": repo["repository_id"], "reason": repr(exc)})

    if not snapshots:
        return {
            "collection_status": "failed",
            "task_status": "failed",
            "validation_status": "failed",
            "exit_code": 1,
            "error": '; '.join(f['reason'] for f in failures) or 'no repository data collected',
            "errors": [f["reason"] for f in failures] or ["no repository data collected"],
            "warnings": [],
        }

    collected_at = iso_utc(max(observations))
    snapshot = {
        "schema_version": schema_version,
        "project_id": project["project_id"],
        "run_id": context.run_id,
        "code_sha": context.code_sha,
        "collector": project["collector"],
        "window": window,
        "collected_at": collected_at,
        "repositories": snapshots,
        "errors": failures,
    }
    snapshot_path, snapshot_sha256 = write_snapshot(work_dir, project["project_id"], snapshot)
    error_reasons = [f["reason"] for f in failures]
    return {
        "collection_status": "failed" if failures else "success",
        "task_status": "partial" if failures else "success",
        "validation_status": "failed" if failures else "passed",
        "validation_scope": "adapter_project_gate",
        "exit_code": 1 if failures else 0,
        "snapshot_version": f'{project["project_id"]}@{collected_at}',
        "snapshot_path": snapshot_path.name,
        "snapshot_sha256": snapshot_sha256,
        "window": window,
        "collected_at": collected_at,
        "artifact": snapshot_path.name,
        "error": '; '.join(error_reasons) if failures else None,
        "errors": error_reasons,
        "warnings": warnings,
    }
