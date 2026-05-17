from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_issues(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for issue in gh.list_issues_updated_since(repo, since):
        rec = EventRecord(
            repo=repo,
            kind="issue",
            number=issue["number"],
            title=issue["title"],
            body=issue["body"],
            author=issue["author"],
            state=issue["state"],
            labels=issue["labels"],
            created_at=issue["created_at"],
            updated_at=issue["updated_at"],
            closed_at=issue.get("closed_at"),
            url=issue["url"],
        )
        log.debug(
            "fetch_issues %s: issue #%d %r (state=%s, labels=%r)",
            repo, issue["number"], issue["title"], issue["state"], issue["labels"]
        )
        store.insert(rec)
        count += 1
    return count
