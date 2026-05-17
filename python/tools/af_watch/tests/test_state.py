# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from pathlib import Path

from af_watch.state import State


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    s = State.load(path)
    assert s.last_run is None
    assert s.decisions_log == []

    s.record_run(
        started_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 17, 0, 14, tzinfo=timezone.utc),
        window="2026-05-10_2026-05-17",
        opp_count=11,
        report_path=Path("~/.af-watch/reports/2026-05-17/briefing.md"),
    )
    s.save()

    s2 = State.load(path)
    assert s2.last_run is not None
    assert s2.last_run["opp_count"] == 11


def test_decision_logging(tmp_path: Path) -> None:
    s = State.load(tmp_path / "state.json")
    s.log_decision(opp_id="opp-001", action="acted", note="shipped as PR #5867")
    s.log_decision(opp_id="opp-002", action="declined", note="intentional design")
    s.save()

    s2 = State.load(tmp_path / "state.json")
    assert len(s2.decisions_log) == 2
    assert s2.decisions_log[0]["action"] == "acted"


def test_corpus_refresh_tracking(tmp_path: Path) -> None:
    s = State.load(tmp_path / "state.json")
    s.mark_corpus_refreshed("domain_map/microsoft__agent-framework.md", "2026-05-17")
    s.save()

    s2 = State.load(tmp_path / "state.json")
    assert s2.corpus_last_refreshed["domain_map/microsoft__agent-framework.md"] == "2026-05-17"
