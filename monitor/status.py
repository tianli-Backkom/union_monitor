"""Three independent quality axes (T-008, P-008).

Execution result, evidence integrity and metric eligibility are modeled
separately. No common component may derive one axis from another:

- a success may still carry an evidence gap,
- a running batch is not automatically a data-quality failure,
- one excluded metric does not drop the other metrics,
- ``cancelled`` is expressed as-is and never silently rewritten to ``failure``
  or excluded from history.

The three axis vocabularies match the design tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

EXECUTION_RESULTS = frozenset({"success", "failure", "running", "cancelled", "unknown"})
EVIDENCE_STATES = frozenset({"verified", "approximate", "missing", "invalid", "ambiguous"})
ELIGIBILITY_STATES = frozenset({"included", "excluded", "unknown"})

_TERMINAL = frozenset({"success", "failure", "cancelled"})

_SUCCESS_TOKENS = frozenset({"success", "succeeded", "passed"})
_FAILURE_TOKENS = frozenset({"failure", "failed", "error"})
_RUNNING_TOKENS = frozenset({"running", "in_progress", "inprogress", "queued", "building"})
_CANCELLED_TOKENS = frozenset({"cancelled", "canceled", "aborted", "not_built"})


def normalize_execution_result(raw_result: Optional[str]) -> str:
    """Normalise a platform result token to the shared vocabulary.

    Only clear tokens are mapped; anything else becomes ``unknown`` while the
    raw value is preserved by the caller. A cancelled/aborted execution is never
    rewritten into a failure.
    """
    if raw_result is None:
        return "unknown"
    token = str(raw_result).strip().lower()
    if token in _SUCCESS_TOKENS:
        return "success"
    if token in _FAILURE_TOKENS:
        return "failure"
    if token in _RUNNING_TOKENS:
        return "running"
    if token in _CANCELLED_TOKENS:
        return "cancelled"
    return "unknown"


def is_terminal(result: str) -> bool:
    return result in _TERMINAL


@dataclass(frozen=True)
class Execution:
    result: str
    raw_result: Optional[str] = None

    def __post_init__(self) -> None:
        if self.result not in EXECUTION_RESULTS:
            raise ValueError(f"invalid execution result {self.result!r}")


@dataclass(frozen=True)
class Evidence:
    state: str
    issues: tuple[str, ...] = ()
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise ValueError(f"invalid evidence state {self.state!r}")


@dataclass(frozen=True)
class Eligibility:
    metric: str
    state: str
    reason: Optional[str] = None
    profile_version: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.metric:
            raise ValueError("eligibility requires a metric name")
        if self.state not in ELIGIBILITY_STATES:
            raise ValueError(f"invalid eligibility state {self.state!r}")


def eligibility_for(metric: str, eligible: Optional[bool], reason: Optional[str] = None, profile_version: Optional[str] = None) -> Eligibility:
    """Build a per-metric eligibility entry without borrowing other metrics."""
    if eligible is None:
        state = "unknown"
    else:
        state = "included" if eligible else "excluded"
    return Eligibility(metric=metric, state=state, reason=reason, profile_version=profile_version)


@dataclass
class Axes:
    """The three independent axes attached to one measured entity."""

    execution: Execution
    evidence: Evidence
    eligibility: Mapping[str, Eligibility] = field(default_factory=dict)