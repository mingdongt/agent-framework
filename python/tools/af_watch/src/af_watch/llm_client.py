# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import re
from typing import Any

from af_watch.exceptions import ReasoningError

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


async def _default_runner(argv: list[str], *, stdin_bytes: bytes) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(stdin_bytes)
    return proc.returncode or 0, stdout, stderr


class LLMClient:
    """Drives Claude via the local `claude` CLI in print mode.

    Each call spawns `claude -p --output-format json --system-prompt ... --model ...`
    and pipes the user prompt via stdin. No API key is needed; the CLI uses the
    operator's enterprise auth.
    """

    def __init__(
        self,
        *,
        claude_path: str = "claude",
        model: str = "claude-opus-4-7",
        runner: Any | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self._claude = claude_path
        self._model = model
        self._timeout = timeout_seconds
        self._runner = runner if runner is not None else _default_runner

    async def complete(self, *, system: str, user: str) -> str:
        argv = [
            self._claude,
            "-p",
            "--system-prompt", system,
            "--model", self._model,
            "--output-format", "json",
            "--tools", "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources", "",
        ]
        try:
            returncode, stdout, stderr = await asyncio.wait_for(
                self._runner(argv, stdin_bytes=user.encode("utf-8")),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise ReasoningError(f"claude CLI timeout after {self._timeout}s") from exc

        if returncode != 0:
            raise ReasoningError(
                f"claude CLI failed (rc={returncode}): {stderr.decode('utf-8', 'replace')[:500]}"
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ReasoningError(f"claude CLI emitted non-JSON: {stdout[:200]!r}") from exc

        if payload.get("is_error"):
            raise ReasoningError(f"claude CLI returned error: {payload.get('result', '')}")

        result = payload.get("result")
        if not isinstance(result, str):
            raise ReasoningError(f"claude CLI result missing or non-string: {payload}")
        return result

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_retries: int = 2,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            text = await self.complete(system=system, user=user)
            extracted = self._extract_json(text)
            if extracted is None:
                last_error = ReasoningError(f"no JSON in response (attempt {attempt + 1})")
                user = user + "\n\nReminder: respond with valid JSON only."
                continue
            try:
                return json.loads(extracted)
            except json.JSONDecodeError as exc:
                last_error = exc
                user = user + f"\n\nPrevious response had invalid JSON: {exc}. Respond with valid JSON only."
        raise ReasoningError(f"failed to parse JSON after {max_retries} attempts: {last_error}")

    @staticmethod
    def _extract_json(text: str) -> str | None:
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            return text
        match = _JSON_FENCE.search(text)
        if match:
            return match.group(1)
        start = text.find("{")
        if start == -1:
            start = text.find("[")
        if start == -1:
            return None
        return text[start:]
