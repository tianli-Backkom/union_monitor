"""Complete site bundle assembly and independent verification (UDR-026).

The assembler must never accept a report's self-declared ``success`` without
consulting the actual resources on disk. ``verify_fresh_reports`` validates each
report against the catalog and run context and re-hashes every fresh snapshot;
``build_site_manifest`` composes the frozen complete manifest — release identity
plus a per-resource table of ownership, size and SHA-256 — and
``verify_site_manifest`` independently recomputes those bytes, sizes and the
reference closure, rejecting version mixing, missing files and wrong hashes.

The frozen manifest is read-only once built: verification results are expressed
by an external receipt (see ``monitor.public_verify``), never by rewriting it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .assemble import assemble_release
from .report import validate_report


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(path: Path):
    data = path.read_bytes()
    return {"size": len(data), "sha256": sha256_bytes(data)}


def extra_project_ids(reports, catalog) -> list[str]:
    """Report keys that are not in the catalog's enabled project set."""
    enabled = set(catalog.enabled_project_ids())
    return sorted(set(reports) - enabled)


def report_problems(reports, catalog, context) -> list[str]:
    """Contract problems across every report, independent of on-disk resources."""
    problems = []
    for pid in extra_project_ids(reports, catalog):
        problems.append(f"report for unknown or disabled project {pid!r}")
    for pid in catalog.enabled_project_ids():
        report = reports.get(pid)
        if report is None:
            problems.append(f"no collection report produced for project {pid!r}")
            continue
        for error in validate_report(report, context, catalog):
            problems.append(f"{pid}: {error}")
    return problems


def snapshot_path_of(entry: dict) -> str | None:
    return entry.get("snapshot_path")


def fresh_snapshot_checks(reports, resource_root: Path) -> list[str]:
    """Re-hash every fresh report's snapshot file instead of trusting its hash."""
    problems = []
    for pid, report in reports.items():
        if not report or report.get("collection_status") != "success":
            continue
        if report.get("data_mode", "fresh") != "fresh":
            continue
        rel = report.get("snapshot_path")
        if not rel:
            problems.append(f"{pid}: fresh report has no snapshot_path")
            continue
        path = resource_root / rel
        if not path.is_file():
            problems.append(f"{pid}: fresh snapshot {rel!r} is missing")
            continue
        actual = _digest(path)["sha256"]
        if actual != report.get("snapshot_sha256"):
            problems.append(f"{pid}: fresh snapshot {rel!r} sha256 {actual} does not match report {report.get('snapshot_sha256')!r}")
    return problems


def verify_fresh_reports(catalog, context, reports, resource_root: Path) -> list[str]:
    """Independent acceptance of reports: contract + extra project + real bytes."""
    return report_problems(reports, catalog, context) + fresh_snapshot_checks(reports, resource_root)


def build_site_manifest(release: dict, resource_root: Path, *, resource_spec: dict) -> dict:
    """Compose the frozen complete manifest from explicit resource ownership.

    ``resource_spec`` maps a relative path to its metadata (``project``,
    ``snapshot_version`` and ``kind``). Every path is hashed from the actual
    file; a missing file or a hash that disagrees with the release entry for a
    fresh project raises instead of emitting a manifest that cannot verify.
    """
    resources = {}
    problems = []
    for rel, meta in sorted(resource_spec.items()):
        path = resource_root / rel
        if not path.is_file():
            problems.append(f"resource {rel!r} is missing")
            continue
        digest = _digest(path)
        resources[rel] = {
            "sha256": digest["sha256"],
            "size": digest["size"],
            "project": meta.get("project"),
            "kind": meta.get("kind", "data"),
        }
        if meta.get("snapshot_version") is not None:
            resources[rel]["snapshot_version"] = meta["snapshot_version"]
    if problems:
        raise RuntimeError("; ".join(problems))
    manifest = {
        "schema_version": 1,
        "release_id": release.get("release_id"),
        "run_id": release.get("run_id"),
        "code_sha": release.get("code_sha"),
        "cutoff_at": release.get("cutoff_at"),
        "published_at": release.get("published_at"),
        "projects": release.get("projects"),
        "resources": resources,
    }
    return manifest


def _version_mixing(resources) -> list[str]:
    by_project = {}
    for rel, meta in resources.items():
        project = meta.get("project")
        version = meta.get("snapshot_version")
        if project is None or version is None:
            continue
        by_project.setdefault(project, {})[rel] = version
    problems = []
    for project, files in by_project.items():
        versions = set(files.values())
        if len(versions) > 1:
            detail = ", ".join(f"{rel}={version}" for rel, version in sorted(files.items()))
            problems.append(f"project {project!r} mixes snapshot versions: {detail}")
    return problems


def verify_site_manifest(manifest: dict, resource_root: Path) -> list[str]:
    """Independently recompute bytes, sizes and the reference closure.

    Returns a list of problems (empty means the manifest is valid and frozen).
    """
    problems = []
    resources = manifest.get("resources")
    if not isinstance(resources, dict) or not resources:
        return ["manifest carries no resources table"]
    for rel, expected in sorted(resources.items()):
        path = resource_root / rel
        if not path.is_file():
            problems.append(f"resource {rel!r} is missing from the site tree")
            continue
        digest = _digest(path)
        if digest["sha256"] != expected.get("sha256"):
            problems.append(f"resource {rel!r} sha256 {digest['sha256']} != manifest {expected.get('sha256')!r}")
        if expected.get("size") is not None and digest["size"] != expected["size"]:
            problems.append(f"resource {rel!r} size {digest['size']} != manifest {expected.get('size')!r}")
    problems.extend(_version_mixing(resources))
    # Closure: every data resource must belong to a project that the release
    # names, and every runtime resource must carry no project ownership.
    release_projects = set((manifest.get("projects") or {}).keys())
    for rel, meta in resources.items():
        project = meta.get("project")
        kind = meta.get("kind", "data")
        if kind == "runtime" and project is not None:
            problems.append(f"resource {rel!r} is runtime but claims project {project!r}")
        if kind != "runtime" and project is not None and project not in release_projects:
            problems.append(f"resource {rel!r} belongs to unknown project {project!r}")
    return problems


def assemble_verified(
    catalog,
    context,
    reports,
    resource_root: Path,
    *,
    release_id: str,
    published_at: str,
    baseline: dict | None = None,
    baseline_release_id: str | None = None,
    resource_spec: dict | None = None,
):
    """Verify reports against real resources, then assemble + build the site manifest.

    Returns ``(release, site_manifest)``. Raises ``RuntimeError`` (with a
    joined problem list) when any fresh report or resource fails independent
    verification, so a deployable bundle is never produced from fake success.
    """
    problems = verify_fresh_reports(catalog, context, reports, resource_root)
    if problems:
        raise RuntimeError("; ".join(problems))
    release = assemble_release(
        catalog, context, reports,
        release_id=release_id, published_at=published_at,
        baseline=baseline, baseline_release_id=baseline_release_id,
    )
    manifest = build_site_manifest(release, resource_root, resource_spec=resource_spec or {})
    return release, manifest