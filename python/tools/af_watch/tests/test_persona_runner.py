# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from typing import Any

import pytest

from af_watch.models import CodeRegion, Hypothesis
from af_watch.reasoning.persona_runner import PersonaRunner


class _StubLLM:
    def __init__(self, response: Any) -> None:
        self.response = response

    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any:
        return self.response


def _persona(tmp_path: Path, name: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(f"# {name}\n\n## Who I am\nA security person.\n", encoding="utf-8")
    return p


def _region() -> CodeRegion:
    return CodeRegion(
        id="r-1",
        repo="microsoft/agent-framework",
        file="python/mcp_http.py",
        line_start=1,
        line_end=300,
        selection_reason="changed",
        recent_change_context="MCP",
    )


@pytest.mark.asyncio
async def test_returns_hypotheses_for_region(tmp_path: Path) -> None:
    p = _persona(tmp_path, "security_boundary")
    llm = _StubLLM([
        {
            "invariant": "auth headers stripped on cross-origin redirect",
            "violation_condition": "MCP 307 to different origin",
            "repro_sketch": "mock MCP, sniff",
            "severity": "high",
            "confidence": 0.85,
        }
    ])
    runner = PersonaRunner(llm=llm)
    out = await runner.run(p, region=_region(), code="// fake source")
    assert len(out) == 1
    assert isinstance(out[0], Hypothesis)
    assert out[0].persona == "security_boundary"
    assert out[0].confidence == 0.85
    assert out[0].repo == "microsoft/agent-framework"
    assert out[0].file == "python/mcp_http.py"


@pytest.mark.asyncio
async def test_skips_malformed_hypotheses(tmp_path: Path) -> None:
    p = _persona(tmp_path, "x")
    llm = _StubLLM([
        {"invariant": "x"},
        {
            "invariant": "y",
            "violation_condition": "z",
            "repro_sketch": "w",
            "severity": "low",
            "confidence": 0.5,
        },
    ])
    runner = PersonaRunner(llm=llm)
    out = await runner.run(p, region=_region(), code="x")
    assert len(out) == 1
    assert out[0].invariant == "y"


@pytest.mark.asyncio
async def test_accepts_list_or_dict_with_hypotheses_key(tmp_path: Path) -> None:
    p = _persona(tmp_path, "x")
    llm = _StubLLM({
        "hypotheses": [
            {
                "invariant": "a", "violation_condition": "b",
                "repro_sketch": "c", "severity": "low", "confidence": 0.3,
            }
        ]
    })
    runner = PersonaRunner(llm=llm)
    out = await runner.run(p, region=_region(), code="x")
    assert len(out) == 1
