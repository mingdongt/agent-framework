from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from af_expert.cli import cli


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
