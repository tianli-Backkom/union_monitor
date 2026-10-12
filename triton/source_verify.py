"""UDR-004: Triton full-source enumeration and independent verification boundary.

Re-reads the raw collection artifacts (``runs.json``, the per-identity job lists
and the PR association records) and reconciles them against the published
dashboard payload. Every category closes as verified / differences / missing
through the shared :mod:`source_coverage` model, so a derived-only or sampled
recomputation can never upgrade to a full pass, and a historical PR association
without raw evidence stays unverified rather than being guessed.
"""
from __future__ import annotations

import json
from pathlib import Path

from source_coverage import SourceCategory, source_report


def raw_identities(runs):
    """Unique ``(run_id, attempt)`` identities from the raw workflow-run list."""
    seen, out = set(), []
    for row in runs:
        ident = (row.get("id"), int(row.get("run_attempt") or 1))
        if ident not in seen:
            seen.add(ident)
            out.append(ident)
    return out


def load_job_files(jobs_dir):
    """Return ``{(run_id, attempt): jobs}`` for every ``{run_id}-{attempt}.json``.

    An unreadable or non-array job file is stored as ``None`` so the caller can
    tell "job evidence unreadable" apart from "job evidence missing".
    """
    found = {}
    if not jobs_dir.is_dir():
        return found
    for path in jobs_dir.glob("*.json"):
        stem = path.stem
        if "-" not in stem:
            continue
        rid_s, attempt_s = stem.rsplit("-", 1)
        try:
            ident = (int(rid_s), int(attempt_s))
        except ValueError:
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = None
        found[ident] = rows
    return found


def load_pr_associations(pr_dir):
    """Return ``{run_id: resolved_pr}`` from ``{run_id}.json`` association files.

    A resolved file carries a top-level ``pr`` (the evidence-backed association
    the resolver wrote after cross-checking head SHA/branch against the PR); an
    unresolved or ambiguous diagnostic carries only ``candidates``/``matches``
    and therefore yields no PR, so it stays missing evidence.
    """
    out = {}
    if not pr_dir.is_dir():
        return out
    for path in pr_dir.glob("*.json"):
        try:
            run_id = int(path.stem)
        except ValueError:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("pr") is None:
            continue
        out[run_id] = data["pr"]
    return out


def published_workflow_attempts(payload):
    """``{(run_id, attempt)}`` present in the published workflow lists."""
    out = set()
    for batch in payload.get("batches", []):
        for workflow in batch.get("workflows", []) or []:
            out.add((workflow.get("id"), int(workflow.get("attempt") or 1)))
    return out


def published_prs(payload):
    """PR numbers published by the payload (unknown-PR batches are excluded)."""
    return {batch["pr"] for batch in payload.get("batches", []) if batch.get("pr") is not None}


def verify_enumeration(runs, jobs_dir, payload, *, pr_dir=None):
    """Reconcile the raw enumeration against the published payload.

    ``runs`` is the raw workflow-run list, ``jobs_dir`` the directory of
    ``{run_id}-{attempt}.json`` job lists and ``payload`` the published payload
    for the same window. ``pr_dir`` (optional) enables PR association closure.
    """
    identities = raw_identities(runs)
    job_files = load_job_files(jobs_dir)
    published = published_workflow_attempts(payload)

    workflow = SourceCategory("workflow_attempt_enumeration")
    for ident in identities:
        workflow.record_applicable(ident)
        if ident in published:
            workflow.record_verified(ident)
        else:
            workflow.record_difference(
                ident,
                f"run {ident[0]} attempt {ident[1]} enumerated from raw source but absent from published workflow attempts",
            )

    jobs = SourceCategory("job_enumeration")
    for ident in identities:
        jobs.record_applicable(ident)
        if ident in job_files:
            rows = job_files[ident]
            if isinstance(rows, list):
                jobs.record_verified(ident)
            else:
                jobs.record_difference(ident, f"run {ident[0]} attempt {ident[1]} job evidence unreadable")
        # else: no job file at all -> missing evidence

    categories = {"workflow_attempt_enumeration": workflow, "job_enumeration": jobs}

    if pr_dir is not None:
        associations = load_pr_associations(pr_dir)
        resolved_prs = set(associations.values())
        pr_category = SourceCategory("pr_association")
        for pr in sorted(published_prs(payload)):
            pr_category.record_applicable(pr)
            if pr in resolved_prs:
                pr_category.record_verified(pr)
            # else: no raw resolved association -> missing evidence
        categories["pr_association"] = pr_category

    return source_report(categories)


def build_coverage_evidence(runs_json, jobs_dir, payload, *, pr_dir=None):
    """Produce the UDR-004 evidence document for a completed enumeration.

    Returns the source-coverage reconciliation plus an ``evidence`` block that
    records the raw artifacts the reconciliation was built from (window, raw
    run count, job/association file counts, published batch/PR counts) and
    whether the payload window matches the raw enumeration window. The evidence
    block keeps the report independently reproducible rather than a bare status.
    """
    report = verify_enumeration(runs_json["runs"], jobs_dir, payload, pr_dir=pr_dir)
    identities = raw_identities(runs_json.get("runs", []))
    job_files = load_job_files(jobs_dir) if jobs_dir.is_dir() else {}
    in_window_job_files = len([k for k in job_files if k in set(identities)])
    evidence = {
        "window_start": runs_json.get("window_start"),
        "window_end": runs_json.get("window_end"),
        "collected_at": runs_json.get("collected_at"),
        "payload_window_start": payload.get("window_start"),
        "payload_window_end": payload.get("window_end"),
        "window_matches_payload": (
            runs_json.get("window_start") == payload.get("window_start")
            and runs_json.get("window_end") == payload.get("window_end")
        ),
        "raw_run_count": len(runs_json.get("runs", [])),
        "job_evidence_files": in_window_job_files,
        "pr_association_files": len(list(pr_dir.glob("*.json"))) if (pr_dir and pr_dir.is_dir()) else 0,
        "published_batches": len(payload.get("batches", [])),
        "published_prs": len(published_prs(payload)),
    }
    return {"status": report["status"], "evidence": evidence, "categories": report["categories"]}


def main(argv=None):
    """CLI: verify a raw enumeration directory against a published payload.

    Usage: python -X utf8 -m triton.source_verify --runs runs.json --jobs DIR
           --payload triton.json [--pr-dir DIR] [--output PATH]
    """
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Triton full-source enumeration verification (UDR-004)")
    ap.add_argument("--runs", required=True, help="path to runs.json")
    ap.add_argument("--jobs", required=True, help="directory of {run_id}-{attempt}.json job lists")
    ap.add_argument("--payload", required=True, help="path to the published triton.json payload")
    ap.add_argument("--pr-dir", default=None, help="optional directory of {run_id}.json PR association records")
    ap.add_argument("--output", default=None, help="write the report here (default: stdout)")
    args = ap.parse_args(argv)

    runs_json = json.loads(Path(args.runs).read_text(encoding="utf-8"))
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    pr_dir = Path(args.pr_dir) if args.pr_dir else None
    report = build_coverage_evidence(runs_json, Path(args.jobs), payload, pr_dir=pr_dir)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"[output] {args.output}")
    else:
        print(text)
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
