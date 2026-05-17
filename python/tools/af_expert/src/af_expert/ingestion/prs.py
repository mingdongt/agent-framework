from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_prs(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for pr in gh.list_pulls_merged_since(repo, since):
        log.info(
            "fetch_prs %s: PR #%d %r (state=%s, labels=%r)",
            repo, pr["number"], pr["title"], pr["state"], pr["labels"]
        )
        try:
            diff = gh.get_pull_diff(repo, pr["number"])
            log.debug("fetch_prs %s: PR #%d diff fetched, %d chars", repo, pr["number"], len(diff) if diff else 0)
        except Exception as e:
            log.warning("Failed to fetch diff for %s#%d: %s", repo, pr["number"], e)
            diff = None
        rec = EventRecord(
            repo=repo,
            kind="pr",
            number=pr["number"],
            title=pr["title"],
            body=pr["body"],
            author=pr["author"],
            state=pr["state"],
            labels=pr["labels"],
            created_at=pr["created_at"],
            updated_at=pr["updated_at"],
            closed_at=pr.get("closed_at"),
            merged_at=pr.get("merged_at"),
            diff=diff,
            url=pr["url"],
        )
        store.insert(rec)
        count += 1
    return count
