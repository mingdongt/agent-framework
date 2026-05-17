# Copyright (c) Microsoft. All rights reserved.

import contextlib
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, cast

from af_fix.exceptions import OpenHandsError
from af_fix.models import FixResult, Issue

_PROMPT_TEMPLATE = """\
You are fixing an issue in an open-source repository.

Repository: {repo}
Issue #{number}: {title}

Issue body:
{body}

The repository is already checked out at /workspace. The default branch is checked out.

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
    """Thin adapter wrapping openhands-sdk Conversation into the contract our code expects."""

    def __init__(self, last_assistant_message: str, history: list[Any]) -> None:
        self.last_assistant_message = last_assistant_message
        self.history = history


def _real_run_controller(
    *,
    workspace: "Path",
    prompt: str,
    model: str,
    api_key: str,
    max_iterations: int,
    openhands_image: str,
) -> "_StateShim":
    """Drive openhands-sdk 1.19.x (LocalConversation) synchronously.

    openhands-sdk 1.19 API:
      - LLM(model=..., api_key=...) — pydantic model; api_key accepts SecretStr or plain str
      - Agent(llm=...) — pydantic model, default tools include TerminalTool / FileEditorTool
      - Conversation(agent, workspace=str|Path) — factory → LocalConversation
      - conversation.send_message(prompt) then conversation.run()
      - Events live in conversation.state.events (EventLog, indexable)
    """
    # TODO: openhands-sdk LocalConversation runs agent code in-process (same host).
    #       For true Docker isolation, switch to RemoteWorkspace pointed at a Docker-hosted
    #       openhands agent server (openhands_agent_server package).  The `openhands_image`
    #       parameter is intentionally accepted here for forward-compatibility but not yet used.
    try:
        from openhands.sdk import LLM, Agent
        from openhands.sdk.conversation.impl.local_conversation import LocalConversation
        from openhands.sdk.event import MessageEvent
        from pydantic import SecretStr
    except ImportError as exc:
        raise OpenHandsError(f"openhands-sdk not installed or incompatible: {exc}") from exc

    llm = LLM(model=model, api_key=SecretStr(api_key))
    agent = Agent(llm=llm)

    conversation = LocalConversation(agent, workspace=str(workspace), max_iteration_per_run=max_iterations)
    try:
        conversation.send_message(prompt)  # type: ignore[arg-type]
        conversation.run()

        # Extract all events for the history list
        events = conversation.state.events
        history: list[Any] = list(events)

        # Find the last agent MessageEvent
        last_msg = ""
        for event in reversed(history):
            if isinstance(event, MessageEvent) and event.source == "agent":
                parts = event.llm_message.content
                texts = []
                for part in parts:
                    text = getattr(part, "text", None)
                    if text:
                        texts.append(text)
                last_msg = "\n".join(texts)
                break

        return _StateShim(last_assistant_message=last_msg, history=history)
    finally:
        with contextlib.suppress(Exception):
            conversation.close()


class OpenHandsRunner:
    """Drives OpenHands inside a Docker container to fix one issue."""

    def __init__(
        self,
        *,
        anthropic_api_key: str,
        model: str = "claude-opus-4-7",
        max_iterations: int = 80,
        openhands_image: str = "ghcr.io/all-hands-ai/runtime:0.20",
        _run_controller: Callable[..., Any] | None = None,
        _git_diff: Callable[[Path], str] | None = None,
    ) -> None:
        self._api_key = anthropic_api_key
        self._model = model
        self._max_iterations = max_iterations
        self._image = openhands_image
        self._is_real_controller = _run_controller is None
        self._run_controller: Callable[..., Any] = cast(
            Callable[..., Any], _run_controller or _real_run_controller
        )
        self._git_diff = _git_diff or _real_git_diff

    def _build_real_kwargs(self, workspace: Path) -> dict[str, Any]:
        """Build keyword arguments for _real_run_controller."""
        return {
            "workspace": workspace,
            "model": self._model,
            "api_key": self._api_key,
            "max_iterations": self._max_iterations,
            "openhands_image": self._image,
        }

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
            if self._is_real_controller:
                kwargs = self._build_real_kwargs(workspace)
                kwargs["prompt"] = prompt
                state = self._run_controller(**kwargs)
            else:
                state = self._run_controller(
                    workspace=workspace,
                    prompt=prompt,
                    model=self._model,
                    max_iterations=self._max_iterations,
                )
        except Exception as exc:
            return FixResult(
                success=False,
                ref=issue.ref,
                workspace=workspace,
                reason=f"openhands error: {exc}",
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
