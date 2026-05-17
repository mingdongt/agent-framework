from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.ranker import RankWeights, rank_candidates


def _candidate(**overrides: object) -> Candidate:
    base = dict(
        id="c-1",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="x/y",
        category="bug",
        title="t",
        description="d",
        suggested_action="a",
        confidence=0.5,
        novelty=0.5,
        actionability=0.5,
        strategy_reputation=0.5,
        status="new",
    )
    base.update(overrides)
    return Candidate(**base)


def test_higher_confidence_ranks_higher() -> None:
    a = _candidate(id="a", confidence=0.9)
    b = _candidate(id="b", confidence=0.3)
    ranked = rank_candidates([a, b])
    assert [c.id for c in ranked] == ["a", "b"]


def test_priority_high_boosts_score() -> None:
    a = _candidate(id="a", target_repo="microsoft/agent-framework")
    b = _candidate(id="b", target_repo="random/other", confidence=0.55)
    priority = {"microsoft/agent-framework": "high", "random/other": "normal"}
    ranked = rank_candidates([a, b], repo_priority=priority)
    assert ranked[0].id == "a"


def test_custom_weights_change_ordering() -> None:
    high_nov = _candidate(id="hn", confidence=0.4, novelty=0.95, actionability=0.3)
    high_act = _candidate(id="ha", confidence=0.4, novelty=0.3, actionability=0.95)

    novelty_weights = RankWeights(w_conf=0.1, w_nov=0.7, w_act=0.1, w_rep=0.1, w_pri=0.0)
    ranked = rank_candidates([high_nov, high_act], weights=novelty_weights)
    assert ranked[0].id == "hn"

    actionability_weights = RankWeights(w_conf=0.1, w_nov=0.1, w_act=0.7, w_rep=0.1, w_pri=0.0)
    ranked2 = rank_candidates([high_nov, high_act], weights=actionability_weights)
    assert ranked2[0].id == "ha"
