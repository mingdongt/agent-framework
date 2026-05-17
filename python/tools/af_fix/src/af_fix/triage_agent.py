# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, Any, Callable

from pydantic import Field

from af_fix.models import Issue, ScoreResult

_TRIAGE_INSTRUCTIONS = """\
You are an OSS issue triage agent.
Score whether this issue is suitable for an AI agent to fix and PR in under 30 minutes.

High (7-10): clear error, full stack trace, reproducible; single-file or small set; no design decision.
Mid  (4-6): clear error but possibly multi-file; small refactor; needs verification.
Low  (0-3): feature request / discussion / proposal; needs architecture; large refactor; vague.

Call submit_score EXACTLY ONCE with score, reason (one line), and suggested_files (best guess at relevant paths).
"""


def _no_score_result(issue: Issue, reason: str) -> ScoreResult:
    return ScoreResult(ref=issue.ref, score=0, reason=reason, suggested_files=[])


def _default_agent_factory(client: Any, tools: list[Any], instructions: str) -> Any:
    from agent_framework import Agent

    return Agent(client=client, name="TriageAgent", instructions=instructions, tools=tools)


def score_one(
    issue: Issue,
    *,
    client: Any,
    _agent_factory: Callable[[Any, list[Any], str], Any] = _default_agent_factory,
) -> ScoreResult:
    """Score one issue with one LLM call."""
    from agent_framework import tool

    captured: dict[str, Any] = {}

    @tool(approval_mode="never_require")
    def submit_score(
        score: Annotated[int, Field(description="Fixability 0-10.")],
        reason: Annotated[str, Field(description="One-line reason.")],
        suggested_files: Annotated[list[str], Field(description="Likely files.")] = [],  # noqa: B006
    ) -> str:
        captured["score"] = max(0, min(10, int(score)))
        captured["reason"] = reason
        captured["suggested_files"] = suggested_files
        return "ok"

    agent = _agent_factory(client, [submit_score], _TRIAGE_INSTRUCTIONS)

    prompt = (
        f"Repo: {issue.ref.repo}\n"
        f"Issue #{issue.ref.number}: {issue.title}\n\n"
        f"Body:\n{issue.body}\n"
    )

    try:
        asyncio.run(agent.run(prompt))
    except Exception as exc:
        return _no_score_result(issue, f"triage error: {exc}")

    if "score" not in captured:
        return _no_score_result(issue, "no score returned")

    return ScoreResult(
        ref=issue.ref,
        score=captured["score"],
        reason=captured["reason"],
        suggested_files=captured["suggested_files"],
    )


class TriageAgent:
    """Per-issue independent LLM scoring; serial in Phase 1."""

    def __init__(
        self,
        client: Any,
        *,
        _score_one: Callable[[Issue], ScoreResult] | None = None,
    ) -> None:
        self._client = client
        self._score_one = _score_one or (lambda issue: score_one(issue, client=client))

    def score_all(self, issues: list[Issue]) -> list[ScoreResult]:
        return [self._score_one(issue) for issue in issues]
