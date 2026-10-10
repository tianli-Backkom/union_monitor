#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A02/A03 整改复验探针：清单自洽校验与每日新版本重盖。

以 audit/2026-10-10 对抗审查 A02/A03 的同一组输入复跑反例，验证修复后：

A02（每日暖缓存恢复后合法新版本无法重写 manifest）：
1. daily_refresh_existing_manifest：恢复缓存 A（含 A 清单）后仅推进索引
   generated_at（结构合法的新数据 B），生产 main(--write-manifest) 必须
   成功并以 B 指纹重盖清单，而非 exit 1；
2. incremental_reuse_verifies_manifest_strictly：增量复用同一份 A 内容时
   verify/--ensure-manifest 仍严格验证 A 清单；内容漂移（镜像同步的
   混版快照）仍被 manifest mismatch 阻断——放宽只针对每日新版本。

A03（缺文件的 manifest 可通过门禁及发布后验证）：
3. truncated_manifest_files_blocked_local：将有效 manifest.files 缩为仅
   repositories.json 并保留原 fingerprint，本地门禁三种模式（verify/
   --ensure-manifest/--write-manifest）必须全部拒绝（指纹↔文件表自洽
   校验；本地计算 11 个文件、清单记录 1 个不得通过）；
4. deployment_truncated_manifest_rejected：发布后 verify_ubs 对同一截断
   清单必须立即拒绝，且不抓取任何 UBS 数据文件；
5. deployment_recomputed_manifest_cannot_shrink_scope：截断后重算指纹的
   自洽清单仍被发布后校验拒绝——必需文件集由已发布索引推导，九份快照
   仍被逐一抓取比对，清单自身无法缩小校验范围；
6. deployment_complete_manifest_fetches_all：完整清单逐文件抓取校验，
   覆盖索引引用的全部快照与兼容文件。

全部篡改仅作用于临时目录中的合成快照束；不修改任何业务源码、测试、
冻结证据或真实快照。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import validate_bundle  # noqa: E402
import triton.verify_deployment as vd  # noqa: E402
from test_bundle_verifier import run_verifier, write_bundle  # noqa: E402

NINE_REPOS = ("ubs-engine", "ubs-comm", "ubs-virt", "ubs-io", "ubs-mem",
              "OmniStateStore", "ham", "ubturbo", "ubs-atomic")
SITE = "https://example.github.io/ubs_core_monitor"


def read_manifest(workspace):
    return json.loads((workspace / "web/data/ubs-manifest.json").read_text("utf-8"))


def probe_daily_refresh(tmp):
    workspace = tmp / "daily-refresh"
    write_bundle(workspace, repos=NINE_REPOS, generated_at="2026-10-08T03:01:57+00:00")
    restore_exit, _ = run_verifier(workspace, "--write-manifest")
    fp_a = read_manifest(workspace)["fingerprint"]
    write_bundle(workspace, repos=NINE_REPOS, generated_at="2026-10-09T03:01:57+00:00")
    code, out = run_verifier(workspace, "--write-manifest")
    stamped = read_manifest(workspace)
    code_plain, out_plain = run_verifier(workspace)
    return {
        "restore_cache_a_exit": restore_exit,
        "bundle_b_write_manifest_exit": code,
        "stale_manifest_reported_as_new_version": "stale manifest from the previous bundle" in out,
        "manifest_written": "manifest=written" in out,
        "restamped_fingerprint": stamped["fingerprint"],
        "fingerprint_advanced": stamped["fingerprint"] != fp_a,
        "plain_verify_exit": code_plain,
        "plain_verify_state": "manifest=verified" in out_plain,
    }


def probe_incremental_reuse(tmp):
    workspace = tmp / "incremental-reuse"
    write_bundle(workspace, repos=NINE_REPOS)
    run_verifier(workspace, "--write-manifest")
    reuse_verify = run_verifier(workspace)
    reuse_ensure = run_verifier(workspace, "--ensure-manifest")
    drift_payload = json.loads((workspace / "web/data/repos/ubs-comm.json").read_text("utf-8"))
    drift_payload["prs"].append({"number": 99, "state": "open", "batches": []})
    drift_bytes = json.dumps(drift_payload, ensure_ascii=False).encode("utf-8")
    (workspace / "web/data/repos/ubs-comm.json").write_bytes(drift_bytes)
    (workspace / "data/repos/ubs-comm.json").write_bytes(drift_bytes)
    drift_verify = run_verifier(workspace)
    drift_ensure = run_verifier(workspace, "--ensure-manifest")
    return {
        "reuse_a_verify_exit": reuse_verify[0],
        "reuse_a_ensure_exit": reuse_ensure[0],
        "reuse_a_verified": "manifest=verified" in reuse_verify[1],
        "drift_verify_exit": drift_verify[0],
        "drift_ensure_exit": drift_ensure[0],
        "drift_reports_manifest_mismatch": "manifest mismatch" in drift_verify[1],
    }


def probe_truncated_local(tmp):
    workspace = tmp / "truncated-local"
    write_bundle(workspace, repos=NINE_REPOS)
    run_verifier(workspace, "--write-manifest")
    expected_files = len(read_manifest(workspace)["files"])
    path = workspace / "web/data/ubs-manifest.json"
    manifest = read_manifest(workspace)
    manifest["files"] = {"repositories.json": manifest["files"]["repositories.json"]}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    modes = {}
    for name, flags in (("verify", ()), ("ensure", ("--ensure-manifest",)),
                        ("write", ("--write-manifest",))):
        code, out = run_verifier(workspace, *flags)
        modes[name] = {"exit": code, "internally_inconsistent": "internally inconsistent" in out}
    return {"local_computed_files": expected_files, "manifest_recorded_files": 1, "modes": modes}


def build_deployment_site():
    entries, site, files = [], {}, {}
    for name in NINE_REPOS:
        rel = f"repos/{name}.json"
        payload = json.dumps({"meta": {"repository": f"openeuler/{name}"}},
                             ensure_ascii=False).encode("utf-8")
        site[rel] = payload
        files[rel] = hashlib.sha256(payload).hexdigest()
        entries.append({"name": name, "repository": f"openeuler/{name}",
                        "status": "success", "snapshot": rel})
    index = json.dumps({"schema_version": 3, "repositories": entries},
                       ensure_ascii=False).encode("utf-8")
    site["repositories.json"] = index
    files["repositories.json"] = hashlib.sha256(index).hexdigest()
    compat = json.dumps({"compat": True}).encode("utf-8")
    site["snapshot.json"] = compat
    files["snapshot.json"] = hashlib.sha256(compat).hexdigest()
    return site, files


def run_verify_ubs(site, manifest_path):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        rel = url.split("/data/", 1)[1]
        if rel not in site:
            raise RuntimeError(f"404 not found: {url}")
        return site[rel]

    with patch.object(vd, "fetch", fake_fetch):
        try:
            record = vd.verify_ubs(SITE, manifest_path)
            return {"ok": True, "file_count": record["file_count"],
                    "fetched_urls": sorted(set(calls))}
        except vd.DeploymentMismatch as error:
            return {"ok": False, "error": str(error), "fetched_urls": sorted(set(calls))}


def probe_deployment(tmp):
    site, files = build_deployment_site()
    complete = tmp / "ubs-manifest-complete.json"
    complete.write_text(json.dumps(
        {"schema": 1, "fingerprint": validate_bundle.recompute_fingerprint(files),
         "generated_at": "2026-10-10T03:00:00+00:00", "files": files},
        ensure_ascii=False), "utf-8")

    truncated = tmp / "ubs-manifest-truncated.json"
    manifest = json.loads(complete.read_text("utf-8"))
    manifest["files"] = {"repositories.json": files["repositories.json"]}
    truncated.write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")

    recomputed = tmp / "ubs-manifest-recomputed.json"
    manifest = json.loads(complete.read_text("utf-8"))
    del manifest["files"]["repos/ubs-engine.json"]
    del manifest["files"]["repos/ubs-atomic.json"]
    manifest["fingerprint"] = validate_bundle.recompute_fingerprint(manifest["files"])
    recomputed.write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")

    snapshot_urls = [f"{SITE}/data/repos/{name}.json" for name in NINE_REPOS]
    return {
        "complete_manifest": run_verify_ubs(site, complete),
        "truncated_manifest": run_verify_ubs(site, truncated),
        "recomputed_manifest": run_verify_ubs(site, recomputed),
        "expected_snapshot_urls": sorted(snapshot_urls),
    }


def main():
    tmp = Path(tempfile.mkdtemp(prefix="a02a03-probes-"))
    try:
        daily = probe_daily_refresh(tmp)
        reuse = probe_incremental_reuse(tmp)
        local = probe_truncated_local(tmp)
        deployment = probe_deployment(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    complete = deployment["complete_manifest"]
    truncated = deployment["truncated_manifest"]
    recomputed = deployment["recomputed_manifest"]
    checks = {
        "daily_refresh_restamps_new_version": (
            daily["restore_cache_a_exit"] == 0
            and daily["bundle_b_write_manifest_exit"] == 0
            and daily["stale_manifest_reported_as_new_version"]
            and daily["manifest_written"]
            and daily["fingerprint_advanced"]
            and daily["plain_verify_exit"] == 0
            and daily["plain_verify_state"]),
        "incremental_reuse_stays_strict": (
            reuse["reuse_a_verify_exit"] == 0 and reuse["reuse_a_ensure_exit"] == 0
            and reuse["reuse_a_verified"]
            and reuse["drift_verify_exit"] != 0 and reuse["drift_ensure_exit"] != 0
            and reuse["drift_reports_manifest_mismatch"]),
        "truncated_table_blocked_in_every_mode": (
            local["local_computed_files"] == 11
            and all(mode["exit"] != 0 and mode["internally_inconsistent"]
                    for mode in local["modes"].values())),
        "deployment_truncated_manifest_rejected_before_fetch": (
            not truncated["ok"]
            and "internally inconsistent" in truncated["error"]
            and truncated["fetched_urls"] == []),
        "deployment_recomputed_manifest_cannot_shrink_scope": (
            not recomputed["ok"]
            and "absent from this build's manifest" in recomputed["error"]
            and "repos/ubs-engine.json" in recomputed["error"]
            and "repos/ubs-atomic.json" in recomputed["error"]
            and all(url in recomputed["fetched_urls"]
                    for url in deployment["expected_snapshot_urls"])),
        "deployment_complete_manifest_fetches_all": (
            complete["ok"] and complete["file_count"] == 11
            and complete["fetched_urls"] == sorted(
                deployment["expected_snapshot_urls"]
                + [f"{SITE}/data/repositories.json", f"{SITE}/data/snapshot.json"])),
    }
    report = {
        "finding": "A02/A03 · P1 · 每日新版本被旧清单阻断；缺文件的清单可通过门禁及发布后验证",
        "requirements": ["REQ-012", "REQ-013", "REQ-022"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "probes": {
            "daily_refresh_existing_manifest": daily,
            "incremental_reuse_verifies_manifest_strictly": reuse,
            "truncated_manifest_files_blocked_local": local,
            "deployment_verification": deployment,
        },
        "checks": checks,
        "all_counterexamples_defeated": all(checks.values()),
        "notes": [
            "All tampering applies only to synthetic bundles in a temporary directory; no production source, test, frozen audit evidence, or real snapshot was modified.",
            "A02 mirrors adversarial-review.md probe daily_refresh_existing_manifest: restore cache A (manifest included), advance only the index generated_at, then run production main(--write-manifest).",
            "A03 mirrors probe truncated_manifest_files: shrink manifest.files to repositories.json only, then run the local gate in every mode and triton.verify_deployment.verify_ubs against the published site.",
            "Deployment fetches are intercepted in memory (unittest.mock.patch); the required file set is derived from the published index, so a manifest cannot shrink what gets verified.",
        ],
    }
    out = ROOT / "audit" / "2026-10-10-remediation" / "evidence" / "a02a03-bundle-chain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"path": str(out), "checks": checks,
                      "all_counterexamples_defeated": report["all_counterexamples_defeated"]},
                     ensure_ascii=False, indent=2))
    return 0 if report["all_counterexamples_defeated"] else 1


if __name__ == "__main__":
    sys.exit(main())
