from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.ingestion.issues import fetch_issues
from af_expert.ingestion.prs import fetch_prs
from af_expert.ingestion.releases import fetch_releases
from af_expert.ingestion.store import EventStore


@pytest.fixture
def store(tmp_state_dir: Path) -> EventStore:
    s = EventStore()
    s.ensure_schema()
    return s


def _fake_pr_record() -> dict[str, object]:
    return {
        "number": 5784,
        "title": "fix: orphan thinking signatures",
        "body": "Fixes #5783.",
        "author": "he-yufeng",
        "state": "merged",
        "labels": ["bug"],
        "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "merged_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "url": "https://github.com/microsoft/agent-framework/pull/5784",
    }


def test_fetch_prs_writes_records_to_store(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_pulls_merged_since.return_value = iter([_fake_pr_record()])
    gh.get_pull_diff.return_value = "diff --git a/foo b/foo\n+x\n"

    count = fetch_prs(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1
    rows = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
        )
    )
    assert len(rows) == 1
    assert rows[0]["diff"].startswith("diff --git")


def test_fetch_prs_swallows_diff_fetch_failure(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_pulls_merged_since.return_value = iter([_fake_pr_record()])
    gh.get_pull_diff.side_effect = RuntimeError("diff fetch failed")

    count = fetch_prs(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
    )
    # Record still written, diff is None
    assert count == 1
    rows = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
        )
    )
    assert rows[0]["diff"] is None


def test_fetch_issues_writes_records(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_issues_updated_since.return_value = iter(
        [
            {
                "number": 5712,
                "title": "[LiteLLM] _is_thinking_blocks_format drops Gemini thinking_blocks",
                "body": "Detailed bug report ...",
                "author": "ThibaultCoudertSephora",
                "state": "open",
                "labels": ["bug"],
                "created_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "closed_at": None,
                "url": "https://github.com/google/adk-python/issues/5712",
            }
        ]
    )
    count = fetch_issues(
        gh, store, repo="google/adk-python", since=datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1


def test_fetch_releases_writes_records(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_releases_since.return_value = iter(
        [
            {
                "number": None,
                "title": "v1.4.0",
                "body": "Release notes ...",
                "author": "release-bot",
                "state": "published",
                "labels": ["v1.4.0"],
                "created_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "url": "https://github.com/microsoft/agent-framework/releases/tag/v1.4.0",
            }
        ]
    )
    count = fetch_releases(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1
