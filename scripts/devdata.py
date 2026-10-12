#!/usr/bin/env python3
"""Bootstrap dev data for the merged monitoring dashboard.

Modes:
  online (default)  Fetch live dashboard data from GitHub Pages.
  --offline         Copy hand-crafted fixtures from tests/fixtures/minimal/.

Files produced (online fetch or offline copy):
  web/data/repositories.json                  multi-repo index
  web/data/<repositories[].snapshot>          per-repo snapshots (e.g. repos/ubs-engine.json)
  data/snapshot.json                          ubs-engine compat snapshot at repo root
                                              (tests/frontend.test.cjs requires ../data/snapshot.json)
  web/data/triton.json                        Triton dashboard JSON (legacy HTML also accepted)

URL overrides (also handy for error-path testing):
  --ubs-url BASE    Base URL of the UBS monitor site.
                    Default: https://tianli-backkom.github.io/union_monitor
  --triton-url URL  Full URL of Triton JSON, or an explicit legacy index.html.
                    Default: https://tianli-backkom.github.io/union_monitor/data/triton.json

Examples:
  python3 scripts/devdata.py
  python3 scripts/devdata.py --offline
  python3 scripts/devdata.py --ubs-url https://invalid.example.test   # exits non-zero
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

USER_AGENT = "merged-monitor-devdata/1.0"
TIMEOUT_SECONDS = 30
DEFAULT_UBS_BASE = "https://tianli-backkom.github.io/union_monitor"
DEFAULT_TRITON_URL = DEFAULT_UBS_BASE + "/data/triton.json"
TRITON_DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = REPO_ROOT / "web" / "data"
ROOT_DATA_DIR = REPO_ROOT / "data"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "minimal"


class DevDataError(Exception):
    """Fatal, user-facing bootstrap error."""


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise DevDataError(f"GET {url} -> HTTP {response.status}")
            return response.read()
    except HTTPError as error:
        raise DevDataError(f"GET {url} -> HTTP {error.code} {error.reason}") from error
    except URLError as error:
        raise DevDataError(f"GET {url} -> {error.reason}") from error
    except TimeoutError as error:
        raise DevDataError(f"GET {url} -> timed out after {TIMEOUT_SECONDS}s") from error
    except OSError as error:
        raise DevDataError(f"GET {url} -> {error}") from error


def parse_json(data: bytes, source: str) -> dict:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevDataError(f"{source}: invalid JSON ({error})") from error
    if not isinstance(payload, dict):
        raise DevDataError(f"{source}: expected a JSON object, got {type(payload).__name__}")
    return payload


def require_keys(payload: dict, keys, source: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise DevDataError(f"{source}: missing required field(s): {', '.join(missing)}")


def safe_snapshot_path(snapshot: str, repo_name: str) -> PurePosixPath:
    path = PurePosixPath(snapshot)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DevDataError(f"repository {repo_name!r}: unsafe snapshot path {snapshot!r}")
    return path


def write_file(target: Path, data: bytes, written: list) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    written.append((target, len(data)))


def report(written: list, mode: str) -> None:
    for target, size in written:
        print(f"  {target.relative_to(REPO_ROOT)}  ({size} bytes)")
    total = sum(size for _, size in written)
    print(f"{mode}: {len(written)} file(s), {total} bytes total")


def publish_catalog(source=None, target=None, written: list | None = None) -> Path:
    """Copy the versioned catalog.json into the served web tree.

    The catalog is the single source of truth for projects/repositories and
    capabilities; the site publishes an identical copy under ``web/data`` so the
    shell and the collection pipeline never drift apart.
    """
    source = Path(source) if source else REPO_ROOT / "catalog.json"
    target = Path(target) if target else WEB_DATA_DIR / "catalog.json"
    if not source.is_file():
        raise DevDataError(f"catalog.json missing at {source}")
    data = source.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    if written is not None:
        written.append((target, source.stat().st_size))
    return target


def run_online(ubs_base: str, triton_url: str, written: list) -> None:
    ubs_base = ubs_base.rstrip("/")

    index_payload = parse_json(
        fetch(f"{ubs_base}/data/repositories.json"), "repositories.json"
    )
    require_keys(index_payload, ["repositories"], "repositories.json")
    repositories = index_payload["repositories"]
    if not isinstance(repositories, list):
        raise DevDataError("repositories.json: 'repositories' must be a list")
    write_file(WEB_DATA_DIR / "repositories.json",
               json.dumps(index_payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n", written)

    skipped = 0
    for entry in repositories:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise DevDataError("repositories.json: entry without a name")
        snapshot = entry.get("snapshot")
        if not snapshot:
            skipped += 1
            continue
        rel = safe_snapshot_path(snapshot, entry["name"])
        payload = parse_json(fetch(f"{ubs_base}/data/{rel.as_posix()}"), str(rel))
        require_keys(payload, ["meta", "prs"], str(rel))
        write_file(WEB_DATA_DIR / Path(*rel.parts), json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n", written)
    if skipped:
        print(f"  (skipped {skipped} repositories without a snapshot)")

    compat = parse_json(fetch(f"{ubs_base}/data/snapshot.json"), "snapshot.json")
    require_keys(compat, ["meta", "prs"], "snapshot.json")
    write_file(ROOT_DATA_DIR / "snapshot.json",
               json.dumps(compat, ensure_ascii=False, indent=2).encode("utf-8") + b"\n", written)

    publish_catalog(written=written)

    triton_data = fetch(triton_url)
    if urlsplit(triton_url).path.lower().endswith(".json") or triton_data.lstrip().startswith((b"{", b"[")):
        triton_payload = parse_json(triton_data, triton_url)
    else:
        html = triton_data.decode("utf-8")
        match = TRITON_DATA_RE.search(html)
        if not match:
            raise DevDataError(f"{triton_url}: no <script type=\"application/json\" id=\"data\"> payload found")
        triton_payload = parse_json(match.group(1).encode("utf-8"), "triton payload")
    require_keys(triton_payload, ["repo", "window_start", "batches", "summary"], "triton payload")
    write_file(WEB_DATA_DIR / "triton.json",
               json.dumps(triton_payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n", written)


def run_offline(written: list) -> None:
    def fixture(rel: str) -> Path:
        return FIXTURES_DIR / rel

    index_path = fixture("repositories.json")
    if not index_path.is_file():
        raise DevDataError(
            f"offline fixture missing: {index_path}\n"
            f"(expected tests/fixtures/minimal/ with repositories.json, repos/<name>.json, snapshot.json, triton.json, release.json)"
        )
    index_payload = parse_json(index_path.read_bytes(), str(index_path))
    require_keys(index_payload, ["repositories"], str(index_path))

    needed = ["repositories.json", "snapshot.json", "triton.json", "release.json"]
    for entry in index_payload["repositories"]:
        snapshot = entry.get("snapshot")
        if snapshot:
            needed.append(PurePosixPath(snapshot).as_posix())

    missing = [name for name in needed if not fixture(name).is_file()]
    if missing:
        raise DevDataError("offline fixture(s) missing: " + ", ".join(str(fixture(name)) for name in missing))

    for name in needed:
        source = fixture(name)
        if name == "snapshot.json":
            target = ROOT_DATA_DIR / "snapshot.json"
        else:
            target = WEB_DATA_DIR / Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append((target, source.stat().st_size))

    publish_catalog(written=written)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap dev data (online fetch or offline fixtures) for the merged monitoring dashboard.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--offline", action="store_true",
                        help="copy tests/fixtures/minimal/ instead of fetching live data")
    parser.add_argument("--ubs-url", metavar="BASE", default=DEFAULT_UBS_BASE,
                        help=f"UBS monitor base URL (default: {DEFAULT_UBS_BASE})")
    parser.add_argument("--triton-url", metavar="URL", default=DEFAULT_TRITON_URL,
                        help=f"Triton JSON or legacy index.html URL (default: {DEFAULT_TRITON_URL})")
    args = parser.parse_args()

    written: list = []
    try:
        if args.offline:
            run_offline(written)
        else:
            run_online(args.ubs_url, args.triton_url, written)
    except DevDataError as error:
        print(f"devdata: error: {error}", file=sys.stderr)
        if written:
            print("devdata: note: files already written before the failure:", file=sys.stderr)
            for target, size in written:
                print(f"  {target.relative_to(REPO_ROOT)}  ({size} bytes)", file=sys.stderr)
        return 1
    report(written, "offline copy complete" if args.offline else "online fetch complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
