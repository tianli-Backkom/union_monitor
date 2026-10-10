"""Unified engineering dashboard: catalog, run context and stable identities.

This package holds the versioned public contracts introduced by the unified
dashboard design (docs/design/2026-10-10-unified-dashboard-*.md). It models
the catalog that drives projects/repositories/capabilities (T-002), the frozen
per-round run context (T-003) and collision-free stable identities (T-005).

It is deliberately dependency-free (Python standard library only) so it can run
inside the existing collection/CI environment without new third-party wheels.
"""

__version__ = "0.1.0"
