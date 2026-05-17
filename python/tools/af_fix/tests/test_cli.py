# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_fix.cli import (
    PRDecision,
    ask_pr_decision,
    parse_args_with_compat,
    parse_retry_id,
    refuse_in_ci,
    run_pipeline,
)
from af_fix.models import AttemptOutcome, FixResult, Issue, IssueRef, PRResult, ScoreResult


def test_parser_defaults() -> None:
    # With subcommands, use `run` explicitly or via compat wrapper
    args = parse_args_with_compat(["--top", "5"])
    assert args.top == 5
    assert args.triage_only is False
    assert args.no_push is False
    assert args.dry_run is False
    assert args.retry_failed is False
    assert args.retry_id is None
    assert args.repos is None


def test_parser_all_flags() -> None:
    args = parse_args_with_compat([
        "--top", "3",
        "--triage-only",
        "--no-push",
        "--dry-run",
        "--retry-failed",
        "--retry-id", "o/r:42",
        "--repos", "a/b,c/d",
    ])
    assert args.top == 3
    assert args.triage_only is True
    assert args.no_push is True
    assert args.dry_run is True
    assert args.retry_failed is True
    assert args.retry_id == "o/r:42"
    assert args.repos == "a/b,c/d"


def test_parse_retry_id_valid() -> None:
    ref = parse_retry_id("microsoft/agent-framework:5887")
    assert ref.repo == "microsoft/agent-framework"
    assert ref.number == 5887


def test_parse_retry_id_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_retry_id("missing-colon")
    with pytest.raises(ValueError):
        parse_retry_id("no-slash:1")


def test_refuse_in_ci_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_FIX_DISABLED", "1")
    with pytest.raises(SystemExit) as exc:
        refuse_in_ci()
    assert exc.value.code != 0


def test_no_refuse_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AF_FIX_DISABLED", raising=False)
    refuse_in_ci()


def _issue(repo: str, n: int) -> Issue:
    return Issue(ref=IssueRef(repo=repo, number=n), title=f"t{n}", body=f"b{n}")


def test_run_pipeline_triage_only(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1), _issue("o/r", 2)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
        ScoreResult(ref=IssueRef(repo="o/r", number=2), score=2, reason="r2"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    args = parse_args_with_compat(["--top", "1", "--triage-only"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=MagicMock(),
        workspace_manager=MagicMock(),
        pr_submitter=MagicMock(),
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
    )
    assert exit_code == 0
    triage.score_all.assert_called_once()


def test_run_pipeline_full_flow_pr_opened(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    ws_mgr = MagicMock()
    ws_mgr.clone.return_value = ws_path

    runner = MagicMock()
    runner.run.return_value = FixResult(
        success=True,
        ref=IssueRef(repo="o/r", number=1),
        workspace=ws_path,
        diff="some diff",
        summary="fix x",
    )

    pr_sub = MagicMock()
    pr_sub.submit.return_value = PRResult(number=999, url="https://x/pr/999")

    args = parse_args_with_compat(["--top", "1"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=runner,
        workspace_manager=ws_mgr,
        pr_submitter=pr_sub,
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
        pr_decision_callback=lambda r, b: PRDecision.YES,
    )
    assert exit_code == 0
    pr_sub.submit.assert_called_once()
    state.record_attempt.assert_called_once()
    kwargs = state.record_attempt.call_args.kwargs
    assert kwargs["outcome"] == AttemptOutcome.PR_OPENED


def test_run_pipeline_records_gave_up_when_agent_gives_up(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    ws_mgr = MagicMock()
    ws_mgr.clone.return_value = ws_path

    runner = MagicMock()
    runner.run.return_value = FixResult(
        success=False,
        ref=IssueRef(repo="o/r", number=1),
        workspace=ws_path,
        gave_up=True,
        reason="cannot reproduce",
    )

    args = parse_args_with_compat(["--top", "1"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=runner,
        workspace_manager=ws_mgr,
        pr_submitter=MagicMock(),
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
    )
    assert exit_code == 0
    kwargs = state.record_attempt.call_args.kwargs
    assert kwargs["outcome"] == AttemptOutcome.GAVE_UP


# ── Task B: PRDecision + ask_pr_decision + per-PR HITL in run_pipeline ───────


def test_pr_decision_yes() -> None:
    decision = ask_pr_decision(prompt_fn=lambda _: "y", show=lambda: None)
    assert decision is PRDecision.YES


def test_pr_decision_no_default() -> None:
    decision = ask_pr_decision(prompt_fn=lambda _: "", show=lambda: None)
    assert decision is PRDecision.NO


def test_pr_decision_edit() -> None:
    decision = ask_pr_decision(prompt_fn=lambda _: "edit", show=lambda: None)
    assert decision is PRDecision.EDIT


def test_pr_decision_handles_eof() -> None:
    def raises_eof(_: str) -> str:
        raise EOFError

    decision = ask_pr_decision(prompt_fn=raises_eof, show=lambda: None)
    assert decision is PRDecision.NO


def test_run_pipeline_skips_pr_when_user_rejects(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    ws_mgr = MagicMock()
    ws_mgr.clone.return_value = ws_path

    runner = MagicMock()
    runner.run.return_value = FixResult(
        success=True,
        ref=IssueRef(repo="o/r", number=1),
        workspace=ws_path,
        diff="some diff",
        summary="fix x",
    )

    pr_sub = MagicMock()

    args = parse_args_with_compat(["--top", "1"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=runner,
        workspace_manager=ws_mgr,
        pr_submitter=pr_sub,
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
        pr_decision_callback=lambda result, branch: PRDecision.NO,
    )
    assert exit_code == 0
    pr_sub.submit.assert_not_called()
    kwargs = state.record_attempt.call_args.kwargs
    assert kwargs["outcome"] == AttemptOutcome.GAVE_UP
    assert kwargs["give_up_reason"] == "user-rejected"


def test_run_pipeline_edit_preserves_workspace(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    ws_mgr = MagicMock()
    ws_mgr.clone.return_value = ws_path

    runner = MagicMock()
    runner.run.return_value = FixResult(
        success=True,
        ref=IssueRef(repo="o/r", number=1),
        workspace=ws_path,
        diff="some diff",
        summary="fix x",
    )

    pr_sub = MagicMock()

    args = parse_args_with_compat(["--top", "1"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=runner,
        workspace_manager=ws_mgr,
        pr_submitter=pr_sub,
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
        pr_decision_callback=lambda result, branch: PRDecision.EDIT,
    )
    assert exit_code == 0
    pr_sub.submit.assert_not_called()
    # No state record for edit — left for manual handling
    state.record_attempt.assert_not_called()


def test_run_pipeline_yes_submits_pr(tmp_path: Path) -> None:
    issues = [_issue("o/r", 1)]
    triage = MagicMock()
    triage.score_all.return_value = [
        ScoreResult(ref=IssueRef(repo="o/r", number=1), score=9, reason="r1"),
    ]
    github = MagicMock()
    github.list_open_issues.return_value = issues
    state = MagicMock()
    state.should_skip.return_value = False

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    ws_mgr = MagicMock()
    ws_mgr.clone.return_value = ws_path

    runner = MagicMock()
    runner.run.return_value = FixResult(
        success=True,
        ref=IssueRef(repo="o/r", number=1),
        workspace=ws_path,
        diff="some diff",
        summary="fix x",
    )

    pr_sub = MagicMock()
    pr_sub.submit.return_value = PRResult(number=999, url="https://x/pr/999")

    args = parse_args_with_compat(["--top", "1"])
    exit_code = run_pipeline(
        args=args,
        target_repos=["o/r"],
        github=github,
        state=state,
        state_path=tmp_path / "state.json",
        triage_agent=triage,
        runner=runner,
        workspace_manager=ws_mgr,
        pr_submitter=pr_sub,
        confirm_callback=lambda ids: True,
        upstream_url_for=lambda r: f"https://x/{r}.git",
        pr_decision_callback=lambda result, branch: PRDecision.YES,
    )
    assert exit_code == 0
    pr_sub.submit.assert_called_once()
    kwargs = state.record_attempt.call_args.kwargs
    assert kwargs["outcome"] == AttemptOutcome.PR_OPENED


# ── Task C: subcommand parser + parse_args_with_compat ───────────────────────


def test_parser_run_subcommand() -> None:
    from af_fix.cli import parse_args_with_compat

    args = parse_args_with_compat(["run", "--top", "3"])
    assert args.command == "run"
    assert args.top == 3


def test_parser_triage_subcommand() -> None:
    from af_fix.cli import parse_args_with_compat

    args = parse_args_with_compat(["triage", "--top", "10"])
    assert args.command == "triage"
    assert args.top == 10


def test_parser_execute_subcommand_from() -> None:
    from af_fix.cli import parse_args_with_compat

    args = parse_args_with_compat(["execute", "--from", "/tmp/t.md"])
    assert args.command == "execute"
    assert args.from_path == "/tmp/t.md"


def test_parser_execute_auto_submit() -> None:
    from af_fix.cli import parse_args_with_compat

    args = parse_args_with_compat(["execute", "--from", "/tmp/t.md", "--auto-submit"])
    assert args.auto_submit is True


def test_parser_backward_compat_no_subcommand() -> None:
    from af_fix.cli import parse_args_with_compat

    # Old-style: `af-fix --top 5` should be treated as `af-fix run --top 5`
    args = parse_args_with_compat(["--top", "5"])
    assert args.command == "run"
    assert args.top == 5
