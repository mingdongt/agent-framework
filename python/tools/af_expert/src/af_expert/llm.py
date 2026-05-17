from __future__ import annotations

import json as _json
import logging
import os as _os
import re
from dataclasses import dataclass
from datetime import datetime as _dt
from pathlib import Path as _Path
from typing import Any

from anthropic import Anthropic


MODEL = "claude-opus-4-7"
MAX_TOKENS_DEFAULT = 4096

log = logging.getLogger(__name__)


def _trace_file() -> _Path | None:
    """Return path to today's trace file, or None if disabled."""
    override = _os.environ.get("AF_EXPERT_TRACE_FILE")
    if override:
        return _Path(override)
    if _os.environ.get("AF_EXPERT_TRACE_DISABLED"):
        return None
    # Default: ~/.af-expert/traces/YYYY-MM-DD.jsonl
    base_env = _os.environ.get("AF_EXPERT_STATE_DIR")
    base = _Path(base_env) if base_env else (_Path.home() / ".af-expert")
    trace_dir = base / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    return trace_dir / f"{_dt.utcnow().date().isoformat()}.jsonl"


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    if len(s) <= n:
        return s
    return s[:n] + f"... ({len(s) - n} more chars)"


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


def parse_json_block(text: str) -> Any:
    """Extract JSON from an LLM response.

    Tries fenced ```json ...``` first, then bare object/array.
    Raises ValueError if nothing parseable found.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        return _json.loads(fenced.group(1))
    bare = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if bare:
        return _json.loads(bare.group(1))
    raise ValueError("No JSON found in LLM response")


class LLM:
    def __init__(self, api_key: str, *, _client: Anthropic | None = None) -> None:
        self._client = _client if _client is not None else Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = MAX_TOKENS_DEFAULT,
        model: str = MODEL,
        caller_label: str = "unknown",
    ) -> LLMResponse:
        log.info(
            "LLM call from %s: system=%d chars, user=%d chars",
            caller_label, len(system), len(user)
        )
        log.debug("LLM user prompt preview (%s): %s", caller_label, _truncate(user, 500))

        # Apply cache_control to the system block. Anthropic accepts a list of
        # system blocks; marking ephemeral cache lets us reuse the briefing
        # context across many calls in a tick.
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
        )
        text_parts = [block.text for block in msg.content if hasattr(block, "text")]
        text = "".join(text_parts)

        response = LLMResponse(
            text=text,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
        )

        log.info(
            "LLM response (%s): %d input, %d output, %d cache_read tokens",
            caller_label, response.input_tokens, response.output_tokens, response.cache_read_tokens,
        )
        log.debug("LLM response preview (%s): %s", caller_label, _truncate(text, 500))

        # Trace file write (best-effort, never raises)
        trace_path = _trace_file()
        if trace_path is not None:
            try:
                trace_entry = {
                    "ts": _dt.utcnow().isoformat() + "Z",
                    "caller": caller_label,
                    "model": model,
                    "system_preview": _truncate(system, 200),
                    "user_preview": _truncate(user, 500),
                    "response": text,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "cache_read_tokens": response.cache_read_tokens,
                    "cache_creation_tokens": response.cache_creation_tokens,
                }
                with trace_path.open("a", encoding="utf-8") as f:
                    f.write(_json.dumps(trace_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                log.warning("Failed to write LLM trace: %s", e)

        return response
