"""``python -m monitor`` CLI (T-012/T-013).

Implements the prepare/collect/validate/assemble pipeline plus the
``verify-deployment`` and ``rollback`` stages. Each command exits non-zero on
failure; a failed collect keeps its honest report rather than a fake success.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .catalog import Catalog
from .context import RunContext, iso_utc
from .plan import plan
from .report import validate_report
from .assemble import assemble_release
from .collect import collect_project
from .verify import verify_deployment, mark_verified
from .rollback import rollback


def _write(path: str, value: dict) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fetch_json(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _now_utc() -> str:
    return iso_utc(datetime.now(timezone.utc).replace(microsecond=0))


def cmd_plan(args: argparse.Namespace) -> int:
    catalog = Catalog.load(args.catalog)
    cutoff = args.cutoff or _now_utc()
    started_at = args.started_at or _now_utc()
    context, matrix = plan(
        catalog,
        run_id=args.run_id,
        code_sha=args.code_sha,
        cutoff_at=cutoff,
        scheduled_for=args.scheduled_for,
        started_at=started_at,
        trigger=args.trigger,
        artifact_root=args.artifact_root,
        publish_mode=args.publish_mode,
    )
    _write(args.context_out, context)
    _write(args.matrix_out, matrix)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    catalog = Catalog.load(args.catalog)
    context = RunContext.from_dict(_load_json(args.context))
    bundle = _load_json(args.bundle)
    report = bundle.get("report") if isinstance(bundle.get("report"), dict) else bundle
    errors = validate_report(report, context, catalog)
    result = {"project_id": report.get("project_id"), "validation_status": "passed" if not errors else "failed", "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def cmd_collect(args: argparse.Namespace) -> int:
    catalog = Catalog.load(args.catalog)
    context = RunContext.from_dict(_load_json(args.context))
    report = collect_project(catalog, context, args.project, args.work_dir)
    _write(args.report_out, report)
    return 0 if report.get("collection_status") == "success" else 1


def cmd_assemble(args: argparse.Namespace) -> int:
    catalog = Catalog.load(args.catalog)
    context = RunContext.from_dict(_load_json(args.context))
    inputs = _load_json(args.inputs)
    reports = inputs.get("projects") if isinstance(inputs.get("projects"), dict) else inputs
    baseline = _load_json(args.baseline) if args.baseline else None
    release = assemble_release(
        catalog,
        context,
        reports,
        release_id=args.release_id,
        published_at=args.published_at,
        baseline=baseline,
        baseline_release_id=args.baseline_release_id,
    )
    release["publishable"] = assemble_release_publishable(release)
    _write(args.out, release)
    return 0


def assemble_release_publishable(release: dict) -> bool:
    from .assemble import is_publishable  # local import keeps the CLI surface tight
    return is_publishable(release)


def cmd_verify_deployment(args: argparse.Namespace) -> int:
    expected = _load_json(args.manifest)
    deployed = _fetch_json(args.url) if args.url else _load_json(args.deployed)
    result = verify_deployment(deployed, expected)
    if result["verified"] and args.out:
        _write(args.out, mark_verified(expected))
        result["verified_manifest"] = args.out
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verified"] else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    baseline = _load_json(args.baseline)
    record = rollback(args.failed_release, baseline, reason=args.reason)
    if args.out:
        _write(args.out, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if record["active_release_id"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m monitor", description="Unified dashboard collection pipeline")
    sub = parser.add_subparsers(dest="command")
    plan_p = sub.add_parser("plan", help="freeze the run context and emit the project matrix")
    plan_p.add_argument("--catalog", required=True, help="path to catalog.json")
    plan_p.add_argument("--run-id", required=True, help="workflow run id + attempt")
    plan_p.add_argument("--code-sha", required=True, help="exact checkout commit")
    plan_p.add_argument("--cutoff", default=None, help="frozen cutoff (ISO, explicit timezone); defaults to now")
    plan_p.add_argument("--scheduled-for", default=None)
    plan_p.add_argument("--started-at", default=None)
    plan_p.add_argument("--trigger", default="schedule", choices=["schedule", "workflow_dispatch", "manual"])
    plan_p.add_argument("--artifact-root", default=None)
    plan_p.add_argument("--publish-mode", default="normal", choices=["normal", "shadow", "audit"])
    plan_p.add_argument("--context-out", required=True)
    plan_p.add_argument("--matrix-out", required=True)
    plan_p.set_defaults(func=cmd_plan)

    val_p = sub.add_parser("validate", help="validate a project bundle report against context and catalog")
    val_p.add_argument("--catalog", required=True)
    val_p.add_argument("--bundle", required=True, help="project bundle JSON (with a `report` field)")
    val_p.add_argument("--context", required=True, help="run context JSON from `plan`")
    val_p.set_defaults(func=cmd_validate)

    col_p = sub.add_parser("collect", help="collect one project and emit its collection report")
    col_p.add_argument("--catalog", required=True)
    col_p.add_argument("--context", required=True, help="run context JSON from `plan`")
    col_p.add_argument("--project", required=True, help="project_id to collect")
    col_p.add_argument("--work-dir", required=True, help="isolated working directory for the collector")
    col_p.add_argument("--report-out", required=True, help="path to write collection-report.json")
    col_p.set_defaults(func=cmd_collect)

    asm_p = sub.add_parser("assemble", help="compose a candidate release manifest")
    asm_p.add_argument("--catalog", required=True)
    asm_p.add_argument("--context", required=True)
    asm_p.add_argument("--inputs", required=True, help="JSON mapping project_id -> collection report")
    asm_p.add_argument("--baseline", default=None, help="optional prior verified release manifest")
    asm_p.add_argument("--baseline-release-id", default=None)
    asm_p.add_argument("--release-id", required=True)
    asm_p.add_argument("--published-at", required=True)
    asm_p.add_argument("--out", required=True)
    asm_p.set_defaults(func=cmd_assemble)

    ver_p = sub.add_parser("verify-deployment", help="verify the deployed release manifest matches the candidate")
    ver_p.add_argument("--manifest", required=True, help="expected candidate release manifest path")
    ver_p.add_argument("--url", default=None, help="URL of the deployed manifest (fetch)")
    ver_p.add_argument("--deployed", default=None, help="path to a downloaded deployed manifest (offline)")
    ver_p.add_argument("--out", default=None, help="write the verified manifest")
    ver_p.set_defaults(func=cmd_verify_deployment)

    rb_p = sub.add_parser("rollback", help="point the verified-release pointer at the trusted baseline")
    rb_p.add_argument("--failed-release", required=True, help="release_id whose verification failed")
    rb_p.add_argument("--baseline", required=True, help="trusted baseline release manifest path")
    rb_p.add_argument("--reason", default=None)
    rb_p.add_argument("--out", default=None, help="write the rollback record")
    rb_p.set_defaults(func=cmd_rollback)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())