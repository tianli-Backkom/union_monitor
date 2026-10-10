"""Prepare step: freeze a run context and emit the dynamic project matrix (T-012).

``plan`` reads the catalog, freezes one run context shared by every enabled
project, and produces the JSON ``matrix`` that GitHub Actions consumes via
``fromJSON``. No main-flow logic branches on a hardcoded project id.
"""

from __future__ import annotations

import hashlib
import json

from .catalog import Catalog
from .context import RunContext


def catalog_fingerprint(data: dict) -> str:
    """Deterministic SHA-256 of the catalog (stable key order, compact separators)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_context(
    catalog: Catalog,
    *,
    run_id: str,
    code_sha: str,
    cutoff_at: str,
    scheduled_for: str | None = None,
    started_at: str | None = None,
    trigger: str = "schedule",
    artifact_root: str | None = None,
    publish_mode: str = "normal",
    catalog_sha256: str | None = None,
) -> dict:
    context = RunContext(
        run_id=run_id,
        code_sha=code_sha,
        cutoff_at=cutoff_at,
        scheduled_for=scheduled_for,
        started_at=started_at,
        trigger=trigger,
        catalog_sha256=catalog_sha256 or catalog_fingerprint(catalog.data),
        project_ids=catalog.enabled_project_ids(),
        artifact_root=artifact_root,
        publish_mode=publish_mode,
    )
    return context.as_dict()


def build_matrix(catalog: Catalog) -> dict:
    """Emit a GitHub Actions ``matrix.include`` covering every enabled project."""
    include = []
    for project in catalog.enabled_projects():
        include.append(
            {
                "project_id": project["project_id"],
                "display_name": project.get("display_name", project["project_id"]),
                "collector": project["collector"],
                "metric_profile": project["metric_profile"],
                "view_profile": project["view_profile"],
                "timeout_minutes": project["timeout_minutes"],
                "repositories": [r["repository_id"] for r in project["repositories"]],
            }
        )
    return {"include": include}


def plan(catalog: Catalog, *, run_id: str, code_sha: str, cutoff_at: str, **kwargs) -> tuple[dict, dict]:
    """Return ``(context, matrix)`` frozen from the catalog and shared cutoff."""
    return build_context(catalog, run_id=run_id, code_sha=code_sha, cutoff_at=cutoff_at, **kwargs), build_matrix(catalog)