from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.architecture.briefing import (
    build_briefing_prompt,
    render_briefing,
)
from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM, LLMResponse


def _make_inventory(tmp_path: Path) -> FileInventory:
    inv = FileInventory(repo_root=tmp_path / "fake-agent")
    inv.source_files = ["src/fake_agent/chat_client.py", "src/fake_agent/_anthropic.py"]
    inv.test_files = ["tests/test_chat.py"]
    inv.provider_files = {"anthropic": ["src/fake_agent/_anthropic.py"]}
    inv.readme_excerpt = "# Fake Agent\n\nMinimal LLM agent framework."
    inv.pyproject_present = True
    return inv


def test_build_prompt_includes_inventory_data(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    prompt = build_briefing_prompt(repo="example/fake-agent", inventory=inv)
    assert "example/fake-agent" in prompt
    assert "chat_client.py" in prompt
    assert "_anthropic.py" in prompt
    assert "Fake Agent" in prompt


def test_render_briefing_returns_markdown(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text=(
            "## Purpose\nA minimal agent framework.\n\n"
            "## Top-level components\n- chat_client.py: provider-agnostic interface\n"
            "## Provider integrations\n- Anthropic: _anthropic.py\n"
        ),
        input_tokens=200, output_tokens=80, cache_read_tokens=0, cache_creation_tokens=0,
    )

    md = render_briefing(repo="example/fake-agent", inventory=inv, llm=llm)
    assert "# example/fake-agent" in md
    assert "A minimal agent framework" in md
    assert "Briefing generated" in md or "last-refreshed" in md.lower()

    call = llm.complete.call_args
    assert call.kwargs.get("caller_label", "").startswith("architecture.briefing")


def test_render_briefing_handles_llm_failure(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = RuntimeError("LLM down")

    md = render_briefing(repo="example/fake-agent", inventory=inv, llm=llm)
    assert "# example/fake-agent" in md
    assert "could not be generated" in md.lower() or "fallback" in md.lower()
