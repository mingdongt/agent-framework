# Copyright (c) Microsoft. All rights reserved.

import sys
from pathlib import Path

from pydantic import BaseModel

from af_watch.exceptions import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


class Config(BaseModel):
    github_token: str
    operator_name: str
    home_repo: str
    target_repos: list[str]
    industry_sources: list[str]

    reasoning_model: str = "claude-opus-4-7"
    claude_cli_path: str = "claude"
    repro_workspace_base: str = "~/.af-fix/workspaces"
    max_regions_per_run: int = 15
    max_hypotheses_per_region: int = 6
    industry_lookback_days: int = 30
    activity_lookback_days: int = 7

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            raise ConfigError(f"config not found at {path}")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

        required = [
            "github_token", "operator_name",
            "home_repo", "target_repos", "industry_sources",
        ]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ConfigError(f"config missing required keys: {missing}")

        for r in raw["target_repos"]:
            if "/" not in r:
                raise ConfigError(f"target_repos entries must be owner/name, got: {r!r}")
        if "/" not in raw["home_repo"]:
            raise ConfigError(f"home_repo must be owner/name, got: {raw['home_repo']!r}")
        if raw["home_repo"] not in raw["target_repos"]:
            raise ConfigError(f"home_repo must appear in target_repos, got: {raw['home_repo']!r}")

        return cls(**raw)
