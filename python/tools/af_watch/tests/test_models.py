# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone

import pytest

from af_watch.models import (
    ActivityEvent,
    CodeRegion,
    Hypothesis,
    IndustryEntry,
    Opportunity,
    OpportunityType,
)


def _now() -> datetime:
    return datetime(2026, 5, 17, tzinfo=timezone.utc)


def test_activity_event_round_trip() -> None:
    event = ActivityEvent(
        repo="microsoft/agent-framework",
        type="pr_merged",
        number=5867,
        title="fix: strip auth header",
        timestamp=_now(),
        author="someone",
        files_changed=["python/x.py"],
        body="...",
        url="https://github.com/microsoft/agent-framework/pull/5867",
    )
    j = event.model_dump_json()
    restored = ActivityEvent.model_validate_json(j)
    assert restored == event


def test_industry_entry_minimum() -> None:
    entry = IndustryEntry(
        timestamp=_now(),
        source="anthropic_blog",
        title="MCP 2025-06 spec",
        summary="OAuth resource tightening",
        url="https://anthropic.com/news/mcp",
    )
    assert entry.title == "MCP 2025-06 spec"


def test_code_region_required_fields() -> None:
    region = CodeRegion(
        repo="microsoft/agent-framework",
        file="python/x.py",
        line_start=10,
        line_end=50,
        selection_reason="changed in PR #5867",
        recent_change_context="MCP redirect handling",
    )
    assert region.line_end > region.line_start


def test_hypothesis_confidence_clamped() -> None:
    h = Hypothesis(
        region_id="r-1",
        repo="microsoft/agent-framework",
        file="python/mcp_http.py",
        persona="security_boundary",
        invariant="auth headers stripped on cross-origin redirect",
        violation_condition="MCP server returns 307 to different origin",
        repro_sketch="mock MCP, sniff headers",
        severity="high",
        confidence=1.5,
    )
    assert h.confidence == 1.0  # clamped
    assert h.repo == "microsoft/agent-framework"
    assert h.file == "python/mcp_http.py"


def test_opportunity_requires_five_slots() -> None:
    opp = Opportunity(
        id="opp-001",
        type=OpportunityType.BUG_FIX,
        target="python/.../mcp_http.py#L256",
        action="PR (fix + test)",
        evidence="repro.py reproduces the leak",
        effort="30min",
        risk="low",
        risk_rationale="additive security fix",
        rationale="cross-origin invariant violated",
        tier=1,
    )
    assert opp.type is OpportunityType.BUG_FIX


def test_opportunity_type_enum_values() -> None:
    assert OpportunityType.BUG_FIX.value == "bug-fix"
    assert OpportunityType.DRIFT_DECISION.value == "drift-decision"
    expected = {
        "bug-fix", "bug-port", "feature-parity",
        "industry-adapt", "design-borrow", "docs-sample", "drift-decision",
    }
    assert {t.value for t in OpportunityType} == expected


def test_opportunity_missing_field_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Opportunity(
            id="x", type=OpportunityType.BUG_FIX,
            target="t", action="a", evidence="e",
            effort="30min",
            # risk missing
            rationale="r", tier=1,
        )  # type: ignore[call-arg]
