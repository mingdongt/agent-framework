# Copyright (c) Microsoft. All rights reserved.

import json

from af_fix.models import Issue, IssueRef, ScoreResult
from af_fix.triage_agent import TriageAgent, score_one


def _issue(n: int, title: str = "t", body: str = "b") -> Issue:
    return Issue(ref=IssueRef(repo="o/r", number=n), title=title, body=body)


def test_score_one_records_clamped_score() -> None:
    """Score 99 is clamped to 10."""
    resp = json.dumps({"score": 99, "reason": "lol", "suggested_files": []})

    result = score_one(_issue(1), _run_claude=lambda prompt: resp)
    assert result.score == 10
    assert result.reason == "lol"
    assert result.ref.number == 1


def test_score_one_handles_no_json() -> None:
    """Response with no JSON → score=0."""
    result = score_one(_issue(1), _run_claude=lambda prompt: "I cannot determine a score.")
    assert result.score == 0
    assert "no score returned" in (result.reason or "")


def test_score_one_handles_malformed_json() -> None:
    """Response with malformed JSON → score=0."""
    result = score_one(_issue(1), _run_claude=lambda prompt: "{not valid json}")
    assert result.score == 0
    assert "no score returned" in (result.reason or "")


def test_score_one_handles_missing_score_key() -> None:
    """JSON without 'score' key → score=0."""
    resp = json.dumps({"reason": "no score here", "suggested_files": []})
    result = score_one(_issue(1), _run_claude=lambda prompt: resp)
    assert result.score == 0
    assert "no score returned" in (result.reason or "")


def test_score_one_handles_exception() -> None:
    """Exception from _run_claude → score=0, reason contains error."""
    def boom(prompt: str) -> str:
        raise RuntimeError("boom")

    result = score_one(_issue(1), _run_claude=boom)
    assert result.score == 0
    assert "boom" in (result.reason or "")


def test_triage_agent_scores_multiple() -> None:
    issues = [_issue(1), _issue(2), _issue(3)]

    def score_fn(issue: Issue) -> ScoreResult:
        return ScoreResult(ref=issue.ref, score=issue.ref.number * 3, reason=f"r{issue.ref.number}")

    agent = TriageAgent(_score_one=score_fn)
    results = agent.score_all(issues)
    by_id = {r.ref.number: r for r in results}
    assert by_id[1].score == 3
    assert by_id[2].score == 6
    assert by_id[3].score == 9


def test_triage_agent_accepts_client_arg() -> None:
    """TriageAgent still accepts client= positional arg for backward compat."""
    agent = TriageAgent(client=None, _score_one=lambda i: ScoreResult(ref=i.ref, score=5, reason="ok"))
    results = agent.score_all([_issue(1)])
    assert results[0].score == 5
