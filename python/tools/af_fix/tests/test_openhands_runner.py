# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path
from unittest.mock import MagicMock

from af_fix.models import Issue, IssueRef
from af_fix.openhands_runner import (
    OpenHandsRunner,
    extract_gave_up_marker,
    extract_summary_marker,
    extract_trajectory_excerpt,
)


def _issue() -> Issue:
    return Issue(ref=IssueRef(repo="o/r", number=42), title="bug", body="something broken")


def test_extract_summary_present() -> None:
    text = "I made the change.\nSUMMARY: fix off-by-one in slicer\nDone."
    assert extract_summary_marker(text) == "fix off-by-one in slicer"


def test_extract_summary_absent() -> None:
    assert extract_summary_marker("no marker here") is None


def test_extract_gave_up_present() -> None:
    text = "Looked at the issue.\nGAVE_UP: cannot reproduce without internet access\n"
    reason = extract_gave_up_marker(text)
    assert reason == "cannot reproduce without internet access"


def test_extract_gave_up_absent() -> None:
    assert extract_gave_up_marker("none") is None


def test_extract_trajectory_excerpt_truncates() -> None:
    events = [f"step {i}" for i in range(500)]
    excerpt = extract_trajectory_excerpt(events, last_n=30)
    lines = excerpt.split("\n")
    assert len(lines) == 30
    assert lines[-1] == "step 499"


def test_runner_returns_gave_up_when_marker_present(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_state = MagicMock()
    fake_state.last_assistant_message = "GAVE_UP: cannot reproduce"
    fake_state.history = []

    def fake_run_controller(**kwargs: object) -> object:
        return fake_state

    runner = OpenHandsRunner(
        anthropic_api_key="k",
        model="claude-opus-4-7",
        max_iterations=80,
        _run_controller=fake_run_controller,
        _git_diff=lambda ws: "",
    )
    result = runner.run(issue=_issue(), workspace=workspace)
    assert result.success is False
    assert result.gave_up is True
    assert "cannot reproduce" in (result.reason or "")


def test_runner_returns_success_when_diff_nonempty(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_state = MagicMock()
    fake_state.last_assistant_message = "Done.\nSUMMARY: fix the thing"
    fake_state.history = ["event1", "event2"]

    runner = OpenHandsRunner(
        anthropic_api_key="k",
        model="claude-opus-4-7",
        max_iterations=80,
        _run_controller=lambda **kw: fake_state,
        _git_diff=lambda ws: "diff --git a/foo b/foo\n+x",
    )
    result = runner.run(issue=_issue(), workspace=workspace)
    assert result.success is True
    assert result.summary == "fix the thing"
    assert "diff --git" in result.diff


def test_runner_returns_failure_when_diff_empty_and_no_gave_up(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    fake_state = MagicMock()
    fake_state.last_assistant_message = "I looked but did nothing."
    fake_state.history = []

    runner = OpenHandsRunner(
        anthropic_api_key="k",
        model="claude-opus-4-7",
        max_iterations=80,
        _run_controller=lambda **kw: fake_state,
        _git_diff=lambda ws: "",
    )
    result = runner.run(issue=_issue(), workspace=workspace)
    assert result.success is False
    assert result.gave_up is False
    assert "no changes" in (result.reason or "").lower()


def test_runner_returns_failure_when_run_controller_raises(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    def bad(**kw: object) -> object:
        raise RuntimeError("docker daemon down")

    runner = OpenHandsRunner(
        anthropic_api_key="k",
        model="claude-opus-4-7",
        max_iterations=80,
        _run_controller=bad,
        _git_diff=lambda ws: "",
    )
    result = runner.run(issue=_issue(), workspace=workspace)
    assert result.success is False
    assert "docker daemon down" in (result.reason or "")
