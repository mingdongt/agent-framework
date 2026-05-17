# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

from af_watch.models import Opportunity, OpportunityType
from af_watch.reproducer import Reproducer


def _opp() -> Opportunity:
    return Opportunity(
        id="x", type=OpportunityType.BUG_FIX,
        target="microsoft/agent-framework:python/x.py:L10",
        action="PR", evidence="e", effort="30min",
        risk="low", risk_rationale="r", rationale="r", tier=2,
    )


def test_skips_when_workspace_missing(tmp_path: Path) -> None:
    repro = Reproducer(workspace_base=tmp_path / "missing", home_repo="microsoft/agent-framework")
    out = repro.attempt(_opp(), repro_script="print('hi')")
    assert out.repro_status == "not_attempted"


def test_marks_confirmed_when_script_exits_nonzero(tmp_path: Path) -> None:
    workspace = tmp_path / "microsoft__agent-framework"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("placeholder", encoding="utf-8")

    script = "import sys; sys.exit(1)"
    repro = Reproducer(
        workspace_base=tmp_path,
        home_repo="microsoft/agent-framework",
        runner=lambda cmd, cwd, timeout: (1, "", ""),
    )
    out = repro.attempt(_opp(), repro_script=script)
    assert out.repro_status == "confirmed"
    assert out.repro_artifact is not None


def test_marks_failed_when_script_exits_zero(tmp_path: Path) -> None:
    workspace = tmp_path / "microsoft__agent-framework"
    workspace.mkdir(parents=True)
    repro = Reproducer(
        workspace_base=tmp_path,
        home_repo="microsoft/agent-framework",
        runner=lambda cmd, cwd, timeout: (0, "ok", ""),
    )
    out = repro.attempt(_opp(), repro_script="x")
    assert out.repro_status == "attempted_failed"


def test_non_home_repo_not_attempted(tmp_path: Path) -> None:
    workspace = tmp_path / "google__adk-python"
    workspace.mkdir(parents=True)
    repro = Reproducer(workspace_base=tmp_path, home_repo="microsoft/agent-framework")
    other = _opp()
    other.target = "google/adk-python:src/x.py"
    out = repro.attempt(other, repro_script="x")
    assert out.repro_status == "not_attempted"


def test_timeout_marked(tmp_path: Path) -> None:
    workspace = tmp_path / "microsoft__agent-framework"
    workspace.mkdir(parents=True)

    def fake(cmd, cwd, timeout):
        raise TimeoutError("too slow")

    repro = Reproducer(
        workspace_base=tmp_path,
        home_repo="microsoft/agent-framework",
        runner=fake,
    )
    out = repro.attempt(_opp(), repro_script="x")
    assert out.repro_status == "attempted_timeout"
