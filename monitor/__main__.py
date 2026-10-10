"""``python -m monitor`` CLI (T-012).

Currently implements the ``plan`` prepare step. ``collect``/``validate``/
``assemble``/``verify-deployment``/``rollback`` are added as their pipeline
stages land; they are intentionally absent rather than stubbed as fake success.
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


def _write(path: str, value: dict) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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