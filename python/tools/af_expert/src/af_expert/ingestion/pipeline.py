from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.ingestion.issues import fetch_issues
from af_expert.ingestion.prs import fetch_prs
from af_expert.ingestion.releases import fetch_releases
from af_expert.ingestion.store import EventStore


log = logging.getLogger(__name__)

# Default lookback when no cursor exists for a repo
DEFAULT_LOOKBACK = timedelta(days=7)


@dataclass
class IngestionResult:
    repos_succeeded: int = 0
    repos_failed: int = 0
    failed_repos: dict[str, str] = field(default_factory=dict)
    new_events: int = 0


def _cursor_for(state: dict[str, Any], repo: str, now: datetime) -> datetime:
    raw = state.get("cursors", {}).get(repo)
    if raw is None:
        return now - DEFAULT_LOOKBACK
    return datetime.fromisoformat(raw)


def _advance_cursor(state: dict[str, Any], repo: str, now: datetime) -> None:
    state.setdefault("cursors", {})[repo] = now.isoformat()


def run_ingestion_tick(
    config: Any,
    gh: Any,
    store: EventStore,
    *,
    now: datetime | None = None,
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
) -> IngestionResult:
    """Run one daily tick. Per-repo isolation: failures don't propagate.

    `load_state` and `save_state` are injected so tests can avoid disk.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    state = load_state()
    result = IngestionResult()

    for repo_cfg in config.repos:
        repo = repo_cfg.owner_repo
        cursor = _cursor_for(state, repo, now)
        try:
            issues_count = fetch_issues(gh, store, repo=repo, since=cursor)
            prs_count = fetch_prs(gh, store, repo=repo, since=cursor)
            releases_count = fetch_releases(gh, store, repo=repo, since=cursor)
            result.new_events += issues_count + prs_count + releases_count
            _advance_cursor(state, repo, now)
            result.repos_succeeded += 1
            save_state(state)
        except Exception as e:
            log.exception("Ingestion failed for %s", repo)
            result.repos_failed += 1
            result.failed_repos[repo] = str(e)

    return result
