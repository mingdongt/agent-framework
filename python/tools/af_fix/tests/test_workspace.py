# Copyright (c) Microsoft. All rights reserved.

import subprocess
from pathlib import Path

import pytest

from af_fix.exceptions import AFFixError
from af_fix.models import IssueRef
from af_fix.workspace import WorkspaceManager, slug


def _init_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=seed, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=seed, check=True)
    (seed / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=seed, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=seed, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=seed, check=True, capture_output=True)
    return origin


def test_slug() -> None:
    assert slug("Fix the bug!") == "fix-the-bug"
    assert slug("a/b\\c:d") == "a-b-c-d"
    assert slug("   ") == ""


def test_clone_creates_workspace(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    assert ws.exists()
    assert (ws / "README.md").exists()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ws, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert len(head) == 40


def test_checkout_branch(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    mgr.checkout_branch(ws, "af-fix/issue-42-x")
    cur = subprocess.run(
        ["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert cur == "af-fix/issue-42-x"


def test_checkout_branch_rejects_non_af_fix(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    with pytest.raises(ValueError, match="af-fix/issue-"):
        mgr.checkout_branch(ws, "wrong-prefix")


def test_diff_against_origin_main(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    (ws / "README.md").write_text("hi\nworld\n", encoding="utf-8")
    diff = mgr.diff_against_origin_main(ws)
    assert "+world" in diff


def test_commit_all_with_changes(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    mgr.checkout_branch(ws, "af-fix/issue-42-x")
    (ws / "new.txt").write_text("x", encoding="utf-8")
    sha = mgr.commit_all(ws, message="fix: new file")
    assert len(sha) == 40


def test_commit_all_no_changes_raises(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    mgr = WorkspaceManager(root=tmp_path / "ws")
    ref = IssueRef(repo="local/test", number=42)
    ws = mgr.clone(ref, upstream_url=str(origin))
    mgr.checkout_branch(ws, "af-fix/issue-42-x")
    with pytest.raises(AFFixError, match="nothing to commit"):
        mgr.commit_all(ws, message="empty")
