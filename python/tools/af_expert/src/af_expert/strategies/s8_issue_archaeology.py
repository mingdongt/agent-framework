from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

ARCHAEOLOGY_LABELS = ["wontfix", "stale", "not-planned"]
DEFAULT_MIN_AGE_DAYS = 180
DEFAULT_MAX_AGE_DAYS = 365 * 3


def archaeology_prompt(*, repo: str, issue: dict[str, Any]) -> str:
    return (
        f"You are evaluating whether a closed/wontfix issue in {repo} is more tractable today.\n\n"
        f"Issue #{issue['number']}: {issue['title']}\n"
        f"Closed at: {issue['closed_at']}\n"
        f"Labels: {issue['labels']}\n\n"
        f"Body:\n{(issue.get('body') or '')[:4000]}\n\n"
        "Consider: have new tools, language features, libraries, or ecosystem patterns "
        "emerged since this issue was closed that would make it tractable now?\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- tractable: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class IssueArchaeologyStrategy(Strategy):
    name = "s8_issue_archaeology"

    def __init__(
        self,
        *args: Any,
        min_age_days: int = DEFAULT_MIN_AGE_DAYS,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        confidence_threshold: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.min_age_days = min_age_days
        self.max_age_days = max_age_days
        self.confidence_threshold = confidence_threshold

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        # Archaeology runs on-demand, not on every tick
        return []

    def on_demand(self, args: dict[str, object]) -> list[Candidate]:
        target_repo = args.get("repo")
        if not isinstance(target_repo, str):
            return []

        now = datetime.now(tz=timezone.utc)
        oldest_age = now - timedelta(days=self.max_age_days)
        newest_age = now - timedelta(days=self.min_age_days)

        produced: list[Candidate] = []
        all_issues = list(self.events.query_closed_issues(
            target_repo, before=newest_age, labels_any_of=ARCHAEOLOGY_LABELS
        ))
        # Process oldest-first so callers get a consistent ordering
        all_issues.sort(key=lambda i: i.get("closed_at") or "")
        for issue in all_issues:
            closed_at = datetime.fromisoformat(issue["closed_at"]) if issue["closed_at"] else None
            if closed_at is None or closed_at < oldest_age:
                continue

            verdict = self._evaluate(target_repo, issue)
            if verdict is None:
                continue
            if not verdict.get("tractable"):
                continue
            conf = float(verdict.get("confidence", 0.0))
            if conf < self.confidence_threshold:
                continue

            candidate = self._build_candidate(target_repo, issue, verdict)
            self.candidates.append(candidate)
            produced.append(candidate)
        return produced

    def _evaluate(self, repo: str, issue: dict[str, Any]) -> dict[str, Any] | None:
        log.debug(
            "S8 _evaluate: %s#%s, title=%r, labels=%r",
            repo, issue.get("number"), issue.get("title"), issue.get("labels")
        )
        try:
            resp = self.llm.complete(
                system="You are an OSS contributor evaluating closed issues for re-opening.",
                user=archaeology_prompt(repo=repo, issue=issue),
                caller_label=f"s8.evaluate[{repo}#{issue.get('number')}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("Archaeology eval failed for %s#%s: %s", repo, issue.get("number"), e)
            return None

    def _build_candidate(
        self, repo: str, issue: dict[str, Any], verdict: dict[str, Any]
    ) -> Candidate:
        return Candidate(
            id=f"s8-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="bug",
            title=f"Reopen candidate: {issue['title']}",
            description=(
                f"This issue was closed/wontfix at {issue['closed_at']}. "
                f"Reasoning: {verdict.get('reasoning', '')}"
            ),
            suggested_action=(
                "Comment on the original issue asking whether maintainers would accept "
                "a re-opened attempt given current ecosystem state, then proceed if positive."
            ),
            evidence_urls=[issue["url"]],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.0)),
            novelty=0.6,
            actionability=0.4,
            strategy_reputation=0.5,
            status="new",
        )
