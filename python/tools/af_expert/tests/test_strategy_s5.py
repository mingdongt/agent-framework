from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.framework_adapters.base import FrameworkAdapter
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.spec_corpus.base import PropertyResult, SpecProperty
from af_expert.strategies.s5_spec_conformance import SpecConformanceStrategy


class _CompliantAdapter(FrameworkAdapter):
    framework = "fake/compliant"

    def simulate_mcp_initialize(self, payload): return {"accepted": True}
    def simulate_mcp_oauth_refresh_request(self, payload): return {"request": {}}
    def simulate_mcp_tool_result(self, payload):
        return {"payload": {"content": [], "isError": False}}


class _BuggyAdapter(FrameworkAdapter):
    framework = "fake/buggy"

    def simulate_mcp_initialize(self, payload): return {"accepted": True}
    def simulate_mcp_oauth_refresh_request(self, payload): return {"request": {"resource": "x"}}
    def simulate_mcp_tool_result(self, payload):
        return {"payload": {"content": "BAD", "isError": "BAD"}}


class _AlwaysPasses(SpecProperty):
    spec = "test"
    name = "always_passes"
    def run(self, adapter): return PropertyResult(passed=True, message="ok")


class _AlwaysFails(SpecProperty):
    spec = "test"
    name = "always_fails"
    def run(self, adapter):
        return PropertyResult(passed=False, message="boom", repro_snippet="assert 1 == 2")


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_strategy_passes_compliant_adapter_emits_no_candidate(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fake/compliant"])

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={"fake/compliant": _CompliantAdapter()},
        properties=[_AlwaysPasses()],
    )
    produced = strat.on_weekly_tick()
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_failing_property_emits_candidate(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fake/buggy"])

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={"fake/buggy": _BuggyAdapter()},
        properties=[_AlwaysFails()],
    )
    produced = strat.on_weekly_tick()
    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "fake/buggy"
    assert c.category == "bug"
    assert "assert 1 == 2" in c.evidence_snippets[0]
    # actionability high because we have a failing test as evidence
    assert c.actionability >= 0.8


def test_strategy_skips_repos_without_adapter(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["unknown/repo"])  # no adapter

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={},
        properties=[_AlwaysFails()],
    )
    produced = strat.on_weekly_tick()
    assert produced == []
