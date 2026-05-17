from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic


MODEL = "claude-opus-4-7"
MAX_TOKENS_DEFAULT = 4096


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
        return json.loads(fenced.group(1))
    bare = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(1))
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
    ) -> LLMResponse:
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
        return LLMResponse(
            text="".join(text_parts),
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
        )
