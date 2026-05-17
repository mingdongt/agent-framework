# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from typing import Protocol

from af_fix.models import FixResult, PRResult
from af_fix.workspace import AF_FIX_BRANCH_PREFIX

_PR_BODY_TEMPLATE = """\
Fixes #{number}

## Summary
{summary}

## Changes
```
{diffstat}
```

## Agent trajectory (last 30 steps)
<details>
<summary>OpenHands trajectory excerpt</summary>

```
{trajectory}
```
</details>

---
Drafted by `af-fix` using OpenHands (CodeActAgent, claude-opus-4-7). Reviewed by @{fork_owner} before ready-for-review.
"""


def render_pr_body(result: FixResult, *, diffstat: str, fork_owner: str) -> str:
    return _PR_BODY_TEMPLATE.format(
        number=result.ref.number,
        summary=result.summary or "(no summary)",
        diffstat=diffstat,
        trajectory=(result.trajectory_excerpt or "")[:8000],
        fork_owner=fork_owner,
    )


class GitHubLike(Protocol):
    def authenticated_login(self) -> str: ...
    def find_open_pr(self, *, upstream: str, head: str) -> PRResult | None: ...
    def create_draft_pr(self, *, upstream: str, title: str, body: str, head: str, base: str) -> PRResult: ...


class WorkspaceManagerLike(Protocol):
    def add_fork_remote(self, workspace: Path, *, fork_url: str) -> None: ...
    def push_to_fork(self, workspace: Path, *, branch: str) -> None: ...
    def diff_stat(self, workspace: Path) -> str: ...


class PRSubmitter:
    def __init__(
        self,
        *,
        github: GitHubLike,
        workspace_manager: WorkspaceManagerLike,
        fork_owner: str,
    ) -> None:
        self._gh = github
        self._ws = workspace_manager
        self._fork_owner = fork_owner

    def verify_fork_owner(self) -> None:
        login = self._gh.authenticated_login()
        if login != self._fork_owner:
            raise ValueError(f"fork_owner mismatch: config says {self._fork_owner!r}, GitHub says {login!r}")

    def submit(self, result: FixResult, *, branch: str) -> PRResult:
        if not branch.startswith(AF_FIX_BRANCH_PREFIX):
            raise ValueError(f"branch must start with {AF_FIX_BRANCH_PREFIX!r}: {branch!r}")

        head = f"{self._fork_owner}:{branch}"
        existing = self._gh.find_open_pr(upstream=result.ref.repo, head=head)
        if existing is not None:
            return existing

        upstream_repo_name = result.ref.repo.split("/", 1)[1]
        fork_url = f"git@github.com:{self._fork_owner}/{upstream_repo_name}.git"
        self._ws.add_fork_remote(result.workspace, fork_url=fork_url)
        self._ws.push_to_fork(result.workspace, branch=branch)

        body = render_pr_body(result, diffstat=self._ws.diff_stat(result.workspace), fork_owner=self._fork_owner)
        title = f"fix: {result.summary}" if result.summary else f"fix: issue #{result.ref.number}"
        return self._gh.create_draft_pr(
            upstream=result.ref.repo,
            title=title,
            body=body,
            head=head,
            base="main",
        )
