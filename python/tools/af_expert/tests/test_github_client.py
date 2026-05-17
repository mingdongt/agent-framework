from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from af_expert.github_client import GitHubClient, RateLimitInfo


def test_list_pulls_merged_since_returns_normalized_records() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_pull = MagicMock()
    fake_pull.number = 5784
    fake_pull.title = "fix: skip orphan Anthropic thinking signatures"
    fake_pull.body = "Fixes #5783."
    fake_pull.merged_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.updated_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.created_at = datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    fake_pull.closed_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.state = "closed"
    fake_pull.user.login = "he-yufeng"
    fake_pull.html_url = "https://github.com/microsoft/agent-framework/pull/5784"
    fake_pull.merged = True
    fake_pull.labels = []

    fake_repo.get_pulls.return_value = [fake_pull]
    fake_github.get_repo.return_value = fake_repo

    client = GitHubClient(token="ghp_test", _github=fake_github)
    since = datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)

    results = list(client.list_pulls_merged_since("microsoft/agent-framework", since))

    assert len(results) == 1
    record = results[0]
    assert record["number"] == 5784
    assert record["title"] == "fix: skip orphan Anthropic thinking signatures"
    assert record["author"] == "he-yufeng"
    assert record["state"] == "merged"
    assert record["url"] == "https://github.com/microsoft/agent-framework/pull/5784"


def test_list_pulls_filters_out_unmerged() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_open_pr = MagicMock()
    fake_open_pr.merged = False
    fake_open_pr.state = "open"
    fake_open_pr.updated_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_repo.get_pulls.return_value = [fake_open_pr]
    fake_github.get_repo.return_value = fake_repo

    client = GitHubClient(token="ghp_test", _github=fake_github)
    since = datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)

    results = list(client.list_pulls_merged_since("microsoft/agent-framework", since))
    assert results == []


def test_get_pull_diff_returns_text() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_pull = MagicMock()
    fake_pull.get_files.return_value = []
    fake_repo.get_pull.return_value = fake_pull
    fake_github.get_repo.return_value = fake_repo

    # PyGithub doesn't expose .diff() directly; we fetch via requester
    fake_github._Github__requester.requestJson.return_value = (
        200,
        {"Content-Type": "text/plain"},
        "diff --git a/foo b/foo\n+x\n",
    )

    client = GitHubClient(token="ghp_test", _github=fake_github)
    diff = client.get_pull_diff("microsoft/agent-framework", 5784)
    assert "diff --git" in diff


def test_rate_limit_info() -> None:
    fake_github = MagicMock()
    fake_rate = MagicMock()
    fake_rate.core.remaining = 4500
    fake_rate.core.limit = 5000
    fake_rate.core.reset = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    fake_github.get_rate_limit.return_value = fake_rate

    client = GitHubClient(token="ghp_test", _github=fake_github)
    info = client.get_rate_limit()
    assert isinstance(info, RateLimitInfo)
    assert info.remaining == 4500
    assert info.limit == 5000
