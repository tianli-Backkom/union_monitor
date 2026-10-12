"""Detect stale or inconsistent public data; this does not trigger collection.

The remote manifest is an integrity baseline, not proof of a trusted release.
Production deployment separately compares it to the exact build's manifest.
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from triton import verify_deployment

SHANGHAI = timezone(timedelta(hours=8))
SITE = "https://tianli-backkom.github.io/union_monitor"


def deadlines(now):
    if now.tzinfo is None:
        raise ValueError("health check clock must have a timezone")
    day = now.astimezone(SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0)
    due = {}
    for project in ("ubs", "triton"):
        slots = [(7, 30, 195)]  # daily build timeout 180 min + publication allowance
        if project == "triton":
            slots += [(hour, 0, 90) for hour in (8, 12, 16, 18, 20)]
        candidates = []
        for offset in (-1, 0):
            for hour, minute, grace in slots:
                slot = day + timedelta(days=offset, hours=hour, minutes=minute)
                if slot + timedelta(minutes=grace) <= now:
                    candidates.append(slot)
        due[project] = max(candidates)
    return due


def check_freshness(timestamps, now):
    errors = []
    for project, due in deadlines(now).items():
        try:
            value = timestamps[project]
            collected = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if collected.tzinfo is None or collected > now + timedelta(minutes=5):
                raise ValueError("timestamp is naive or in the future")
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            errors.append(f"{project}: invalid collection time ({error})")
            continue
        if collected < due:
            errors.append(f"{project}: last data {collected.isoformat()}, overdue planned slot {due.isoformat()}")
    return errors


def inspect_site(site, now):
    base = site.rstrip("/") + "/data/"
    with TemporaryDirectory(prefix="dashboard-health-") as directory:
        manifests = {}
        for name in ("ubs", "triton"):
            raw = verify_deployment.fetch(base + name + "-manifest.json")
            manifests[name] = json.loads(raw)
            Path(directory, name + "-manifest.json").write_bytes(raw)
        # A remote manifest must not navigate out of the public data directory.
        for rel in manifests["ubs"].get("files", {}):
            path = PurePosixPath(rel)
            if path.is_absolute() or ".." in path.parts or "\\" in rel or ":" in rel:
                raise ValueError(f"unsafe manifest path: {rel!r}")
        records, problems = verify_deployment.check_all(
            site, Path(directory, "triton-manifest.json"), Path(directory, "ubs-manifest.json"))
        index = json.loads(verify_deployment.fetch(base + "repositories.json"))
        payload = json.loads(verify_deployment.fetch(base + "triton.json"))
        timestamps = {"ubs": index.get("generated_at"), "triton": payload.get("collected_at")}
        problems.extend(check_freshness(timestamps, now))
        entries = index.get("repositories")
        if not isinstance(entries, list) or not entries:
            problems.append("ubs: no repository entries")
        else:
            for entry in entries:
                if entry.get("status") != "success" or entry.get("meta", {}).get("errors"):
                    problems.append(f"ubs/{entry.get('name')}: collection not successful")
                # An updated index must not hide old per-repository data.
                errors = check_freshness({"ubs": entry.get("meta", {}).get("collected_at"),
                                          "triton": timestamps["triton"]}, now)
                problems.extend(f"ubs/{entry.get('name')}: {error}" for error in errors if error.startswith("ubs:"))
        return {"site": site, "checked_at": now.isoformat(), "scope": "public integrity and freshness",
                "timestamps": timestamps, "checks": records, "problems": problems,
                "success": not problems}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=SITE)
    parser.add_argument("--output", default="test-results/published-health.json")
    args = parser.parse_args()
    report = None
    for attempt in range(1, 4):
        now = datetime.now(timezone.utc)
        try:
            report = inspect_site(args.site, now)
        except Exception as error:
            report = {"site": args.site, "checked_at": now.isoformat(), "success": False,
                      "problems": [f"public health check error: {error}"]}
        if report["success"]:
            break
        if attempt < 3:
            time.sleep(5)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = "PASS" if report["success"] else "FAIL"
    lines = [f"Published dashboard health: {result}",
             "Public fingerprints and planned freshness; this is not source completeness or release promotion proof."]
    lines += report["problems"]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
