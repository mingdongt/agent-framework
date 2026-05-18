from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.s4_provider_release import (
    ProviderReleaseStrategy,
    extract_release_summary_prompt,
)


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_extract_summary_prompt_includes_html() -> None:
    prompt = extract_release_summary_prompt(
        provider="anthropic", html_body="<html>claude-opus-4-7 released</html>"
    )
    assert "anthropic" in prompt.lower()
    assert "claude-opus-4-7" in prompt


def test_strategy_emits_candidate_for_unsupported_release(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()

    summary_resp = LLMResponse(
        text='```json\n{"is_new_release": true, "title": "claude-opus-4-7 GA", "changes": [{"name": "thinking_blocks", "description": "new field for streaming thinking"}]}\n```',
        input_tokens=200, output_tokens=50, cache_read_tokens=0, cache_creation_tokens=0,
    )
    framework_check_resp = LLMResponse(
        text='```json\n{"supports": false, "confidence": 0.8, "reasoning": "no thinking_blocks references in repo"}\n```',
        input_tokens=200, output_tokens=30, cache_read_tokens=0, cache_creation_tokens=0,
    )

    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = [summary_resp, framework_check_resp]

    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    from af_expert.providers.sources import ProviderSource

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = "<html>claude-opus-4-7 released with thinking_blocks</html>"
        with patch(
            "af_expert.strategies.s4_provider_release.PROVIDER_SOURCES",
            new=[ProviderSource(name="anthropic", url="https://docs.anthropic.com/x", kind="html")],
        ):
            produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "microsoft/agent-framework"
    assert c.actionability == 1.0
    assert "thinking_blocks" in c.title or "thinking_blocks" in c.description


def test_strategy_skips_when_no_new_release(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()

    no_release_resp = LLMResponse(
        text='```json\n{"is_new_release": false, "title": "", "changes": []}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = no_release_resp

    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = "<html>some static page</html>"
        produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert produced == []


def test_strategy_skips_empty_poll_body(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = ""
        produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert produced == []
    llm.complete.assert_not_called()
