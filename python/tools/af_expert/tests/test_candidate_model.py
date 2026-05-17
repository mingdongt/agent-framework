from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.candidate.model import Candidate


def test_candidate_minimal() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible orphan thinking signature path",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only thinking blocks before serialize",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    assert c.id == "c-001"
    assert c.category == "bug"


def test_candidate_confidence_bounded() -> None:
    with pytest.raises(ValueError):
        Candidate(
            id="c-002",
            discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
            strategy="s1_pr_forward_port",
            target_repo="x/y",
            category="bug",
            title="t",
            description="d",
            suggested_action="a",
            confidence=1.5,  # out of range
            novelty=0.3,
            actionability=0.5,
            strategy_reputation=0.5,
            status="new",
        )


def test_candidate_serialize_roundtrip() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="x/y",
        category="bug",
        title="t",
        description="d",
        suggested_action="a",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    raw = c.model_dump_json()
    c2 = Candidate.model_validate_json(raw)
    assert c2 == c
