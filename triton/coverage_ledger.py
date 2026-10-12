"""Coverage ledger from raw collection to public workflow/attempt output (UDR-005).

Every round's counting must be independently recomputable by definition: the
number of raw rows returned by the source, the unique ``(run_id, attempt)``
identities they collapse to, and the classification of each unique identity as
one of ``public`` (present in the published workflow/attempt output),
``out_of_window`` (excluded because its batch start falls before the display
window), or ``other`` (any other documented exclusion). Identities that cannot
be assigned to exactly one of those buckets are ``unaccounted`` and keep the
ledger unverified — the difference is never guessed as "two missing" or "two
legal exclusions".

The ledger stores per-identity reasons and exposes ``verify_ledger``, which
recomputes the balances from the entries themselves so that deleting or forging
an exclusion reason is detected and named.
"""

from __future__ import annotations

PUBLIC = "public"
OUT_OF_WINDOW = "out_of_window"
OTHER = "other"
UNACCOUNTED = "unaccounted"

CLASSES = (PUBLIC, OUT_OF_WINDOW, OTHER, UNACCOUNTED)
_EXCLUSION_CLASSES = (OUT_OF_WINDOW, OTHER)


def identity(row):
    """Return the stable ``(run_id, attempt)`` identity for a row."""
    return (row.get("id"), int(row.get("run_attempt") or 1))


def _pair(ident):
    return (ident[0], int(ident[1]))


def unique_identities(raw_rows):
    """Deduplicate raw rows by ``(run_id, attempt)`` in first-seen order.

    Returns ``(ordered_unique_identities, duplicate_identities)``.
    """
    seen = set()
    order = []
    duplicates = []
    for row in raw_rows:
        ident = _pair(identity(row))
        if ident in seen:
            duplicates.append(ident)
        else:
            seen.add(ident)
            order.append(ident)
    return order, duplicates


def _entry(ident, classification, reason):
    return {"run_id": ident[0], "attempt": ident[1],
            "classification": classification, "reason": reason}


def build_ledger(raw_rows, *, public=(), out_of_window=None, other=None):
    """Build the accounting ledger from raw rows and identity classifications.

    ``public`` is an iterable of ``(run_id, attempt)`` identities present in the
    published workflow/attempt output. ``out_of_window`` and ``other`` map
    identity -> exclusion reason (a non-empty, traceable string). Any unique
    identity absent from all three buckets is ``unaccounted``, which keeps the
    ledger ``balanced=False`` / ``verified=False`` instead of guessing.
    """
    order, duplicates = unique_identities(raw_rows)
    public_set = {_pair(i) for i in public}
    out_of_window = {_pair(k): v for k, v in (out_of_window or {}).items()}
    other = {_pair(k): v for k, v in (other or {}).items()}

    # Overlapping classification is a construction error, not a legal exclusion.
    overlap = (public_set & set(out_of_window)) | (public_set & set(other)) | (set(out_of_window) & set(other))
    if overlap:
        raise ValueError(f"identity classified in more than one bucket: {sorted(overlap)}")

    entries = []
    for ident in order:
        if ident in public_set:
            classification, reason = PUBLIC, None
        elif ident in out_of_window:
            classification, reason = OUT_OF_WINDOW, out_of_window[ident]
        elif ident in other:
            classification, reason = OTHER, other[ident]
        else:
            classification, reason = UNACCOUNTED, None
        entries.append(_entry(ident, classification, reason))

    counts = {c: sum(1 for e in entries if e["classification"] == c) for c in CLASSES}
    balanced = counts[UNACCOUNTED] == 0 and counts[PUBLIC] + counts[OUT_OF_WINDOW] + counts[OTHER] == len(order)
    ledger = {
        "raw_count": len(raw_rows),
        "unique_count": len(order),
        "duplicate_count": len(duplicates),
        "public_count": counts[PUBLIC],
        "out_of_window_count": counts[OUT_OF_WINDOW],
        "other_count": counts[OTHER],
        "unaccounted_count": counts[UNACCOUNTED],
        "balanced": balanced,
        "entries": entries,
        "duplicates": [_entry(i, None, None) for i in duplicates],
    }
    ledger["verified"] = balanced and not verify_ledger(ledger)
    return ledger


def verify_ledger(ledger):
    """Independently recompute the ledger's balances from its entries.

    Returns a list of human-readable problems (empty means the ledger is
    internally consistent and complete). Tampered exclusion reasons or forged
    classifications are reported together with the offending identity.
    """
    problems = []
    entries = ledger.get("entries")
    duplicates = ledger.get("duplicates")
    if not isinstance(entries, list):
        return ["ledger entries must be a list"]

    seen = set()
    recomputed = {c: 0 for c in CLASSES}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"entry {position} is not an object")
            continue
        ident = _pair((entry.get("run_id"), entry.get("attempt")))
        label = f"run {ident[0]} attempt {ident[1]}"
        if ident in seen:
            problems.append(f"{label}: duplicate entry")
        seen.add(ident)
        classification = entry.get("classification")
        if classification not in CLASSES:
            problems.append(f"{label}: invalid classification {classification!r}")
            continue
        recomputed[classification] += 1
        if classification in _EXCLUSION_CLASSES:
            if not entry.get("reason"):
                problems.append(f"{label}: {classification} exclusion missing a reason")

    for key, declared in (
        ("public_count", recomputed[PUBLIC]),
        ("out_of_window_count", recomputed[OUT_OF_WINDOW]),
        ("other_count", recomputed[OTHER]),
        ("unaccounted_count", recomputed[UNACCOUNTED]),
    ):
        if ledger.get(key) != declared:
            problems.append(f"{key} declared {ledger.get(key)!r} but entries recompute {declared!r}")

    if ledger.get("unique_count") != len(seen):
        problems.append(f"unique_count declared {ledger.get('unique_count')!r} but {len(seen)} entries exist")
    if ledger.get("raw_count") is not None and ledger.get("duplicate_count") is not None:
        if ledger["raw_count"] != len(seen) + ledger["duplicate_count"]:
            problems.append(
                f"raw_count {ledger['raw_count']!r} != unique {len(seen)} + duplicates {ledger['duplicate_count']!r}"
            )

    dup_ids = set()
    for dup in duplicates:
        ident = _pair((dup.get("run_id"), dup.get("attempt")))
        if ident in dup_ids:
            problems.append(f"run {ident[0]} attempt {ident[1]}: duplicate row counted twice")
        dup_ids.add(ident)
        if ident not in seen:
            problems.append(f"run {ident[0]} attempt {ident[1]}: duplicate references an identity absent from entries")
    if ledger.get("duplicate_count") != len(duplicates):
        problems.append(
            f"duplicate_count declared {ledger.get('duplicate_count')!r} but {len(duplicates)} duplicate rows listed"
        )
    return problems
