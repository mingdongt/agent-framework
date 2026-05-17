from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from af_expert.config import Config, RepoConfig, load_config


def write_config(state_dir: Path, content: str) -> Path:
    cfg_path = state_dir / "config.toml"
    cfg_path.write_text(textwrap.dedent(content).lstrip())
    return cfg_path


def test_load_minimal_valid_config(tmp_state_dir: Path) -> None:
    write_config(
        tmp_state_dir,
        """
        github_token = "ghp_test"
        anthropic_api_key = "sk-ant-test"

        [[repos]]
        owner_repo = "microsoft/agent-framework"
        priority = "high"
        languages = ["python"]
        """,
    )

    cfg = load_config()

    assert cfg.github_token == "ghp_test"
    assert cfg.anthropic_api_key == "sk-ant-test"
    assert len(cfg.repos) == 1
    assert cfg.repos[0].owner_repo == "microsoft/agent-framework"
    assert cfg.repos[0].priority == "high"


def test_load_missing_required_field(tmp_state_dir: Path) -> None:
    write_config(
        tmp_state_dir,
        """
        github_token = "ghp_test"
        # missing anthropic_api_key

        [[repos]]
        owner_repo = "microsoft/agent-framework"
        """,
    )

    with pytest.raises(ValueError, match="anthropic_api_key"):
        load_config()


def test_load_invalid_owner_repo_format(tmp_state_dir: Path) -> None:
    write_config(
        tmp_state_dir,
        """
        github_token = "ghp_test"
        anthropic_api_key = "sk-ant-test"

        [[repos]]
        owner_repo = "agent-framework"
        """,
    )

    with pytest.raises(ValueError, match="owner/repo"):
        load_config()


def test_defaults_applied(tmp_state_dir: Path) -> None:
    write_config(
        tmp_state_dir,
        """
        github_token = "ghp_test"
        anthropic_api_key = "sk-ant-test"

        [[repos]]
        owner_repo = "microsoft/agent-framework"
        """,
    )

    cfg = load_config()

    assert cfg.ingestion.poll_interval_hours == 24
    assert cfg.ingestion.event_retention_days == 365
    assert cfg.architecture.refresh_trigger == "drift"
    assert cfg.repos[0].priority == "normal"
