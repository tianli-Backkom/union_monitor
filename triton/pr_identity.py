"""Resolve PR identities from explicit run evidence or fork/ref/commit evidence."""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


class PRResolver:
    def __init__(self, api, evidence_dir=None):
        self.api=api
        self.evidence_dir=Path(evidence_dir) if evidence_dir else None
        self.cache={}

    def read(self, path, many=False):
        key=(path,many)
        if key not in self.cache:
            self.cache[key]=self.api.pages(path) if many else self.api.get(path)[0]
        return self.cache[key]

    @staticmethod
    def same_source(run, pr):
        head=pr.get("head") or {}
        repo=head.get("repo") or {}
        source=run.get("head_repository") or {}
        if run.get("head_branch") and head.get("ref")!=run["head_branch"]: return False
        if source.get("id") and repo.get("id"): return source["id"]==repo["id"]
        if source.get("full_name") and repo.get("full_name"):
            return source["full_name"].lower()==repo["full_name"].lower()
        return False

    @staticmethod
    def existed(run, pr):
        if not pr.get("created_at") or not run.get("created_at"): return True
        parse=lambda x:datetime.fromisoformat(x.replace("Z","+00:00"))
        return parse(pr["created_at"])<=parse(run["created_at"])

    def resolve(self, run):
        linked=run.get("pull_requests") or []
        explicit={p["number"]:p for p in linked if p.get("number")}
        candidates=[]
        if explicit:
            candidates=[self.read(f"/pulls/{n}") for n in explicit]
        else:
            source=run.get("head_repository") or {}
            owner=(source.get("owner") or {}).get("login") or source.get("full_name","").split("/")[0]
            if owner and run.get("head_branch"):
                head=quote(owner+":"+run["head_branch"],safe="")
                candidates=self.read(f"/pulls?state=all&head={head}",many=True)
            if not candidates:
                candidates=self.read(f"/commits/{run['head_sha']}/pulls",many=True)
        matches=[]
        for pr in candidates:
            number=pr.get("number")
            if not number or not self.existed(run,pr): continue
            is_linked=number in explicit
            if not is_linked and not self.same_source(run,pr): continue
            sha=run.get("head_sha")
            snapshot=((explicit.get(number) or {}).get("head") or {}).get("sha")
            if is_linked and snapshot:
                matches.append((pr,snapshot,"run.pull_requests.head.sha"));continue
            if sha and sha==(pr.get("head") or {}).get("sha"):
                matches.append((pr,sha,"source_repository+branch+head_sha"));continue
            if sha and any(c.get("sha")==sha for c in self.read(f"/pulls/{number}/commits",many=True)):
                matches.append((pr,sha,"source_repository+branch+pr_commit_history"))
        # Never guess from title, nearest creation time, or the first branch match.
        matches={p[0]["number"]:p for p in matches}
        if len(matches)!=1:
            diagnostic={"run_id":run.get("id"),"head_sha":run.get("head_sha"),"head_branch":run.get("head_branch"),"candidates":[p.get("number") for p in candidates],"matches":list(matches)}
            self.save(run,diagnostic)
            raise ValueError(f"PR identity unresolved/ambiguous: {diagnostic}")
        pr,sha,method=next(iter(matches.values()))
        result={"pr":pr["number"],"pr_url":pr.get("html_url") or f"https://github.com/triton-lang/triton-ascend/pull/{pr['number']}",
                "pr_title":pr.get("title"),"base_branch":(pr.get("base") or {}).get("ref"),"head_sha":sha,
                "pr_evidence":{"method":method,"run_id":run.get("id"),"pr":pr["number"],"raw_run_sha":run.get("head_sha"),"resolved_head_sha":sha,
                               "source_repository":(pr.get("head",{}).get("repo") or {}).get("full_name"),"head_ref":(pr.get("head") or {}).get("ref")}}
        if not result["pr_title"] or not result["base_branch"]:
            raise ValueError(f"PR {pr['number']} metadata incomplete")
        self.save(run,result)
        return result

    def save(self,run,value):
        if self.evidence_dir:
            self.evidence_dir.mkdir(parents=True,exist_ok=True)
            (self.evidence_dir/f"{run['id']}.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")


def association_error_kind(exc):
    """Classify an association failure for honest reporting (UDR-002).

    A ``ValueError`` is an ordinary unknown outcome (no evidence, or ambiguous
    candidates); anything else — a network error, rate limit or other source
    request failure — is a source failure that must never be re-labelled
    ``unknown`` and never become a "verified" association.
    """
    return "unknown" if isinstance(exc, ValueError) else "source_failure"


def recover_identities(runs, resolver):
    """Re-attempt association for runs previously left ``unresolved`` (UDR-002).

    Each run/attempt is updated **in place** (never duplicated), so every
    identity still appears exactly once. Returns a list of recovery records
    that keep the previous unknown state and the new evidence-backed
    association as migration evidence.

    - A run that resolves now is recovered and recorded with ``recovery``
      migration evidence; its previous ``unresolved`` state is preserved in
      that record, not discarded.
    - A run that is still unresolved for lack or ambiguity of evidence stays
      untouched (NOT claimed recovered).
    - A source request failure propagates (raises) instead of being downgraded
      to ``unknown`` or wrapped as a recovered success.
    """
    records = []
    for run in runs:
        evidence = run.get("pr_evidence") or {}
        if evidence.get("method") != "unresolved":
            continue
        previous = {"method": "unresolved", "error": evidence.get("error"),
                    "run_id": run.get("id")}
        try:
            result = resolver.resolve(run)
        except ValueError:
            # Ordinary unknown/ambiguous: keep the run's honest unresolved gap.
            continue
        # Any non-ValueError (source request failure) propagates unchanged.
        for key in ("pr", "pr_url", "pr_title", "base_branch", "head_sha", "pr_evidence"):
            if key in result:
                run[key] = result[key]
        method = (result.get("pr_evidence") or {}).get("method")
        record = {
            "run_id": run.get("id"),
            "attempt": int(run.get("run_attempt") or 1),
            "previous": previous,
            "recovered_method": method,
            "pr": result.get("pr"),
            "head_sha": result.get("head_sha"),
        }
        run["recovery"] = record
        records.append(record)
    return records
