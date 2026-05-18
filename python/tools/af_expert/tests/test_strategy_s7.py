from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s7_feature_propagation import (
    FeaturePropagationStrategy,
    is_likely_feature_pr,
)


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_is_likely_feature_pr_title_match() -> None:
    assert is_likely_feature_pr(title="feat: add Magentic", labels=[]) is True
    assert is_likely_feature_pr(title="feat(scope): add X", labels=[]) is True


def test_is_likely_feature_pr_label_match() -> None:
    assert is_likely_feature_pr(title="something", labels=["enhancement"]) is True


def test_is_likely_feature_pr_excludes_fix() -> None:
    assert is_likely_feature_pr(title="fix: bug", labels=["bug"]) is False


def _make_feat_pr(repo: str, number: int, title: str) -> EventRecord:
    return EventRecord(
        repo=repo, kind="pr", number=number,
        title=title, body="A substantial new feature.",
        diff="+++ b/x.py\n+ class NewThing: pass\n",
        author="someone", state="merged", labels=["enhancement"],
        created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        merged_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        url=f"https://github.com/{repo}/pull/{number}",
    )


def test_strategy_emits_candidate_for_unsupported_feature(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    events.insert(_make_feat_pr("microsoft/agent-framework", 5778, "feat: add Magentic multi-agent"))

    candidates = CandidateStore()

    extract_resp = LLMResponse(
        text='```json\n{"feature_name": "magentic_multi_agent", "summary": "Multi-agent orchestration"}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    sister_check_resp = LLMResponse(
        text='```json\n{"has_equivalent": false, "confidence": 0.7, "reasoning": "no multi-agent abstraction found"}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = [extract_resp, sister_check_resp]

    cfg = _config(["microsoft/agent-framework", "langchain-ai/langchain"])
    strat = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 13, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)

    assert len(produced) == 1
    assert produced[0].target_repo == "langchain-ai/langchain"
    assert produced[0].category == "feature"
