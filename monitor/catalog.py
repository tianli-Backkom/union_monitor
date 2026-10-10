"""Versioned project catalog: source instances, collectors, profiles and projects.

The catalog is the single source of truth for which projects, repositories and
capabilities the dashboard exposes (T-002). The public runtime reads ``projects``
and generates the user-visible directory and collection Matrix from ``enabled``
entries only; no part of the main flow branches on a hardcoded ``project_id``.

See the synthetic example in docs/design/2026-10-10-unified-dashboard-architecture.md
(anchor ``example-catalog``). The concrete catalog.json at the repository root
reflects the real UBS and Triton-Ascend projects.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_VERSION = 1


class CatalogError(ValueError):
    """The catalog is structurally or referentially invalid."""


class Catalog:
    def __init__(self, data: dict):
        if not isinstance(data, dict):
            raise CatalogError("catalog root must be an object")
        self.data = data
        self._validate()

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        raw = Path(path).read_text(encoding="utf-8")
        return cls(json.loads(raw))

    @classmethod
    def from_dict(cls, data: dict) -> "Catalog":
        return cls(data)

    # -- validation --------------------------------------------------------
    def _validate(self) -> None:
        data = self.data
        if data.get("schema_version") != SCHEMA_VERSION:
            raise CatalogError(
                f"unsupported schema_version {data.get('schema_version')!r} (expected {SCHEMA_VERSION})"
            )
        for key in ("schedule", "source_instances", "collectors", "metric_profiles", "view_profiles", "projects"):
            if key not in data or not isinstance(data[key], dict if key != "projects" else list):
                raise CatalogError(f"catalog missing or malformed section: {key}")
        self._validate_schedule(data["schedule"])
        self._validate_source_instances(data["source_instances"])
        self._validate_projects(data)

    @staticmethod
    def _validate_schedule(schedule: dict) -> None:
        for key in ("timezone", "local_time", "frequency"):
            if not schedule.get(key):
                raise CatalogError(f"schedule missing {key!r}")

    @staticmethod
    def _validate_source_instances(instances: dict) -> None:
        if not instances:
            raise CatalogError("catalog requires at least one source instance")
        seen_urls: set[str] = set()
        for key, value in instances.items():
            base_url = value.get("base_url") or ""
            if not value.get("provider"):
                raise CatalogError(f"source instance {key!r} missing provider")
            parts = urlsplit(base_url)
            if parts.scheme != "https" or not parts.hostname:
                raise CatalogError(f"source instance {key!r} has an invalid base_url {base_url!r}")
            if base_url in seen_urls:
                raise CatalogError(f"duplicate source base_url {base_url!r}")
            seen_urls.add(base_url)

    @staticmethod
    def _validate_projects(data: dict) -> None:
        projects = data["projects"]
        seen_ids: set[str] = set()
        for project in projects:
            project_id = project.get("project_id")
            if not project_id:
                raise CatalogError("project missing project_id")
            if project_id in seen_ids:
                raise CatalogError(f"duplicate project_id {project_id!r}")
            seen_ids.add(project_id)
            for ref in ("collector", "metric_profile", "view_profile"):
                target = project.get(ref)
                if target not in data[ref + "s"]:
                    raise CatalogError(f"project {project_id!r} references unknown {ref} {target!r}")
            window = project.get("window") or {}
            if not window.get("time_basis") or not isinstance(window.get("hours"), (int, float)) or window["hours"] <= 0:
                raise CatalogError(f"project {project_id!r} has an invalid window {window!r}")
            if not isinstance(project.get("timeout_minutes"), (int, float)) or project["timeout_minutes"] <= 0:
                raise CatalogError(f"project {project_id!r} missing positive timeout_minutes")
            repositories = project.get("repositories")
            if not isinstance(repositories, list) or not repositories:
                raise CatalogError(f"project {project_id!r} has no repositories")
            seen_repos: set[str] = set()
            for repo in repositories:
                repo_id = repo.get("repository_id")
                branches = repo.get("target_branches")
                if not branches or not isinstance(branches, list):
                    raise CatalogError(f"repository {repo_id!r} in {project_id!r} missing target_branches")
                if ":" not in repo_id or "/" not in repo_id:
                    raise CatalogError(f"repository id {repo_id!r} must be source_instance:owner/repository")
                if repo_id.split(":", 1)[0] not in data["source_instances"]:
                    raise CatalogError(f"repository {repo_id!r} references unknown source instance")
                if repo_id in seen_repos:
                    raise CatalogError(f"duplicate repository id {repo_id!r} in project {project_id!r}")
                seen_repos.add(repo_id)

    # -- accessors ---------------------------------------------------------
    @property
    def projects(self) -> list[dict]:
        return self.data["projects"]

    def project(self, project_id: str) -> dict:
        for project in self.projects:
            if project["project_id"] == project_id:
                return project
        raise CatalogError(f"unknown project_id {project_id!r}")

    def enabled_projects(self) -> list[dict]:
        return [p for p in self.projects if p.get("enabled")]

    def enabled_project_ids(self) -> list[str]:
        return [p["project_id"] for p in self.enabled_projects()]

    def source_instance(self, instance_id: str) -> dict:
        try:
            return self.data["source_instances"][instance_id]
        except KeyError:
            raise CatalogError(f"unknown source instance {instance_id!r}") from None

    def repository_ids(self, project_id: str) -> list[str]:
        return [r["repository_id"] for r in self.project(project_id)["repositories"]]
