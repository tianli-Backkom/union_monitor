"""Stable ordering and pagination (T-006, P-006).

A list is first fully ordered, then sliced for display. Missing sort keys always
land after known values (a real zero is a valid value, not missing), ties use a
stable identity, and pagination never duplicates or drops a row across pages.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Optional

PAGE_SIZES = (15, 30, 50)
DEFAULT_PAGE_SIZE = 15


def stable_sort(
    items: Iterable,
    key: Callable[[object], Optional[object]],
    reverse: bool = False,
    identity: Optional[Callable[[object], object]] = None,
) -> list:
    """Return a fully ordered list: key (desc if reverse), then stable identity.

    Items whose key evaluates to ``None`` are treated as missing and placed
    after every known value, regardless of ``reverse``. ``identity`` (or the
    original input order when omitted) is applied ascending as the final
    tie-break so the sequence is reproducible.
    """
    decorated = list(enumerate(items))

    def item_key(pair):
        return key(pair[1])

    def identity_key(pair):
        idx, item = pair
        if identity is None:
            return idx
        return (identity(item), idx)

    known = [pair for pair in decorated if item_key(pair) is not None]
    missing = [pair for pair in decorated if item_key(pair) is None]
    known.sort(key=identity_key)
    known.sort(key=item_key, reverse=reverse)
    missing.sort(key=identity_key)
    return [item for _, item in known + missing]


def paginate(items: Iterable, page: int, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    """Slice a fully ordered list into one page (1-based, clamped)."""
    if page_size <= 0:
        raise ValueError(f"invalid page size {page_size!r}")
    materialized = list(items)
    total = len(materialized)
    if total == 0:
        return {"items": [], "page": 1, "pages": 0, "total": 0, "start": 0, "end": 0}
    pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    return {
        "items": materialized[start:end],
        "page": page,
        "pages": pages,
        "total": total,
        "start": start + 1,
        "end": end,
    }