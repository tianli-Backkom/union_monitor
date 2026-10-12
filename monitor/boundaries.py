"""Boundaries: cache isolation, source evidence, public resources and permissions (UDR-031).

Source caches are scoped per community/collector/version and are only an
accelerator — run artefacts, raw source evidence and the trusted persistent
release bundle stay separate. The public resource whitelist admits only display
data and the necessary runtime metadata; SQLite, raw caches and full logs are
never published. Sensitive values (secrets, sentinels) must never appear in
collector responses, errors or staged output.

The functions here are pure and community-agnostic.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Public surface: display data and the runtime files the page actually needs.
PUBLIC_RESOURCE_EXTENSIONS = frozenset({
    ".json", ".csv", ".html", ".js", ".css", ".svg", ".ico", ".png",
    ".txt", ".md", ".map", ".webmanifest", ".woff", ".woff2",
})
# Never public: databases, raw source caches and full logs.
FORBIDDEN_MARKERS = (".sqlite", ".sqlite3", ".db", ".raw", ".log", ".tmp", ".pkl", ".pickle", ".pyc")


def cache_key(source_instance: str, collector: str, collector_version, project_id: str | None = None) -> str:
    """A cache namespace isolated by community/collector/version (and project)."""
    parts = [source_instance, collector, f"v{collector_version}"]
    if project_id:
        parts.append(project_id)
    return "/".join(parts)


def sentinel_in(text: str | bytes, sentinel: str) -> bool:
    """True when the sentinel value leaks into collector text/bytes."""
    if not sentinel:
        return False
    if isinstance(text, bytes):
        return sentinel.encode("utf-8", "replace") in text
    return sentinel in text


def whitelisted_public_path(rel: str) -> bool:
    """A relative path may appear on the public site only if it is a display
    or runtime resource — never a database, raw cache or full log."""
    p = rel.replace("\\", "/")
    lowered = p.lower()
    if any(marker in lowered for marker in FORBIDDEN_MARKERS):
        return False
    if not p or p.endswith("/"):
        return False
    parts = PurePosixPath(p).parts
    if any(part.startswith(".") for part in parts):
        return False
    return PurePosixPath(p).suffix.lower() in PUBLIC_RESOURCE_EXTENSIONS


def scan_public_resources(resources, files=None, *, sentinel: str | None = None) -> list[str]:
    """Audit a candidate public resource set; return a list of named problems.

    ``resources`` maps relative path -> bytes (or a manifest dict of
    ``{rel: {"sha256", "size"}}``). Every resource must be whitelisted and must
    not leak the sentinel value.
    """
    problems: list[str] = []
    if files is None:
        entries = [(rel, None) for rel in resources]
    else:
        entries = list(files.items())
    known = set(resources) if isinstance(resources, dict) else set(resources)
    for rel, data in entries:
        if not whitelisted_public_path(rel):
            problems.append(f"non-whitelisted public resource: {rel!r}")
        if data is not None and sentinel_in(data, sentinel or ""):
            problems.append(f"sentinel leaked in resource: {rel!r}")
    return problems