from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_expert.ingestion.store import EventStore, EventRecord


@pytest.fixture
def store(tmp_state_dir: Path) -> EventStore:
    s = EventStore()
    s.ensure_schema()
    return s


def _make_record(**kwargs: object) -> EventRecord:
    base = {
        "repo": "microsoft/agent-framework",
        "kind": "pr",
        "number": 5784,
        "title": "fix: orphan thinking signatures",
        "body": "Fixes #5783",
        "diff": "diff --git ...",
        "author": "he-yufeng",
        "state": "merged",
        "labels": [],
        "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "merged_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "url": "https://github.com/microsoft/agent-framework/pull/5784",
        "raw": {"some": "json"},
    }
    base.update(kwargs)
    return EventRecord(**base)


def test_ensure_schema_creates_tables(store: EventStore) -> None:
    cur = store._conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('events', 'events_fts')"
    )
    names = {row[0] for row in cur.fetchall()}
    assert "events" in names
    assert "events_fts" in names


def test_insert_and_read_back(store: EventStore) -> None:
    rec = _make_record()
    store.insert(rec)
    rows = list(store.query_recent_prs("microsoft/agent-framework", since=rec.created_at, only_merged=True))
    assert len(rows) == 1
    assert rows[0]["number"] == 5784
    assert rows[0]["title"] == "fix: orphan thinking signatures"


def test_insert_is_idempotent_on_repo_kind_number(store: EventStore) -> None:
    rec = _make_record()
    store.insert(rec)
    rec2 = _make_record(title="updated title")
    store.insert(rec2)

    rows = list(store.query_recent_prs("microsoft/agent-framework", since=rec.created_at, only_merged=True))
    assert len(rows) == 1
    assert rows[0]["title"] == "updated title"


def test_fts_search_by_title(store: EventStore) -> None:
    store.insert(_make_record(number=1, title="orphan thinking signatures"))
    store.insert(_make_record(number=2, title="completely unrelated"))

    results = list(store.fts_search("orphan thinking"))
    assert len(results) == 1
    assert results[0]["number"] == 1


def test_query_recent_prs_only_merged_flag(store: EventStore) -> None:
    store.insert(_make_record(number=1, state="merged"))
    store.insert(_make_record(number=2, state="closed", merged_at=None))

    merged_only = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 1, 1, tzinfo=timezone.utc), only_merged=True
        )
    )
    assert len(merged_only) == 1
    assert merged_only[0]["number"] == 1
