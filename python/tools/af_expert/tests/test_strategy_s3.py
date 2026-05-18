from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s3_hypothesis_verify import HypothesisVerifyStrategy


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def _h(hid: str = "h-001") -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement="MCP OAuth refresh-token grants violate RFC 8707",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )


def test_strategy_picks_one_unverified_pair(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    hs.upsert(_h("h-001"))

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"outcome": "non_compliant", "reasoning": "checks fail", "confidence": 0.8}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    cfg = _config(["microsoft/agent-framework", "langchain-ai/langchain"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    deltas = IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    )
    produced = strat.on_ingestion_complete(deltas)
    # Exactly one verification per tick
    assert llm.complete.call_count == 1
    # non_compliant verdict -> emits candidate
    assert len(produced) == 1
    assert produced[0].category == "bug"


def test_strategy_skips_when_all_verified(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    h = _h("h-001")
    h.verifications["x/y"] = Verification(
        repo="x/y", verified_at="2026-05-18", outcome="compliant", reasoning="ok"
    )
    hs.upsert(h)

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["x/y"])  # only one repo, already verified
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_skips_archived_hypotheses(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    h = _h("h-001"); h.status = "archived"
    hs.upsert(h)

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["x/y"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_compliant_verdict_no_candidate(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    hs.upsert(_h("h-001"))

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"outcome": "compliant", "reasoning": "implementation passes spec", "confidence": 0.9}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    cfg = _config(["x/y"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    # No candidate for compliant verdict but verification IS recorded
    assert produced == []
    assert hs.get("h-001").verifications.get("x/y") is not None
    assert hs.get("h-001").verifications["x/y"].outcome == "compliant"
