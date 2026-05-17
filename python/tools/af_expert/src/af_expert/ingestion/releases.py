from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_releases(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for rel in gh.list_releases_since(repo, since):
        rec = EventRecord(
            repo=repo,
            kind="release",
            number=None,
            title=rel["title"],
            body=rel["body"],
            author=rel["author"],
            state=rel["state"],
            labels=rel["labels"],
            created_at=rel["created_at"],
            updated_at=rel["updated_at"],
            url=rel["url"],
        )
        store.insert(rec)
        count += 1
    return count
