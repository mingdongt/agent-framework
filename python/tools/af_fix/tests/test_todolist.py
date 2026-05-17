# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from pathlib import Path

from af_fix.models import Issue, IssueRef, ScoreResult
from af_fix.todolist import (
    TodoList,
    load_todolist_json,
    parse_checked_items,
    render_markdown,
    save_todolist,
)


def _make_scores() -> list[ScoreResult]:
    return [
        ScoreResult(
            ref=IssueRef(repo="microsoft/agent-framework", number=5887),
            score=9,
            reason="clear stack trace",
            suggested_files=["packages/core/foo.py"],
        ),
        ScoreResult(
            ref=IssueRef(repo="vllm-project/vllm", number=42723),
            score=7,
            reason="single-file fix",
            suggested_files=["vllm/v1/ubatch.py"],
        ),
        ScoreResult(
            ref=IssueRef(repo="AstrBotDevs/AstrBot", number=8195),
            score=3,
            reason="vague",
            suggested_files=[],
        ),
    ]


def _make_issues() -> dict[str, Issue]:
    return {
        "microsoft/agent-framework#5887": Issue(
            ref=IssueRef(repo="microsoft/agent-framework", number=5887),
            title="title 5887", body="body 5887",
        ),
        "vllm-project/vllm#42723": Issue(
            ref=IssueRef(repo="vllm-project/vllm", number=42723),
            title="title vllm", body="body vllm",
        ),
        "AstrBotDevs/AstrBot#8195": Issue(
            ref=IssueRef(repo="AstrBotDevs/AstrBot", number=8195),
            title="title astrbot", body="body astrbot",
        ),
    }


def test_render_markdown_orders_by_score_desc() -> None:
    scores = _make_scores()
    issues = _make_issues()
    when = datetime(2026, 5, 18, 10, 30, 0, tzinfo=timezone.utc)
    md = render_markdown(scores=scores, issues_by_key=issues, generated_at=when)

    # First listed should be the highest-score issue
    idx_5887 = md.find("microsoft/agent-framework#5887")
    idx_vllm = md.find("vllm-project/vllm#42723")
    idx_astrbot = md.find("AstrBotDevs/AstrBot#8195")
    assert idx_5887 < idx_vllm < idx_astrbot


def test_render_markdown_contains_required_sections() -> None:
    scores = _make_scores()
    issues = _make_issues()
    when = datetime(2026, 5, 18, 10, 30, 0, tzinfo=timezone.utc)
    md = render_markdown(scores=scores, issues_by_key=issues, generated_at=when)

    assert "2026-05-18T10:30:00" in md
    assert "af-fix execute --from" in md
    assert "[ ] microsoft/agent-framework#5887 (score: 9)" in md
    assert "clear stack trace" in md
    assert "Suggested files: packages/core/foo.py" in md
    assert "https://github.com/microsoft/agent-framework/issues/5887" in md


def test_save_todolist_writes_both_files(tmp_path: Path) -> None:
    scores = _make_scores()
    issues = _make_issues()
    when = datetime(2026, 5, 18, 10, 30, 0, tzinfo=timezone.utc)
    md_path, json_path = save_todolist(
        scores=scores,
        issues_by_key=issues,
        generated_at=when,
        out_dir=tmp_path,
    )
    assert md_path.exists()
    assert json_path.exists()
    assert md_path.suffix == ".md"
    assert json_path.suffix == ".json"
    assert md_path.stem == json_path.stem


def test_parse_checked_items_returns_only_checked(tmp_path: Path) -> None:
    md = """# triage results

- [x] microsoft/agent-framework#5887 (score: 9) — checked one
- [ ] vllm-project/vllm#42723 (score: 7) — unchecked
- [X] AstrBotDevs/AstrBot#8195 (score: 3) — capital X also counts
"""
    items = parse_checked_items(md)
    keys = [(i.repo, i.number) for i in items]
    assert ("microsoft/agent-framework", 5887) in keys
    assert ("AstrBotDevs/AstrBot", 8195) in keys
    assert ("vllm-project/vllm", 42723) not in keys


def test_load_todolist_json_round_trips(tmp_path: Path) -> None:
    scores = _make_scores()
    issues = _make_issues()
    when = datetime(2026, 5, 18, 10, 30, 0, tzinfo=timezone.utc)
    _md_path, json_path = save_todolist(
        scores=scores,
        issues_by_key=issues,
        generated_at=when,
        out_dir=tmp_path,
    )
    todolist = load_todolist_json(json_path)
    assert isinstance(todolist, TodoList)
    assert len(todolist.items) == 3
    keys = [(i.repo, i.number) for i in todolist.items]
    assert ("microsoft/agent-framework", 5887) in keys


def test_parse_checked_items_ignores_malformed_lines() -> None:
    md = """
- [x] valid/repo#42 (score: 9) — ok
- [ ] valid/repo#43 (score: 7) — unchecked
- [x] not a real item line
- random text
- [x] another/repo#100 (score: 8) — ok
"""
    items = parse_checked_items(md)
    keys = [(i.repo, i.number) for i in items]
    assert ("valid/repo", 42) in keys
    assert ("another/repo", 100) in keys
    assert len(items) == 2
