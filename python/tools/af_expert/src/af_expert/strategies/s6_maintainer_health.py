from __future__ import annotations

import logging
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

MIN_PR_VOLUME = 10
DEGRADATION_FACTOR = 2.0


@dataclass
class RepoMetrics:
    repo: str
    pr_count: int
    pr_merge_median_hours: float | None
    issue_backlog_growth: int


def _query_prs_in_window(
    events: Any, repo: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    sql = (
        "SELECT * FROM events WHERE repo=? AND kind='pr' AND state='merged' "
        "AND merged_at IS NOT NULL AND merged_at >= ? AND merged_at <= ? "
        "ORDER BY merged_at"
    )
    rows = events._conn.execute(sql, (repo, start.isoformat(), end.isoformat()))
    return [dict(r) for r in rows]


def _query_issues_in_window(
    events: Any, repo: str, start: datetime, end: datetime, state: str
) -> int:
    sql = (
        "SELECT COUNT(*) FROM events WHERE repo=? AND kind='issue' AND state=? "
        "AND created_at >= ? AND created_at <= ?"
    )
    row = events._conn.execute(sql, (repo, state, start.isoformat(), end.isoformat())).fetchone()
    return int(row[0] if row else 0)


def compute_metrics(
    repo: str, *, events: Any, now: datetime, window_days: int = 30
) -> RepoMetrics:
    window_start = now - timedelta(days=window_days)
    prs = _query_prs_in_window(events, repo, window_start, now)

    merge_hours: list[float] = []
    for pr in prs:
        try:
            created = datetime.fromisoformat(pr["created_at"])
            merged = datetime.fromisoformat(pr["merged_at"])
            delta = (merged - created).total_seconds() / 3600.0
            if delta >= 0:
                merge_hours.append(delta)
        except (TypeError, ValueError):
            continue

    median = statistics.median(merge_hours) if merge_hours else None

    opened = _query_issues_in_window(events, repo, window_start, now, "open")
    closed = _query_issues_in_window(events, repo, window_start, now, "closed")
    backlog_growth = opened - closed

    return RepoMetrics(
        repo=repo,
        pr_count=len(prs),
        pr_merge_median_hours=median,
        issue_backlog_growth=backlog_growth,
    )


class MaintainerHealthStrategy(Strategy):
    name = "s6_maintainer_health"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:  # type: ignore[override]
        if now is None:
            now = datetime.now(tz=timezone.utc)

        produced: list[Candidate] = []
        for repo_cfg in self.config.repos:
            repo = repo_cfg.owner_repo
            current = compute_metrics(repo, events=self.events, now=now, window_days=30)
            prior = compute_metrics(
                repo, events=self.events, now=now - timedelta(days=30), window_days=60
            )

            if current.pr_count < MIN_PR_VOLUME:
                log.info(
                    "S6 skip %s: current PR volume %d < %d", repo, current.pr_count, MIN_PR_VOLUME
                )
                continue

            if (
                current.pr_merge_median_hours is not None
                and prior.pr_merge_median_hours is not None
                and prior.pr_merge_median_hours > 0
                and current.pr_merge_median_hours / prior.pr_merge_median_hours
                > DEGRADATION_FACTOR
            ):
                candidate = self._build_degradation_candidate(repo, current, prior)
                self.candidates.append(candidate)
                produced.append(candidate)
                log.info(
                    "S6 %s: PR median latency degraded %.1fh -> %.1fh",
                    repo,
                    prior.pr_merge_median_hours,
                    current.pr_merge_median_hours,
                )

        return produced

    def _build_degradation_candidate(
        self, repo: str, current: RepoMetrics, prior: RepoMetrics
    ) -> Candidate:
        ratio = (
            current.pr_merge_median_hours / prior.pr_merge_median_hours
            if prior.pr_merge_median_hours
            else float("inf")
        )
        return Candidate(
            id=f"s6-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="maintenance",
            title=f"{repo} maintainer-response latency degraded {ratio:.1f}x",
            description=(
                f"Repo {repo} shows PR merge median latency increase from "
                f"{prior.pr_merge_median_hours:.1f}h to {current.pr_merge_median_hours:.1f}h "
                f"({ratio:.1f}x worse). Current PR volume in last 30d: {current.pr_count}. "
                f"Issue backlog growth: {current.issue_backlog_growth} (open - closed)."
            ),
            suggested_action=(
                f"Consider becoming a co-maintainer on {repo}, or proposing a structural "
                f"improvement (CI speedup, triage automation, etc.). Engage on a recent stale PR first."
            ),
            evidence_urls=[f"https://github.com/{repo}/pulls?q=is%3Apr+is%3Aclosed"],
            evidence_snippets=[],
            confidence=0.7,
            novelty=0.5,
            actionability=0.3,
            strategy_reputation=0.5,
            status="new",
        )
