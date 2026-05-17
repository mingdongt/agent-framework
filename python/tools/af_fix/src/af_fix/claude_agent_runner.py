# Copyright (c) Microsoft. All rights reserved.

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, cast

from af_fix.exceptions import ClaudeAgentError
from af_fix.models import FixResult, Issue

_PROMPT_TEMPLATE = """\
You are fixing an issue in an open-source repository.

Repository: {repo}
Issue #{number}: {title}

Issue body:
{body}

The repository is already checked out at the current working directory. The default branch is checked out.

Your task:
1. Read the issue carefully.
2. Reproduce or confirm the bug if possible.
3. Make the minimum change required to fix it.
4. Run the test suite (or the relevant subset) and confirm it passes.
5. Write a brief one-line summary at the end like:
   SUMMARY: <conventional-commits style fix message>

Hard constraints:
- Touch only files needed for the fix.
- No new dependencies, no CI changes, no formatter sweeps.
- If the issue is too broad, malformed, or undecidable: STOP and write "GAVE_UP: <reason>".
"""

_SUMMARY_RE = re.compile(r"SUMMARY:\s*(.+?)(?:\n|$)")
_GAVE_UP_RE = re.compile(r"GAVE_UP:\s*(.+?)(?:\n|$)")


def extract_summary_marker(text: str) -> str | None:
    m = _SUMMARY_RE.search(text or "")
    return m.group(1).strip() if m else None


def extract_gave_up_marker(text: str) -> str | None:
    m = _GAVE_UP_RE.search(text or "")
    return m.group(1).strip() if m else None


def extract_trajectory_excerpt(history: list[Any], *, last_n: int = 30) -> str:
    tail = history[-last_n:] if len(history) > last_n else history
    return "\n".join(str(e) for e in tail)


def _real_git_diff(workspace: Path) -> str:
    r = subprocess.run(
        ["git", "diff", "origin/main"],  # noqa: S607
        cwd=workspace, capture_output=True, text=True, check=False,
    )
    return r.stdout


class _StateShim:
    """Thin adapter wrapping claude-agent-sdk messages into the contract our code expects."""

    def __init__(self, last_assistant_message: str, history: list[Any]) -> None:
        self.last_assistant_message = last_assistant_message
        self.history = history


def _extract_text_from_message(msg: Any) -> str:
    """Extract text content from a claude-agent-sdk AssistantMessage."""
    try:
        from claude_agent_sdk.types import AssistantMessage, TextBlock
    except ImportError:
        return str(msg)

    if not isinstance(msg, AssistantMessage):
        return ""
    texts = []
    for block in msg.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)
    return "\n".join(texts)


def _real_run_claude(
    *,
    workspace: Path,
    prompt: str,
    model: str,
    max_turns: int,
) -> "_StateShim":
    """Drive claude-agent-sdk synchronously against the workspace.

    NOTE: Claude Code SDK runs in-process (same host). The agent has the same
    filesystem and network access as the calling process. Run only against
    trusted repos until containerization is added (Phase 2).
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError as exc:
        raise ClaudeAgentError(f"claude-agent-sdk not installed or incompatible: {exc}") from exc

    options = ClaudeAgentOptions(
        cwd=str(workspace),
        model=model,
        max_turns=max_turns,
        # Allow standard code-editing tools; no MCP or special tools needed
        permission_mode="acceptEdits",
    )

    async def _run() -> list[Any]:
        messages: list[Any] = []
        async for msg in query(prompt=prompt, options=options):
            messages.append(msg)
        return messages

    messages = asyncio.run(_run())

    last = ""
    for m in reversed(messages):
        text = _extract_text_from_message(m)
        if text:
            last = text
            break

    return _StateShim(last_assistant_message=last, history=messages)


class ClaudeAgentRunner:
    """Drives Claude Code SDK to fix one issue."""

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-7",
        max_turns: int = 80,
        _run_claude: Callable[..., Any] | None = None,
        _git_diff: Callable[[Path], str] | None = None,
    ) -> None:
        self._model = model
        self._max_turns = max_turns
        self._is_real_claude = _run_claude is None
        self._run_claude: Callable[..., Any] = cast(
            Callable[..., Any], _run_claude or _real_run_claude
        )
        self._git_diff = _git_diff or _real_git_diff

    def _build_prompt(self, issue: Issue) -> str:
        return _PROMPT_TEMPLATE.format(
            repo=issue.ref.repo,
            number=issue.ref.number,
            title=issue.title,
            body=issue.body,
        )

    def run(self, *, issue: Issue, workspace: Path) -> FixResult:
        prompt = self._build_prompt(issue)

        try:
            if self._is_real_claude:
                state = self._run_claude(
                    workspace=workspace,
                    prompt=prompt,
                    model=self._model,
                    max_turns=self._max_turns,
                )
            else:
                state = self._run_claude(
                    workspace=workspace,
                    prompt=prompt,
                    model=self._model,
                    max_turns=self._max_turns,
                )
        except Exception as exc:
            return FixResult(
                success=False,
                ref=issue.ref,
                workspace=workspace,
                reason=f"claude agent error: {exc}",
            )

        last_msg = getattr(state, "last_assistant_message", "") or ""
        history = list(getattr(state, "history", []))

        gave_up_reason = extract_gave_up_marker(last_msg)
        if gave_up_reason is not None:
            return FixResult(
                success=False,
                ref=issue.ref,
                workspace=workspace,
                reason=gave_up_reason,
                gave_up=True,
                trajectory_excerpt=extract_trajectory_excerpt(history),
            )

        diff = self._git_diff(workspace)
        if not diff.strip():
            return FixResult(
                success=False,
                ref=issue.ref,
                workspace=workspace,
                reason="no changes produced",
                trajectory_excerpt=extract_trajectory_excerpt(history),
            )

        summary = extract_summary_marker(last_msg) or f"fix issue #{issue.ref.number}"
        return FixResult(
            success=True,
            ref=issue.ref,
            workspace=workspace,
            diff=diff,
            summary=summary,
            trajectory_excerpt=extract_trajectory_excerpt(history),
        )
