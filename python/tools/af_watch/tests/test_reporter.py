# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from pathlib import Path

from af_watch.models import (
    BriefingData,
    IndustryEntry,
    Opportunity,
    OpportunityType,
)
from af_watch.reporter import Reporter


def _opp(id_: str = "opp-001", type_: OpportunityType = OpportunityType.BUG_FIX) -> Opportunity:
    return Opportunity(
        id=id_, type=type_,
        target="microsoft/agent-framework:python/x.py#L256",
        action="PR (fix)",
        evidence="repro.py reproduces it",
        effort="30min",
        risk="low", risk_rationale="additive",
        rationale="cross-origin invariant violated",
        tier=1, repro_status="confirmed",
    )


def _data() -> BriefingData:
    return BriefingData(
        window_start=datetime(2026, 5, 10, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 17, tzinfo=timezone.utc),
        opportunities=[_opp("opp-001"), _opp("opp-002", OpportunityType.FEATURE_PARITY)],
        industry_highlights=[IndustryEntry(
            timestamp=datetime(2026, 5, 15, tzinfo=timezone.utc),
            source="anthropic_blog",
            title="MCP 2025-06",
            summary="OAuth resource tightening",
            url="https://anthropic.com/news/mcp",
        )],
        activity_summary={"microsoft/agent-framework": 32},
    )


def test_writes_briefing_markdown(tmp_path: Path) -> None:
    reporter = Reporter(reports_root=tmp_path)
    path = reporter.write(_data())
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Weekly Briefing" in content
    assert "opp-001" in content
    assert "opp-002" in content
    assert "MCP 2025-06" in content


def test_creates_deep_dive_per_opportunity(tmp_path: Path) -> None:
    reporter = Reporter(reports_root=tmp_path)
    reporter.write(_data())
    deep = tmp_path / "2026-05-17" / "deep_dives"
    assert (deep / "opp-001" / "analysis.md").exists()
    assert (deep / "opp-002" / "analysis.md").exists()


def test_writes_opportunities_jsonl(tmp_path: Path) -> None:
    reporter = Reporter(reports_root=tmp_path)
    reporter.write(_data())
    jsonl = tmp_path / "2026-05-17" / "opportunities.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
