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
from .context import iso_utc
from .plan import plan


def _write(path: str, value: dict) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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