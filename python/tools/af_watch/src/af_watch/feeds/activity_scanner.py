# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime
from typing import Any

from github import Github

from af_watch.exceptions import FeedError
from af_watch.models import ActivityEvent


class ActivityScanner:
    def __init__(self, *, token: str | None = None, gh: Any | None = None) -> None:
        if gh is not None:
            self._gh = gh
        elif token is not None:
            self._gh = Github(token)
        else:
            raise FeedError("ActivityScanner requires token or gh")

    def scan_repo(self, repo: str, *, since: datetime, until: datetime) -> list[ActivityEvent]:
        try:
            raw_repo = self._gh.get_repo(repo)
        except Exception as exc:
            raise FeedError(f"failed to load repo {repo}: {exc}") from exc

        events: list[ActivityEvent] = []

        for pr in raw_repo.get_pulls(state="closed", sort="updated", direction="desc"):
            merged_at = getattr(pr, "merged_at", None)
            if merged_at is None:
                continue
            if not (since <= merged_at <= until):
                if merged_at < since:
                    break
                continue
            events.append(self._pr_to_event(repo, pr))

        for issue in raw_repo.get_issues(state="closed", sort="updated", direction="desc"):
            if getattr(issue, "pull_request", None) is not None:
                continue
            closed_at = getattr(issue, "closed_at", None)
            if closed_at is None:
                continue
            if not (since <= closed_at <= until):
                if closed_at < since:
                    break
                continue
            events.append(self._issue_to_event(repo, issue))

        for release in raw_repo.get_releases():
            published = getattr(release, "published_at", None)
            if published is None:
                continue
            if not (since <= published <= until):
                continue
            events.append(self._release_to_event(repo, release))

        return events

    def scan_all(
        self,
        repos: list[str],
        *,
        since: datetime,
        until: datetime,
    ) -> list[ActivityEvent]:
        all_events: list[ActivityEvent] = []
        for repo in repos:
            all_events.extend(self.scan_repo(repo, since=since, until=until))
        return all_events

    @staticmethod
    def _pr_to_event(repo: str, pr: Any) -> ActivityEvent:
        files: list[str] = []
        try:
            files = [f.filename for f in pr.get_files()]
        except Exception:
            files = []
        return ActivityEvent(
            repo=repo,
            type="pr_merged",
            number=pr.number,
            title=pr.title,
            timestamp=pr.merged_at,
            author=getattr(pr.user, "login", None),
            files_changed=files,
            labels=[lbl.name for lbl in (pr.labels or [])],
            body=pr.body or "",
            url=pr.html_url,
        )

    @staticmethod
    def _issue_to_event(repo: str, issue: Any) -> ActivityEvent:
        return ActivityEvent(
            repo=repo,
            type="issue_closed",
            number=issue.number,
            title=issue.title,
            timestamp=issue.closed_at,
            author=getattr(issue.user, "login", None),
            labels=[lbl.name for lbl in (issue.labels or [])],
            body=issue.body or "",
            url=issue.html_url,
        )

    @staticmethod
    def _release_to_event(repo: str, release: Any) -> ActivityEvent:
        return ActivityEvent(
            repo=repo,
            type="release",
            number=None,
            title=release.title or release.tag_name,
            timestamp=release.published_at,
            body=release.body or "",
            url=release.html_url,
        )
