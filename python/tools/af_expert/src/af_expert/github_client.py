from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from github import Github
from github.GithubException import GithubException


@dataclass(frozen=True)
class RateLimitInfo:
    remaining: int
    limit: int
    reset_at: datetime


class GitHubClient:
    """Thin wrapper over PyGithub.

    Constructor accepts an optional `_github` injection point for tests.
    Public methods return plain dicts (not PyGithub objects), so consumers
    are not coupled to PyGithub's API surface.
    """

    def __init__(self, token: str, *, _github: Github | None = None) -> None:
        self._gh = _github if _github is not None else Github(token, per_page=100)
        self._token = token

    def get_rate_limit(self) -> RateLimitInfo:
        rl = self._gh.get_rate_limit()
        return RateLimitInfo(
            remaining=rl.core.remaining,
            limit=rl.core.limit,
            reset_at=rl.core.reset,
        )

    def list_issues_updated_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for issue in repo.get_issues(state="all", since=since, sort="updated"):
            # PyGithub: pull requests show up as issues too; filter them out
            if issue.pull_request is not None:
                continue
            yield {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body or "",
                "author": issue.user.login if issue.user else "unknown",
                "state": issue.state,
                "labels": [lab.name for lab in issue.labels],
                "created_at": issue.created_at,
                "updated_at": issue.updated_at,
                "closed_at": issue.closed_at,
                "url": issue.html_url,
            }

    def list_pulls_merged_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
            if pr.updated_at < since:
                break
            if not pr.merged:
                continue
            yield {
                "number": pr.number,
                "title": pr.title,
                "body": pr.body or "",
                "author": pr.user.login if pr.user else "unknown",
                "state": "merged",
                "labels": [lab.name for lab in pr.labels],
                "created_at": pr.created_at,
                "updated_at": pr.updated_at,
                "merged_at": pr.merged_at,
                "closed_at": pr.closed_at,
                "url": pr.html_url,
            }

    def get_pull_diff(self, owner_repo: str, number: int) -> str:
        """Fetch unified diff text for a PR.

        Uses GitHub's API `.diff` representation by setting the right Accept header.
        """
        headers = {"Accept": "application/vnd.github.v3.diff"}
        url = f"/repos/{owner_repo}/pulls/{number}"
        _status, _headers, data = self._gh._Github__requester.requestJson(
            "GET", url, headers=headers
        )
        return data if isinstance(data, str) else json.dumps(data)

    def list_releases_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for rel in repo.get_releases():
            if rel.published_at and rel.published_at < since:
                break
            yield {
                "number": None,
                "title": rel.name or rel.tag_name,
                "body": rel.body or "",
                "author": rel.author.login if rel.author else "unknown",
                "state": "published",
                "labels": [rel.tag_name],
                "created_at": rel.created_at,
                "updated_at": rel.published_at,
                "url": rel.html_url,
            }
