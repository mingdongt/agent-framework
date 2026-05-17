# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

import pytest

from af_watch.config import Config
from af_watch.exceptions import ConfigError


def write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    cfg = write(tmp_path / "c.toml", '''
github_token = "ghp_x"
operator_name = "Eric"
home_repo = "microsoft/agent-framework"
target_repos = ["microsoft/agent-framework", "google/adk-python"]
industry_sources = ["https://anthropic.com/news"]
''')
    c = Config.load(cfg)
    assert c.home_repo == "microsoft/agent-framework"
    assert len(c.target_repos) == 2
    assert c.reasoning_model == "claude-opus-4-7"  # default
    assert c.claude_cli_path == "claude"  # default
    assert c.max_regions_per_run == 15  # default


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config not found"):
        Config.load(tmp_path / "nope.toml")


def test_missing_required(tmp_path: Path) -> None:
    cfg = write(tmp_path / "c.toml", 'github_token = "x"\n')
    with pytest.raises(ConfigError, match="missing required"):
        Config.load(cfg)


def test_repo_format_validation(tmp_path: Path) -> None:
    cfg = write(tmp_path / "c.toml", '''
github_token = "x"
operator_name = "Eric"
home_repo = "agent-framework"
target_repos = ["agent-framework"]
industry_sources = []
''')
    with pytest.raises(ConfigError, match="owner/name"):
        Config.load(cfg)


def test_home_repo_must_be_in_targets(tmp_path: Path) -> None:
    cfg = write(tmp_path / "c.toml", '''
github_token = "x"
operator_name = "Eric"
home_repo = "microsoft/agent-framework"
target_repos = ["google/adk-python"]
industry_sources = []
''')
    with pytest.raises(ConfigError, match="home_repo must appear"):
        Config.load(cfg)
