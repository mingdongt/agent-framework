# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_fix.models import FixResult, IssueRef, PRResult
from af_fix.pr_submitter import PRSubmitter, render_pr_body


def _result(
    number: int = 42,
    summary: str = "fix bug",
    workspace: Path | None = None,
) -> FixResult:
    return FixResult(
        success=True,
        ref=IssueRef(repo="o/r", number=number),
        workspace=workspace or Path("/tmp/ws"),
        diff="diff --git a/foo b/foo\n+x\n",
        summary=summary,
        trajectory_excerpt="step1\nstep2\n",
    )


def test_render_pr_body_contains_required_sections() -> None:
    body = render_pr_body(_result(), diffstat="foo | 1 +", fork_owner="me")
    assert "Fixes #42" in body
    assert "fix bug" in body
    assert "foo | 1 +" in body
    assert "step1" in body
    assert "OpenHands" in body
    assert "@me" in body


def test_submitter_rejects_non_af_fix_branch(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    fake_gh = MagicMock()
    fake_gh.authenticated_login.return_value = "me"
    fake_ws_mgr = MagicMock()
    submitter = PRSubmitter(github=fake_gh, workspace_manager=fake_ws_mgr, fork_owner="me")
    with pytest.raises(ValueError, match="af-fix/issue-"):
        submitter.submit(_result(workspace=workspace), branch="random-branch")


def test_submitter_refuses_mismatched_fork_owner() -> None:
    fake_gh = MagicMock()
    fake_gh.authenticated_login.return_value = "someone-else"
    submitter = PRSubmitter(github=fake_gh, workspace_manager=MagicMock(), fork_owner="me")
    with pytest.raises(ValueError, match="fork_owner mismatch"):
        submitter.verify_fork_owner()


def test_submitter_returns_existing_pr_when_present(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_gh = MagicMock()
    fake_gh.authenticated_login.return_value = "me"
    fake_gh.find_open_pr.return_value = PRResult(number=99, url="https://x/pr/99")

    fake_ws_mgr = MagicMock()

    submitter = PRSubmitter(github=fake_gh, workspace_manager=fake_ws_mgr, fork_owner="me")
    pr = submitter.submit(_result(workspace=workspace), branch="af-fix/issue-42-x")
    assert pr.number == 99
    fake_gh.create_draft_pr.assert_not_called()
    fake_ws_mgr.push_to_fork.assert_not_called()


def test_submitter_happy_path(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_gh = MagicMock()
    fake_gh.authenticated_login.return_value = "me"
    fake_gh.find_open_pr.return_value = None
    fake_gh.create_draft_pr.return_value = PRResult(number=5888, url="https://x/pr/5888")

    fake_ws_mgr = MagicMock()
    fake_ws_mgr.diff_stat.return_value = "foo | 1 +"

    submitter = PRSubmitter(github=fake_gh, workspace_manager=fake_ws_mgr, fork_owner="me")
    pr = submitter.submit(_result(workspace=workspace), branch="af-fix/issue-42-x")

    assert pr.number == 5888
    fake_ws_mgr.add_fork_remote.assert_called_once()
    fake_ws_mgr.push_to_fork.assert_called_once_with(workspace, branch="af-fix/issue-42-x")
    fake_gh.create_draft_pr.assert_called_once()
    call_kwargs = fake_gh.create_draft_pr.call_args.kwargs
    assert call_kwargs["upstream"] == "o/r"
    assert call_kwargs["head"] == "me:af-fix/issue-42-x"
    assert call_kwargs["base"] == "main"
    assert call_kwargs["title"].startswith("fix:")
