# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from typing import Any

import pytest

from af_watch.corpus_loader import CorpusSnapshot
from af_watch.models import OpportunityType
from af_watch.reasoning.question_runner import QuestionRunner


class _StubLLM:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any:
        self.last_system = system
        self.last_user = user
        return self.response


def _question_file(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _snapshot() -> CorpusSnapshot:
    return CorpusSnapshot(
        domain_maps={"microsoft/agent-framework": "(home)"},
        comparison_matrix={
            "mcp_x": {
                "description": "X",
                "frameworks": {
                    "microsoft/agent-framework": {"status": "not_implemented"},
                    "google/adk-python": {"status": "implemented"},
                },
            }
        },
        industry_intel={"2026-05": "(empty)"},
    )


@pytest.mark.asyncio
async def test_runs_question_and_parses_opportunities(tmp_path: Path) -> None:
    q = _question_file(tmp_path, "feature_lag", """# feature_lag

## System prompt
You score features.

## Output schema
{"opportunities": [...]}
""")
    llm = _StubLLM({
        "opportunities": [
            {
                "type": "feature-parity",
                "target": "python/mcp.py",
                "action": "PR (add MCP X)",
                "evidence": "matrix mcp_x",
                "effort": "2h",
                "risk": "low",
                "risk_rationale": "additive",
                "rationale": "n-1/n gap",
            }
        ]
    })
    runner = QuestionRunner(llm=llm)
    opps = await runner.run(q, snapshot=_snapshot(), home_repo="microsoft/agent-framework")
    assert len(opps) == 1
    assert opps[0].type is OpportunityType.FEATURE_PARITY
    assert opps[0].target == "python/mcp.py"


@pytest.mark.asyncio
async def test_skips_opportunities_missing_required_slots(tmp_path: Path) -> None:
    q = _question_file(tmp_path, "x", "## System prompt\nx\n## Output schema\nx\n")
    llm = _StubLLM({
        "opportunities": [
            {"type": "feature-parity"},  # missing slots
            {
                "type": "feature-parity",
                "target": "t", "action": "a", "evidence": "e",
                "effort": "30min", "risk": "low",
                "rationale": "r",
            },
        ]
    })
    runner = QuestionRunner(llm=llm)
    opps = await runner.run(q, snapshot=_snapshot(), home_repo="microsoft/agent-framework")
    assert len(opps) == 1


@pytest.mark.asyncio
async def test_unknown_type_skipped(tmp_path: Path) -> None:
    q = _question_file(tmp_path, "x", "## System prompt\nx\n## Output schema\nx\n")
    llm = _StubLLM({
        "opportunities": [{
            "type": "made-up-type",
            "target": "t", "action": "a", "evidence": "e",
            "effort": "30min", "risk": "low", "rationale": "r",
        }]
    })
    runner = QuestionRunner(llm=llm)
    opps = await runner.run(q, snapshot=_snapshot(), home_repo="microsoft/agent-framework")
    assert opps == []
