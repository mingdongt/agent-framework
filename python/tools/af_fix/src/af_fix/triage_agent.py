# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import re
from typing import Any, Callable

from af_fix.models import Issue, ScoreResult

_TRIAGE_INSTRUCTIONS = """\
You are an OSS issue triage agent.
Score whether this issue is suitable for an AI agent to fix and PR in under 30 minutes.

High (7-10): clear error, full stack trace, reproducible; single-file or small set; no design decision.
Mid  (4-6): clear error but possibly multi-file; small refactor; needs verification.
Low  (0-3): feature request / discussion / proposal; needs architecture; large refactor; vague.

Output JSON exactly like this (no markdown fences, no extra text):
{"score": N, "reason": "one-line reason", "suggested_files": ["path/to/file.py"]}
"""


def _no_score_result(issue: Issue, reason: str) -> ScoreResult:
    return ScoreResult(ref=issue.ref, score=0, reason=reason, suggested_files=[])


def _default_run_claude(prompt: str) -> str:
    """Default implementation: calls claude-agent-sdk with max_turns=1."""
    from claude_agent_sdk import ClaudeAgentOptions, query
    from claude_agent_sdk.types import AssistantMessage, TextBlock

    options = ClaudeAgentOptions(
        max_turns=1,
        tools=None,
        permission_mode="bypassPermissions",
    )

    async def _run() -> str:
        last_text = ""
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        last_text = block.text
        return last_text

    return asyncio.run(_run())


_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def score_one(
    issue: Issue,
    *,
    _run_claude: Callable[[str], str] | None = None,
    # Kept for backward compatibility — not used
    client: Any = None,
    _agent_factory: Any = None,
) -> ScoreResult:
    """Score one issue with one LLM call via claude-agent-sdk."""
    runner = _run_claude or _default_run_claude

    prompt = (
        f"{_TRIAGE_INSTRUCTIONS}\n\n"
        f"Repo: {issue.ref.repo}\n"
        f"Issue #{issue.ref.number}: {issue.title}\n\n"
        f"Body:\n{issue.body}\n"
    )

    try:
        response_text = runner(prompt)
    except Exception as exc:
        return _no_score_result(issue, f"triage error: {exc}")

    # Extract JSON from the response
    m = _JSON_RE.search(response_text or "")
    if not m:
        return _no_score_result(issue, "no score returned")

    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return _no_score_result(issue, "no score returned")

    if "score" not in data:
        return _no_score_result(issue, "no score returned")

    score = max(0, min(10, int(data["score"])))
    reason = str(data.get("reason", ""))
    suggested_files = list(data.get("suggested_files", []))

    return ScoreResult(
        ref=issue.ref,
        score=score,
        reason=reason,
        suggested_files=suggested_files,
    )


class TriageAgent:
    """Per-issue independent LLM scoring; serial in Phase 1."""

    def __init__(
        self,
        client: Any = None,
        *,
        _score_one: Callable[[Issue], ScoreResult] | None = None,
    ) -> None:
        self._client = client  # kept for backward compat; not used
        self._score_one = _score_one or (lambda issue: score_one(issue))

    def score_all(self, issues: list[Issue]) -> list[ScoreResult]:
        return [self._score_one(issue) for issue in issues]
