"""Duration validity, percentile and display rules (T-009, P-009).

Internal durations are milliseconds. Aggregation uses raw values, never a
rounded display string. A legal duration is finite and non-negative; missing,
unparseable, negative, NaN and infinite values are never coerced to zero, and a
real zero is a legal value distinct from "unknown".

Display is in minutes with two decimals. A non-zero value below 0.01 min renders
as ``<0.01 min``; real zero renders ``0.00 min``; unknown renders ``—``.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

MINUTE_MS = 60_000.0
DISPLAY_THRESHOLD_MS = 600.0  # 0.01 min


def valid_duration(value) -> bool:
    """True for a finite, non-negative numeric duration (bool excluded)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value >= 0


def seconds_to_ms(seconds: float) -> float:
    """Convert a second-precision source value to the internal ms unit."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        raise ValueError("seconds must be numeric")
    return float(seconds) * 1000.0


def percentile_inc(values: Iterable, q: float = 0.9) -> Optional[float]:
    """PERCENTILE.INC linear interpolation over valid durations (empty -> None)."""
    samples = sorted(v for v in values if valid_duration(v))
    if not samples:
        return None
    pos = (len(samples) - 1) * q
    lo = int(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(samples[lo])
    return float(samples[lo] + (samples[hi] - samples[lo]) * (pos - lo))


def format_minutes(ms) -> str:
    """Format an internal ms duration for the main minute-based display."""
    if not valid_duration(ms):
        return "—"
    if ms == 0:
        return "0.00 min"
    if ms < DISPLAY_THRESHOLD_MS:
        return "<0.01 min"
    return f"{ms / MINUTE_MS:.2f} min"


def format_observed(ms, as_of: Optional[str] = None) -> str:
    """Format a profile-observed (non-terminal) duration without claiming a final value."""
    if not valid_duration(ms):
        return "—"
    base = f"已观测 {ms / MINUTE_MS:.2f} min"
    if as_of:
        return f"{base} · 截至 {as_of}"
    return base