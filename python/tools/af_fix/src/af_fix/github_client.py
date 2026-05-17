# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from github import Github

from af_fix.exceptions import GitHubAPIError
from af_fix.models import Issue, IssueRef, PRResult


class GitHubClient:
    def __init__(self, token: str, gh: Any = None) -> None:
        self._gh = gh if gh is not None else Github(token)

    def authenticated_login(self) -> str:
        return self._gh.get_user().login

    def list_open_issues(self, repo: str) -> list[Issue]:
        try:
            raw_repo = self._gh.get_repo(repo)
        except Exception as exc:
            raise GitHubAPIError(f"failed to load repo {repo}: {exc}") from exc

        out: list[Issue] = []
        for raw in raw_repo.get_issues(state="open"):
            if getattr(raw, "pull_request", None) is not None:
                continue
            out.append(self._to_issue(repo, raw))
        return out

    def find_open_pr(self, *, upstream: str, head: str) -> PRResult | None:
        try:
            repo = self._gh.get_repo(upstream)
            pulls = list(repo.get_pulls(state="open", head=head))
        except Exception as exc:
            raise GitHubAPIError(f"failed to query PRs on {upstream}: {exc}") from exc
        if not pulls:
            return None
        return PRResult(number=pulls[0].number, url=pulls[0].html_url)

    def create_draft_pr(
        self,
        *,
        upstream: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PRResult:
        try:
            repo = self._gh.get_repo(upstream)
            pr = repo.create_pull(title=title, body=body, head=head, base=base, draft=True)
        except Exception as exc:
            raise GitHubAPIError(f"failed to create PR on {upstream}: {exc}") from exc
        return PRResult(number=pr.number, url=pr.html_url)

    @staticmethod
    def _to_issue(repo: str, raw: Any) -> Issue:
        return Issue(
            ref=IssueRef(repo=repo, number=raw.number),
            title=raw.title,
            body=raw.body or "",
            labels=[lbl.name for lbl in getattr(raw, "labels", [])],
            comments_count=getattr(raw, "comments", 0),
            created_at=getattr(raw, "created_at", None),
        )
