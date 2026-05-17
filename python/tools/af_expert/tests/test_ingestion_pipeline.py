from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.ingestion.pipeline import IngestionResult, run_ingestion_tick


def test_run_tick_advances_cursor_on_success(tmp_state_dir: Path) -> None:
    cfg = MagicMock()
    repo_cfg = MagicMock(owner_repo="microsoft/agent-framework")
    cfg.repos = [repo_cfg]

    gh = MagicMock()
    gh.list_issues_updated_since.return_value = iter([])
    gh.list_pulls_merged_since.return_value = iter([])
    gh.list_releases_since.return_value = iter([])

    store = MagicMock()

    state: dict[str, object] = {"version": 1, "cursors": {}, "stats": {}}

    def loader() -> dict[str, object]:
        return state

    saved: list[dict[str, object]] = []

    def saver(new_state: dict[str, object]) -> None:
        saved.append(new_state)
        state.update(new_state)

    result = run_ingestion_tick(
        cfg, gh, store, now=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        load_state=loader, save_state=saver,
    )

    assert isinstance(result, IngestionResult)
    assert "microsoft/agent-framework" in saved[-1]["cursors"]


def test_run_tick_isolates_per_repo_failure(tmp_state_dir: Path) -> None:
    cfg = MagicMock()
    cfg.repos = [
        MagicMock(owner_repo="microsoft/agent-framework"),
        MagicMock(owner_repo="failing/repo"),
        MagicMock(owner_repo="another/repo"),
    ]

    gh = MagicMock()

    def issues_side_effect(repo: str, since: datetime) -> object:
        if repo == "failing/repo":
            raise RuntimeError("simulated GitHub error")
        return iter([])

    gh.list_issues_updated_since.side_effect = issues_side_effect
    gh.list_pulls_merged_since.return_value = iter([])
    gh.list_releases_since.return_value = iter([])

    store = MagicMock()
    state: dict[str, object] = {"version": 1, "cursors": {}, "stats": {}}

    result = run_ingestion_tick(
        cfg, gh, store,
        now=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        load_state=lambda: state,
        save_state=lambda s: state.update(s),
    )

    assert result.repos_succeeded == 2
    assert result.repos_failed == 1
    assert "failing/repo" in result.failed_repos
    # Cursors still advanced for successful repos
    assert "microsoft/agent-framework" in state["cursors"]
    assert "another/repo" in state["cursors"]
    # Failed repo's cursor NOT advanced
    assert "failing/repo" not in state["cursors"]


def test_run_tick_uses_existing_cursor() -> None:
    cfg = MagicMock()
    cfg.repos = [MagicMock(owner_repo="microsoft/agent-framework")]

    gh = MagicMock()
    gh.list_issues_updated_since.return_value = iter([])
    gh.list_pulls_merged_since.return_value = iter([])
    gh.list_releases_since.return_value = iter([])

    store = MagicMock()
    existing = "2026-05-15T00:00:00+00:00"
    state: dict[str, object] = {"version": 1, "cursors": {"microsoft/agent-framework": existing}, "stats": {}}

    run_ingestion_tick(
        cfg, gh, store,
        now=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        load_state=lambda: state,
        save_state=lambda s: state.update(s),
    )

    # Verify the fetchers were called with the cursor time, not now
    args, _ = gh.list_pulls_merged_since.call_args
    assert args[0] == "microsoft/agent-framework"
    assert args[1] == datetime.fromisoformat(existing)
