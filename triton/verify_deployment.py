"""Post-deployment verification: every published data file must match this exact build (REQ-022)."""
import argparse
import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .quality import fingerprint

RETRIES = 8
RETRY_SLEEP = 20


class DeploymentMismatch(RuntimeError):
    """Published files disagree with this build's manifests."""


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def verify_triton(site, triton_manifest):
    """The page loads /data/triton.json at runtime — verify that real entry, not embedded HTML (REQ-022 AC02)."""
    manifest = json.loads(triton_manifest.read_text(encoding="utf-8"))
    url = site.rstrip("/") + "/data/triton.json"
    payload = json.loads(fetch(url).decode("utf-8"))
    if fingerprint(payload) != manifest["sha256"]:
        raise DeploymentMismatch(
            f"triton.json at {url}: published data differs from this build (expected fingerprint {manifest['sha256']})")
    return {"file": "triton.json", "url": url, "fingerprint": manifest["sha256"],
            "collected_at": manifest.get("collected_at")}


def verify_ubs(site, ubs_manifest):
    """The published index and every manifest-recorded snapshot must match this build (REQ-022 AC01)."""
    manifest = json.loads(ubs_manifest.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise DeploymentMismatch(f"{ubs_manifest} carries no file digests to verify against")
    checked, problems = [], []
    for rel, digest in sorted(files.items()):
        url = site.rstrip("/") + "/data/" + rel
        actual = sha256_bytes(fetch(url))
        if actual != digest:
            problems.append(f"{rel} at {url}: published sha256 {actual}, this build recorded {digest}")
        else:
            checked.append({"file": rel, "url": url, "sha256": digest})
    if problems:
        raise DeploymentMismatch("; ".join(problems))
    return {"files": checked, "file_count": len(checked), "fingerprint": manifest.get("fingerprint"),
            "generated_at": manifest.get("generated_at")}


def verify_published_manifests(site, triton_manifest, ubs_manifest):
    """The published manifests themselves must be this build's manifests."""
    problems = []
    for rel, path in (("triton-manifest.json", triton_manifest), ("ubs-manifest.json", ubs_manifest)):
        url = site.rstrip("/") + "/data/" + rel
        actual = sha256_bytes(fetch(url))
        expected = sha256_bytes(path.read_bytes())
        if actual != expected:
            problems.append(f"{rel} at {url}: published manifest sha256 {actual} differs from this build's {expected}")
    if problems:
        raise DeploymentMismatch("; ".join(problems))
    return {"published_manifests": ["triton-manifest.json", "ubs-manifest.json"]}


def check_all(site, triton_manifest, ubs_manifest):
    """Run every verifier; transient fetch errors propagate, mismatches accumulate with file names."""
    checks = (
        ("triton", verify_triton, (triton_manifest,)),
        ("ubs", verify_ubs, (ubs_manifest,)),
        ("manifests", verify_published_manifests, (triton_manifest, ubs_manifest)),
    )
    problems, records = [], {}
    for name, verify, arguments in checks:
        try:
            records[name] = verify(site, *arguments)
        except DeploymentMismatch as error:
            problems.extend(str(error).split("; "))
    return records, problems


def record_success(site, records):
    record = {"run_id": os.environ.get("GITHUB_RUN_ID"), "run_number": os.environ.get("GITHUB_RUN_NUMBER"),
              "workflow": os.environ.get("GITHUB_WORKFLOW"), "site": site.rstrip("/"),
              "verified_at": datetime.now(timezone.utc).isoformat(),
              "triton": records.get("triton"), "ubs": records.get("ubs")}
    print("[verify-deployment] PASS " + json.dumps(record, ensure_ascii=False), flush=True)
    write_summary(success_markdown(record))
    return record


def success_markdown(record):
    triton, ubs = record["triton"], record["ubs"]
    lines = ["## 部署后数据验证通过（REQ-022）",
             f"- 运行：{record.get('workflow') or 'workflow'} run {record.get('run_number') or '-'}（ID {record.get('run_id') or '-'}）",
             f"- 校验时刻：{record['verified_at']}",
             f"- Triton：{triton['url']} 指纹 `{triton['fingerprint']}`（采集时间 {triton.get('collected_at')}）",
             f"- UBS：{ubs['file_count']} 个公开文件逐一比对通过，束指纹 `{ubs['fingerprint']}`",
             "- 公开 manifest：triton-manifest.json 与 ubs-manifest.json 与本次构建逐字节一致"]
    return "\n".join(lines) + "\n"


def fail(site, problems):
    message = ("deployment verification FAILED — published files disagree with this build: " + "; ".join(problems)
               + ". The workflow fails; no rollback is claimed or performed "
                 "(Pages keeps serving the deployed version until a later run replaces it).")
    print(f"::error::[verify-deployment] {message}", flush=True)
    lines = (["## 部署后数据验证失败（REQ-022）", "不一致文件："] + [f"- {problem}" for problem in problems]
             + ["", "本次运行已失败；未执行也不会宣称自动回滚，Pages 继续提供当前已部署版本。"])
    write_summary("\n".join(lines) + "\n")
    raise DeploymentMismatch(message)


def write_summary(markdown):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")


def run(site, triton_manifest, ubs_manifest):
    """Verify until consistent or retries run out; return the success record (REQ-022 AC04)."""
    problems = []
    for attempt in range(1, RETRIES + 1):
        try:
            records, problems = check_all(site, triton_manifest, ubs_manifest)
        except Exception as error:  # network/parse failures retry like mismatches
            problems = [f"verification error: {error!r}"]
        if not problems:
            return record_success(site, records)
        print(f"[verify-deployment] attempt {attempt}/{RETRIES}: " + "; ".join(problems), flush=True)
        if attempt < RETRIES:
            time.sleep(RETRY_SLEEP)
    fail(site, problems)


def main():
    parser = argparse.ArgumentParser(
        description="Verify published dashboard data against this build's manifests (REQ-022)")
    parser.add_argument("url", help="published site base URL, e.g. https://user.github.io/repo")
    parser.add_argument("--triton-manifest", default="web/data/triton-manifest.json")
    parser.add_argument("--ubs-manifest", default="web/data/ubs-manifest.json")
    args = parser.parse_args()
    triton_manifest, ubs_manifest = Path(args.triton_manifest), Path(args.ubs_manifest)
    for manifest in (triton_manifest, ubs_manifest):
        if not manifest.is_file():
            print(f"::error::[verify-deployment] manifest missing: {manifest} "
                  "— cannot verify without this build's baseline", flush=True)
            return 1
    try:
        run(args.url, triton_manifest, ubs_manifest)
    except DeploymentMismatch:
        return 1  # details already reported via ::error:: and the run summary
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
