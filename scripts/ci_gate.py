"""Fail the required PR check unless every named prerequisite passed."""
from __future__ import annotations

import argparse
import json
import os
import sys

REQUIRED_JOBS = frozenset({"python-tests", "frontend-tests", "collector-contracts", "workflow-lint"})


def problems_for(results: object) -> list[str]:
    if not isinstance(results, dict):
        return ["needs must be a JSON object"]
    problems = []
    missing = REQUIRED_JOBS - results.keys()
    unexpected = results.keys() - REQUIRED_JOBS
    if missing:
        problems.append("missing jobs: " + ", ".join(sorted(missing)))
    if unexpected:
        problems.append("unexpected jobs: " + ", ".join(sorted(unexpected)))
    for name in sorted(REQUIRED_JOBS & results.keys()):
        job = results[name]
        outcome = job.get("result") if isinstance(job, dict) else None
        if outcome != "success":
            problems.append(f"{name}: {outcome!r}, required 'success'")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.environ.get("RESULTS_JSON", "{}"))
    args = parser.parse_args()
    try:
        results = json.loads(args.results)
    except (TypeError, ValueError) as error:
        print(f"gate FAILED: invalid needs JSON: {error}", file=sys.stderr)
        return 1
    problems = problems_for(results)
    if problems:
        print("gate FAILED:\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("gate PASSED: " + ", ".join(sorted(REQUIRED_JOBS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
