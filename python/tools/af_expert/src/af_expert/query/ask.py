from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.store import CandidateStore
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM


def _build_context(
    events: EventStore, candidates: CandidateStore, question: str
) -> str:
    since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    parts: list[str] = []

    # FTS5 treats some punctuation as operators; strip trailing punctuation to
    # avoid syntax errors on natural-language questions (e.g. "MCP support?").
    fts_query = question.rstrip("?!.,;:")
    try:
        fts_hits = list(events.fts_search(fts_query, limit=20))
    except Exception:
        fts_hits = []
    if fts_hits:
        parts.append("## Recent events matching the question")
        for hit in fts_hits:
            parts.append(
                f"- [{hit['kind']}] {hit['repo']}#{hit.get('number')} {hit['title']}"
            )
        parts.append("")

    recent_candidates = list(candidates.list_since(since))
    if recent_candidates:
        parts.append("## Recent candidates (last 7 days)")
        for c in recent_candidates:
            parts.append(
                f"- **{c.id}** ({c.confidence:.2f}) `{c.target_repo}` — {c.title}"
            )
        parts.append("")

    if not parts:
        return "No recent events or candidates available."
    return "\n".join(parts)


def answer(
    *,
    question: str,
    events: EventStore,
    candidates: CandidateStore,
    llm: LLM,
) -> str:
    context = _build_context(events, candidates, question)
    system = (
        "You are an expert in the OSS agent framework / LLM ecosystem. "
        "You answer questions based on the provided context. Do not fabricate. "
        "When you cite specific frameworks/PRs, only reference items present in the context. "
        "Keep answers under 300 words unless asked for depth."
    )
    user = f"## Question\n{question}\n\n## Context\n{context}"
    resp = llm.complete(system=system, user=user)
    return resp.text
