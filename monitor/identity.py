"""Collision-free stable identities for projects, repositories, PRs and batches.

Identities must not change when records are re-sorted, re-grouped, re-collected
or when two same-number PRs appear in different repositories. They also must not
collide for same-named repositories hosted on different source instances or
organisations (T-005).

Rules:
- repository id      = ``<source_instance_id>:<owner>/<repository>`` (case-preserved)
- PR id              = ``<repository_id>#<number>``
- UBS batch id       = the complete Jenkins trigger URL
- Triton batch id    = ``run:<run_id>:attempt:<n>`` (rerun) or ``sha:<head_sha>`` (first commit)
- task id            = ``<batch_id>::task::<source_task_key>``

None of these derive from list position, sort order or a bare title/序号.
"""

from __future__ import annotations


def repository_id(source_instance_id: str, owner: str, repository: str) -> str:
    """Compose ``source_instance_id:owner/repository`` without lowercasing."""
    if not source_instance_id or not owner or not repository:
        raise ValueError(
            "repository identity requires source instance, owner and repository"
        )
    return f"{source_instance_id}:{owner}/{repository}"


def split_repository_id(repository_id: str) -> tuple[str, str, str]:
    """Return ``(source_instance_id, owner, repository)`` for a valid id."""
    if ":" not in repository_id or "/" not in repository_id:
        raise ValueError(f"malformed repository id: {repository_id!r}")
    instance, _, path = repository_id.partition(":")
    owner, _, repo = path.partition("/")
    if not instance or not owner or not repo:
        raise ValueError(f"malformed repository id: {repository_id!r}")
    return instance, owner, repo


def pr_id(repository_id: str, number: int) -> str:
    """Compose the PR identity that includes source instance + full repository."""
    if not isinstance(number, int) or number <= 0:
        raise ValueError("PR number must be a positive integer")
    if ":" not in repository_id or "/" not in repository_id:
        raise ValueError(f"malformed repository id: {repository_id!r}")
    return f"{repository_id}#{number}"


def batch_id_for_trigger(trigger_url: str) -> str:
    """UBS batch identity is the complete Jenkins trigger URL."""
    if not trigger_url:
        raise ValueError("trigger URL is required for UBS batch identity")
    return trigger_url


def batch_id_for_attempt(run_id: str, attempt: int | None = None) -> str:
    """Triton manual rerun batch identity: workflow run id + attempt."""
    if not run_id:
        raise ValueError("run id is required for a rerun batch identity")
    return f"run:{run_id}:attempt:{attempt if attempt is not None else 1}"


def batch_id_for_commit(head_sha: str) -> str:
    """Triton first-commit batch identity is the real PR head SHA."""
    if not head_sha:
        raise ValueError("head sha is required for a commit batch identity")
    return f"sha:{head_sha}"


def task_id(batch_id: str, source_task_key: str) -> str:
    """Compose a task identity from its batch identity and source task key."""
    if not batch_id or not source_task_key:
        raise ValueError("task identity requires batch id and source task key")
    return f"{batch_id}::task::{source_task_key}"
