"""Frozen per-round run context shared by every enabled project (T-003).

``prepare`` produces one run context and passes the same file and fingerprint to
every project, so that a slow or delayed collector cannot pick a different clock
reading and split a round. ``cutoff_at`` is frozen at prepare time and must carry
an explicit timezone; project windows derive from it (``start_at = cutoff_at -
hours``, ``end_at = cutoff_at`` for fresh data).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_time(value: str) -> datetime:
    """Parse an ISO timestamp and require an explicit timezone."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must have an explicit timezone")
    return parsed


def iso_utc(value: datetime) -> str:
    """Render a tz-aware datetime as a UTC ``Z``-suffixed string."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RunContext:
    def __init__(
        self,
        *,
        run_id: str,
        code_sha: str,
        cutoff_at: str,
        scheduled_for: str | None = None,
        started_at: str | None = None,
        trigger: str = "schedule",
        catalog_sha256: str | None = None,
        project_ids: list[str] | None = None,
        artifact_root: str | None = None,
        publish_mode: str = "normal",
    ):
        if not run_id or not code_sha:
            raise ValueError("run context requires run_id and code_sha")
        self.run_id = run_id
        self.code_sha = code_sha
        self.cutoff_at = utc_time(cutoff_at)  # frozen; never re-read the clock
        self.scheduled_for = scheduled_for
        self.started_at = started_at
        self.trigger = trigger
        self.catalog_sha256 = catalog_sha256
        self.project_ids = list(project_ids) if project_ids is not None else []
        self.artifact_root = artifact_root
        self.publish_mode = publish_mode

    def window(self, hours: int | float) -> dict:
        """Return the shared-cutoff window ``{start_at, end_at}`` for ``hours``."""
        if not isinstance(hours, (int, float)) or hours <= 0:
            raise ValueError("window hours must be positive")
        end = self.cutoff_at
        start = end - timedelta(hours=hours)
        return {"start_at": iso_utc(start), "end_at": iso_utc(end)}

    @classmethod
    def from_dict(cls, data: dict) -> "RunContext":
        """Rebuild a context from the JSON emitted by ``as_dict``."""
        keys = ("run_id", "code_sha", "cutoff_at", "scheduled_for", "started_at", "trigger", "catalog_sha256", "project_ids", "artifact_root", "publish_mode")
        return cls(**{k: data.get(k) for k in keys})

    def window_for(self, project: dict) -> dict:
        """Derive the window for a catalog project from its declared time basis."""
        window = project.get("window") or {}
        hours = window.get("hours")
        if not hours:
            raise ValueError(f"project {project.get('project_id')!r} has no window hours")
        result = self.window(hours)
        result["time_basis"] = window.get("time_basis")
        return result

    def as_dict(self) -> dict:
        value = {
            "schema_version": 1,
            "run_id": self.run_id,
            "code_sha": self.code_sha,
            "trigger": self.trigger,
            "scheduled_for": self.scheduled_for,
            "started_at": self.started_at,
            "cutoff_at": iso_utc(self.cutoff_at),
            "project_ids": self.project_ids,
            "artifact_root": self.artifact_root,
            "publish_mode": self.publish_mode,
        }
        if self.catalog_sha256 is not None:
            value["catalog_sha256"] = self.catalog_sha256
        return value
