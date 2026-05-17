from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from af_expert.candidate.model import Candidate


def render_digest(
    *,
    since: datetime,
    candidates: list[Candidate],
    ingestion_summary: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# af-expert digest — since {since.isoformat()}")
    lines.append("")

    if ingestion_summary:
        succ = ingestion_summary.get("repos_succeeded", 0)
        fail = ingestion_summary.get("repos_failed", 0)
        events = ingestion_summary.get("new_events", 0)
        lines.append(f"**Ingestion:** {succ} repos succeeded, {fail} repo failed, {events} new events")
        lines.append("")

    lines.append(f"## {len(candidates)} new candidates")
    lines.append("")

    if not candidates:
        lines.append("No candidates produced in this window.")
        return "\n".join(lines)

    by_strategy = Counter(c.strategy for c in candidates)
    by_repo = Counter(c.target_repo for c in candidates)

    lines.append("### By strategy")
    for strategy, count in by_strategy.most_common():
        lines.append(f"- `{strategy}`: {count}")
    lines.append("")

    lines.append("### By target repo (top 10)")
    for repo, count in by_repo.most_common(10):
        lines.append(f"- `{repo}`: {count}")
    lines.append("")

    lines.append("### Top 5 by confidence")
    top = sorted(candidates, key=lambda c: c.confidence, reverse=True)[:5]
    for c in top:
        lines.append(f"- **{c.id}** ({c.confidence:.2f}) `{c.target_repo}` — {c.title}")
    lines.append("")

    return "\n".join(lines)
