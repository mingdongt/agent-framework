# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from pathlib import Path

from af_fix.models import AttemptOutcome, IssueRef
from af_fix.state import State


def _now() -> datetime:
    return datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)


def test_empty_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = State.load(path)
    assert state.attempts == {}
    state.save()
    reloaded = State.load(path)
    assert reloaded.attempts == {}


def test_state_with_entry_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = State.load(path)
    ref = IssueRef(repo="microsoft/agent-framework", number=5887)
    state.record_attempt(
        ref,
        outcome=AttemptOutcome.PR_OPENED,
        branch="af-fix/issue-5887-foo",
        now=_now(),
        pr_url="https://github.com/microsoft/agent-framework/pull/5888",
    )
    state.save()
    reloaded = State.load(path)
    assert ref.key in reloaded.attempts
    assert reloaded.attempts[ref.key].outcome == AttemptOutcome.PR_OPENED


def test_should_skip_default(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    ref1 = IssueRef(repo="o/r", number=1)
    ref2 = IssueRef(repo="o/r", number=2)
    state.record_attempt(ref1, outcome=AttemptOutcome.PR_OPENED, branch="b1", now=_now())
    state.record_attempt(ref2, outcome=AttemptOutcome.GAVE_UP, branch=None, now=_now())
    assert state.should_skip(ref1) is True
    assert state.should_skip(ref2) is True
    assert state.should_skip(IssueRef(repo="o/r", number=99)) is False


def test_should_skip_with_retry_failed(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    ref_pr = IssueRef(repo="o/r", number=1)
    ref_gave = IssueRef(repo="o/r", number=2)
    ref_err = IssueRef(repo="o/r", number=3)
    state.record_attempt(ref_pr, outcome=AttemptOutcome.PR_OPENED, branch="b", now=_now())
    state.record_attempt(ref_gave, outcome=AttemptOutcome.GAVE_UP, branch=None, now=_now())
    state.record_attempt(ref_err, outcome=AttemptOutcome.ERROR, branch=None, now=_now())
    assert state.should_skip(ref_pr, retry_failed=True) is True
    assert state.should_skip(ref_gave, retry_failed=True) is False
    assert state.should_skip(ref_err, retry_failed=True) is False


def test_record_attempt_increments_count(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    ref = IssueRef(repo="o/r", number=42)
    state.record_attempt(ref, outcome=AttemptOutcome.ERROR, branch=None, now=_now())
    state.record_attempt(ref, outcome=AttemptOutcome.PR_OPENED, branch="b", now=_now())
    assert state.attempts[ref.key].attempt_count == 2
    assert state.attempts[ref.key].outcome == AttemptOutcome.PR_OPENED


def test_issue_ref_key_format() -> None:
    ref = IssueRef(repo="microsoft/agent-framework", number=5887)
    assert ref.key == "microsoft/agent-framework#5887"
