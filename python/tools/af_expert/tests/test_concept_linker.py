from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.architecture.scanner import FileInventory
from af_expert.concept.linker import (
    build_linker_prompt,
    link_concept_to_repo,
)
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.llm import LLM, LLMResponse


def _make_inv(tmp_path: Path) -> FileInventory:
    inv = FileInventory(repo_root=tmp_path / "fake")
    inv.source_files = [
        "src/agent_framework/_mcp.py",
        "src/agent_framework/_anthropic.py",
    ]
    inv.provider_files = {"anthropic": ["src/agent_framework/_anthropic.py"]}
    return inv


def test_linker_prompt_includes_concept_and_files(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)
    prompt = build_linker_prompt(repo="microsoft/agent-framework", concept=c, inventory=inv)
    assert "mcp.oauth.refresh" in prompt
    assert "RFC 8707" in prompt
    assert "_mcp.py" in prompt


def test_link_returns_impl_when_llm_finds_match(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text=(
            '```json\n'
            '{"matches": true, "files": ["src/agent_framework/_mcp.py"], '
            '"functions": ["_refresh_token"], "confidence": 0.85}\n'
            '```'
        ),
        input_tokens=200, output_tokens=40, cache_read_tokens=0, cache_creation_tokens=0,
    )

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is not None
    assert impl.repo == "microsoft/agent-framework"
    assert "src/agent_framework/_mcp.py" in impl.files
    assert "_refresh_token" in impl.functions


def test_link_returns_none_when_no_match(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"matches": false, "files": [], "functions": [], "confidence": 0.1}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is None


def test_link_returns_none_on_llm_error(tmp_path: Path) -> None:
    c = Concept(id="x.y", description="...", spec_ref="")
    inv = _make_inv(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = RuntimeError("LLM down")

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is None
