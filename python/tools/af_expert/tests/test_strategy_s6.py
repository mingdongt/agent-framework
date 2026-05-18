from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM
from af_expert.strategies.s6_maintainer_health import (
    MaintainerHealthStrategy,
    RepoMetrics,
    compute_metrics,
)


def _make_pr(repo: str, number: int, created: datetime, merged: datetime | None) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="pr",
        number=number,
        title=f"PR {number}",
        body="",
        author="someone",
        state="merged" if merged else "open",
        labels=[],
        created_at=created,
        updated_at=merged or created,
        merged_at=merged,
        url=f"https://github.com/{repo}/pull/{number}",
    )


def _make_issue(repo: str, number: int, created: datetime, closed: datetime | None) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="issue",
        number=number,
        title=f"Issue {number}",
        body="",
        author="someone",
        state="closed" if closed else "open",
        labels=[],
        created_at=created,
        updated_at=closed or created,
        closed_at=closed,
        url=f"https://github.com/{repo}/issues/{number}",
    )


def test_compute_metrics_basic(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    for i in range(3):
        events.insert(_make_pr("x/y", i, now - timedelta(days=2), now - timedelta(days=1)))

    metrics = compute_metrics("x/y", events=events, now=now, window_days=30)

    assert isinstance(metrics, RepoMetrics)
    assert metrics.pr_count == 3
    assert metrics.pr_merge_median_hours is not None
    assert 20 < metrics.pr_merge_median_hours < 28


def test_strategy_emits_candidate_for_degraded_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    for i in range(10):
        created = now - timedelta(days=45)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 1000 + i, created, merged))

    for i in range(10):
        created = now - timedelta(days=15)
        merged = created + timedelta(hours=24)
        events.insert(_make_pr("x/y", 2000 + i, created, merged))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "x/y"
    assert c.category == "maintenance"
    assert "latency" in c.description.lower() or "median" in c.description.lower()
    llm.complete.assert_not_called()


def test_strategy_no_candidate_for_healthy_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    for i in range(10):
        created = now - timedelta(days=45)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 1000 + i, created, merged))
    for i in range(10):
        created = now - timedelta(days=15)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 2000 + i, created, merged))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert produced == []


def test_strategy_skips_low_volume_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    for i in range(2):
        events.insert(_make_pr("x/y", i, now - timedelta(days=15), now - timedelta(days=14)))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert produced == []
