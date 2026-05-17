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


KNOWN_SUBCOMMANDS = {"triage", "execute", "run"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="af-fix", description="Triage and fix OSS issues via Claude Code.")
    sub = p.add_subparsers(dest="command", required=True)

    def _shared_top(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--top", type=int, default=5, help="Issues to consider across all repos.")
        parser.add_argument("--repos", type=str, default=None, help="Comma-separated owner/name override.")
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--retry-id", type=str, default=None)

    # `run` — all in one (legacy / explicit)
    p_run = sub.add_parser("run", help="Triage + fix + open PRs in one shot.")
    _shared_top(p_run)
    p_run.add_argument("--triage-only", action="store_true", help="Score and print top-N; do not run Claude Code.")
    p_run.add_argument("--no-push", action="store_true", help="Run Claude Code fully; skip push & PR creation.")
    p_run.add_argument("--dry-run", action="store_true", help="Print what would happen; no API calls.")
    p_run.add_argument("--auto-submit", action="store_true", help="Skip per-PR confirm.")

    # `triage` — only score + save artifact
    p_triage = sub.add_parser("triage", help="Score issues and save todolist artifact; do not fix.")
    _shared_top(p_triage)
    p_triage.add_argument("--save", type=str, default=None, help="Output dir for todolist (default ~/.af-fix/).")

    # `execute` — read todolist and fix checked items
    p_exec = sub.add_parser("execute", help="Execute fixes for items checked in a todolist.")
    p_exec.add_argument("--from", dest="from_path", type=str, required=True, help="Path to todolist .md.")
    p_exec.add_argument("--no-push", action="store_true")
    p_exec.add_argument("--dry-run", action="store_true")
    p_exec.add_argument("--auto-submit", action="store_true")

    return p


def parse_args_with_compat(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse argv, injecting 'run' when no subcommand is present (backward compat)."""
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        # No subcommand → treat as `run`
        argv = ["run", *list(argv)]
    elif argv[0] not in KNOWN_SUBCOMMANDS:
        argv = ["run", *list(argv)]
    return parser.parse_args(argv)


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
    runner: Any,
    workspace_manager: Any,
    pr_submitter: Any,
    upstream_url_for: Callable[[str], str],
    confirm_callback: Callable[[list[str]], bool] = _default_confirm,
    pr_decision_callback: Callable[[Any, str], PRDecision] = _default_pr_decision,
    # Backward-compat alias
    openhands_runner: Any = None,
) -> int:
    # Support legacy kwarg name
    if openhands_runner is not None and runner is None:
        runner = openhands_runner

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

    # 3. For each top issue: clone → claude agent → commit → submit
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

        result = runner.run(issue=issue, workspace=workspace)

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


def triage_pipeline(
    *,
    args: argparse.Namespace,
    target_repos: list[str],
    github: Any,
    state: Any,
    triage_agent: Any,
) -> int:
    """Run triage and save todolist artifact; do not fix."""
    from af_fix.todolist import save_todolist

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

    scores = triage_agent.score_all(all_issues)
    issues_by_key = {i.ref.key: i for i in all_issues}

    out_dir = Path(args.save) if args.save else Path.home() / ".af-fix"
    md_path, _json_path = save_todolist(
        scores=scores,
        issues_by_key=issues_by_key,
        generated_at=datetime.now(timezone.utc),
        out_dir=out_dir,
    )
    print("Triage complete. Top results:")
    for s in sorted(scores, key=lambda x: x.score, reverse=True)[: args.top]:
        print(f"  {s.ref.key}  score={s.score:2d}  {s.reason}")
    print(f"\nTodolist written to: {md_path}")
    print(f"Edit and run: af-fix execute --from {md_path}")
    return 0


def execute_pipeline(
    *,
    args: argparse.Namespace,
    github: Any,
    state: Any,
    state_path: Path,
    runner: Any,
    workspace_manager: Any,
    pr_submitter: Any,
    upstream_url_for: Callable[[str], str],
    pr_decision_callback: Callable[[Any, str], PRDecision] | None = None,
    # Backward-compat alias
    openhands_runner: Any = None,
) -> int:
    from af_fix.models import Issue
    from af_fix.todolist import load_todolist_json, parse_checked_items

    # Support legacy kwarg name
    if openhands_runner is not None and runner is None:
        runner = openhands_runner

    md_path = Path(args.from_path)
    if not md_path.exists():
        print(f"todolist not found: {md_path}")
        return 2

    md = md_path.read_text(encoding="utf-8")
    checked_refs = parse_checked_items(md)
    if not checked_refs:
        print("No checked items in todolist. Nothing to do.")
        return 0

    json_path = md_path.with_suffix(".json")
    todolist = load_todolist_json(json_path)
    metadata_by_key = {f"{i.repo}#{i.number}": i for i in todolist.items}

    pr_callback = pr_decision_callback or _default_pr_decision
    if args.auto_submit:
        pr_callback = lambda r, b: PRDecision.YES  # noqa: E731

    for ref in checked_refs:
        key = f"{ref.repo}#{ref.number}"
        item = metadata_by_key.get(key)
        if item is None:
            print(f"{key}: not in todolist JSON; skipping")
            continue
        issue = Issue(ref=ref, title=item.title, body=item.body)
        now = datetime.now(timezone.utc)

        try:
            workspace = workspace_manager.clone(ref, upstream_url=upstream_url_for(ref.repo))
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=None, now=now,
                give_up_reason=f"clone failed: {exc}",
            )
            print(f"{key}: clone failed ({exc})")
            continue

        result = runner.run(issue=issue, workspace=workspace)
        if not result.success:
            outcome = AttemptOutcome.GAVE_UP if result.gave_up else AttemptOutcome.ERROR
            state.record_attempt(
                ref, outcome=outcome, branch=None, now=now,
                give_up_reason=result.reason,
            )
            print(f"{key}: skipped ({result.reason})")
            continue

        branch = f"af-fix/issue-{ref.number}-{slug(result.summary or issue.title)}"
        try:
            workspace_manager.checkout_branch(workspace, branch)
            workspace_manager.commit_all(workspace, message=f"fix: {result.summary}\n\nFixes #{ref.number}")
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=branch, now=now,
                give_up_reason=f"commit failed: {exc}",
            )
            print(f"{key}: commit failed ({exc})")
            continue

        if args.no_push or args.dry_run:
            print(f"{key}: would push {branch} (skipped)")
            continue

        decision = pr_callback(result, branch)
        if decision is PRDecision.NO:
            state.record_attempt(
                ref, outcome=AttemptOutcome.GAVE_UP, branch=branch, now=now,
                give_up_reason="user-rejected",
            )
            print(f"{key}: PR skipped (user-rejected)")
            continue
        if decision is PRDecision.EDIT:
            print(f"{key}: workspace + branch retained at {workspace} (no state record)")
            continue

        try:
            pr = pr_submitter.submit(result, branch=branch)
            state.record_attempt(
                ref, outcome=AttemptOutcome.PR_OPENED, branch=branch, now=now, pr_url=pr.url,
            )
            print(f"{key}: PR opened — {pr.url}")
        except Exception as exc:
            state.record_attempt(
                ref, outcome=AttemptOutcome.ERROR, branch=branch, now=now,
                give_up_reason=f"submit failed: {exc}",
            )
            print(f"{key}: submit failed ({exc})")

    state.save()
    return 0


def main(argv: list[str] | None = None) -> int:
    refuse_in_ci()
    args = parse_args_with_compat(argv)

    # Lazy imports — keep CLI import lightweight
    from af_fix.claude_agent_runner import ClaudeAgentRunner
    from af_fix.config import Config
    from af_fix.github_client import GitHubClient
    from af_fix.pr_submitter import PRSubmitter
    from af_fix.state import State
    from af_fix.triage_agent import TriageAgent
    from af_fix.workspace import WorkspaceManager

    cfg = Config.load(Path.home() / ".af-fix" / "config.toml")
    state_path = Path.home() / ".af-fix" / "state.json"
    state = State.load(state_path)

    github = GitHubClient(token=cfg.github_token)

    def upstream_url_for(repo: str) -> str:
        return f"https://github.com/{repo}.git"

    if args.command == "triage":
        target_repos = args.repos.split(",") if args.repos else cfg.target_repos
        triage_agent = TriageAgent()
        return triage_pipeline(
            args=args,
            target_repos=target_repos,
            github=github,
            state=state,
            triage_agent=triage_agent,
        )

    if args.command == "execute":
        agent_runner = ClaudeAgentRunner(model=cfg.model, max_turns=cfg.max_turns)
        workspace_manager = WorkspaceManager(root=Path.home() / ".af-fix" / "workspaces")
        pr_submitter = PRSubmitter(github=github, workspace_manager=workspace_manager, fork_owner=cfg.fork_owner)
        pr_submitter.verify_fork_owner()
        return execute_pipeline(
            args=args,
            github=github,
            state=state,
            state_path=state_path,
            runner=agent_runner,
            workspace_manager=workspace_manager,
            pr_submitter=pr_submitter,
            upstream_url_for=upstream_url_for,
        )

    # Default: command == "run"
    target_repos = args.repos.split(",") if args.repos else cfg.target_repos
    triage_agent = TriageAgent()
    agent_runner = ClaudeAgentRunner(model=cfg.model, max_turns=cfg.max_turns)
    workspace_manager = WorkspaceManager(root=Path.home() / ".af-fix" / "workspaces")
    pr_submitter = PRSubmitter(github=github, workspace_manager=workspace_manager, fork_owner=cfg.fork_owner)
    pr_submitter.verify_fork_owner()

    pr_callback: Callable[[Any, str], PRDecision]
    pr_callback = (lambda r, b: PRDecision.YES) if args.auto_submit else _default_pr_decision
    return run_pipeline(
        args=args,
        target_repos=target_repos,
        github=github,
        state=state,
        state_path=state_path,
        triage_agent=triage_agent,
        runner=agent_runner,
        workspace_manager=workspace_manager,
        pr_submitter=pr_submitter,
        upstream_url_for=upstream_url_for,
        pr_decision_callback=pr_callback,
    )


if __name__ == "__main__":
    sys.exit(main())
