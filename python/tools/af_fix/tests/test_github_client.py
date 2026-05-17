# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock

import pytest

from af_fix.exceptions import GitHubAPIError
from af_fix.github_client import GitHubClient
from af_fix.models import IssueRef  # noqa: F401  -- kept for documentation; PRResult used via return types


def _fake_issue(number: int, title: str, body: str = "", pr_attr: bool = False) -> MagicMock:
    m = MagicMock()
    m.number = number
    m.title = title
    m.body = body
    m.labels = []
    m.comments = 0
    m.created_at = None
    m.pull_request = MagicMock() if pr_attr else None
    return m


def _build(repo_to_issues: dict, repo_to_pulls: dict | None = None, login: str = "mingdongtan") -> GitHubClient:
    fake_gh = MagicMock()
    fake_gh.get_user.return_value.login = login

    def get_repo(name: str) -> MagicMock:
        r = MagicMock()
        r.get_issues.return_value = repo_to_issues.get(name, [])
        if repo_to_pulls is not None:
            r.get_pulls.return_value = repo_to_pulls.get(name, [])
        else:
            r.get_pulls.return_value = []
        return r

    fake_gh.get_repo.side_effect = get_repo
    return GitHubClient(token="fake", gh=fake_gh)


def test_list_open_issues_excludes_prs() -> None:
    issues = [
        _fake_issue(1, "real issue"),
        _fake_issue(2, "PR masquerading", pr_attr=True),
        _fake_issue(3, "another"),
    ]
    client = _build({"o/r": issues})
    out = client.list_open_issues("o/r")
    nums = [i.ref.number for i in out]
    assert 1 in nums
    assert 2 not in nums
    assert 3 in nums
    for i in out:
        assert i.ref.repo == "o/r"


def test_authenticated_login() -> None:
    client = _build({}, login="testuser")
    assert client.authenticated_login() == "testuser"


def test_find_open_pr_returns_existing() -> None:
    fake_pr = MagicMock()
    fake_pr.number = 99
    fake_pr.html_url = "https://x/pr/99"
    client = _build({"o/r": []}, repo_to_pulls={"o/r": [fake_pr]})
    res = client.find_open_pr(upstream="o/r", head="me:branch")
    assert res is not None
    assert res.number == 99


def test_find_open_pr_none_when_empty() -> None:
    client = _build({"o/r": []}, repo_to_pulls={"o/r": []})
    assert client.find_open_pr(upstream="o/r", head="me:branch") is None


def test_create_draft_pr_forces_draft_true() -> None:
    fake_pr = MagicMock()
    fake_pr.number = 5888
    fake_pr.html_url = "https://x/pr/5888"
    fake_gh = MagicMock()
    fake_gh.get_user.return_value.login = "me"
    fake_repo = MagicMock()
    fake_repo.create_pull.return_value = fake_pr
    fake_gh.get_repo.return_value = fake_repo

    client = GitHubClient(token="fake", gh=fake_gh)
    res = client.create_draft_pr(upstream="o/r", title="t", body="b", head="me:branch", base="main")
    assert res.number == 5888
    kwargs = fake_repo.create_pull.call_args.kwargs
    assert kwargs["draft"] is True
    assert kwargs["base"] == "main"
    assert kwargs["head"] == "me:branch"


def test_create_pull_failure_translates() -> None:
    fake_gh = MagicMock()
    fake_gh.get_user.return_value.login = "me"
    fake_repo = MagicMock()
    fake_repo.create_pull.side_effect = RuntimeError("upstream down")
    fake_gh.get_repo.return_value = fake_repo

    client = GitHubClient(token="fake", gh=fake_gh)
    with pytest.raises(GitHubAPIError):
        client.create_draft_pr(upstream="o/r", title="t", body="b", head="me:b", base="main")
