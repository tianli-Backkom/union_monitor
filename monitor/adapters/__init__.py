"""Per-project collector adapters (T-012).

The catalog's ``collectors`` section maps each collector to an ``entrypoint``
(a ``module.submodule`` import path). :func:`resolve` imports that module and
returns its ``collect(project, context, work_dir) -> dict`` callable, which
returns a *partial* collection report:

* ``collection_status`` — ``"success"`` or ``"failed"``;
* on success: ``samples``, ``coverage``, ``collected_at``, ``window``,
  ``snapshot_version``, ``snapshot_sha256``;
* optional ``validation_status``, ``errors``, ``warnings``, ``cache``.

A missing adapter module raises :class:`AdapterError`; the collect step then
records an honest ``failed`` report — it never fakes success.
"""

from __future__ import annotations

import importlib


class AdapterError(Exception):
    """A project's collector adapter cannot be located or invoked."""


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