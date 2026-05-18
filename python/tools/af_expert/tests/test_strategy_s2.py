from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.strategies.s2_structural_diff import (
    StructuralDiffStrategy,
    find_lagging_impls,
)


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_find_lagging_impls_detects_stale(tmp_state_dir: Path) -> None:
    store = ConceptGraphStore()
    c = Concept(
        id="mcp.oauth.refresh",
        description="...",
        spec_ref="RFC 8707",
        implementations={
            "fresh/repo": ConceptImplementation(
                repo="fresh/repo", files=["x.py"], functions=[],
                last_modified="2026-05-10",
            ),
            "stale/repo": ConceptImplementation(
                repo="stale/repo", files=["y.py"], functions=[],
                last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    lagging = find_lagging_impls(
        store=store, now=datetime(2026, 5, 18, tzinfo=timezone.utc), staleness_days=180
    )
    repos = [(concept_id, impl.repo) for concept_id, impl in lagging]
    assert ("mcp.oauth.refresh", "stale/repo") in repos
    assert all("fresh/repo" not in r for _, r in repos)


def test_strategy_emits_candidate_for_lagging_repo(tmp_state_dir: Path) -> None:
    store = ConceptGraphStore()
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh handling",
        spec_ref="RFC 8707",
        implementations={
            "fresh/repo": ConceptImplementation(
                repo="fresh/repo", files=["x.py"], functions=["f"], last_modified="2026-05-10",
            ),
            "stale/repo": ConceptImplementation(
                repo="stale/repo", files=["y.py"], functions=["g"], last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    candidates = CandidateStore()
    events = EventStore(); events.ensure_schema()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fresh/repo", "stale/repo"])

    strat = StructuralDiffStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, concept_store=store
    )
    produced = strat.on_weekly_tick(now=datetime(2026, 5, 18, tzinfo=timezone.utc))

    assert len(produced) >= 1
    assert any(p.target_repo == "stale/repo" for p in produced)


def test_strategy_skips_repos_not_in_config(tmp_state_dir: Path) -> None:
    store = ConceptGraphStore()
    c = Concept(
        id="x.y",
        description="...",
        spec_ref="",
        implementations={
            "untracked/repo": ConceptImplementation(
                repo="untracked/repo", files=["x"], functions=[], last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    candidates = CandidateStore()
    events = EventStore(); events.ensure_schema()
    llm = MagicMock(spec=LLM)
    cfg = _config(["other/repo"])

    strat = StructuralDiffStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, concept_store=store
    )
    produced = strat.on_weekly_tick(now=datetime(2026, 5, 18, tzinfo=timezone.utc))
    assert all(p.target_repo != "untracked/repo" for p in produced)
