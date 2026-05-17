# Copyright (c) Microsoft. All rights reserved.

import argparse
import asyncio
import logging
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rich.logging import RichHandler

from af_watch.config import Config
from af_watch.consolidator import Consolidator
from af_watch.corpus_loader import CorpusLoader
from af_watch.exceptions import AFWatchError
from af_watch.feeds.activity_scanner import ActivityScanner
from af_watch.llm_client import LLMClient
from af_watch.models import BriefingData
from af_watch.reasoning.persona_runner import PersonaRunner
from af_watch.reasoning.question_runner import QuestionRunner
from af_watch.reasoning.runner import ReasoningRunner
from af_watch.region_selector import RegionSelector
from af_watch.reporter import Reporter
from af_watch.reproducer import Reproducer
from af_watch.state import State

_LOG = logging.getLogger("af_watch")


def af_watch_home() -> Path:
    override = os.environ.get("AF_WATCH_HOME")
    if override:
        return Path(override)
    return Path.home() / ".af-watch"


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="af-watch")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="scaffold ~/.af-watch/")

    run = sub.add_parser("run", help="full pipeline: scan + reason + report")
    run.add_argument("--window", default="7d", help="lookback duration (e.g. 7d, 14d)")
    run.add_argument("--skip-repro", action="store_true")
    run.add_argument("--repos", help="comma-separated owner/name overrides")

    sub.add_parser("report", help="re-render briefing from existing artifacts")
    sub.add_parser("open", help="open latest briefing in editor")

    corpus = sub.add_parser("corpus", help="corpus maintenance")
    corpus_sub = corpus.add_subparsers(dest="corpus_action", required=True)
    refresh = corpus_sub.add_parser("refresh", help="list stale corpus files")
    refresh.add_argument("--stale-days", type=int, default=28)
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("AF_WATCH_DISABLED") == "1":
        print("af-watch: disabled (AF_WATCH_DISABLED=1)", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(show_time=False)],
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init([])
    if args.cmd == "run":
        return asyncio.run(cmd_run(args))
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "open":
        return cmd_open(args)
    if args.cmd == "corpus":
        return cmd_corpus(args)
    return 2


def cmd_corpus(args: argparse.Namespace) -> int:
    if args.corpus_action != "refresh":
        _LOG.error("unknown corpus action: %s", args.corpus_action)
        return 2

    state = State.load(af_watch_home() / "state.json")
    cutoff = date.today() - timedelta(days=args.stale_days)
    corpus_dir = package_root() / "corpus"
    stale: list[str] = []
    for md in sorted(corpus_dir.glob("**/*.md")):
        if md.name == "README.md":
            continue
        rel = md.relative_to(corpus_dir).as_posix()
        last = state.corpus_last_refreshed.get(rel)
        if last is None:
            stale.append(f"{rel}  (never refreshed)")
            continue
        try:
            last_date = date.fromisoformat(last)
        except ValueError:
            stale.append(f"{rel}  (invalid date {last!r})")
            continue
        if last_date < cutoff:
            stale.append(f"{rel}  (last {last}, > {args.stale_days}d ago)")
    if not stale:
        _LOG.info("all corpus files refreshed within %d days", args.stale_days)
        return 0
    _LOG.info("stale corpus files (please refresh):")
    for line in stale:
        _LOG.info("  %s", line)
    _LOG.info("after editing, update state.corpus_last_refreshed (Phase 1 manual; Phase 2 automates).")
    return 0


def cmd_init(_argv: list[str]) -> int:
    home = af_watch_home()
    home.mkdir(parents=True, exist_ok=True)
    cfg = home / "config.toml"
    if cfg.exists():
        _LOG.info("config already exists at %s — not overwritten", cfg)
        return 0
    cfg.write_text(_SAMPLE_CONFIG, encoding="utf-8")
    _LOG.info("scaffolded %s", cfg)
    return 0


def cmd_report(_args: argparse.Namespace) -> int:
    _LOG.info("af-watch report: re-rendering not yet implemented (Phase 2)")
    return 0


def cmd_open(_args: argparse.Namespace) -> int:
    state = State.load(af_watch_home() / "state.json")
    if state.last_run is None:
        _LOG.error("no prior run; nothing to open")
        return 1
    path = state.last_run["report_path"]
    _LOG.info("briefing: %s", path)
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    home = af_watch_home()
    try:
        cfg = Config.load(home / "config.toml")
    except AFWatchError as exc:
        _LOG.error("config error: %s", exc)
        return 1

    state = State.load(home / "state.json")

    until = datetime.now(tz=timezone.utc)
    since = until - _parse_window(args.window)
    repos = args.repos.split(",") if args.repos else cfg.target_repos

    started = datetime.now(tz=timezone.utc)
    _LOG.info("scanning %d repos from %s", len(repos), since.isoformat())

    scanner = ActivityScanner(token=cfg.github_token)
    events = scanner.scan_all(repos, since=since, until=until)
    _LOG.info("activity events: %d", len(events))

    feeds_dir = home / "feeds" / "activity"
    feeds_dir.mkdir(parents=True, exist_ok=True)
    feeds_file = feeds_dir / f"{until.strftime('%Y-%m-%d')}.jsonl"
    feeds_file.write_text("\n".join(e.model_dump_json() for e in events), encoding="utf-8")

    corpus = CorpusLoader(corpus_dir=package_root() / "corpus").load()
    region_selector = RegionSelector(max_regions=cfg.max_regions_per_run)
    regions = region_selector.select(events)
    _LOG.info("regions selected: %d", len(regions))

    if not _have_claude_cli(cfg.claude_cli_path):
        _LOG.error(
            "claude CLI not found on PATH (looked for %r). Install it or set claude_cli_path.",
            cfg.claude_cli_path,
        )
        return 1
    llm = LLMClient(claude_path=cfg.claude_cli_path, model=cfg.reasoning_model)
    qr = QuestionRunner(llm=llm)
    pr = PersonaRunner(llm=llm)

    def _read_code(repo: str, file: str) -> str:
        ws = Path(cfg.repro_workspace_base).expanduser() / repo.replace("/", "__") / file
        try:
            return ws.read_text(encoding="utf-8")[:50_000]
        except OSError:
            return ""

    runner = ReasoningRunner(
        question_runner=qr,
        persona_runner=pr,
        questions_dir=package_root() / "src" / "af_watch" / "reasoning" / "questions",
        personas_dir=package_root() / "src" / "af_watch" / "reasoning" / "personas",
        code_reader=_read_code,
    )
    strategic, tactical_hyps = await runner.run(snapshot=corpus, home_repo=cfg.home_repo, regions=regions)
    _LOG.info("strategic opportunities: %d / tactical hypotheses: %d", len(strategic), len(tactical_hyps))

    consolidator = Consolidator()
    opps = consolidator.consolidate(strategic=strategic, tactical_hypotheses=tactical_hyps)

    if not args.skip_repro:
        # Phase 1: no auto-generated repro scripts yet; Reproducer call deferred.
        # Just re-tier in case some opportunities are pre-marked confirmed (e.g., manual repro).
        _ = Reproducer(
            workspace_base=Path(cfg.repro_workspace_base).expanduser(),
            home_repo=cfg.home_repo,
        )
        opps = consolidator.retier_after_repro(opps)

    industry_highlights: list = []  # Phase 1: industry crawler integration deferred
    activity_summary: dict[str, int] = {}
    for e in events:
        if e.type == "pr_merged":
            activity_summary[e.repo] = activity_summary.get(e.repo, 0) + 1

    data = BriefingData(
        window_start=since,
        window_end=until,
        opportunities=opps,
        industry_highlights=industry_highlights,
        activity_summary=activity_summary,
    )
    reporter = Reporter(reports_root=home / "reports")
    briefing_path = reporter.write(data)
    _LOG.info("briefing: %s", briefing_path)

    state.record_run(
        started_at=started,
        completed_at=datetime.now(tz=timezone.utc),
        window=f"{since.strftime('%Y-%m-%d')}_{until.strftime('%Y-%m-%d')}",
        opp_count=len(opps),
        report_path=briefing_path,
    )
    state.save()
    return 0


def _parse_window(window: str) -> timedelta:
    window = window.strip().lower()
    if window.endswith("d"):
        return timedelta(days=int(window[:-1]))
    if window.endswith("h"):
        return timedelta(hours=int(window[:-1]))
    raise ValueError(f"unrecognized window: {window!r}")


def _have_claude_cli(path: str) -> bool:
    return shutil.which(path) is not None


_SAMPLE_CONFIG = '''# af-watch config — fill in before first run.
# LLM auth: uses the local `claude` CLI binary; no API key needed.
# Make sure `claude --version` works before running `af-watch run`.

# github_token = "ghp_xxx"
# operator_name = "Your Name"
# home_repo = "microsoft/agent-framework"
# target_repos = [
#     "microsoft/agent-framework",
#     "google/adk-python",
#     "langchain-ai/langchain",
#     "langchain-ai/langgraph",
#     "pydantic/pydantic-ai",
#     "openai/openai-agents-python",
#     "OpenHands/software-agent-sdk",
#     "stanfordnlp/dspy",
#     "strands-agents/sdk-python",
#     "Arize-ai/phoenix",
# ]
# industry_sources = [
#     "https://www.anthropic.com/news",
#     "https://openai.com/blog",
#     "https://ai.google.dev/changelog",
# ]
# reasoning_model = "claude-opus-4-7"
# claude_cli_path = "claude"   # override if `claude` is not on PATH
# repro_workspace_base = "~/.af-fix/workspaces"
'''
