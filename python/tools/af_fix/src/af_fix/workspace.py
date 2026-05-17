# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: S603, S607

import re
import subprocess
from pathlib import Path

from af_fix.exceptions import AFFixError
from af_fix.models import IssueRef

AF_FIX_BRANCH_PREFIX = "af-fix/issue-"


def slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:max_len].rstrip("-")


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path_for(self, ref: IssueRef) -> Path:
        owner, name = ref.repo.split("/", 1)
        return self.root / f"{owner}__{name}" / f"issue-{ref.number}"

    def clone(self, ref: IssueRef, *, upstream_url: str) -> Path:
        path = self._path_for(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            subprocess.run(
                ["git", "clone", upstream_url, str(path)],
                check=True, capture_output=True,
            )
            # Ensure local identity so commits don't fail when global config is missing.
            subprocess.run(
                ["git", "config", "user.email", "af-fix@example.invalid"],
                cwd=path, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "af-fix"],
                cwd=path, check=True, capture_output=True,
            )
        return path

    def checkout_branch(self, workspace: Path, branch: str) -> None:
        if not branch.startswith(AF_FIX_BRANCH_PREFIX):
            raise ValueError(f"branch must start with {AF_FIX_BRANCH_PREFIX!r}: {branch!r}")
        subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=workspace, check=True, capture_output=True,
        )

    def diff_against_origin_main(self, workspace: Path) -> str:
        result = subprocess.run(
            ["git", "diff", "origin/main"],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        return result.stdout

    def commit_all(self, workspace: Path, *, message: str) -> str:
        subprocess.run(
            ["git", "add", "-A"], cwd=workspace, check=True, capture_output=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if not status:
            raise AFFixError("nothing to commit")
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=workspace, check=True, capture_output=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace, capture_output=True, text=True, check=True,
        ).stdout.strip()

    def add_fork_remote(self, workspace: Path, *, fork_url: str) -> None:
        existing = subprocess.run(
            ["git", "remote"],
            cwd=workspace, capture_output=True, text=True, check=True,
        ).stdout.split()
        if "fork" not in existing:
            subprocess.run(
                ["git", "remote", "add", "fork", fork_url],
                cwd=workspace, check=True, capture_output=True,
            )

    def push_to_fork(self, workspace: Path, *, branch: str) -> None:
        subprocess.run(
            ["git", "push", "-u", "fork", branch],
            cwd=workspace, check=True, capture_output=True,
        )

    def diff_stat(self, workspace: Path) -> str:
        result = subprocess.run(
            ["git", "diff", "--stat", "origin/main"],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        return result.stdout.strip() or "(empty)"
