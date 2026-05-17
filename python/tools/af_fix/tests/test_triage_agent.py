# Copyright (c) Microsoft. All rights reserved.

import asyncio
from unittest.mock import MagicMock

from af_fix.models import Issue, IssueRef, ScoreResult
from af_fix.triage_agent import TriageAgent, score_one


def _issue(n: int, title: str = "t", body: str = "b") -> Issue:
    return Issue(ref=IssueRef(repo="o/r", number=n), title=title, body=body)


class FakeAgent:
    def __init__(self, scripted: tuple[str, dict] | Exception) -> None:
        self.scripted = scripted
        self.tools: list = []

    async def run(self, prompt: str) -> str:
        if isinstance(self.scripted, Exception):
            raise self.scripted
        name, kwargs = self.scripted
        # agent_framework @tool returns FunctionTool with .name attribute (not __name__)
        tool = next(t for t in self.tools if getattr(t, "name", getattr(t, "__name__", None)) == name)
        result = tool(**kwargs)
        if asyncio.iscoroutine(result):
            await result
        return "done"


def test_score_one_records_clamped_score() -> None:
    fake = FakeAgent(scripted=("submit_score", {"score": 99, "reason": "lol", "suggested_files": []}))

    def factory(client, tools, instructions):
        fake.tools = tools
        return fake

    result = score_one(_issue(1), client=MagicMock(), _agent_factory=factory)
    assert result.score == 10
    assert result.reason == "lol"
    assert result.ref.number == 1


def test_score_one_handles_no_submit() -> None:
    # FakeAgent that does nothing
    class _NoopAgent:
        def __init__(self) -> None:
            self.tools: list = []

        async def run(self, prompt: str) -> str:
            return "noop"

    noop = _NoopAgent()

    def factory(client, tools, instructions):
        noop.tools = tools
        return noop

    result = score_one(_issue(1), client=MagicMock(), _agent_factory=factory)
    assert result.score == 0
    assert "no score returned" in (result.reason or "")


def test_score_one_handles_exception() -> None:
    fake = FakeAgent(scripted=RuntimeError("boom"))

    def factory(client, tools, instructions):
        fake.tools = tools
        return fake

    result = score_one(_issue(1), client=MagicMock(), _agent_factory=factory)
    assert result.score == 0
    assert "boom" in (result.reason or "")


def test_triage_agent_scores_multiple() -> None:
    issues = [_issue(1), _issue(2), _issue(3)]

    def score_fn(issue: Issue) -> ScoreResult:
        return ScoreResult(ref=issue.ref, score=issue.ref.number * 3, reason=f"r{issue.ref.number}")

    agent = TriageAgent(client=MagicMock(), _score_one=score_fn)
    results = agent.score_all(issues)
    by_id = {r.ref.number: r for r in results}
    assert by_id[1].score == 3
    assert by_id[2].score == 6
    assert by_id[3].score == 9
