from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s1_pr_forward_port import (
    BugPattern,
    PRForwardPortStrategy,
    extract_pattern_prompt,
    is_likely_bug_fix,
)


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_is_likely_bug_fix_title_match() -> None:
    assert is_likely_bug_fix(title="fix: skip orphan thinking", labels=[]) is True
    assert is_likely_bug_fix(title="fix(scope): handle X", labels=[]) is True
    assert is_likely_bug_fix(title="bug: ...", labels=[]) is True


def test_is_likely_bug_fix_label_match() -> None:
    assert is_likely_bug_fix(title="generic title", labels=["bug"]) is True
    assert is_likely_bug_fix(title="generic title", labels=["fix", "p1"]) is True


def test_is_likely_bug_fix_no_match() -> None:
    assert is_likely_bug_fix(title="feat: add x", labels=["enhancement"]) is False
    assert is_likely_bug_fix(title="docs: update README", labels=[]) is False


def test_extract_pattern_prompt_includes_diff_and_title() -> None:
    prompt = extract_pattern_prompt(
        title="fix: orphan thinking",
        body="Fixes #5783",
        diff="diff --git a/foo b/foo\n+x\n",
    )
    assert "fix: orphan thinking" in prompt
    assert "diff --git" in prompt
    assert "Fixes #5783" in prompt


def _make_pr(repo: str, number: int) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="pr",
        number=number,
        title="fix: orphan Anthropic thinking signatures",
        body="Fixes #5783. The serializer no longer emits null thinking blocks.",
        diff="diff --git a/x.py b/x.py\n+    if thinking is None:\n+        continue\n",
        author="he-yufeng",
        state="merged",
        labels=["bug"],
        created_at=datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        merged_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        url=f"https://github.com/{repo}/pull/{number}",
    )


def test_strategy_skips_non_bug_fix_prs(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    feat_pr = _make_pr("microsoft/agent-framework", 5778)
    feat_pr.title = "feat: add Magentic"
    feat_pr.labels = ["enhancement"]
    events.insert(feat_pr)

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    cfg = _config_for(["microsoft/agent-framework", "pydantic/pydantic-ai"])
    strat = PRForwardPortStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_emits_candidates_when_pattern_matches(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    events.insert(_make_pr("microsoft/agent-framework", 5784))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    # First LLM call: extract pattern
    pattern_response = LLMResponse(
        text='```json\n{"pattern_name": "Anthropic orphan thinking", "failure_mode": "...", "code_shape_hints": ["serialize"], "fix_shape_hints": ["filter null"]}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    # Per-repo matching calls
    match_response = LLMResponse(
        text='```json\n{"matches": true, "confidence": 0.75, "target_files": ["src/foo.py"], "reasoning": "looks similar"}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    no_match_response = LLMResponse(
        text='```json\n{"matches": false, "confidence": 0.1, "target_files": [], "reasoning": "no analog"}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm.complete.side_effect = [pattern_response, match_response, no_match_response]

    cfg = _config_for(["microsoft/agent-framework", "pydantic/pydantic-ai", "google/adk-python"])
    strat = PRForwardPortStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        confidence_threshold=0.5,
    )

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)

    assert len(produced) == 1
    c = produced[0]
    assert c.strategy == "s1_pr_forward_port"
    assert c.target_repo == "pydantic/pydantic-ai"
    assert c.confidence == 0.75
    assert "microsoft/agent-framework" in c.evidence_urls[0]
    # Self-reference excluded (source repo not scanned)
    assert all("microsoft/agent-framework" != x for x in [c.target_repo])
