from __future__ import annotations

from datetime import datetime, timedelta, timezone

from af_expert.candidate.model import Candidate
from af_expert.query.digest import render_digest


def _make_candidate(cid: str, repo: str, strategy: str, confidence: float) -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime.now(tz=timezone.utc),
        strategy=strategy,
        target_repo=repo,
        category="bug",
        title=f"Issue in {repo}",
        description="d",
        suggested_action="a",
        confidence=confidence,
        novelty=0.5,
        actionability=0.5,
        strategy_reputation=0.5,
        status="new",
    )


def test_digest_shows_counts_by_strategy_and_repo() -> None:
    candidates = [
        _make_candidate("c-1", "pydantic/pydantic-ai", "s1_pr_forward_port", 0.7),
        _make_candidate("c-2", "google/adk-python", "s1_pr_forward_port", 0.6),
        _make_candidate("c-3", "microsoft/agent-framework", "s8_issue_archaeology", 0.8),
    ]
    md = render_digest(
        since=datetime.now(tz=timezone.utc) - timedelta(days=1),
        candidates=candidates,
        ingestion_summary={"repos_succeeded": 3, "repos_failed": 0, "new_events": 12},
    )
    assert "3 new candidates" in md
    assert "s1_pr_forward_port" in md
    assert "s8_issue_archaeology" in md
    assert "pydantic/pydantic-ai" in md


def test_digest_with_no_candidates() -> None:
    md = render_digest(
        since=datetime.now(tz=timezone.utc) - timedelta(days=1),
        candidates=[],
        ingestion_summary={"repos_succeeded": 2, "repos_failed": 1, "new_events": 0},
    )
    assert "0 new candidates" in md or "No candidates" in md
    assert "1 repo failed" in md or "1 failed" in md
