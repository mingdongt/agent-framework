from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore


def _make_h(hid: str = "h-001") -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement="MCP OAuth grants violate RFC 8707",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )


def test_empty_store(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    assert s.list_active() == []


def test_add_and_get(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    s.upsert(_make_h("h-001"))
    fetched = s.get("h-001")
    assert fetched is not None
    assert fetched.statement == "MCP OAuth grants violate RFC 8707"


def test_attach_verification(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    s.upsert(_make_h("h-001"))
    v = Verification(repo="x/y", verified_at="2026-05-18", outcome="non_compliant", reasoning="...")
    s.attach_verification("h-001", v)

    h = s.get("h-001")
    assert "x/y" in h.verifications


def test_list_active_excludes_archived(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    h1 = _make_h("h-001"); h1.status = "active"
    h2 = _make_h("h-002"); h2.status = "archived"
    s.upsert(h1)
    s.upsert(h2)
    active = s.list_active()
    assert len(active) == 1
    assert active[0].id == "h-001"


def test_unverified_repos(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    h = _make_h("h-001")
    h.verifications["x/y"] = Verification(
        repo="x/y", verified_at="2026-05-18", outcome="compliant", reasoning="ok"
    )
    s.upsert(h)

    unverified = s.unverified_repos("h-001", all_repos=["x/y", "a/b", "c/d"])
    assert "x/y" not in unverified
    assert set(unverified) == {"a/b", "c/d"}
