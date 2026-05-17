from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from af_expert.candidate.export import render_candidate_spec
from af_expert.candidate.ranker import RankWeights, rank_candidates
from af_expert.candidate.store import CandidateStore
from af_expert.config import _state_dir, load_config
from af_expert.github_client import GitHubClient
from af_expert.ingestion.pipeline import run_ingestion_tick
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.query.ask import answer
from af_expert.query.digest import render_digest
from af_expert.state import StateDir, load_state, save_state
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s1_pr_forward_port import PRForwardPortStrategy
from af_expert.strategies.s8_issue_archaeology import IssueArchaeologyStrategy


DEFAULT_CONFIG_BODY = """\
# af-expert config

github_token = ""          # GitHub PAT, public_repo scope
anthropic_api_key = ""     # Anthropic API key

[ingestion]
poll_interval_hours = 24
event_retention_days = 365

[architecture]
refresh_trigger = "drift"   # drift | weekly | manual
refresh_min_days = 7

# Add at least one repo entry. Use priority high/normal/low.

[[repos]]
owner_repo = "microsoft/agent-framework"
priority = "high"
languages = ["python", "csharp"]

# [[repos]]
# owner_repo = "langchain-ai/langchain"
# priority = "normal"
# languages = ["python"]
"""


@click.group()
def cli() -> None:
    """af-expert: continuously-learning domain expert for OSS agent frameworks."""


@cli.command()
def init() -> None:
    """Initialize ~/.af-expert/ with a config template."""
    sd = StateDir()
    sd.ensure_layout()
    cfg_path = sd.root / "config.toml"
    if cfg_path.exists():
        click.echo(f"Config already exists at {cfg_path}; will not overwrite.", err=True)
        sys.exit(2)
    cfg_path.write_text(DEFAULT_CONFIG_BODY)
    click.echo(f"Wrote template config to {cfg_path}")
    click.echo("Edit it, then run `af-expert tick`.")


@cli.command()
@click.option("--include-archaeology", is_flag=True, default=False)
def tick(include_archaeology: bool) -> None:
    """Run one ingestion + strategy tick."""
    cfg = load_config()
    sd = StateDir()
    sd.ensure_layout()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    gh = GitHubClient(token=cfg.github_token)
    llm = LLM(api_key=cfg.anthropic_api_key)

    with sd.lock():
        now = datetime.now(tz=timezone.utc)
        # Strategies look at events from the last 7 days regardless of where
        # individual repo cursors are. This is a Wave 1 simplification; Wave 2
        # uses per-repo deltas from architecture-change-detection.
        since = now - timedelta(days=7)

        result = run_ingestion_tick(
            cfg, gh, events, now=now, load_state=load_state, save_state=save_state
        )
        click.echo(
            f"Ingestion: {result.repos_succeeded} ok, "
            f"{result.repos_failed} failed, {result.new_events} new events"
        )

        repos_with_new_prs = [r.owner_repo for r in cfg.repos if r.owner_repo not in result.failed_repos]

        deltas = IngestionDeltas(since=since, repos_with_new_prs=repos_with_new_prs)

        s1 = PRForwardPortStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        s1_produced = s1.on_ingestion_complete(deltas)
        click.echo(f"S1 (PR forward-port) produced {len(s1_produced)} candidates")

        s8_produced: list = []
        if include_archaeology:
            s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            for repo_cfg in cfg.repos:
                s8_produced.extend(s8.on_demand({"repo": repo_cfg.owner_repo}))
            click.echo(f"S8 (issue archaeology) produced {len(s8_produced)} candidates")

        digest_md = render_digest(
            since=since,
            candidates=s1_produced + s8_produced,
            ingestion_summary={
                "repos_succeeded": result.repos_succeeded,
                "repos_failed": result.repos_failed,
                "new_events": result.new_events,
            },
        )
        digest_path = sd.root / "digests" / f"{now.date().isoformat()}.md"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(digest_md)
        click.echo(f"Digest written to {digest_path}")


@cli.command()
@click.option("--since", default="1d", help="duration like '1d', '7d', '24h'")
def digest(since: str) -> None:
    """Print or build a digest for the given window."""
    sd = StateDir()
    candidates = CandidateStore()
    now = datetime.now(tz=timezone.utc)
    delta = _parse_duration(since)
    since_dt = now - delta
    cs = list(candidates.list_since(since_dt))
    md = render_digest(since=since_dt, candidates=cs)
    click.echo(md)


@cli.command()
@click.option("--strategy", default=None)
@click.option("--top", default=10, type=int)
def suggest(strategy: str | None, top: int) -> None:
    """Show top-N candidates by ranker score."""
    cfg = load_config()
    candidates = CandidateStore()
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)
    pool = list(candidates.list_since(since))
    if strategy:
        pool = [c for c in pool if c.strategy == strategy]
    repo_priority = {r.owner_repo: r.priority for r in cfg.repos}
    ranked = rank_candidates(pool, repo_priority=repo_priority)
    for c in ranked[:top]:
        click.echo(f"{c.id}\t{c.confidence:.2f}\t{c.target_repo}\t{c.title}")


@cli.command()
@click.argument("question")
def ask(question: str) -> None:
    """Ask a natural-language question."""
    cfg = load_config()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    click.echo(answer(question=question, events=events, candidates=candidates, llm=llm))


@cli.group()
def candidate() -> None:
    """Candidate management."""


@candidate.command("show")
@click.argument("candidate_id")
def candidate_show(candidate_id: str) -> None:
    store = CandidateStore()
    c = store.get(candidate_id)
    if c is None:
        click.echo(f"Candidate {candidate_id} not found", err=True)
        sys.exit(2)
    click.echo(c.model_dump_json(indent=2))


@candidate.command("accept")
@click.argument("candidate_id")
@click.option("--notes", default="")
def candidate_accept(candidate_id: str, notes: str) -> None:
    store = CandidateStore()
    store.update_status(candidate_id, status="accepted", notes=notes)
    click.echo(f"Marked {candidate_id} as accepted")


@candidate.command("reject")
@click.argument("candidate_id")
@click.option("--notes", default="")
def candidate_reject(candidate_id: str, notes: str) -> None:
    store = CandidateStore()
    store.update_status(candidate_id, status="rejected", notes=notes)
    click.echo(f"Marked {candidate_id} as rejected")


@candidate.command("export")
@click.argument("candidate_id")
def candidate_export(candidate_id: str) -> None:
    store = CandidateStore()
    c = store.get(candidate_id)
    if c is None:
        click.echo(f"Candidate {candidate_id} not found", err=True)
        sys.exit(2)
    click.echo(render_candidate_spec(c))


@cli.group()
def strategy() -> None:
    """Strategy management."""


@strategy.command("list")
def strategy_list() -> None:
    click.echo("Enabled strategies (Wave 1):")
    click.echo("  s1_pr_forward_port")
    click.echo("  s8_issue_archaeology  (on-demand only)")


@strategy.command("run")
@click.argument("name")
@click.option("--repo", default=None)
def strategy_run(name: str, repo: str | None) -> None:
    cfg = load_config()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    if name == "s8_issue_archaeology":
        s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        targets = [repo] if repo else [r.owner_repo for r in cfg.repos]
        total = 0
        for r in targets:
            produced = s8.on_demand({"repo": r})
            total += len(produced)
            click.echo(f"{r}: {len(produced)} candidates")
        click.echo(f"Total: {total}")
    else:
        click.echo(f"Strategy '{name}' is not on-demand-runnable in Wave 1", err=True)
        sys.exit(2)


@cli.command()
def stats() -> None:
    """Show summary stats."""
    state = load_state()
    cursors = state.get("cursors", {})
    click.echo(f"Tracked repos with cursors: {len(cursors)}")
    for repo, ts in sorted(cursors.items()):
        click.echo(f"  {repo}\t{ts}")


def _parse_duration(s: str) -> timedelta:
    s = s.strip().lower()
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=int(s[:-1]))
    raise click.UsageError(f"Cannot parse duration: {s!r}")
