"""Persistent verified baseline and atomic pointer promotion (UDR-028).

A verified release is archived immutably (never overwritten) together with its
complete resource bytes, and a ``verified.json`` pointer records the recoverable
``current``/``previous`` pair. Promotion is atomic and non-force-push: it only
advances the pointer when the expected prior state still matches, so a
concurrent newer promotion can never be silently overwritten.

The promotion sequence is strict: public verification → archive → archive
re-check → pointer promotion. A pointer that names a missing or corrupted
archive is a baseline fault, never "first start with no prior release".
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .public_verify import sha256_bytes


class BaselineError(RuntimeError):
    """The persistent baseline is missing, corrupted or conflicting."""


class ConflictError(BaselineError):
    """The pointer advanced concurrently; force overwriting is refused."""


class ArchiveMissingError(BaselineError):
    """A pointer references a release archive that does not exist."""


class ReleaseStore:
    """Immutable ``releases/<id>/`` archive plus a ``verified.json`` pointer."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.releases = self.root / "releases"
        self.pointer_path = self.root / "verified.json"

    # -- archive ----------------------------------------------------------
    def archive_dir(self, release_id: str) -> Path:
        return self.releases / release_id

    def write_archive(self, release_id: str, manifest: dict, files: dict[str, bytes]) -> Path:
        """Write an immutable bundle; raising if it already exists or re-check fails."""
        dest = self.archive_dir(release_id)
        if dest.exists():
            raise BaselineError(f"archive {release_id!r} already exists and is immutable")
        dest.mkdir(parents=True)
        (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for rel, data in files.items():
            path = dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        problems = self.verify_archive(release_id)
        if problems:
            raise BaselineError("archive re-check failed: " + "; ".join(problems))
        return dest

    def read_archive(self, release_id: str) -> tuple[dict, dict[str, bytes]]:
        dest = self.archive_dir(release_id)
        manifest_path = dest / "manifest.json"
        if not manifest_path.is_file():
            raise ArchiveMissingError(f"archive {release_id!r} has no manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = {}
        for rel in (manifest.get("resources") or {}):
            path = dest / rel
            if not path.is_file():
                raise ArchiveMissingError(f"archive {release_id!r} is missing resource {rel!r}")
            files[rel] = path.read_bytes()
        return manifest, files

    def verify_archive(self, release_id: str) -> list[str]:
        """Re-check the archived bytes against the archived manifest."""
        try:
            manifest, files = self.read_archive(release_id)
        except ArchiveMissingError as exc:
            return [str(exc)]
        problems = []
        resources = manifest.get("resources") or {}
        if set(files) != set(resources):
            problems.append("archived resource set differs from the manifest resources table")
        for rel, meta in resources.items():
            data = files.get(rel)
            if data is None:
                problems.append(f"resource {rel!r} missing from archive")
                continue
            if sha256_bytes(data) != meta.get("sha256"):
                problems.append(f"resource {rel!r} sha256 does not match its manifest")
            if meta.get("size") is not None and len(data) != meta["size"]:
                problems.append(f"resource {rel!r} size does not match its manifest")
        return problems

    # -- pointer ----------------------------------------------------------
    def pointer(self) -> dict | None:
        if not self.pointer_path.is_file():
            return None
        return json.loads(self.pointer_path.read_text(encoding="utf-8"))

    def _write_pointer_atomic(self, state: dict) -> None:
        tmp = self.pointer_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.pointer_path)

    def promote(self, release_id: str, *, expected_previous: dict | None = None) -> dict:
        """Atomically advance ``current`` to ``release_id`` (non-force).

        ``expected_previous`` guards against concurrent promotion: when it is
        provided and differs from the on-disk pointer, the promotion raises
        ``ConflictError`` instead of silently overwriting a newer state.
        """
        actual = self.pointer()
        if expected_previous is not None and actual != expected_previous:
            raise ConflictError(
                f"pointer advanced concurrently: expected {expected_previous!r}, found {actual!r}"
            )
        # A destroyed archive for the new release is a baseline fault, not a
        # pointer write that later cannot be recovered.
        if self.verify_archive(release_id):
            raise BaselineError(f"cannot promote {release_id!r}: archive re-check failed")
        previous = actual.get("current") if actual else None
        state = {"current": release_id, "previous": previous}
        self._write_pointer_atomic(state)
        return state

    def cold_restore(self, release_id: str | None = None) -> tuple[dict, dict[str, bytes]]:
        """Restore a release from the immutable archive, ignoring any cache."""
        target = release_id or (self.pointer() or {}).get("current")
        if not target:
            raise ArchiveMissingError("no current release to restore")
        return self.read_archive(target)


def promote_sequence(store: ReleaseStore, release_id: str, manifest: dict, files: dict[str, bytes],
                     *, verify_fn=None, expected_previous=None) -> dict:
    """Verify → archive → re-check → promote, returning the new pointer state.

    ``verify_fn(release_id, manifest)`` returns a receipt; a non-``verified``
    receipt aborts before archiving so no unverified bundle becomes a baseline.
    """
    if verify_fn is not None:
        receipt = verify_fn(release_id, manifest)
        if not receipt.get("verified"):
            raise BaselineError(f"public verification failed for {release_id!r}: {receipt!r}")
    store.write_archive(release_id, manifest, files)
    return store.promote(release_id, expected_previous=expected_previous)