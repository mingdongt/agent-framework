# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from af_watch.feeds.activity_scanner import ActivityScanner


def _now() -> datetime:
    return datetime(2026, 5, 17, tzinfo=timezone.utc)


def _mock_pr(*, number: int, merged_at: datetime, title: str = "fix: x") -> Any:
    m = MagicMock()
    m.number = number
    m.title = title
    m.merged_at = merged_at
    m.closed_at = merged_at
    m.body = "body"
    m.html_url = f"https://github.com/x/x/pull/{number}"
    m.user.login = "someone"
    m.labels = []
    f = MagicMock()
    f.filename = "src/x.py"
    m.get_files.return_value = [f]
    return m


def _mock_issue(*, number: int, closed_at: datetime) -> Any:
    m = MagicMock()
    m.number = number
    m.title = "an issue"
    m.body = "body"
    m.closed_at = closed_at
    m.html_url = f"https://github.com/x/x/issues/{number}"
    m.user.login = "someone"
    m.labels = []
    m.pull_request = None
    return m


def test_pulls_merged_prs_within_window() -> None:
    gh = MagicMock()
    repo = MagicMock()
    in_window = _now() - timedelta(days=2)
    out_window = _now() - timedelta(days=14)
    repo.get_pulls.return_value = [
        _mock_pr(number=1, merged_at=in_window),
        _mock_pr(number=2, merged_at=out_window),
    ]
    repo.get_issues.return_value = []
    repo.get_releases.return_value = []
    gh.get_repo.return_value = repo

    scanner = ActivityScanner(gh=gh)
    events = scanner.scan_repo("x/x", since=_now() - timedelta(days=7), until=_now())
    assert len(events) == 1
    assert events[0].number == 1
    assert events[0].type == "pr_merged"


def test_skips_unmerged_prs() -> None:
    gh = MagicMock()
    repo = MagicMock()
    unmerged = _mock_pr(number=1, merged_at=None)  # type: ignore[arg-type]
    unmerged.merged_at = None
    repo.get_pulls.return_value = [unmerged]
    repo.get_issues.return_value = []
    repo.get_releases.return_value = []
    gh.get_repo.return_value = repo

    scanner = ActivityScanner(gh=gh)
    events = scanner.scan_repo("x/x", since=_now() - timedelta(days=7), until=_now())
    assert events == []


def test_pulls_closed_issues_excluding_prs() -> None:
    gh = MagicMock()
    repo = MagicMock()
    repo.get_pulls.return_value = []
    repo.get_issues.return_value = [
        _mock_issue(number=10, closed_at=_now() - timedelta(days=1)),
    ]
    repo.get_releases.return_value = []
    gh.get_repo.return_value = repo

    scanner = ActivityScanner(gh=gh)
    events = scanner.scan_repo("x/x", since=_now() - timedelta(days=7), until=_now())
    assert any(e.type == "issue_closed" for e in events)


def test_scan_all_aggregates_repos() -> None:
    gh = MagicMock()
    repo_a = MagicMock()
    repo_a.get_pulls.return_value = [_mock_pr(number=1, merged_at=_now() - timedelta(days=1))]
    repo_a.get_issues.return_value = []
    repo_a.get_releases.return_value = []
    repo_b = MagicMock()
    repo_b.get_pulls.return_value = [_mock_pr(number=2, merged_at=_now() - timedelta(days=1))]
    repo_b.get_issues.return_value = []
    repo_b.get_releases.return_value = []
    gh.get_repo.side_effect = [repo_a, repo_b]

    scanner = ActivityScanner(gh=gh)
    events = scanner.scan_all(["a/a", "b/b"], since=_now() - timedelta(days=7), until=_now())
    assert len(events) == 2
    assert {e.repo for e in events} == {"a/a", "b/b"}
