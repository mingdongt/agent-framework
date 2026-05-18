from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.hypothesis.model import Hypothesis, Verification


def test_verification_minimal() -> None:
    v = Verification(
        repo="microsoft/agent-framework",
        verified_at="2026-05-18",
        outcome="compliant",
        reasoning="checked _mcp.py",
    )
    assert v.outcome == "compliant"


def test_hypothesis_minimal() -> None:
    h = Hypothesis(
        id="h-001",
        statement="MCP OAuth refresh-token grants in most frameworks send the resource parameter, violating RFC 8707 §2.2",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    assert h.id == "h-001"
    assert h.status == "active"
    assert h.verifications == {}


def test_hypothesis_outcome_validation() -> None:
    with pytest.raises(ValueError):
        Verification(
            repo="x/y",
            verified_at="2026-05-18",
            outcome="invalid-outcome",
            reasoning="...",
        )


def test_hypothesis_roundtrip() -> None:
    h = Hypothesis(
        id="h-001",
        statement="...",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        verifications={
            "x/y": Verification(
                repo="x/y", verified_at="2026-05-18", outcome="non_compliant", reasoning="..."
            ),
        },
    )
    raw = h.model_dump_json()
    h2 = Hypothesis.model_validate_json(raw)
    assert h2 == h
