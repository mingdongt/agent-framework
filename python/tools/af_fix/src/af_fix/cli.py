# Copyright (c) Microsoft. All rights reserved.

import argparse
import os
import sys
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from af_fix.models import AttemptOutcome, IssueRef, ScoreResult
from af_fix.workspace import slug


class PRDecision(StrEnum):
    YES = "yes"
    NO = "no"
    EDIT = "edit"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="af-fix", description="Triage and fix OSS issues via OpenHands.")
    p.add_argument("--top", type=int, default=5, help="Number of issues to fix across all repos (default 5).")
    p.add_argument("--triage-only", action="store_true", help="Score and print top-N; do not run OpenHands.")
    p.add_argument("--no-push", action="store_true", help="Run OpenHands fully; skip push & PR creation.")
    p.add_argument("--dry-run", action="store_true", help="Print what would happen; no LLM calls, no API calls.")
    p.add_argument("--retry-failed", action="store_true", help="Allow re-attempt of gave_up / error outcomes.")
    p.add_argument("--retry-id", type=str, default=None, help="Force retry of one specific issue, format owner/name:N.")
    p.add_argument("--repos", type=str, default=None, help="Comma-separated override list of owner/name repos.")
    return p


def parse_retry_id(s: str) -> IssueRef:
    if ":" not in s:
        raise ValueError(f"--retry-id must be owner/name:N, got {s!r}")
    repo, n = s.rsplit(":", 1)
    if "/" not in repo:
        raise ValueError(f"--retry-id repo must be owner/name, got {repo!r}")
    return IssueRef(repo=repo, number=int(n))


def refuse_in_ci() -> None:
    if os.environ.get("AF_FIX_DISABLED") == "1":
        sys.stderr.write("af-fix refuses to run: AF_FIX_DISABLED=1 is set.\n")
        sys.exit(2)


def _default_confirm(ids: list[str]) -> bool:
    print("\nPress Enter to proceed, Ctrl-C to abort: ", end="", flush=True)
    try:
        input()
        return True
    except (KeyboardInterrupt, EOFError):
        return False


def ask_pr_decision(
    *,
    prompt_fn: Callable[[str], str] = input,
    show: Callable[[], None] = lambda: None,
) -> PRDecision:
    show()
    try:
        answer = prompt_fn("Open PR? [y/N/edit] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return PRDecision.NO
    if answer in {"y", "yes"}:
        return PRDecision.YES
    if answer == "edit":
        return PRDecision.EDIT
    return PRDecision.NO


def _default_pr_decision(result: Any, branch: str) -> PRDecision:
    def show() -> None:
        print("\n" + "─" * 60)
        print(f"{result.ref.key} — fix candidate ready")
        print(f"Summary: {result.summary}")
        print(f"Branch:  {branch}")
        diff_lines = (result.diff or "").splitlines()
        print(f"Diff lines: {len(diff_lines)}")
        if diff_lines:
            print("\nDiff preview (first 60 lines):")
            for line in diff_lines[:60]:
                print(line)
        print("─" * 60)

    return ask_pr_decision(show=show)


def _print_triage(scores: list[ScoreResult], top_n: int) -> list[ScoreResult]:
    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    top = sorted_scores[:top_n]
    print(f"\nTop {len(top)} candidates:")
    for s in top:
        print(f"  {s.ref.key}  score={s.score:2d}  {s.reason}")
    return top


def run_pipeline(
    *,
    args: argparse.Namespace,
    target_repos: list[str],
    github: Any,
    state: Any,
    state_path: Path,
    triage_agent: Any,
    openhands_runner: Any,
    workspace_manager: Any,
    pr_submitter: Any,
    upstream_url_for: Callable[[str], str],
    confirm_callback: Callable[[list[str]], bool] = _default_confirm,
    pr_decision_callback: Callable[[Any, str], PRDecision] = _default_pr_decision,
) -> int:
    # 1. Collect issues across repos
    all_issues = []
    target_ref = parse_retry_id(args.retry_id) if args.retry_id else None
    for repo in target_repos:
        for issue in github.list_open_issues(repo):
            if target_ref is not None:
                if issue.ref.key != target_ref.key:
                    continue
            elif state.should_skip(issue.ref, retry_failed=args.retry_failed):
                continue
            all_issues.append(issue)

    # 2. Triage
    scores = triage_agent.score_all(all_issues)
    top_scores = _print_triage(scores, args.top)

    if args.triage_only:
        return 0

    if not confirm_callback([s.ref.key for s in top_scores]):
        print("Aborted.")
        return 1

    by_key = {i.ref.key: i for i in all_issues}

    # 3. For each top issue: clone → openhands → commit → submit
    for score in top_scores:
        ref = score.ref
        issue = by_key[ref.key]
        now = datetime.now(timezone.utc)
        try:
            workspace = workspace_manager.clone(ref, upstream_url=upstream_url_for(ref.repo))
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=None, now=now,
                give_up_reason=f"clone failed: {exc}",
            )
            print(f"{ref.key}: clone failed ({exc})")
            continue

        result = openhands_runner.run(issue=issue, workspace=workspace)

        if not result.success:
            outcome = AttemptOutcome.GAVE_UP if result.gave_up else AttemptOutcome.ERROR
            state.record_attempt(
                ref, outcome=outcome, branch=None, now=now,
                give_up_reason=result.reason,
            )
            print(f"{ref.key}: skipped ({result.reason})")
            continue

        branch = f"af-fix/issue-{ref.number}-{slug(result.summary or issue.title)}"

        try:
            workspace_manager.checkout_branch(workspace, branch)
            workspace_manager.commit_all(
                workspace,
                message=f"fix: {result.summary}\n\nFixes #{ref.number}",
            )
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=branch, now=now,
                give_up_reason=f"commit failed: {exc}",
            )
            print(f"{ref.key}: commit failed ({exc})")
            continue

        if args.no_push or args.dry_run:
            print(f"{ref.key}: would push {branch} (skipped)")
            continue

        # Per-PR HITL confirmation
        decision = pr_decision_callback(result, branch)
        if decision is PRDecision.NO:
            state.record_attempt(
                ref, outcome=AttemptOutcome.GAVE_UP, branch=branch, now=now,
                give_up_reason="user-rejected",
            )
            print(f"{ref.key}: PR skipped (user-rejected)")
            continue
        if decision is PRDecision.EDIT:
            print(f"{ref.key}: workspace + branch retained at {workspace} (no state record)")
            continue

        try:
            pr = pr_submitter.submit(result, branch=branch)
            state.record_attempt(
                ref, outcome=AttemptOutcome.PR_OPENED, branch=branch, now=now, pr_url=pr.url,
            )
            print(f"{ref.key}: PR opened — {pr.url}")
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=branch, now=now,
                give_up_reason=f"submit failed: {exc}",
            )
            print(f"{ref.key}: submit failed ({exc})")

    state.save()
    return 0


def main(argv: list[str] | None = None) -> int:
    refuse_in_ci()
    parser = build_parser()
    args = parser.parse_args(argv)

    # Lazy imports — keep CLI import lightweight
    from af_fix.config import Config
    from af_fix.github_client import GitHubClient
    from af_fix.openhands_runner import OpenHandsRunner
    from af_fix.pr_submitter import PRSubmitter
    from af_fix.state import State
    from af_fix.triage_agent import TriageAgent
    from af_fix.workspace import WorkspaceManager

    cfg = Config.load(Path.home() / ".af-fix" / "config.toml")
    state_path = Path.home() / ".af-fix" / "state.json"
    state = State.load(state_path)

    github = GitHubClient(token=cfg.github_token)
    target_repos = args.repos.split(",") if args.repos else cfg.target_repos

    chat_client = _build_chat_client(cfg)
    triage_agent = TriageAgent(client=chat_client)

    runner = OpenHandsRunner(
        anthropic_api_key=cfg.anthropic_api_key,
        model=cfg.fix_model,
        max_iterations=cfg.openhands_max_iterations,
        openhands_image=cfg.openhands_image,
    )

    workspace_manager = WorkspaceManager(root=Path.home() / ".af-fix" / "workspaces")
    pr_submitter = PRSubmitter(github=github, workspace_manager=workspace_manager, fork_owner=cfg.fork_owner)

    pr_submitter.verify_fork_owner()

    def upstream_url_for(repo: str) -> str:
        return f"https://github.com/{repo}.git"

    return run_pipeline(
        args=args,
        target_repos=target_repos,
        github=github,
        state=state,
        state_path=state_path,
        triage_agent=triage_agent,
        openhands_runner=runner,
        workspace_manager=workspace_manager,
        pr_submitter=pr_submitter,
        upstream_url_for=upstream_url_for,
    )


def _build_chat_client(cfg: Any) -> Any:
    """Build the Anthropic chat client for TriageAgent (agent-framework)."""
    from agent_framework.anthropic import AnthropicClient

    return AnthropicClient(api_key=cfg.anthropic_api_key, model=cfg.triage_model)


if __name__ == "__main__":
    sys.exit(main())
