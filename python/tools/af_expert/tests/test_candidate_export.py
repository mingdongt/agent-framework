from __future__ import annotations

from datetime import datetime, timezone

from af_expert.candidate.export import render_candidate_spec
from af_expert.candidate.model import Candidate


def test_render_includes_essential_fields() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        target_files=["src/x.py"],
        category="bug",
        title="Possible orphan signature",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only blocks",
        evidence_urls=["https://github.com/microsoft/agent-framework/pull/5784"],
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    md = render_candidate_spec(c)
    assert "# Candidate c-001" in md
    assert "**Repo:** pydantic/pydantic-ai" in md
    assert "**Strategy:** s1_pr_forward_port" in md
    assert "Filter signature-only blocks" in md
    assert "https://github.com/microsoft/agent-framework/pull/5784" in md
    assert "src/x.py" in md
