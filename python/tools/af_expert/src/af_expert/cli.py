from __future__ import annotations

import logging
import os

logging.basicConfig(
    level=os.environ.get("AF_EXPERT_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

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
from af_expert.architecture.refresh import refresh_one_repo
from af_expert.concept.linker import link_concept_to_repo
from af_expert.concept.seed import seed_into
from af_expert.concept.store import ConceptGraphStore
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s1_pr_forward_port import PRForwardPortStrategy
from af_expert.strategies.s2_structural_diff import StructuralDiffStrategy
from af_expert.strategies.s4_provider_release import ProviderReleaseStrategy
from af_expert.strategies.s6_maintainer_health import MaintainerHealthStrategy
from af_expert.strategies.s7_feature_propagation import FeaturePropagationStrategy
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
@click.option("--include-providers", is_flag=True, default=False, help="Run S4 provider release strategy")
@click.option("--include-health", is_flag=True, default=False, help="Run S6 maintainer health strategy")
@click.option("--include-structural", is_flag=True, default=False, help="Run S2 structural diff")
@click.option("--include-propagation", is_flag=True, default=False, help="Run S7 feature propagation")
@click.option(
    "--strategies-only",
    is_flag=True,
    default=False,
    help="Skip ingestion; run strategies against already-ingested events in DB.",
)
def tick(
    include_archaeology: bool, include_providers: bool, include_health: bool,
    include_structural: bool, include_propagation: bool, strategies_only: bool,
) -> None:
    """Run one ingestion + strategy tick."""
    cfg = load_config()
    sd = StateDir()
    sd.ensure_layout()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)

    with sd.lock():
        now = datetime.now(tz=timezone.utc)

        if strategies_only:
            # Skip ingestion entirely. Build IngestionDeltas from existing DB state:
            # - since = oldest cursor across all repos (widest possible query window)
            # - repos_with_new_prs = all configured repos (every strategy runs on every repo)
            state = load_state()
            cursors = state.get("cursors", {})
            all_repos = [r.owner_repo for r in cfg.repos]
            if cursors:
                since = min(
                    datetime.fromisoformat(ts) for ts in cursors.values()
                )
            else:
                # No cursors yet — fall back to 7-day window so strategies still run
                since = now - timedelta(days=7)
            deltas = IngestionDeltas(since=since, repos_with_new_prs=all_repos)
            click.echo("Ingestion: skipped (--strategies-only)")
            ingestion_summary: dict[str, int] = {"repos_succeeded": 0, "repos_failed": 0, "new_events": 0}
        else:
            gh = GitHubClient(token=cfg.github_token)
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
            ingestion_summary = {
                "repos_succeeded": result.repos_succeeded,
                "repos_failed": result.repos_failed,
                "new_events": result.new_events,
            }

        s1 = PRForwardPortStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        s1_produced = s1.on_ingestion_complete(deltas)
        click.echo(f"S1 (PR forward-port) produced {len(s1_produced)} candidates")

        all_produced = list(s1_produced)

        if include_providers:
            s4 = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s4_produced = s4.on_ingestion_complete(deltas)
            click.echo(f"S4 (provider release) produced {len(s4_produced)} candidates")
            all_produced.extend(s4_produced)

        if include_health:
            s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s6_produced = s6.on_weekly_tick(now=now)
            click.echo(f"S6 (maintainer health) produced {len(s6_produced)} candidates")
            all_produced.extend(s6_produced)

        # Construct concept_store once (used by S2)
        concept_store = ConceptGraphStore()

        if include_structural:
            s2 = StructuralDiffStrategy(
                config=cfg, events=events, candidates=candidates, llm=llm, concept_store=concept_store
            )
            s2_produced = s2.on_weekly_tick(now=now)
            click.echo(f"S2 (structural diff) produced {len(s2_produced)} candidates")
            all_produced.extend(s2_produced)

        if include_propagation:
            s7 = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s7_produced = s7.on_ingestion_complete(deltas)
            click.echo(f"S7 (feature propagation) produced {len(s7_produced)} candidates")
            all_produced.extend(s7_produced)

        if include_archaeology:
            s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s8_produced: list = []
            for repo_cfg in cfg.repos:
                s8_produced.extend(s8.on_demand({"repo": repo_cfg.owner_repo}))
            click.echo(f"S8 (issue archaeology) produced {len(s8_produced)} candidates")
            all_produced.extend(s8_produced)

        digest_md = render_digest(
            since=since,
            candidates=all_produced,
            ingestion_summary=ingestion_summary,
        )
        digest_path = sd.root / "digests" / f"{now.date().isoformat()}.md"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(digest_md)
        click.echo(f"Digest written to {digest_path}")

        trace_dir = sd.root / "traces"
        if trace_dir.exists():
            trace_file = trace_dir / f"{now.date().isoformat()}.jsonl"
            if trace_file.exists():
                size_kb = trace_file.stat().st_size // 1024
                click.echo(f"LLM trace: {trace_file} ({size_kb} KB)")


@cli.command()
@click.argument("repo", required=False)
@click.option("--all", "refresh_all", is_flag=True, default=False, help="Refresh all configured repos")
def refresh(repo: str | None, refresh_all: bool) -> None:
    """Refresh architecture briefing for one or all repos."""
    cfg = load_config()
    llm = LLM(api_key=cfg.anthropic_api_key)

    if refresh_all:
        targets = [r.owner_repo for r in cfg.repos]
    elif repo:
        targets = [repo]
    else:
        click.echo("Provide a repo name or --all", err=True)
        sys.exit(2)

    for target in targets:
        click.echo(f"Refreshing {target}...")
        result = refresh_one_repo(target, llm=llm)
        if result.success:
            click.echo(f"  OK briefing written to {result.briefing_path}")
        else:
            click.echo(f"  FAILED: {result.error}", err=True)


@cli.group()
def concept() -> None:
    """Concept graph management."""


@concept.command("seed")
def concept_seed() -> None:
    store = ConceptGraphStore()
    n = seed_into(store)
    click.echo(f"Seeded {n} concepts into {store.path}")


@concept.command("list")
def concept_list() -> None:
    store = ConceptGraphStore()
    concepts = store.list_all()
    if not concepts:
        click.echo("(concept graph empty — run `af-expert concept seed`)")
        return
    for c in concepts:
        click.echo(f"  {c.id}\t{c.description}")


@concept.command("show")
@click.argument("concept_id")
def concept_show(concept_id: str) -> None:
    store = ConceptGraphStore()
    c = store.get(concept_id)
    if c is None:
        click.echo(f"concept {concept_id!r} not found", err=True)
        sys.exit(2)
    click.echo(c.model_dump_json(indent=2))


@concept.command("link")
@click.argument("concept_id")
@click.option("--repo", required=True)
def concept_link(concept_id: str, repo: str) -> None:
    from af_expert.architecture.refresh import _clone_repo_shallow
    from af_expert.architecture.scanner import scan_repo_locally
    import tempfile
    from pathlib import Path
    import shutil

    cfg = load_config()
    store = ConceptGraphStore()
    c = store.get(concept_id)
    if c is None:
        click.echo(f"concept {concept_id!r} not found; run `af-expert concept seed` first", err=True)
        sys.exit(2)

    llm = LLM(api_key=cfg.anthropic_api_key)
    tmp_dir = Path(tempfile.mkdtemp(prefix="af-expert-concept-link-"))
    try:
        clone_dir = tmp_dir / repo.split("/")[-1]
        try:
            _clone_repo_shallow(repo, clone_dir)
        except Exception as e:
            click.echo(f"clone failed: {e}", err=True)
            sys.exit(2)
        inv = scan_repo_locally(clone_dir)
        impl = link_concept_to_repo(repo=repo, concept=c, inventory=inv, llm=llm)
        if impl is None:
            click.echo(f"{concept_id} -> {repo}: no link found")
            return
        store.attach_implementation(concept_id, impl)
        click.echo(f"linked {concept_id} -> {repo}: files={impl.files} functions={impl.functions}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
    click.echo("Strategies (Wave 1 + 2 + 3):")
    click.echo("  s1_pr_forward_port      (on-tick)")
    click.echo("  s2_structural_diff      (on-tick with --include-structural)")
    click.echo("  s4_provider_release     (on-tick with --include-providers)")
    click.echo("  s6_maintainer_health    (on-tick with --include-health)")
    click.echo("  s7_feature_propagation  (on-tick with --include-propagation)")
    click.echo("  s8_issue_archaeology    (on-demand or with --include-archaeology)")


@strategy.command("run")
@click.argument("name")
@click.option("--repo", default=None)
def strategy_run(name: str, repo: str | None) -> None:
    cfg = load_config()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    concept_store = ConceptGraphStore()

    if name == "s8_issue_archaeology":
        s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        targets = [repo] if repo else [r.owner_repo for r in cfg.repos]
        total = 0
        for r in targets:
            produced = s8.on_demand({"repo": r})
            total += len(produced)
            click.echo(f"{r}: {len(produced)} candidates")
        click.echo(f"Total: {total}")
    elif name == "s4_provider_release":
        s4 = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s4.on_ingestion_complete(IngestionDeltas(
            since=datetime.now(tz=timezone.utc), repos_with_new_prs=[r.owner_repo for r in cfg.repos],
        ))
        click.echo(f"S4: {len(produced)} candidates")
    elif name == "s6_maintainer_health":
        s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s6.on_weekly_tick()
        click.echo(f"S6: {len(produced)} candidates")
    elif name == "s2_structural_diff":
        s2 = StructuralDiffStrategy(
            config=cfg, events=events, candidates=candidates, llm=llm, concept_store=concept_store
        )
        produced = s2.on_weekly_tick()
        click.echo(f"S2: {len(produced)} candidates")
    elif name == "s7_feature_propagation":
        s7 = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s7.on_ingestion_complete(IngestionDeltas(
            since=datetime.now(tz=timezone.utc) - timedelta(days=7),
            repos_with_new_prs=[r.owner_repo for r in cfg.repos],
        ))
        click.echo(f"S7: {len(produced)} candidates")
    else:
        click.echo(f"Strategy '{name}' not recognized", err=True)
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
