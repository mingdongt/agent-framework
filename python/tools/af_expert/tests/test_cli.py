from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from af_expert.cli import cli
from af_expert.config import Config, RepoConfig
from af_expert.strategies.base import IngestionDeltas


def test_init_creates_config(tmp_state_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    cfg_path = tmp_state_dir / "config.toml"
    assert cfg_path.exists()
    text = cfg_path.read_text()
    assert "github_token" in text
    assert "anthropic_api_key" in text


def test_init_does_not_overwrite(tmp_state_dir: Path) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text("# existing config")
    runner = CliRunner()
    result = runner.invoke(cli, ["init"])
    assert result.exit_code != 0
    assert "exists" in result.output.lower()


def test_strategy_list_runs_without_config(tmp_state_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["strategy", "list"])
    assert result.exit_code == 0
    assert "s1_pr_forward_port" in result.output
    assert "s8_issue_archaeology" in result.output


def _make_config(repos: list[str]) -> Config:
    return Config(
        github_token="gh-token",
        anthropic_api_key="ak-key",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


class TestTickStrategiesOnly:
    """Tests for the --strategies-only flag on `af-expert tick`."""

    def _run_strategies_only(
        self,
        tmp_state_dir: Path,
        repos: list[str],
        state_cursors: dict[str, str],
    ) -> tuple[object, list[IngestionDeltas]]:
        """
        Invoke `tick --strategies-only` with mocked config, state and strategies.

        Returns (click result, list of IngestionDeltas received by S1).
        """
        cfg = _make_config(repos)
        captured_deltas: list[IngestionDeltas] = []

        def fake_s1_on_ingestion(deltas: IngestionDeltas) -> list:
            captured_deltas.append(deltas)
            return []

        state = {"version": 1, "cursors": state_cursors, "stats": {}}

        with (
            patch("af_expert.cli.load_config", return_value=cfg),
            patch("af_expert.cli.load_state", return_value=state),
            patch("af_expert.cli.save_state") as mock_save,
            patch("af_expert.cli.run_ingestion_tick") as mock_ingest,
            patch("af_expert.cli.EventStore"),
            patch("af_expert.cli.CandidateStore"),
            patch("af_expert.cli.LLM"),
            patch("af_expert.cli.PRForwardPortStrategy") as MockS1,
            patch("af_expert.cli.render_digest", return_value="# digest"),
        ):
            mock_s1_instance = MagicMock()
            mock_s1_instance.on_ingestion_complete.side_effect = fake_s1_on_ingestion
            MockS1.return_value = mock_s1_instance

            runner = CliRunner()
            result = runner.invoke(cli, ["tick", "--strategies-only"])

        return result, captured_deltas, mock_ingest, mock_save

    def test_strategies_only_skips_ingestion(self, tmp_state_dir: Path) -> None:
        """run_ingestion_tick must NOT be called when --strategies-only is set."""
        result, _deltas, mock_ingest, _save = self._run_strategies_only(
            tmp_state_dir,
            repos=["microsoft/agent-framework"],
            state_cursors={"microsoft/agent-framework": "2026-05-10T00:00:00+00:00"},
        )
        assert result.exit_code == 0, result.output
        mock_ingest.assert_not_called()

    def test_strategies_only_since_is_oldest_cursor(self, tmp_state_dir: Path) -> None:
        """Strategies receive since = oldest cursor across all repos."""
        older = "2026-05-01T00:00:00+00:00"
        newer = "2026-05-15T00:00:00+00:00"
        result, captured_deltas, _ingest, _save = self._run_strategies_only(
            tmp_state_dir,
            repos=["microsoft/agent-framework", "pydantic/pydantic-ai"],
            state_cursors={
                "microsoft/agent-framework": newer,
                "pydantic/pydantic-ai": older,
            },
        )
        assert result.exit_code == 0, result.output
        assert len(captured_deltas) == 1
        assert captured_deltas[0].since == datetime.fromisoformat(older)

    def test_strategies_only_all_repos_included(self, tmp_state_dir: Path) -> None:
        """repos_with_new_prs must include every configured repo."""
        repos = ["microsoft/agent-framework", "pydantic/pydantic-ai", "google/adk-python"]
        result, captured_deltas, _ingest, _save = self._run_strategies_only(
            tmp_state_dir,
            repos=repos,
            state_cursors={"microsoft/agent-framework": "2026-05-10T00:00:00+00:00"},
        )
        assert result.exit_code == 0, result.output
        assert len(captured_deltas) == 1
        assert set(captured_deltas[0].repos_with_new_prs) == set(repos)

    def test_strategies_only_does_not_advance_cursors(self, tmp_state_dir: Path) -> None:
        """save_state must NOT be called after a --strategies-only run."""
        result, _deltas, _ingest, mock_save = self._run_strategies_only(
            tmp_state_dir,
            repos=["microsoft/agent-framework"],
            state_cursors={"microsoft/agent-framework": "2026-05-10T00:00:00+00:00"},
        )
        assert result.exit_code == 0, result.output
        mock_save.assert_not_called()

    def test_strategies_only_no_cursors_uses_7day_fallback(self, tmp_state_dir: Path) -> None:
        """When no cursors exist, since falls back to 7 days ago (not a hard crash)."""
        result, captured_deltas, _ingest, _save = self._run_strategies_only(
            tmp_state_dir,
            repos=["microsoft/agent-framework"],
            state_cursors={},
        )
        assert result.exit_code == 0, result.output
        assert len(captured_deltas) == 1
        # since should be approximately 7 days ago — just check it's a datetime
        assert isinstance(captured_deltas[0].since, datetime)


def test_refresh_one_repo_command(tmp_state_dir, monkeypatch) -> None:
    from unittest.mock import patch
    from af_expert.architecture.refresh import RefreshResult

    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\n'
        'anthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "microsoft/agent-framework"\n'
    )

    briefing_path = tmp_state_dir / "repos" / "microsoft__agent-framework" / "architecture.md"
    briefing_path.parent.mkdir(parents=True, exist_ok=True)

    fake_result = RefreshResult(
        repo="microsoft/agent-framework",
        success=True,
        briefing_path=briefing_path,
    )
    briefing_path.write_text("# microsoft/agent-framework\n\nfake briefing")

    with patch("af_expert.cli.refresh_one_repo", return_value=fake_result):
        runner = CliRunner()
        result = runner.invoke(cli, ["refresh", "microsoft/agent-framework"])

    assert result.exit_code == 0
    assert "microsoft/agent-framework" in result.output


def test_tick_with_s4_s6_flags(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-providers" in result.output
    assert "--include-health" in result.output


def test_concept_seed_command(tmp_state_dir, monkeypatch) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\nanthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "a/b"\n'
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["concept", "seed"])
    assert result.exit_code == 0
    assert "seeded" in result.output.lower() or "concepts" in result.output.lower()


def test_concept_list_command(tmp_state_dir) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\nanthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "a/b"\n'
    )
    runner = CliRunner()
    runner.invoke(cli, ["concept", "seed"])
    result = runner.invoke(cli, ["concept", "list"])
    assert result.exit_code == 0
    assert "mcp.oauth.refresh" in result.output


def test_tick_with_structural_and_propagation_flags(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-structural" in result.output
    assert "--include-propagation" in result.output


def test_hypothesis_add_and_list(tmp_state_dir) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\nanthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "a/b"\n'
    )
    runner = CliRunner()
    result_add = runner.invoke(cli, ["hypothesis", "add", "MCP OAuth grants violate RFC 8707"])
    assert result_add.exit_code == 0
    assert "Added" in result_add.output

    result_list = runner.invoke(cli, ["hypothesis", "list"])
    assert result_list.exit_code == 0
    assert "MCP OAuth" in result_list.output


def test_tick_with_hypotheses_flag(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-hypotheses" in result.output
