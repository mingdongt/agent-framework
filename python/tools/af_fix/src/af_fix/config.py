# Copyright (c) Microsoft. All rights reserved.

import sys
from pathlib import Path

from pydantic import BaseModel

from af_fix.exceptions import ConfigError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


class Config(BaseModel):
    github_token: str
    fork_owner: str
    target_repos: list[str]

    model: str = "claude-opus-4-7"
    max_turns: int = 80

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            raise ConfigError(f"config not found at {path}")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

        required = ["github_token", "fork_owner", "target_repos"]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ConfigError(f"config missing required keys: {missing}")

        for r in raw["target_repos"]:
            if "/" not in r:
                raise ConfigError(f"target_repos entries must be owner/name, got: {r!r}")

        return cls(**raw)
