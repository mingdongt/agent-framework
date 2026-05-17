from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore


def _make_candidate(cid: str = "c-001") -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible bug",
        description="Description",
        suggested_action="Fix it",
        confidence=0.7,
        novelty=0.5,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )


def test_append_and_list_today(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))
    s.append(_make_candidate("c-002"))

    today = list(s.list_today())
    assert {c.id for c in today} == {"c-001", "c-002"}


def test_get_returns_by_id(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))

    c = s.get("c-001")
    assert c is not None
    assert c.id == "c-001"

    assert s.get("nonexistent") is None


def test_update_status_writes_overlay(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))

    s.update_status("c-001", status="accepted", notes="looks good")

    c = s.get("c-001")
    assert c is not None
    assert c.status == "accepted"
    assert c.notes == "looks good"


def test_list_since_filters_by_date(tmp_state_dir: Path) -> None:
    s = CandidateStore()

    old = _make_candidate("c-old")
    old.discovered_at = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    new = _make_candidate("c-new")
    new.discovered_at = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

    s.append(old)
    s.append(new)

    since = datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    results = list(s.list_since(since))
    assert {c.id for c in results} == {"c-new"}
