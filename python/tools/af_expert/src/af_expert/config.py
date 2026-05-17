from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _state_dir() -> Path:
    env = os.environ.get("AF_EXPERT_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".af-expert"


class IngestionConfig(BaseModel):
    poll_interval_hours: int = 24
    event_retention_days: int = 365


class ArchitectureConfig(BaseModel):
    refresh_trigger: Literal["drift", "weekly", "manual"] = "drift"
    refresh_min_days: int = 7


class RepoConfig(BaseModel):
    owner_repo: str
    priority: Literal["high", "normal", "low"] = "normal"
    languages: list[str] = Field(default_factory=list)

    @field_validator("owner_repo")
    @classmethod
    def _validate_owner_repo(cls, v: str) -> str:
        if "/" not in v or v.count("/") != 1:
            raise ValueError(f"owner_repo must be 'owner/repo', got {v!r}")
        owner, repo = v.split("/")
        if not owner or not repo:
            raise ValueError(f"owner_repo must be 'owner/repo', got {v!r}")
        return v


class Config(BaseModel):
    github_token: str
    anthropic_api_key: str
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    architecture: ArchitectureConfig = Field(default_factory=ArchitectureConfig)
    repos: list[RepoConfig] = Field(default_factory=list)


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = _state_dir() / "config.toml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found at {path}. Run `af-expert init`.")

    raw = tomllib.loads(path.read_text())
    try:
        return Config.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Invalid config at {path}: {e}") from e
