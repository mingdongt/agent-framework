from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.s8_issue_archaeology import IssueArchaeologyStrategy


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def _make_issue(repo: str, number: int, labels: list[str], closed_at: datetime) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="issue",
        number=number,
        title="thread-safe state mutation across coroutines",
        body="When using ContextVar-style mutation, ...",
        author="someuser",
        state="closed",
        labels=labels,
        created_at=closed_at,
        updated_at=closed_at,
        closed_at=closed_at,
        url=f"https://github.com/{repo}/issues/{number}",
    )


def test_strategy_finds_tractable_archaeology(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    events.insert(_make_issue("microsoft/agent-framework", 100, ["wontfix"], datetime(2024, 6, 1, tzinfo=timezone.utc)))
    events.insert(_make_issue("microsoft/agent-framework", 101, ["stale"], datetime(2025, 1, 1, tzinfo=timezone.utc)))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    tractable_resp = LLMResponse(
        text='```json\n{"tractable": true, "confidence": 0.7, "reasoning": "asyncio context vars exist now"}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    untractable_resp = LLMResponse(
        text='```json\n{"tractable": false, "confidence": 0.2, "reasoning": "unchanged"}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm.complete.side_effect = [tractable_resp, untractable_resp]

    cfg = _config_for(["microsoft/agent-framework"])
    strat = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_demand({"repo": "microsoft/agent-framework"})

    assert len(produced) == 1
    assert produced[0].category == "bug"
    assert "issues/100" in produced[0].evidence_urls[0]


def test_strategy_skips_when_no_archived_issues(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config_for(["microsoft/agent-framework"])
    strat = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_demand({"repo": "microsoft/agent-framework"})
    assert produced == []
    llm.complete.assert_not_called()
