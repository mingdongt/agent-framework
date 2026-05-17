from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.query.ask import answer


def _make_candidate(cid: str = "c-1") -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible orphan signature",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only blocks",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )


def test_answer_calls_llm_with_question_and_context(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    candidates.append(_make_candidate())

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text="The state of MCP support is fragmented across frameworks.",
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )

    response = answer(question="state of MCP support?", events=events, candidates=candidates, llm=llm)

    assert "MCP" in response
    call = llm.complete.call_args
    assert "state of MCP support" in call.kwargs["user"]
