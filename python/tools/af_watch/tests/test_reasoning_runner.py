# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from typing import Any

import pytest

from af_watch.corpus_loader import CorpusSnapshot
from af_watch.models import CodeRegion, Hypothesis, Opportunity, OpportunityType
from af_watch.reasoning.runner import ReasoningRunner


class _StubQR:
    def __init__(self, opp: Opportunity) -> None:
        self.opp = opp
        self.calls = 0

    async def run(self, question_path: Path, *, snapshot: Any, home_repo: str) -> list[Opportunity]:
        self.calls += 1
        return [self.opp]


class _StubPR:
    def __init__(self, hypothesis: Hypothesis) -> None:
        self.hypothesis = hypothesis
        self.calls = 0

    async def run(self, persona_path: Path, *, region: CodeRegion, code: str) -> list[Hypothesis]:
        self.calls += 1
        return [self.hypothesis]


def _snapshot() -> CorpusSnapshot:
    return CorpusSnapshot(domain_maps={}, comparison_matrix={}, industry_intel={})


def _opp() -> Opportunity:
    return Opportunity(
        id="x", type=OpportunityType.FEATURE_PARITY,
        target="t", action="a", evidence="e",
        effort="2h", risk="low", risk_rationale="x", rationale="r", tier=4,
    )


def _hyp(region_id: str) -> Hypothesis:
    return Hypothesis(
        region_id=region_id,
        repo="a/a",
        file="x.py",
        persona="p",
        invariant="i", violation_condition="v",
        repro_sketch="s", severity="low", confidence=0.5,
    )


@pytest.mark.asyncio
async def test_runs_all_questions_and_personas(tmp_path: Path) -> None:
    qdir = tmp_path / "questions"
    qdir.mkdir()
    pdir = tmp_path / "personas"
    pdir.mkdir()
    for n in ["a", "b"]:
        (qdir / f"{n}.md").write_text("## System prompt\nx\n", encoding="utf-8")
    for n in ["x", "y"]:
        (pdir / f"{n}.md").write_text("p\n", encoding="utf-8")

    qr = _StubQR(_opp())
    pr = _StubPR(_hyp("r-1"))
    regions = [
        CodeRegion(id="r-1", repo="a/a", file="x.py", line_start=1, line_end=10,
                   selection_reason="x", recent_change_context="x"),
    ]

    def fake_read(repo: str, file: str) -> str:
        return "// fake source"

    runner = ReasoningRunner(
        question_runner=qr,
        persona_runner=pr,
        questions_dir=qdir,
        personas_dir=pdir,
        code_reader=fake_read,
    )
    opps, hyps = await runner.run(
        snapshot=_snapshot(),
        home_repo="a/a",
        regions=regions,
    )

    assert qr.calls == 2   # both questions
    assert pr.calls == 2   # both personas (one region x two personas)
    assert len(opps) == 2  # one opp per question
    assert len(hyps) == 2  # one hypothesis per (region x persona)


@pytest.mark.asyncio
async def test_errors_in_one_question_dont_kill_run(tmp_path: Path) -> None:
    qdir = tmp_path / "questions"
    qdir.mkdir()
    pdir = tmp_path / "personas"
    pdir.mkdir()
    (qdir / "good.md").write_text("## System prompt\nx\n", encoding="utf-8")
    (qdir / "bad.md").write_text("## System prompt\nx\n", encoding="utf-8")

    class FlakyQR:
        async def run(self, question_path: Path, *, snapshot: Any, home_repo: str) -> list[Opportunity]:
            if question_path.stem == "bad":
                raise RuntimeError("boom")
            return [_opp()]

    runner = ReasoningRunner(
        question_runner=FlakyQR(),
        persona_runner=_StubPR(_hyp("r-1")),
        questions_dir=qdir,
        personas_dir=pdir,
        code_reader=lambda repo, file: "x",
    )
    opps, _ = await runner.run(snapshot=_snapshot(), home_repo="a/a", regions=[])
    assert len(opps) == 1
