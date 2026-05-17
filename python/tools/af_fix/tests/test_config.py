# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

import pytest

from af_fix.config import Config
from af_fix.exceptions import ConfigError


def _valid_toml() -> str:
    return (
        'github_token = "ghp_xxx"\n'
        'fork_owner = "mingdongtan"\n'
        'anthropic_api_key = "sk-ant-xxx"\n'
        'target_repos = ["microsoft/agent-framework", "vllm-project/vllm"]\n'
    )


def test_load_minimal(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(_valid_toml(), encoding="utf-8")
    cfg = Config.load(p)
    assert cfg.github_token == "ghp_xxx"
    assert cfg.fork_owner == "mingdongtan"
    assert cfg.anthropic_api_key == "sk-ant-xxx"
    assert cfg.target_repos == ["microsoft/agent-framework", "vllm-project/vllm"]


def test_defaults_for_optional(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(_valid_toml(), encoding="utf-8")
    cfg = Config.load(p)
    assert cfg.openhands_max_iterations == 80
    assert cfg.triage_model == "claude-opus-4-7"
    assert cfg.fix_model == "claude-opus-4-7"


def test_missing_required_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "x"\nfork_owner = "y"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"anthropic_api_key|target_repos"):
        Config.load(p)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        Config.load(tmp_path / "nope.toml")


def test_target_repos_must_have_slash(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text(
        'github_token = "x"\nfork_owner = "y"\nanthropic_api_key = "z"\ntarget_repos = ["badrepo"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="owner/name"):
        Config.load(p)
