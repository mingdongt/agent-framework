# af-expert Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core platform of `af-expert` plus strategies S1 (跨仓 PR 移植) and S8 (Issue 考古). At the end of Wave 1, `af-expert tick` runs against 20+ configured OSS repos, ingests their daily issue/PR/release deltas into SQLite, runs S1 + S8 strategies, and produces at least one real candidate per week from each enabled strategy.

**Architecture:** Local-only Python CLI under `python/tools/af_expert/`. State lives in `~/.af-expert/`. Markdown files for human-readable briefings, SQLite + FTS5 for event history, JSONL for daily candidate logs. Claude Opus 4.7 via Anthropic SDK with prompt caching for all LLM calls. No RAG, no graph DB, no Docker — those are later waves.

**Tech Stack:** Python 3.12+, `uv` for project management, `pydantic` for models, `PyGithub` for GitHub API, `anthropic` SDK for LLM, stdlib `sqlite3`, `tomllib` for config, `click` for CLI, `pytest` for tests.

**Reference spec:** [docs/superpowers/specs/2026-05-17-af-expert-design.md](../specs/2026-05-17-af-expert-design.md)

---

## File Structure

```
python/tools/af_expert/
├── pyproject.toml                            # uv project config
├── README.md                                 # operator-facing setup + usage
├── src/af_expert/
│   ├── __init__.py
│   ├── _version.py
│   ├── config.py                             # ~/.af-expert/config.toml loading + validation
│   ├── state.py                              # ~/.af-expert dir layout + atomic writes + lock
│   ├── github_client.py                      # PyGithub wrapper, multi-repo, rate-limit handling
│   ├── llm.py                                # Anthropic SDK wrapper with caching
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── store.py                          # SQLite + FTS5 wrapper, schema, cursor management
│   │   ├── issues.py                         # fetch + normalize issues per repo
│   │   ├── prs.py                            # fetch + normalize PRs (with diff for merged)
│   │   ├── releases.py                       # fetch + normalize releases
│   │   └── pipeline.py                       # daily tick orchestrator
│   ├── candidate/
│   │   ├── __init__.py
│   │   ├── model.py                          # pydantic Candidate model
│   │   ├── store.py                          # JSONL append-only per day
│   │   ├── ranker.py                         # confidence × novelty × actionability × reputation
│   │   └── export.py                         # candidate → markdown spec file (for af-fix)
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                           # Strategy ABC
│   │   ├── s1_pr_forward_port.py             # 跨仓 PR 移植
│   │   └── s8_issue_archaeology.py           # Issue 考古
│   ├── query/
│   │   ├── __init__.py
│   │   ├── digest.py                         # daily digest renderer
│   │   └── ask.py                            # conversational query
│   └── cli.py                                # click commands: init / tick / digest / suggest / ask / candidate / strategy / stats
└── tests/
    ├── conftest.py                           # pytest fixtures: tmp state dir, fake GitHub, fake LLM
    ├── fixtures/
    │   ├── github_pr_5784.json               # canned PR for S1 tests
    │   ├── github_issue_5712.json
    │   └── architecture_briefing_sample.md
    ├── test_config.py
    ├── test_state.py
    ├── test_github_client.py
    ├── test_llm.py
    ├── test_ingestion_store.py
    ├── test_ingestion_fetchers.py
    ├── test_ingestion_pipeline.py
    ├── test_candidate_model.py
    ├── test_candidate_store.py
    ├── test_candidate_ranker.py
    ├── test_candidate_export.py
    ├── test_strategy_s1.py
    ├── test_strategy_s8.py
    ├── test_query_digest.py
    ├── test_query_ask.py
    ├── test_cli.py
    └── e2e/
        └── test_smoke.py                     # real LLM + real GitHub, manual marker
```

**Conventions enforced by all tasks below:**

- Every Python module uses `from __future__ import annotations`
- Type hints required on all public functions
- All file I/O on state goes through `state.py` (atomic write helper)
- All LLM calls go through `llm.py` (prompt caching applied centrally)
- Tests never hit the real network unless marked `@pytest.mark.e2e`
- Each task ends with one commit; commit message convention: `feat(af-expert): <what>` for features, `test(af-expert): <what>` for test-only commits, `chore(af-expert): <what>` for boilerplate

---

## Task 1: Bootstrap project skeleton

**Files:**
- Create: `python/tools/af_expert/pyproject.toml`
- Create: `python/tools/af_expert/src/af_expert/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/_version.py`
- Create: `python/tools/af_expert/README.md`
- Create: `python/tools/af_expert/tests/conftest.py`
- Create: `python/tools/af_expert/tests/__init__.py`
- Create: `python/tools/af_expert/.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p python/tools/af_expert/src/af_expert/ingestion
mkdir -p python/tools/af_expert/src/af_expert/candidate
mkdir -p python/tools/af_expert/src/af_expert/strategies
mkdir -p python/tools/af_expert/src/af_expert/query
mkdir -p python/tools/af_expert/tests/fixtures
mkdir -p python/tools/af_expert/tests/e2e
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "af-expert"
version = "0.1.0"
description = "Continuously-learning domain expert for OSS agent framework contributions"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40.0",
    "pygithub>=2.5.0",
    "pydantic>=2.10.0",
    "click>=8.1.7",
    "tomli; python_version<'3.11'",
    "platformdirs>=4.3.0",
]

[project.scripts]
af-expert = "af_expert.cli:cli"

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-mock>=3.14.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
    "pyright>=1.1.380",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/af_expert"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "e2e: end-to-end tests requiring real network + API keys (manual run only)",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
ignore = ["E501"]

[tool.pyright]
include = ["src"]
typeCheckingMode = "strict"
pythonVersion = "3.12"
```

- [ ] **Step 3: Write `src/af_expert/__init__.py`**

```python
from __future__ import annotations

from af_expert._version import __version__

__all__ = ["__version__"]
```

- [ ] **Step 4: Write `src/af_expert/_version.py`**

```python
from __future__ import annotations

__version__ = "0.1.0"
```

- [ ] **Step 5: Write `tests/conftest.py`** (minimal; fixtures grow per task)

```python
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect AF_EXPERT_STATE_DIR to a tmp dir for the duration of a test."""
    state_dir = tmp_path / "af-expert"
    state_dir.mkdir()
    monkeypatch.setenv("AF_EXPERT_STATE_DIR", str(state_dir))
    yield state_dir
```

- [ ] **Step 6: Write `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 7: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.venv/
dist/
build/
*.egg-info/
```

- [ ] **Step 8: Write minimal `README.md`**

```markdown
# af-expert

Continuously-learning domain expert agent for OSS agent framework contributions.

See design spec: `docs/superpowers/specs/2026-05-17-af-expert-design.md`
See Wave 1 plan: `docs/superpowers/plans/2026-05-18-af-expert-wave1.md`

## Quickstart (Wave 1)

```bash
cd python/tools/af_expert
uv sync --all-extras
af-expert init
$EDITOR ~/.af-expert/config.toml
af-expert tick
af-expert digest
af-expert suggest --top 10
```
```

- [ ] **Step 9: Verify project installs cleanly**

```bash
cd python/tools/af_expert
uv sync --all-extras
```

Expected: no errors. `uv run python -c "import af_expert; print(af_expert.__version__)"` prints `0.1.0`.

- [ ] **Step 10: Commit**

```bash
git add python/tools/af_expert/
git commit -m "feat(af-expert): bootstrap project skeleton"
```

---

## Task 2: Config loader

**Files:**
- Create: `python/tools/af_expert/src/af_expert/config.py`
- Test: `python/tools/af_expert/tests/test_config.py`

The config is a TOML file at `~/.af-expert/config.toml` (or `$AF_EXPERT_STATE_DIR/config.toml`). Schema is fixed at this stage; later waves may add sections.

- [ ] **Step 1: Write failing test for config load + validation**

`tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test, confirm failure**

```bash
cd python/tools/af_expert
uv run pytest tests/test_config.py -v
```

Expected: ImportError or ModuleNotFoundError on `af_expert.config`.

- [ ] **Step 3: Write `src/af_expert/config.py`**

```python
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
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/config.py python/tools/af_expert/tests/test_config.py
git commit -m "feat(af-expert): config loader with TOML schema"
```

---

## Task 3: State directory + atomic write helper

**Files:**
- Create: `python/tools/af_expert/src/af_expert/state.py`
- Test: `python/tools/af_expert/tests/test_state.py`

The state module owns: directory layout, atomic writes (tmp + rename), single-process locking, and the `state.json` file with cursor positions.

- [ ] **Step 1: Write failing tests**

`tests/test_state.py`:

```python
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from af_expert.state import (
    StateDir,
    StateLockError,
    atomic_write,
    load_state,
    save_state,
)


def test_state_dir_layout(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    assert (tmp_state_dir / "repos").is_dir()
    assert (tmp_state_dir / "candidates").is_dir()
    assert (tmp_state_dir / "digests").is_dir()


def test_atomic_write_roundtrip(tmp_state_dir: Path) -> None:
    target = tmp_state_dir / "foo.json"
    atomic_write(target, '{"a": 1}')
    assert target.read_text() == '{"a": 1}'


def test_atomic_write_overwrites(tmp_state_dir: Path) -> None:
    target = tmp_state_dir / "foo.json"
    atomic_write(target, "v1")
    atomic_write(target, "v2")
    assert target.read_text() == "v2"


def test_atomic_write_no_partial_on_failure(tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_state_dir / "foo.json"
    target.write_text("original")

    import af_expert.state as state_mod

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated rename failure")

    monkeypatch.setattr(state_mod.os, "replace", boom)

    with pytest.raises(RuntimeError):
        atomic_write(target, "new")

    assert target.read_text() == "original"


def test_load_state_missing_returns_empty(tmp_state_dir: Path) -> None:
    state = load_state()
    assert state == {"version": 1, "cursors": {}, "stats": {}}


def test_save_and_load_state(tmp_state_dir: Path) -> None:
    save_state({"version": 1, "cursors": {"microsoft/agent-framework": "2026-05-17T00:00:00Z"}, "stats": {}})
    state = load_state()
    assert state["cursors"]["microsoft/agent-framework"] == "2026-05-17T00:00:00Z"


def test_lock_prevents_concurrent_run(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    with sd.lock():
        with pytest.raises(StateLockError):
            with sd.lock():
                pass


def test_lock_releases_on_exit(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    with sd.lock():
        pass

    with sd.lock():
        pass  # second acquisition should now succeed
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_state.py -v
```

Expected: ImportError on `af_expert.state`.

- [ ] **Step 3: Write `src/af_expert/state.py`**

```python
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from af_expert.config import _state_dir


class StateLockError(RuntimeError):
    pass


def atomic_write(target: Path, content: str) -> None:
    """Atomic write: write to tmp file, then os.replace into target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class StateDir:
    def __init__(self) -> None:
        self.root = _state_dir()

    def ensure_layout(self) -> None:
        for sub in ("repos", "candidates", "digests"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def lock_path(self) -> Path:
        return self.root / "lock"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError as e:
            existing = self.lock_path.read_text(errors="ignore").strip()
            raise StateLockError(
                f"Lock held (pid {existing}) at {self.lock_path}. "
                f"If no af-expert process is running, remove this file."
            ) from e
        try:
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)


def load_state() -> dict[str, Any]:
    sd = StateDir()
    if not sd.state_path.exists():
        return {"version": 1, "cursors": {}, "stats": {}}
    return json.loads(sd.state_path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    sd = StateDir()
    sd.ensure_layout()
    atomic_write(sd.state_path, json.dumps(state, indent=2, sort_keys=True))
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_state.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/state.py python/tools/af_expert/tests/test_state.py
git commit -m "feat(af-expert): state dir with atomic write + lock"
```

---

## Task 4: GitHub client wrapper

**Files:**
- Create: `python/tools/af_expert/src/af_expert/github_client.py`
- Test: `python/tools/af_expert/tests/test_github_client.py`

Thin wrapper over `PyGithub` so callers don't import it directly. Handles: rate-limit-aware fetching, per-repo error isolation, normalized return shapes.

- [ ] **Step 1: Write failing tests using mock**

`tests/test_github_client.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from af_expert.github_client import GitHubClient, RateLimitInfo


def test_list_pulls_merged_since_returns_normalized_records() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_pull = MagicMock()
    fake_pull.number = 5784
    fake_pull.title = "fix: skip orphan Anthropic thinking signatures"
    fake_pull.body = "Fixes #5783."
    fake_pull.merged_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.updated_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.created_at = datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    fake_pull.closed_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_pull.state = "closed"
    fake_pull.user.login = "he-yufeng"
    fake_pull.html_url = "https://github.com/microsoft/agent-framework/pull/5784"
    fake_pull.merged = True
    fake_pull.labels = []

    fake_repo.get_pulls.return_value = [fake_pull]
    fake_github.get_repo.return_value = fake_repo

    client = GitHubClient(token="ghp_test", _github=fake_github)
    since = datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)

    results = list(client.list_pulls_merged_since("microsoft/agent-framework", since))

    assert len(results) == 1
    record = results[0]
    assert record["number"] == 5784
    assert record["title"] == "fix: skip orphan Anthropic thinking signatures"
    assert record["author"] == "he-yufeng"
    assert record["state"] == "merged"
    assert record["url"] == "https://github.com/microsoft/agent-framework/pull/5784"


def test_list_pulls_filters_out_unmerged() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_open_pr = MagicMock()
    fake_open_pr.merged = False
    fake_open_pr.state = "open"
    fake_open_pr.updated_at = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    fake_repo.get_pulls.return_value = [fake_open_pr]
    fake_github.get_repo.return_value = fake_repo

    client = GitHubClient(token="ghp_test", _github=fake_github)
    since = datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)

    results = list(client.list_pulls_merged_since("microsoft/agent-framework", since))
    assert results == []


def test_get_pull_diff_returns_text() -> None:
    fake_github = MagicMock()
    fake_repo = MagicMock()
    fake_pull = MagicMock()
    fake_pull.get_files.return_value = []
    fake_repo.get_pull.return_value = fake_pull
    fake_github.get_repo.return_value = fake_repo

    # PyGithub doesn't expose .diff() directly; we fetch via requester
    fake_github._Github__requester.requestJson.return_value = (
        200,
        {"Content-Type": "text/plain"},
        "diff --git a/foo b/foo\n+x\n",
    )

    client = GitHubClient(token="ghp_test", _github=fake_github)
    diff = client.get_pull_diff("microsoft/agent-framework", 5784)
    assert "diff --git" in diff


def test_rate_limit_info() -> None:
    fake_github = MagicMock()
    fake_rate = MagicMock()
    fake_rate.core.remaining = 4500
    fake_rate.core.limit = 5000
    fake_rate.core.reset = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    fake_github.get_rate_limit.return_value = fake_rate

    client = GitHubClient(token="ghp_test", _github=fake_github)
    info = client.get_rate_limit()
    assert isinstance(info, RateLimitInfo)
    assert info.remaining == 4500
    assert info.limit == 5000
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_github_client.py -v
```

Expected: ImportError on `af_expert.github_client`.

- [ ] **Step 3: Write `src/af_expert/github_client.py`**

```python
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from github import Github
from github.GithubException import GithubException


@dataclass(frozen=True)
class RateLimitInfo:
    remaining: int
    limit: int
    reset_at: datetime


class GitHubClient:
    """Thin wrapper over PyGithub.

    Constructor accepts an optional `_github` injection point for tests.
    Public methods return plain dicts (not PyGithub objects), so consumers
    are not coupled to PyGithub's API surface.
    """

    def __init__(self, token: str, *, _github: Github | None = None) -> None:
        self._gh = _github if _github is not None else Github(token, per_page=100)
        self._token = token

    def get_rate_limit(self) -> RateLimitInfo:
        rl = self._gh.get_rate_limit()
        return RateLimitInfo(
            remaining=rl.core.remaining,
            limit=rl.core.limit,
            reset_at=rl.core.reset,
        )

    def list_issues_updated_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for issue in repo.get_issues(state="all", since=since, sort="updated"):
            # PyGithub: pull requests show up as issues too; filter them out
            if issue.pull_request is not None:
                continue
            yield {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body or "",
                "author": issue.user.login if issue.user else "unknown",
                "state": issue.state,
                "labels": [lab.name for lab in issue.labels],
                "created_at": issue.created_at,
                "updated_at": issue.updated_at,
                "closed_at": issue.closed_at,
                "url": issue.html_url,
            }

    def list_pulls_merged_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for pr in repo.get_pulls(state="closed", sort="updated", direction="desc"):
            if pr.updated_at < since:
                break
            if not pr.merged:
                continue
            yield {
                "number": pr.number,
                "title": pr.title,
                "body": pr.body or "",
                "author": pr.user.login if pr.user else "unknown",
                "state": "merged",
                "labels": [lab.name for lab in pr.labels],
                "created_at": pr.created_at,
                "updated_at": pr.updated_at,
                "merged_at": pr.merged_at,
                "closed_at": pr.closed_at,
                "url": pr.html_url,
            }

    def get_pull_diff(self, owner_repo: str, number: int) -> str:
        """Fetch unified diff text for a PR.

        Uses GitHub's API `.diff` representation by setting the right Accept header.
        """
        headers = {"Accept": "application/vnd.github.v3.diff"}
        url = f"/repos/{owner_repo}/pulls/{number}"
        _status, _headers, data = self._gh._Github__requester.requestJson(
            "GET", url, headers=headers
        )
        return data if isinstance(data, str) else json.dumps(data)

    def list_releases_since(
        self, owner_repo: str, since: datetime
    ) -> Iterator[dict[str, Any]]:
        repo = self._gh.get_repo(owner_repo)
        for rel in repo.get_releases():
            if rel.published_at and rel.published_at < since:
                break
            yield {
                "number": None,
                "title": rel.name or rel.tag_name,
                "body": rel.body or "",
                "author": rel.author.login if rel.author else "unknown",
                "state": "published",
                "labels": [rel.tag_name],
                "created_at": rel.created_at,
                "updated_at": rel.published_at,
                "url": rel.html_url,
            }
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_github_client.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/github_client.py python/tools/af_expert/tests/test_github_client.py
git commit -m "feat(af-expert): GitHub client wrapper with normalized return shapes"
```

---

## Task 5: Event store (SQLite + FTS5)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/ingestion/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/ingestion/store.py`
- Test: `python/tools/af_expert/tests/test_ingestion_store.py`

SQLite + FTS5 over `events` table. Single DB file at `~/.af-expert/events.db`. Cursors stored in `state.json` (handled by Task 3), not in the DB.

- [ ] **Step 1: Write failing tests**

`tests/test_ingestion_store.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_expert.ingestion.store import EventStore, EventRecord


@pytest.fixture
def store(tmp_state_dir: Path) -> EventStore:
    s = EventStore()
    s.ensure_schema()
    return s


def _make_record(**kwargs: object) -> EventRecord:
    base = {
        "repo": "microsoft/agent-framework",
        "kind": "pr",
        "number": 5784,
        "title": "fix: orphan thinking signatures",
        "body": "Fixes #5783",
        "diff": "diff --git ...",
        "author": "he-yufeng",
        "state": "merged",
        "labels": [],
        "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "merged_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "url": "https://github.com/microsoft/agent-framework/pull/5784",
        "raw": {"some": "json"},
    }
    base.update(kwargs)
    return EventRecord(**base)


def test_ensure_schema_creates_tables(store: EventStore) -> None:
    cur = store._conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('events', 'events_fts')"
    )
    names = {row[0] for row in cur.fetchall()}
    assert "events" in names
    assert "events_fts" in names


def test_insert_and_read_back(store: EventStore) -> None:
    rec = _make_record()
    store.insert(rec)
    rows = list(store.query_recent_prs("microsoft/agent-framework", since=rec.created_at, only_merged=True))
    assert len(rows) == 1
    assert rows[0]["number"] == 5784
    assert rows[0]["title"] == "fix: orphan thinking signatures"


def test_insert_is_idempotent_on_repo_kind_number(store: EventStore) -> None:
    rec = _make_record()
    store.insert(rec)
    rec2 = _make_record(title="updated title")
    store.insert(rec2)

    rows = list(store.query_recent_prs("microsoft/agent-framework", since=rec.created_at, only_merged=True))
    assert len(rows) == 1
    assert rows[0]["title"] == "updated title"


def test_fts_search_by_title(store: EventStore) -> None:
    store.insert(_make_record(number=1, title="orphan thinking signatures"))
    store.insert(_make_record(number=2, title="completely unrelated"))

    results = list(store.fts_search("orphan thinking"))
    assert len(results) == 1
    assert results[0]["number"] == 1


def test_query_recent_prs_only_merged_flag(store: EventStore) -> None:
    store.insert(_make_record(number=1, state="merged"))
    store.insert(_make_record(number=2, state="closed", merged_at=None))

    merged_only = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 1, 1, tzinfo=timezone.utc), only_merged=True
        )
    )
    assert len(merged_only) == 1
    assert merged_only[0]["number"] == 1
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_ingestion_store.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/ingestion/__init__.py`**

```python
```

- [ ] **Step 4: Write `src/af_expert/ingestion/store.py`**

```python
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from af_expert.config import _state_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    number       INTEGER,
    title        TEXT,
    body         TEXT,
    diff         TEXT,
    author       TEXT,
    state        TEXT,
    labels       TEXT,
    created_at   TEXT,
    updated_at   TEXT,
    closed_at    TEXT,
    merged_at    TEXT,
    url          TEXT,
    raw          TEXT,
    ingested_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repo, kind, number)
);

CREATE INDEX IF NOT EXISTS idx_events_repo_kind_created ON events (repo, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_events_repo_kind_merged ON events (repo, kind, merged_at);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title, body, diff, labels,
    content='events', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, body, diff, labels)
    VALUES (new.id, new.title, new.body, new.diff, new.labels);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, body, diff, labels)
    VALUES('delete', old.id, old.title, old.body, old.diff, old.labels);
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, body, diff, labels)
    VALUES('delete', old.id, old.title, old.body, old.diff, old.labels);
    INSERT INTO events_fts(rowid, title, body, diff, labels)
    VALUES (new.id, new.title, new.body, new.diff, new.labels);
END;
"""


@dataclass
class EventRecord:
    repo: str
    kind: str  # "issue" | "pr" | "release"
    number: int | None
    title: str
    body: str
    author: str
    state: str
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    diff: str | None = None
    url: str = ""
    raw: dict[str, Any] | None = None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class EventStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "events.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def ensure_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def insert(self, rec: EventRecord) -> None:
        payload = {
            "repo": rec.repo,
            "kind": rec.kind,
            "number": rec.number,
            "title": rec.title,
            "body": rec.body,
            "diff": rec.diff,
            "author": rec.author,
            "state": rec.state,
            "labels": json.dumps(rec.labels),
            "created_at": _iso(rec.created_at),
            "updated_at": _iso(rec.updated_at),
            "closed_at": _iso(rec.closed_at),
            "merged_at": _iso(rec.merged_at),
            "url": rec.url,
            "raw": json.dumps(rec.raw or {}),
        }
        self._conn.execute(
            """
            INSERT INTO events (repo, kind, number, title, body, diff, author, state, labels,
                                created_at, updated_at, closed_at, merged_at, url, raw)
            VALUES (:repo, :kind, :number, :title, :body, :diff, :author, :state, :labels,
                    :created_at, :updated_at, :closed_at, :merged_at, :url, :raw)
            ON CONFLICT(repo, kind, number) DO UPDATE SET
                title=excluded.title,
                body=excluded.body,
                diff=excluded.diff,
                author=excluded.author,
                state=excluded.state,
                labels=excluded.labels,
                updated_at=excluded.updated_at,
                closed_at=excluded.closed_at,
                merged_at=excluded.merged_at,
                url=excluded.url,
                raw=excluded.raw
            """,
            payload,
        )
        self._conn.commit()

    def query_recent_prs(
        self,
        repo: str,
        since: datetime,
        only_merged: bool = True,
    ) -> Iterator[dict[str, Any]]:
        where = ["repo = ?", "kind = 'pr'", "updated_at >= ?"]
        params: list[Any] = [repo, since.isoformat()]
        if only_merged:
            where.append("state = 'merged'")
        sql = f"SELECT * FROM events WHERE {' AND '.join(where)} ORDER BY merged_at DESC"
        for row in self._conn.execute(sql, params):
            yield dict(row)

    def query_closed_issues(
        self,
        repo: str,
        before: datetime,
        labels_any_of: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        where = ["repo = ?", "kind = 'issue'", "state = 'closed'", "closed_at <= ?"]
        params: list[Any] = [repo, before.isoformat()]
        if labels_any_of:
            # naive substring match within JSON-encoded labels
            label_clause = " OR ".join(["labels LIKE ?"] * len(labels_any_of))
            where.append(f"({label_clause})")
            params.extend([f'%"{lab}"%' for lab in labels_any_of])
        sql = f"SELECT * FROM events WHERE {' AND '.join(where)} ORDER BY closed_at DESC"
        for row in self._conn.execute(sql, params):
            yield dict(row)

    def fts_search(self, query: str, limit: int = 50) -> Iterator[dict[str, Any]]:
        sql = """
            SELECT e.* FROM events e
            JOIN events_fts ON events_fts.rowid = e.id
            WHERE events_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        for row in self._conn.execute(sql, (query, limit)):
            yield dict(row)

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run pytest tests/test_ingestion_store.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add python/tools/af_expert/src/af_expert/ingestion/ python/tools/af_expert/tests/test_ingestion_store.py
git commit -m "feat(af-expert): SQLite + FTS5 event store"
```

---

## Task 6: LLM wrapper

**Files:**
- Create: `python/tools/af_expert/src/af_expert/llm.py`
- Test: `python/tools/af_expert/tests/test_llm.py`

Single chokepoint for Anthropic SDK calls. Applies prompt caching to large system context. Returns parsed JSON when requested.

- [ ] **Step 1: Write failing tests**

`tests/test_llm.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from af_expert.llm import LLM, LLMResponse, parse_json_block


def test_parse_json_block_extracts_fenced() -> None:
    content = "Here is the answer:\n\n```json\n{\"score\": 5}\n```\n\nThanks."
    assert parse_json_block(content) == {"score": 5}


def test_parse_json_block_extracts_bare() -> None:
    content = '{"score": 5}'
    assert parse_json_block(content) == {"score": 5}


def test_parse_json_block_raises_on_no_json() -> None:
    with pytest.raises(ValueError):
        parse_json_block("no json here")


def test_llm_complete_invokes_anthropic_with_caching() -> None:
    fake_client = MagicMock()
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_msg.usage.input_tokens = 100
    fake_msg.usage.output_tokens = 20
    fake_msg.usage.cache_read_input_tokens = 0
    fake_msg.usage.cache_creation_input_tokens = 0
    fake_client.messages.create.return_value = fake_msg

    llm = LLM(api_key="sk-ant-test", _client=fake_client)
    resp = llm.complete(
        system="long system prompt with big context",
        user="short user prompt",
    )

    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.input_tokens == 100

    call = fake_client.messages.create.call_args
    # System message has cache_control on large context blocks
    system_arg = call.kwargs["system"]
    assert isinstance(system_arg, list)
    assert any(
        block.get("cache_control", {}).get("type") == "ephemeral" for block in system_arg
    )
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_llm.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/llm.py`**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic


MODEL = "claude-opus-4-7"
MAX_TOKENS_DEFAULT = 4096


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


def parse_json_block(text: str) -> Any:
    """Extract JSON from an LLM response.

    Tries fenced ```json ...``` first, then bare object/array.
    Raises ValueError if nothing parseable found.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    bare = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if bare:
        return json.loads(bare.group(1))
    raise ValueError("No JSON found in LLM response")


class LLM:
    def __init__(self, api_key: str, *, _client: Anthropic | None = None) -> None:
        self._client = _client if _client is not None else Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = MAX_TOKENS_DEFAULT,
        model: str = MODEL,
    ) -> LLMResponse:
        # Apply cache_control to the system block. Anthropic accepts a list of
        # system blocks; marking ephemeral cache lets us reuse the briefing
        # context across many calls in a tick.
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user}],
        )
        text_parts = [block.text for block in msg.content if hasattr(block, "text")]
        return LLMResponse(
            text="".join(text_parts),
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_llm.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/llm.py python/tools/af_expert/tests/test_llm.py
git commit -m "feat(af-expert): Anthropic LLM wrapper with prompt caching"
```

---

## Task 7: Ingestion fetchers (issues + PRs + releases)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/ingestion/issues.py`
- Create: `python/tools/af_expert/src/af_expert/ingestion/prs.py`
- Create: `python/tools/af_expert/src/af_expert/ingestion/releases.py`
- Test: `python/tools/af_expert/tests/test_ingestion_fetchers.py`

Each fetcher uses the GitHubClient to pull deltas since a cursor and writes EventRecord rows into the EventStore. PR fetcher additionally fetches diff text for merged PRs (needed by S1).

- [ ] **Step 1: Write failing tests**

`tests/test_ingestion_fetchers.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.ingestion.issues import fetch_issues
from af_expert.ingestion.prs import fetch_prs
from af_expert.ingestion.releases import fetch_releases
from af_expert.ingestion.store import EventStore


@pytest.fixture
def store(tmp_state_dir: Path) -> EventStore:
    s = EventStore()
    s.ensure_schema()
    return s


def _fake_pr_record() -> dict[str, object]:
    return {
        "number": 5784,
        "title": "fix: orphan thinking signatures",
        "body": "Fixes #5783.",
        "author": "he-yufeng",
        "state": "merged",
        "labels": ["bug"],
        "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "merged_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "url": "https://github.com/microsoft/agent-framework/pull/5784",
    }


def test_fetch_prs_writes_records_to_store(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_pulls_merged_since.return_value = iter([_fake_pr_record()])
    gh.get_pull_diff.return_value = "diff --git a/foo b/foo\n+x\n"

    count = fetch_prs(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1
    rows = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
        )
    )
    assert len(rows) == 1
    assert rows[0]["diff"].startswith("diff --git")


def test_fetch_prs_swallows_diff_fetch_failure(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_pulls_merged_since.return_value = iter([_fake_pr_record()])
    gh.get_pull_diff.side_effect = RuntimeError("diff fetch failed")

    count = fetch_prs(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
    )
    # Record still written, diff is None
    assert count == 1
    rows = list(
        store.query_recent_prs(
            "microsoft/agent-framework", since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc)
        )
    )
    assert rows[0]["diff"] is None


def test_fetch_issues_writes_records(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_issues_updated_since.return_value = iter(
        [
            {
                "number": 5712,
                "title": "[LiteLLM] _is_thinking_blocks_format drops Gemini thinking_blocks",
                "body": "Detailed bug report ...",
                "author": "ThibaultCoudertSephora",
                "state": "open",
                "labels": ["bug"],
                "created_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "closed_at": None,
                "url": "https://github.com/google/adk-python/issues/5712",
            }
        ]
    )
    count = fetch_issues(
        gh, store, repo="google/adk-python", since=datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1


def test_fetch_releases_writes_records(store: EventStore) -> None:
    gh = MagicMock()
    gh.list_releases_since.return_value = iter(
        [
            {
                "number": None,
                "title": "v1.4.0",
                "body": "Release notes ...",
                "author": "release-bot",
                "state": "published",
                "labels": ["v1.4.0"],
                "created_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc),
                "url": "https://github.com/microsoft/agent-framework/releases/tag/v1.4.0",
            }
        ]
    )
    count = fetch_releases(
        gh, store, repo="microsoft/agent-framework", since=datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    )
    assert count == 1
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_ingestion_fetchers.py -v
```

Expected: ImportError on the three fetcher modules.

- [ ] **Step 3: Write `src/af_expert/ingestion/issues.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_issues(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for issue in gh.list_issues_updated_since(repo, since):
        rec = EventRecord(
            repo=repo,
            kind="issue",
            number=issue["number"],
            title=issue["title"],
            body=issue["body"],
            author=issue["author"],
            state=issue["state"],
            labels=issue["labels"],
            created_at=issue["created_at"],
            updated_at=issue["updated_at"],
            closed_at=issue.get("closed_at"),
            url=issue["url"],
        )
        store.insert(rec)
        count += 1
    return count
```

- [ ] **Step 4: Write `src/af_expert/ingestion/prs.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_prs(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for pr in gh.list_pulls_merged_since(repo, since):
        try:
            diff = gh.get_pull_diff(repo, pr["number"])
        except Exception as e:
            log.warning("Failed to fetch diff for %s#%d: %s", repo, pr["number"], e)
            diff = None
        rec = EventRecord(
            repo=repo,
            kind="pr",
            number=pr["number"],
            title=pr["title"],
            body=pr["body"],
            author=pr["author"],
            state=pr["state"],
            labels=pr["labels"],
            created_at=pr["created_at"],
            updated_at=pr["updated_at"],
            closed_at=pr.get("closed_at"),
            merged_at=pr.get("merged_at"),
            diff=diff,
            url=pr["url"],
        )
        store.insert(rec)
        count += 1
    return count
```

- [ ] **Step 5: Write `src/af_expert/ingestion/releases.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from af_expert.ingestion.store import EventRecord, EventStore


log = logging.getLogger(__name__)


def fetch_releases(gh: Any, store: EventStore, *, repo: str, since: datetime) -> int:
    count = 0
    for rel in gh.list_releases_since(repo, since):
        rec = EventRecord(
            repo=repo,
            kind="release",
            number=None,
            title=rel["title"],
            body=rel["body"],
            author=rel["author"],
            state=rel["state"],
            labels=rel["labels"],
            created_at=rel["created_at"],
            updated_at=rel["updated_at"],
            url=rel["url"],
        )
        store.insert(rec)
        count += 1
    return count
```

- [ ] **Step 6: Run tests, confirm pass**

```bash
uv run pytest tests/test_ingestion_fetchers.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add python/tools/af_expert/src/af_expert/ingestion/issues.py python/tools/af_expert/src/af_expert/ingestion/prs.py python/tools/af_expert/src/af_expert/ingestion/releases.py python/tools/af_expert/tests/test_ingestion_fetchers.py
git commit -m "feat(af-expert): per-source ingestion fetchers"
```

---

## Task 8: Ingestion pipeline orchestrator

**Files:**
- Create: `python/tools/af_expert/src/af_expert/ingestion/pipeline.py`
- Test: `python/tools/af_expert/tests/test_ingestion_pipeline.py`

Daily tick orchestrator. For each repo in config: fetch issues + PRs + releases since cursor, update cursor atomically. Per-repo isolation: one repo's failure does not abort the tick.

- [ ] **Step 1: Write failing tests**

`tests/test_ingestion_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_ingestion_pipeline.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/ingestion/pipeline.py`**

```python
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.ingestion.issues import fetch_issues
from af_expert.ingestion.prs import fetch_prs
from af_expert.ingestion.releases import fetch_releases
from af_expert.ingestion.store import EventStore


log = logging.getLogger(__name__)

# Default lookback when no cursor exists for a repo
DEFAULT_LOOKBACK = timedelta(days=7)


@dataclass
class IngestionResult:
    repos_succeeded: int = 0
    repos_failed: int = 0
    failed_repos: dict[str, str] = field(default_factory=dict)
    new_events: int = 0


def _cursor_for(state: dict[str, Any], repo: str, now: datetime) -> datetime:
    raw = state.get("cursors", {}).get(repo)
    if raw is None:
        return now - DEFAULT_LOOKBACK
    return datetime.fromisoformat(raw)


def _advance_cursor(state: dict[str, Any], repo: str, now: datetime) -> None:
    state.setdefault("cursors", {})[repo] = now.isoformat()


def run_ingestion_tick(
    config: Any,
    gh: Any,
    store: EventStore,
    *,
    now: datetime | None = None,
    load_state: Callable[[], dict[str, Any]],
    save_state: Callable[[dict[str, Any]], None],
) -> IngestionResult:
    """Run one daily tick. Per-repo isolation: failures don't propagate.

    `load_state` and `save_state` are injected so tests can avoid disk.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    state = load_state()
    result = IngestionResult()

    for repo_cfg in config.repos:
        repo = repo_cfg.owner_repo
        cursor = _cursor_for(state, repo, now)
        try:
            issues_count = fetch_issues(gh, store, repo=repo, since=cursor)
            prs_count = fetch_prs(gh, store, repo=repo, since=cursor)
            releases_count = fetch_releases(gh, store, repo=repo, since=cursor)
            result.new_events += issues_count + prs_count + releases_count
            _advance_cursor(state, repo, now)
            result.repos_succeeded += 1
            save_state(state)
        except Exception as e:
            log.exception("Ingestion failed for %s", repo)
            result.repos_failed += 1
            result.failed_repos[repo] = str(e)

    return result
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_ingestion_pipeline.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/ingestion/pipeline.py python/tools/af_expert/tests/test_ingestion_pipeline.py
git commit -m "feat(af-expert): ingestion pipeline orchestrator"
```

---

## Task 9: Candidate model + store

**Files:**
- Create: `python/tools/af_expert/src/af_expert/candidate/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/candidate/model.py`
- Create: `python/tools/af_expert/src/af_expert/candidate/store.py`
- Test: `python/tools/af_expert/tests/test_candidate_model.py`
- Test: `python/tools/af_expert/tests/test_candidate_store.py`

- [ ] **Step 1: Write failing tests for model**

`tests/test_candidate_model.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.candidate.model import Candidate


def test_candidate_minimal() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible orphan thinking signature path",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only thinking blocks before serialize",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    assert c.id == "c-001"
    assert c.category == "bug"


def test_candidate_confidence_bounded() -> None:
    with pytest.raises(ValueError):
        Candidate(
            id="c-002",
            discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
            strategy="s1_pr_forward_port",
            target_repo="x/y",
            category="bug",
            title="t",
            description="d",
            suggested_action="a",
            confidence=1.5,  # out of range
            novelty=0.3,
            actionability=0.5,
            strategy_reputation=0.5,
            status="new",
        )


def test_candidate_serialize_roundtrip() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="x/y",
        category="bug",
        title="t",
        description="d",
        suggested_action="a",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    raw = c.model_dump_json()
    c2 = Candidate.model_validate_json(raw)
    assert c2 == c
```

- [ ] **Step 2: Write `src/af_expert/candidate/__init__.py`**

```python
```

- [ ] **Step 3: Write `src/af_expert/candidate/model.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["bug", "feature", "maintenance", "consolidation"]
Status = Literal["new", "reviewed", "accepted", "rejected", "shipped"]


class Candidate(BaseModel):
    id: str
    discovered_at: datetime
    strategy: str

    target_repo: str
    target_files: list[str] = Field(default_factory=list)
    target_lines: list[tuple[int, int]] = Field(default_factory=list)
    category: Category

    title: str
    description: str
    suggested_action: str

    evidence_urls: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    strategy_reputation: float = Field(ge=0.0, le=1.0)

    status: Status = "new"
    notes: str = ""
```

- [ ] **Step 4: Write failing tests for store**

`tests/test_candidate_store.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore


def _make_candidate(cid: str = "c-001") -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible bug",
        description="Description",
        suggested_action="Fix it",
        confidence=0.7,
        novelty=0.5,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )


def test_append_and_list_today(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))
    s.append(_make_candidate("c-002"))

    today = list(s.list_today())
    assert {c.id for c in today} == {"c-001", "c-002"}


def test_get_returns_by_id(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))

    c = s.get("c-001")
    assert c is not None
    assert c.id == "c-001"

    assert s.get("nonexistent") is None


def test_update_status_writes_overlay(tmp_state_dir: Path) -> None:
    s = CandidateStore()
    s.append(_make_candidate("c-001"))

    s.update_status("c-001", status="accepted", notes="looks good")

    c = s.get("c-001")
    assert c is not None
    assert c.status == "accepted"
    assert c.notes == "looks good"


def test_list_since_filters_by_date(tmp_state_dir: Path) -> None:
    s = CandidateStore()

    old = _make_candidate("c-old")
    old.discovered_at = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    new = _make_candidate("c-new")
    new.discovered_at = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

    s.append(old)
    s.append(new)

    since = datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
    results = list(s.list_since(since))
    assert {c.id for c in results} == {"c-new"}
```

- [ ] **Step 5: Write `src/af_expert/candidate/store.py`**

```python
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.config import _state_dir
from af_expert.state import atomic_write


class CandidateStore:
    """Append-only JSONL per day. Status updates are stored in an overlay file."""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base if base else _state_dir() / "candidates"
        self.base.mkdir(parents=True, exist_ok=True)
        self.overlay_path = self.base / "status_overlay.json"

    def _file_for(self, when: datetime) -> Path:
        return self.base / f"{when.date().isoformat()}.jsonl"

    def append(self, candidate: Candidate) -> None:
        path = self._file_for(candidate.discovered_at)
        with path.open("a", encoding="utf-8") as f:
            f.write(candidate.model_dump_json() + "\n")

    def _load_overlay(self) -> dict[str, dict[str, Any]]:
        if not self.overlay_path.exists():
            return {}
        return json.loads(self.overlay_path.read_text(encoding="utf-8"))

    def _save_overlay(self, overlay: dict[str, dict[str, Any]]) -> None:
        atomic_write(self.overlay_path, json.dumps(overlay, indent=2, sort_keys=True))

    def _apply_overlay(self, c: Candidate) -> Candidate:
        overlay = self._load_overlay()
        update = overlay.get(c.id)
        if update is None:
            return c
        # Re-validate by merging fields
        merged = c.model_dump()
        merged.update(update)
        return Candidate.model_validate(merged)

    def list_since(self, since: datetime) -> Iterator[Candidate]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        cutoff_date = since.date()
        for path in sorted(self.base.glob("*.jsonl")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < cutoff_date:
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = Candidate.model_validate_json(line)
                    if c.discovered_at >= since:
                        yield self._apply_overlay(c)

    def list_today(self) -> Iterator[Candidate]:
        today_start = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self.list_since(today_start)

    def get(self, candidate_id: str) -> Candidate | None:
        for path in sorted(self.base.glob("*.jsonl"), reverse=True):
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = Candidate.model_validate_json(line)
                    if c.id == candidate_id:
                        return self._apply_overlay(c)
        return None

    def update_status(
        self, candidate_id: str, *, status: str, notes: str | None = None
    ) -> None:
        overlay = self._load_overlay()
        existing = overlay.get(candidate_id, {})
        existing["status"] = status
        if notes is not None:
            existing["notes"] = notes
        overlay[candidate_id] = existing
        self._save_overlay(overlay)
```

- [ ] **Step 6: Run tests, confirm pass**

```bash
uv run pytest tests/test_candidate_model.py tests/test_candidate_store.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 7: Commit**

```bash
git add python/tools/af_expert/src/af_expert/candidate/ python/tools/af_expert/tests/test_candidate_model.py python/tools/af_expert/tests/test_candidate_store.py
git commit -m "feat(af-expert): candidate model + JSONL store with status overlay"
```

---

## Task 10: Strategy base + candidate ranker

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/strategies/base.py`
- Create: `python/tools/af_expert/src/af_expert/candidate/ranker.py`
- Test: `python/tools/af_expert/tests/test_candidate_ranker.py`

- [ ] **Step 1: Write `src/af_expert/strategies/__init__.py`**

```python
```

- [ ] **Step 2: Write `src/af_expert/strategies/base.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.config import Config
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM


@dataclass
class IngestionDeltas:
    """Container for what changed in this tick.

    For Wave 1 we only need to know which repos had new merged PRs.
    Future strategies may need more (releases, architecture changes, etc.).
    """
    since: datetime
    repos_with_new_prs: list[str]


class Strategy(ABC):
    name: str

    def __init__(
        self,
        *,
        config: Config,
        events: EventStore,
        candidates: CandidateStore,
        llm: LLM,
    ) -> None:
        self.config = config
        self.events = events
        self.candidates = candidates
        self.llm = llm

    @abstractmethod
    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        """Called after the daily tick finishes ingestion. Return new candidates."""

    def on_weekly_tick(self) -> list[Candidate]:
        """Override for strategies that run weekly (e.g., S5). Default: no-op."""
        return []

    def on_demand(self, args: dict[str, object]) -> list[Candidate]:
        """Override for strategies that support operator-initiated runs. Default: no-op."""
        return []
```

- [ ] **Step 3: Write failing tests for ranker**

`tests/test_candidate_ranker.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.ranker import RankWeights, rank_candidates


def _candidate(**overrides: object) -> Candidate:
    base = dict(
        id="c-1",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="x/y",
        category="bug",
        title="t",
        description="d",
        suggested_action="a",
        confidence=0.5,
        novelty=0.5,
        actionability=0.5,
        strategy_reputation=0.5,
        status="new",
    )
    base.update(overrides)
    return Candidate(**base)


def test_higher_confidence_ranks_higher() -> None:
    a = _candidate(id="a", confidence=0.9)
    b = _candidate(id="b", confidence=0.3)
    ranked = rank_candidates([a, b])
    assert [c.id for c in ranked] == ["a", "b"]


def test_priority_high_boosts_score() -> None:
    a = _candidate(id="a", target_repo="microsoft/agent-framework")
    b = _candidate(id="b", target_repo="random/other", confidence=0.55)
    priority = {"microsoft/agent-framework": "high", "random/other": "normal"}
    ranked = rank_candidates([a, b], repo_priority=priority)
    assert ranked[0].id == "a"


def test_custom_weights_change_ordering() -> None:
    high_nov = _candidate(id="hn", confidence=0.4, novelty=0.95, actionability=0.3)
    high_act = _candidate(id="ha", confidence=0.4, novelty=0.3, actionability=0.95)

    novelty_weights = RankWeights(w_conf=0.1, w_nov=0.7, w_act=0.1, w_rep=0.1, w_pri=0.0)
    ranked = rank_candidates([high_nov, high_act], weights=novelty_weights)
    assert ranked[0].id == "hn"

    actionability_weights = RankWeights(w_conf=0.1, w_nov=0.1, w_act=0.7, w_rep=0.1, w_pri=0.0)
    ranked2 = rank_candidates([high_nov, high_act], weights=actionability_weights)
    assert ranked2[0].id == "ha"
```

- [ ] **Step 4: Write `src/af_expert/candidate/ranker.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from af_expert.candidate.model import Candidate


PRIORITY_WEIGHTS = {"high": 1.0, "normal": 0.5, "low": 0.0}


@dataclass(frozen=True)
class RankWeights:
    w_conf: float = 0.35
    w_nov: float = 0.20
    w_act: float = 0.25
    w_rep: float = 0.15
    w_pri: float = 0.05


def score_candidate(
    c: Candidate, weights: RankWeights, repo_priority: dict[str, str] | None = None
) -> float:
    pri_value = 0.5
    if repo_priority is not None:
        priority = repo_priority.get(c.target_repo, "normal")
        pri_value = PRIORITY_WEIGHTS.get(priority, 0.5)
    return (
        weights.w_conf * c.confidence
        + weights.w_nov * c.novelty
        + weights.w_act * c.actionability
        + weights.w_rep * c.strategy_reputation
        + weights.w_pri * pri_value
    )


def rank_candidates(
    candidates: list[Candidate],
    *,
    weights: RankWeights | None = None,
    repo_priority: dict[str, str] | None = None,
) -> list[Candidate]:
    if weights is None:
        weights = RankWeights()
    return sorted(
        candidates,
        key=lambda c: score_candidate(c, weights, repo_priority),
        reverse=True,
    )
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run pytest tests/test_candidate_ranker.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add python/tools/af_expert/src/af_expert/strategies/__init__.py python/tools/af_expert/src/af_expert/strategies/base.py python/tools/af_expert/src/af_expert/candidate/ranker.py python/tools/af_expert/tests/test_candidate_ranker.py
git commit -m "feat(af-expert): strategy base ABC + candidate ranker"
```

---

## Task 11: Strategy S1 — 跨仓 PR 移植

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s1_pr_forward_port.py`
- Test: `python/tools/af_expert/tests/test_strategy_s1.py`

Implementation has two LLM phases:
1. **Extract pattern** from a fix-PR's diff + body → structured `{pattern_name, failure_mode, code_shape_hints, fix_shape_hints}`
2. **Apply pattern** to each other tracked repo → ask LLM whether the same shape exists (given the repo's recent file list / a narrowed file list)

For Wave 1, "narrowed file list" is just the repo's top-level python module index — we don't yet have architecture briefings to consult. This is intentional: S1 in Wave 1 produces lower-confidence candidates but proves the loop.

- [ ] **Step 1: Write failing tests**

`tests/test_strategy_s1.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s1_pr_forward_port import (
    BugPattern,
    PRForwardPortStrategy,
    extract_pattern_prompt,
    is_likely_bug_fix,
)


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_is_likely_bug_fix_title_match() -> None:
    assert is_likely_bug_fix(title="fix: skip orphan thinking", labels=[]) is True
    assert is_likely_bug_fix(title="fix(scope): handle X", labels=[]) is True
    assert is_likely_bug_fix(title="bug: ...", labels=[]) is True


def test_is_likely_bug_fix_label_match() -> None:
    assert is_likely_bug_fix(title="generic title", labels=["bug"]) is True
    assert is_likely_bug_fix(title="generic title", labels=["fix", "p1"]) is True


def test_is_likely_bug_fix_no_match() -> None:
    assert is_likely_bug_fix(title="feat: add x", labels=["enhancement"]) is False
    assert is_likely_bug_fix(title="docs: update README", labels=[]) is False


def test_extract_pattern_prompt_includes_diff_and_title() -> None:
    prompt = extract_pattern_prompt(
        title="fix: orphan thinking",
        body="Fixes #5783",
        diff="diff --git a/foo b/foo\n+x\n",
    )
    assert "fix: orphan thinking" in prompt
    assert "diff --git" in prompt
    assert "Fixes #5783" in prompt


def _make_pr(repo: str, number: int) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="pr",
        number=number,
        title="fix: orphan Anthropic thinking signatures",
        body="Fixes #5783. The serializer no longer emits null thinking blocks.",
        diff="diff --git a/x.py b/x.py\n+    if thinking is None:\n+        continue\n",
        author="he-yufeng",
        state="merged",
        labels=["bug"],
        created_at=datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        merged_at=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        url=f"https://github.com/{repo}/pull/{number}",
    )


def test_strategy_skips_non_bug_fix_prs(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    feat_pr = _make_pr("microsoft/agent-framework", 5778)
    feat_pr.title = "feat: add Magentic"
    feat_pr.labels = ["enhancement"]
    events.insert(feat_pr)

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    cfg = _config_for(["microsoft/agent-framework", "pydantic/pydantic-ai"])
    strat = PRForwardPortStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_emits_candidates_when_pattern_matches(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    events.insert(_make_pr("microsoft/agent-framework", 5784))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    # First LLM call: extract pattern
    pattern_response = LLMResponse(
        text='```json\n{"pattern_name": "Anthropic orphan thinking", "failure_mode": "...", "code_shape_hints": ["serialize"], "fix_shape_hints": ["filter null"]}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    # Per-repo matching calls
    match_response = LLMResponse(
        text='```json\n{"matches": true, "confidence": 0.75, "target_files": ["src/foo.py"], "reasoning": "looks similar"}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    no_match_response = LLMResponse(
        text='```json\n{"matches": false, "confidence": 0.1, "target_files": [], "reasoning": "no analog"}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm.complete.side_effect = [pattern_response, match_response, no_match_response]

    cfg = _config_for(["microsoft/agent-framework", "pydantic/pydantic-ai", "google/adk-python"])
    strat = PRForwardPortStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        confidence_threshold=0.5,
    )

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 12, 0, 0, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)

    assert len(produced) == 1
    c = produced[0]
    assert c.strategy == "s1_pr_forward_port"
    assert c.target_repo == "pydantic/pydantic-ai"
    assert c.confidence == 0.75
    assert "microsoft/agent-framework" in c.evidence_urls[0]
    # Self-reference excluded (source repo not scanned)
    assert all("microsoft/agent-framework" != x for x in [c.target_repo])
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_strategy_s1.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/strategies/s1_pr_forward_port.py`**

```python
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

# Heuristic: title looks like a bug fix
_FIX_TITLE_PATTERN = re.compile(r"^(fix|bug|hotfix)[\(:]", re.IGNORECASE)
_BUG_LABELS = {"bug", "fix", "p0", "p1", "regression"}


def is_likely_bug_fix(title: str, labels: list[str]) -> bool:
    if _FIX_TITLE_PATTERN.search(title or ""):
        return True
    if any(lab.lower() in _BUG_LABELS for lab in labels):
        return True
    if title and title.lower().startswith("bug"):
        return True
    return False


@dataclass(frozen=True)
class BugPattern:
    pattern_name: str
    failure_mode: str
    code_shape_hints: list[str]
    fix_shape_hints: list[str]


def extract_pattern_prompt(*, title: str, body: str, diff: str) -> str:
    return (
        "You will be given the title, body, and diff of a merged bug-fix PR.\n"
        "Extract the bug pattern as JSON with these fields:\n"
        "- pattern_name: a short identifier (snake_case)\n"
        "- failure_mode: one-paragraph description of what was broken and why\n"
        "- code_shape_hints: list of 3-6 short strings describing what to grep for in another codebase\n"
        "- fix_shape_hints: list of 2-4 short strings describing the shape of a fix\n\n"
        "Respond with ONLY the JSON in a fenced ```json block.\n\n"
        f"TITLE:\n{title}\n\n"
        f"BODY:\n{body}\n\n"
        f"DIFF:\n{diff[:8000]}\n"
    )


def match_prompt(*, pattern: BugPattern, target_repo: str) -> str:
    return (
        f"You are checking whether a bug pattern exists in repository {target_repo}.\n\n"
        f"Pattern name: {pattern.pattern_name}\n"
        f"Failure mode: {pattern.failure_mode}\n"
        f"What to look for: {', '.join(pattern.code_shape_hints)}\n"
        f"What a fix would look like: {', '.join(pattern.fix_shape_hints)}\n\n"
        "Based on your training-time knowledge of this repository's structure "
        "(do NOT fabricate exact line numbers; only mention file paths you actually recall), "
        "decide whether the same bug shape is plausibly present.\n\n"
        "Respond with ONLY a fenced ```json block with fields:\n"
        "- matches: true | false\n"
        "- confidence: float 0.0-1.0 (be conservative; default 0.3 if uncertain)\n"
        "- target_files: list of likely file paths (use [] if uncertain)\n"
        "- reasoning: 2-3 sentences\n"
    )


class PRForwardPortStrategy(Strategy):
    name = "s1_pr_forward_port"

    def __init__(
        self,
        *args: Any,
        confidence_threshold: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.confidence_threshold = confidence_threshold

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []
        all_repos = [r.owner_repo for r in self.config.repos]

        for source_repo in deltas.repos_with_new_prs:
            for pr in self.events.query_recent_prs(source_repo, since=deltas.since, only_merged=True):
                labels = self._parse_labels(pr["labels"])
                if not is_likely_bug_fix(pr["title"], labels):
                    continue
                pattern = self._extract_pattern(pr)
                if pattern is None:
                    continue

                for target_repo in all_repos:
                    if target_repo == source_repo:
                        continue
                    match = self._match_in_repo(pattern, target_repo)
                    if match is None:
                        continue
                    if not match.get("matches"):
                        continue
                    conf = float(match.get("confidence", 0.0))
                    if conf < self.confidence_threshold:
                        continue
                    candidate = self._build_candidate(
                        source_repo=source_repo,
                        source_pr=pr,
                        target_repo=target_repo,
                        pattern=pattern,
                        match=match,
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _parse_labels(self, raw: Any) -> list[str]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            import json
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return []

    def _extract_pattern(self, pr: dict[str, Any]) -> BugPattern | None:
        prompt = extract_pattern_prompt(
            title=pr["title"], body=pr.get("body") or "", diff=pr.get("diff") or ""
        )
        try:
            resp = self.llm.complete(
                system="You are a senior engineer who extracts bug patterns from PR diffs.",
                user=prompt,
            )
            data = parse_json_block(resp.text)
            return BugPattern(
                pattern_name=data["pattern_name"],
                failure_mode=data["failure_mode"],
                code_shape_hints=list(data.get("code_shape_hints", [])),
                fix_shape_hints=list(data.get("fix_shape_hints", [])),
            )
        except Exception as e:
            log.warning("Pattern extraction failed for %s#%d: %s", pr["repo"], pr["number"], e)
            return None

    def _match_in_repo(self, pattern: BugPattern, target_repo: str) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are evaluating whether a known bug pattern exists in a given repository.",
                user=match_prompt(pattern=pattern, target_repo=target_repo),
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("Match check failed for %s: %s", target_repo, e)
            return None

    def _build_candidate(
        self,
        *,
        source_repo: str,
        source_pr: dict[str, Any],
        target_repo: str,
        pattern: BugPattern,
        match: dict[str, Any],
    ) -> Candidate:
        return Candidate(
            id=f"s1-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=target_repo,
            target_files=list(match.get("target_files", [])),
            category="bug",
            title=f"Possible {pattern.pattern_name} in {target_repo}",
            description=(
                f"Pattern: {pattern.pattern_name}\n\n"
                f"Failure mode: {pattern.failure_mode}\n\n"
                f"Reasoning: {match.get('reasoning', '')}\n\n"
                f"Source PR (already merged): {source_repo}#{source_pr['number']}"
            ),
            suggested_action=f"Port the fix shape from {source_repo}#{source_pr['number']}: "
            + "; ".join(pattern.fix_shape_hints),
            evidence_urls=[source_pr.get("url", "")],
            evidence_snippets=[],
            confidence=float(match.get("confidence", 0.0)),
            novelty=0.3,
            actionability=0.75,
            strategy_reputation=0.5,
            status="new",
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_strategy_s1.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/strategies/s1_pr_forward_port.py python/tools/af_expert/tests/test_strategy_s1.py
git commit -m "feat(af-expert): S1 cross-repo PR forward-port strategy"
```

---

## Task 12: Strategy S8 — Issue 考古

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s8_issue_archaeology.py`
- Test: `python/tools/af_expert/tests/test_strategy_s8.py`

S8 runs on demand (not every tick). Operator calls `af-expert tick --include-archaeology` or `af-expert strategy run s8 --repo X`. The strategy pulls closed `wontfix` / `stale` / `not-planned` issues from the last 6-36 months and asks the LLM whether each is more tractable today.

- [ ] **Step 1: Write failing tests**

`tests/test_strategy_s8.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.s8_issue_archaeology import IssueArchaeologyStrategy


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def _make_issue(repo: str, number: int, labels: list[str], closed_at: datetime) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="issue",
        number=number,
        title="thread-safe state mutation across coroutines",
        body="When using ContextVar-style mutation, ...",
        author="someuser",
        state="closed",
        labels=labels,
        created_at=closed_at,
        updated_at=closed_at,
        closed_at=closed_at,
        url=f"https://github.com/{repo}/issues/{number}",
    )


def test_strategy_finds_tractable_archaeology(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    events.insert(_make_issue("microsoft/agent-framework", 100, ["wontfix"], datetime(2024, 6, 1, tzinfo=timezone.utc)))
    events.insert(_make_issue("microsoft/agent-framework", 101, ["stale"], datetime(2025, 1, 1, tzinfo=timezone.utc)))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    tractable_resp = LLMResponse(
        text='```json\n{"tractable": true, "confidence": 0.7, "reasoning": "asyncio context vars exist now"}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    untractable_resp = LLMResponse(
        text='```json\n{"tractable": false, "confidence": 0.2, "reasoning": "unchanged"}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm.complete.side_effect = [tractable_resp, untractable_resp]

    cfg = _config_for(["microsoft/agent-framework"])
    strat = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_demand({"repo": "microsoft/agent-framework"})

    assert len(produced) == 1
    assert produced[0].category == "bug"
    assert "issues/100" in produced[0].evidence_urls[0]


def test_strategy_skips_when_no_archived_issues(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config_for(["microsoft/agent-framework"])
    strat = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_demand({"repo": "microsoft/agent-framework"})
    assert produced == []
    llm.complete.assert_not_called()
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_strategy_s8.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/strategies/s8_issue_archaeology.py`**

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

ARCHAEOLOGY_LABELS = ["wontfix", "stale", "not-planned"]
DEFAULT_MIN_AGE_DAYS = 180
DEFAULT_MAX_AGE_DAYS = 365 * 3


def archaeology_prompt(*, repo: str, issue: dict[str, Any]) -> str:
    return (
        f"You are evaluating whether a closed/wontfix issue in {repo} is more tractable today.\n\n"
        f"Issue #{issue['number']}: {issue['title']}\n"
        f"Closed at: {issue['closed_at']}\n"
        f"Labels: {issue['labels']}\n\n"
        f"Body:\n{(issue.get('body') or '')[:4000]}\n\n"
        "Consider: have new tools, language features, libraries, or ecosystem patterns "
        "emerged since this issue was closed that would make it tractable now?\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- tractable: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class IssueArchaeologyStrategy(Strategy):
    name = "s8_issue_archaeology"

    def __init__(
        self,
        *args: Any,
        min_age_days: int = DEFAULT_MIN_AGE_DAYS,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        confidence_threshold: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.min_age_days = min_age_days
        self.max_age_days = max_age_days
        self.confidence_threshold = confidence_threshold

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        # Archaeology runs on-demand, not on every tick
        return []

    def on_demand(self, args: dict[str, object]) -> list[Candidate]:
        target_repo = args.get("repo")
        if not isinstance(target_repo, str):
            return []

        now = datetime.now(tz=timezone.utc)
        oldest_age = now - timedelta(days=self.max_age_days)
        newest_age = now - timedelta(days=self.min_age_days)

        produced: list[Candidate] = []
        for issue in self.events.query_closed_issues(
            target_repo, before=newest_age, labels_any_of=ARCHAEOLOGY_LABELS
        ):
            closed_at = datetime.fromisoformat(issue["closed_at"]) if issue["closed_at"] else None
            if closed_at is None or closed_at < oldest_age:
                continue

            verdict = self._evaluate(target_repo, issue)
            if verdict is None:
                continue
            if not verdict.get("tractable"):
                continue
            conf = float(verdict.get("confidence", 0.0))
            if conf < self.confidence_threshold:
                continue

            candidate = self._build_candidate(target_repo, issue, verdict)
            self.candidates.append(candidate)
            produced.append(candidate)
        return produced

    def _evaluate(self, repo: str, issue: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are an OSS contributor evaluating closed issues for re-opening.",
                user=archaeology_prompt(repo=repo, issue=issue),
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("Archaeology eval failed for %s#%s: %s", repo, issue.get("number"), e)
            return None

    def _build_candidate(
        self, repo: str, issue: dict[str, Any], verdict: dict[str, Any]
    ) -> Candidate:
        return Candidate(
            id=f"s8-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="bug",
            title=f"Reopen candidate: {issue['title']}",
            description=(
                f"This issue was closed/wontfix at {issue['closed_at']}. "
                f"Reasoning: {verdict.get('reasoning', '')}"
            ),
            suggested_action=(
                "Comment on the original issue asking whether maintainers would accept "
                "a re-opened attempt given current ecosystem state, then proceed if positive."
            ),
            evidence_urls=[issue["url"]],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.0)),
            novelty=0.6,
            actionability=0.4,
            strategy_reputation=0.5,
            status="new",
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_strategy_s8.py -v
```

Expected: all 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/strategies/s8_issue_archaeology.py python/tools/af_expert/tests/test_strategy_s8.py
git commit -m "feat(af-expert): S8 issue archaeology strategy"
```

---

## Task 13: Candidate export for af-fix handoff

**Files:**
- Create: `python/tools/af_expert/src/af_expert/candidate/export.py`
- Test: `python/tools/af_expert/tests/test_candidate_export.py`

Produces a markdown spec file that af-fix can consume (once af-fix's `--candidate-spec` extension lands; for Wave 1 the file is operator-facing).

- [ ] **Step 1: Write failing tests**

`tests/test_candidate_export.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from af_expert.candidate.export import render_candidate_spec
from af_expert.candidate.model import Candidate


def test_render_includes_essential_fields() -> None:
    c = Candidate(
        id="c-001",
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        target_files=["src/x.py"],
        category="bug",
        title="Possible orphan signature",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only blocks",
        evidence_urls=["https://github.com/microsoft/agent-framework/pull/5784"],
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )
    md = render_candidate_spec(c)
    assert "# Candidate c-001" in md
    assert "**Repo:** pydantic/pydantic-ai" in md
    assert "**Strategy:** s1_pr_forward_port" in md
    assert "Filter signature-only blocks" in md
    assert "https://github.com/microsoft/agent-framework/pull/5784" in md
    assert "src/x.py" in md
```

- [ ] **Step 2: Run test, confirm failure**

```bash
uv run pytest tests/test_candidate_export.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/candidate/export.py`**

```python
from __future__ import annotations

from af_expert.candidate.model import Candidate


def render_candidate_spec(c: Candidate) -> str:
    lines: list[str] = []
    lines.append(f"# Candidate {c.id}")
    lines.append("")
    lines.append(f"**Repo:** {c.target_repo}")
    lines.append(f"**Strategy:** {c.strategy}")
    lines.append(f"**Category:** {c.category}")
    lines.append(f"**Confidence:** {c.confidence:.2f}")
    lines.append(f"**Discovered:** {c.discovered_at.isoformat()}")
    lines.append(f"**Title:** {c.title}")
    lines.append("")
    lines.append("## Description")
    lines.append(c.description)
    lines.append("")
    if c.target_files:
        lines.append("## Target")
        for path in c.target_files:
            lines.append(f"- `{path}`")
        lines.append("")
    if c.evidence_urls or c.evidence_snippets:
        lines.append("## Evidence")
        for url in c.evidence_urls:
            lines.append(f"- {url}")
        for snip in c.evidence_snippets:
            lines.append("```")
            lines.append(snip)
            lines.append("```")
        lines.append("")
    lines.append("## Suggested action")
    lines.append(c.suggested_action)
    lines.append("")
    if c.notes:
        lines.append("## Operator notes")
        lines.append(c.notes)
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test, confirm pass**

```bash
uv run pytest tests/test_candidate_export.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/candidate/export.py python/tools/af_expert/tests/test_candidate_export.py
git commit -m "feat(af-expert): candidate → markdown spec export for af-fix handoff"
```

---

## Task 14: Query — digest renderer

**Files:**
- Create: `python/tools/af_expert/src/af_expert/query/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/query/digest.py`
- Test: `python/tools/af_expert/tests/test_query_digest.py`

Daily digest. Reads ingestion state + new candidates, renders a markdown summary.

- [ ] **Step 1: Write failing tests**

`tests/test_query_digest.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from af_expert.candidate.model import Candidate
from af_expert.query.digest import render_digest


def _make_candidate(cid: str, repo: str, strategy: str, confidence: float) -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime.now(tz=timezone.utc),
        strategy=strategy,
        target_repo=repo,
        category="bug",
        title=f"Issue in {repo}",
        description="d",
        suggested_action="a",
        confidence=confidence,
        novelty=0.5,
        actionability=0.5,
        strategy_reputation=0.5,
        status="new",
    )


def test_digest_shows_counts_by_strategy_and_repo() -> None:
    candidates = [
        _make_candidate("c-1", "pydantic/pydantic-ai", "s1_pr_forward_port", 0.7),
        _make_candidate("c-2", "google/adk-python", "s1_pr_forward_port", 0.6),
        _make_candidate("c-3", "microsoft/agent-framework", "s8_issue_archaeology", 0.8),
    ]
    md = render_digest(
        since=datetime.now(tz=timezone.utc) - timedelta(days=1),
        candidates=candidates,
        ingestion_summary={"repos_succeeded": 3, "repos_failed": 0, "new_events": 12},
    )
    assert "3 new candidates" in md
    assert "s1_pr_forward_port" in md
    assert "s8_issue_archaeology" in md
    assert "pydantic/pydantic-ai" in md


def test_digest_with_no_candidates() -> None:
    md = render_digest(
        since=datetime.now(tz=timezone.utc) - timedelta(days=1),
        candidates=[],
        ingestion_summary={"repos_succeeded": 2, "repos_failed": 1, "new_events": 0},
    )
    assert "0 new candidates" in md or "No candidates" in md
    assert "1 repo failed" in md or "1 failed" in md
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_query_digest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/query/__init__.py`**

```python
```

- [ ] **Step 4: Write `src/af_expert/query/digest.py`**

```python
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from af_expert.candidate.model import Candidate


def render_digest(
    *,
    since: datetime,
    candidates: list[Candidate],
    ingestion_summary: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# af-expert digest — since {since.isoformat()}")
    lines.append("")

    if ingestion_summary:
        succ = ingestion_summary.get("repos_succeeded", 0)
        fail = ingestion_summary.get("repos_failed", 0)
        events = ingestion_summary.get("new_events", 0)
        lines.append(f"**Ingestion:** {succ} repos succeeded, {fail} repo(s) failed, {events} new events")
        lines.append("")

    lines.append(f"## {len(candidates)} new candidates")
    lines.append("")

    if not candidates:
        lines.append("No candidates produced in this window.")
        return "\n".join(lines)

    by_strategy = Counter(c.strategy for c in candidates)
    by_repo = Counter(c.target_repo for c in candidates)

    lines.append("### By strategy")
    for strategy, count in by_strategy.most_common():
        lines.append(f"- `{strategy}`: {count}")
    lines.append("")

    lines.append("### By target repo (top 10)")
    for repo, count in by_repo.most_common(10):
        lines.append(f"- `{repo}`: {count}")
    lines.append("")

    lines.append("### Top 5 by confidence")
    top = sorted(candidates, key=lambda c: c.confidence, reverse=True)[:5]
    for c in top:
        lines.append(f"- **{c.id}** ({c.confidence:.2f}) `{c.target_repo}` — {c.title}")
    lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run pytest tests/test_query_digest.py -v
```

Expected: all 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add python/tools/af_expert/src/af_expert/query/__init__.py python/tools/af_expert/src/af_expert/query/digest.py python/tools/af_expert/tests/test_query_digest.py
git commit -m "feat(af-expert): daily digest renderer"
```

---

## Task 15: Query — ask command

**Files:**
- Create: `python/tools/af_expert/src/af_expert/query/ask.py`
- Test: `python/tools/af_expert/tests/test_query_ask.py`

Conversational query. For Wave 1, builds context from: today's candidates, last 7 days of events (FTS-searched against the question keywords), and per-repo titles. No architecture briefings yet (Wave 2).

- [ ] **Step 1: Write failing tests**

`tests/test_query_ask.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.query.ask import answer


def _make_candidate(cid: str = "c-1") -> Candidate:
    return Candidate(
        id=cid,
        discovered_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        strategy="s1_pr_forward_port",
        target_repo="pydantic/pydantic-ai",
        category="bug",
        title="Possible orphan signature",
        description="Same shape as agent-framework#5784",
        suggested_action="Filter signature-only blocks",
        confidence=0.7,
        novelty=0.3,
        actionability=0.8,
        strategy_reputation=0.5,
        status="new",
    )


def test_answer_calls_llm_with_question_and_context(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    candidates.append(_make_candidate())

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text="The state of MCP support is fragmented across frameworks.",
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )

    response = answer(question="state of MCP support?", events=events, candidates=candidates, llm=llm)

    assert "MCP" in response
    call = llm.complete.call_args
    assert "state of MCP support" in call.kwargs["user"]
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_query_ask.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/query/ask.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.store import CandidateStore
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM


def _build_context(
    events: EventStore, candidates: CandidateStore, question: str
) -> str:
    since = datetime.now(tz=timezone.utc) - timedelta(days=7)
    parts: list[str] = []

    fts_hits = list(events.fts_search(question, limit=20))
    if fts_hits:
        parts.append("## Recent events matching the question")
        for hit in fts_hits:
            parts.append(
                f"- [{hit['kind']}] {hit['repo']}#{hit.get('number')} {hit['title']}"
            )
        parts.append("")

    recent_candidates = list(candidates.list_since(since))
    if recent_candidates:
        parts.append("## Recent candidates (last 7 days)")
        for c in recent_candidates:
            parts.append(
                f"- **{c.id}** ({c.confidence:.2f}) `{c.target_repo}` — {c.title}"
            )
        parts.append("")

    if not parts:
        return "No recent events or candidates available."
    return "\n".join(parts)


def answer(
    *,
    question: str,
    events: EventStore,
    candidates: CandidateStore,
    llm: LLM,
) -> str:
    context = _build_context(events, candidates, question)
    system = (
        "You are an expert in the OSS agent framework / LLM ecosystem. "
        "You answer questions based on the provided context. Do not fabricate. "
        "When you cite specific frameworks/PRs, only reference items present in the context. "
        "Keep answers under 300 words unless asked for depth."
    )
    user = f"## Question\n{question}\n\n## Context\n{context}"
    resp = llm.complete(system=system, user=user)
    return resp.text
```

- [ ] **Step 4: Run test, confirm pass**

```bash
uv run pytest tests/test_query_ask.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/query/ask.py python/tools/af_expert/tests/test_query_ask.py
git commit -m "feat(af-expert): conversational ask query"
```

---

## Task 16: CLI

**Files:**
- Create: `python/tools/af_expert/src/af_expert/cli.py`
- Test: `python/tools/af_expert/tests/test_cli.py`

`click`-based CLI. Subcommands: `init`, `tick`, `digest`, `suggest`, `ask`, `candidate show/accept/reject/export`, `strategy list/run`, `stats`.

- [ ] **Step 1: Write failing tests**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write `src/af_expert/cli.py`**

```python
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from af_expert.candidate.export import render_candidate_spec
from af_expert.candidate.ranker import RankWeights, rank_candidates
from af_expert.candidate.store import CandidateStore
from af_expert.config import _state_dir, load_config
from af_expert.github_client import GitHubClient
from af_expert.ingestion.pipeline import run_ingestion_tick
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.query.ask import answer
from af_expert.query.digest import render_digest
from af_expert.state import StateDir, load_state, save_state
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s1_pr_forward_port import PRForwardPortStrategy
from af_expert.strategies.s8_issue_archaeology import IssueArchaeologyStrategy


DEFAULT_CONFIG_BODY = """\
# af-expert config

github_token = ""          # GitHub PAT, public_repo scope
anthropic_api_key = ""     # Anthropic API key

[ingestion]
poll_interval_hours = 24
event_retention_days = 365

[architecture]
refresh_trigger = "drift"   # drift | weekly | manual
refresh_min_days = 7

# Add at least one repo entry. Use priority high/normal/low.

[[repos]]
owner_repo = "microsoft/agent-framework"
priority = "high"
languages = ["python", "csharp"]

# [[repos]]
# owner_repo = "langchain-ai/langchain"
# priority = "normal"
# languages = ["python"]
"""


@click.group()
def cli() -> None:
    """af-expert: continuously-learning domain expert for OSS agent frameworks."""


@cli.command()
def init() -> None:
    """Initialize ~/.af-expert/ with a config template."""
    sd = StateDir()
    sd.ensure_layout()
    cfg_path = sd.root / "config.toml"
    if cfg_path.exists():
        click.echo(f"Config already exists at {cfg_path}; will not overwrite.", err=True)
        sys.exit(2)
    cfg_path.write_text(DEFAULT_CONFIG_BODY)
    click.echo(f"Wrote template config to {cfg_path}")
    click.echo("Edit it, then run `af-expert tick`.")


@cli.command()
@click.option("--include-archaeology", is_flag=True, default=False)
def tick(include_archaeology: bool) -> None:
    """Run one ingestion + strategy tick."""
    cfg = load_config()
    sd = StateDir()
    sd.ensure_layout()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    gh = GitHubClient(token=cfg.github_token)
    llm = LLM(api_key=cfg.anthropic_api_key)

    with sd.lock():
        now = datetime.now(tz=timezone.utc)
        # Strategies look at events from the last 7 days regardless of where
        # individual repo cursors are. This is a Wave 1 simplification; Wave 2
        # uses per-repo deltas from architecture-change-detection.
        since = now - timedelta(days=7)

        result = run_ingestion_tick(
            cfg, gh, events, now=now, load_state=load_state, save_state=save_state
        )
        click.echo(
            f"Ingestion: {result.repos_succeeded} ok, "
            f"{result.repos_failed} failed, {result.new_events} new events"
        )

        repos_with_new_prs = [r.owner_repo for r in cfg.repos if r.owner_repo not in result.failed_repos]

        deltas = IngestionDeltas(since=since, repos_with_new_prs=repos_with_new_prs)

        s1 = PRForwardPortStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        s1_produced = s1.on_ingestion_complete(deltas)
        click.echo(f"S1 (PR forward-port) produced {len(s1_produced)} candidates")

        s8_produced: list = []
        if include_archaeology:
            s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            for repo_cfg in cfg.repos:
                s8_produced.extend(s8.on_demand({"repo": repo_cfg.owner_repo}))
            click.echo(f"S8 (issue archaeology) produced {len(s8_produced)} candidates")

        digest_md = render_digest(
            since=since,
            candidates=s1_produced + s8_produced,
            ingestion_summary={
                "repos_succeeded": result.repos_succeeded,
                "repos_failed": result.repos_failed,
                "new_events": result.new_events,
            },
        )
        digest_path = sd.root / "digests" / f"{now.date().isoformat()}.md"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(digest_md)
        click.echo(f"Digest written to {digest_path}")


@cli.command()
@click.option("--since", default="1d", help="duration like '1d', '7d', '24h'")
def digest(since: str) -> None:
    """Print or build a digest for the given window."""
    sd = StateDir()
    candidates = CandidateStore()
    now = datetime.now(tz=timezone.utc)
    delta = _parse_duration(since)
    since_dt = now - delta
    cs = list(candidates.list_since(since_dt))
    md = render_digest(since=since_dt, candidates=cs)
    click.echo(md)


@cli.command()
@click.option("--strategy", default=None)
@click.option("--top", default=10, type=int)
def suggest(strategy: str | None, top: int) -> None:
    """Show top-N candidates by ranker score."""
    cfg = load_config()
    candidates = CandidateStore()
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)
    pool = list(candidates.list_since(since))
    if strategy:
        pool = [c for c in pool if c.strategy == strategy]
    repo_priority = {r.owner_repo: r.priority for r in cfg.repos}
    ranked = rank_candidates(pool, repo_priority=repo_priority)
    for c in ranked[:top]:
        click.echo(f"{c.id}\t{c.confidence:.2f}\t{c.target_repo}\t{c.title}")


@cli.command()
@click.argument("question")
def ask(question: str) -> None:
    """Ask a natural-language question."""
    cfg = load_config()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    click.echo(answer(question=question, events=events, candidates=candidates, llm=llm))


@cli.group()
def candidate() -> None:
    """Candidate management."""


@candidate.command("show")
@click.argument("candidate_id")
def candidate_show(candidate_id: str) -> None:
    store = CandidateStore()
    c = store.get(candidate_id)
    if c is None:
        click.echo(f"Candidate {candidate_id} not found", err=True)
        sys.exit(2)
    click.echo(c.model_dump_json(indent=2))


@candidate.command("accept")
@click.argument("candidate_id")
@click.option("--notes", default="")
def candidate_accept(candidate_id: str, notes: str) -> None:
    store = CandidateStore()
    store.update_status(candidate_id, status="accepted", notes=notes)
    click.echo(f"Marked {candidate_id} as accepted")


@candidate.command("reject")
@click.argument("candidate_id")
@click.option("--notes", default="")
def candidate_reject(candidate_id: str, notes: str) -> None:
    store = CandidateStore()
    store.update_status(candidate_id, status="rejected", notes=notes)
    click.echo(f"Marked {candidate_id} as rejected")


@candidate.command("export")
@click.argument("candidate_id")
def candidate_export(candidate_id: str) -> None:
    store = CandidateStore()
    c = store.get(candidate_id)
    if c is None:
        click.echo(f"Candidate {candidate_id} not found", err=True)
        sys.exit(2)
    click.echo(render_candidate_spec(c))


@cli.group()
def strategy() -> None:
    """Strategy management."""


@strategy.command("list")
def strategy_list() -> None:
    click.echo("Enabled strategies (Wave 1):")
    click.echo("  s1_pr_forward_port")
    click.echo("  s8_issue_archaeology  (on-demand only)")


@strategy.command("run")
@click.argument("name")
@click.option("--repo", default=None)
def strategy_run(name: str, repo: str | None) -> None:
    cfg = load_config()
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    if name == "s8_issue_archaeology":
        s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        targets = [repo] if repo else [r.owner_repo for r in cfg.repos]
        total = 0
        for r in targets:
            produced = s8.on_demand({"repo": r})
            total += len(produced)
            click.echo(f"{r}: {len(produced)} candidates")
        click.echo(f"Total: {total}")
    else:
        click.echo(f"Strategy '{name}' is not on-demand-runnable in Wave 1", err=True)
        sys.exit(2)


@cli.command()
def stats() -> None:
    """Show summary stats."""
    state = load_state()
    cursors = state.get("cursors", {})
    click.echo(f"Tracked repos with cursors: {len(cursors)}")
    for repo, ts in sorted(cursors.items()):
        click.echo(f"  {repo}\t{ts}")


def _parse_duration(s: str) -> timedelta:
    s = s.strip().lower()
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=int(s[:-1]))
    raise click.UsageError(f"Cannot parse duration: {s!r}")
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Verify CLI invokes end-to-end (no network)**

```bash
cd python/tools/af_expert
uv run af-expert --help
uv run af-expert strategy list
```

Expected: help text prints; `strategy list` shows S1 and S8.

- [ ] **Step 6: Commit**

```bash
git add python/tools/af_expert/src/af_expert/cli.py python/tools/af_expert/tests/test_cli.py
git commit -m "feat(af-expert): click CLI with tick/digest/suggest/ask/candidate/strategy"
```

---

## Task 17: E2E smoke test (manual, gated)

**Files:**
- Create: `python/tools/af_expert/tests/e2e/__init__.py`
- Create: `python/tools/af_expert/tests/e2e/test_smoke.py`

Single test that runs the full pipeline against 2 small real repos using real API keys. Marked `@pytest.mark.e2e` so it never runs in CI; operator runs it manually.

- [ ] **Step 1: Write `tests/e2e/__init__.py`** (empty)

```python
```

- [ ] **Step 2: Write `tests/e2e/test_smoke.py`**

```python
from __future__ import annotations

import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_expert.cli import cli
from click.testing import CliRunner


@pytest.mark.e2e
def test_e2e_tick_produces_at_least_ingestion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run a real tick against 2 small real repos. Verifies ingestion + S1 loop end-to-end."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("GITHUB_TOKEN"):
        pytest.skip("Set ANTHROPIC_API_KEY and GITHUB_TOKEN to run e2e smoke")

    state_dir = tmp_path / "af-expert"
    state_dir.mkdir()
    monkeypatch.setenv("AF_EXPERT_STATE_DIR", str(state_dir))

    cfg = state_dir / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            github_token = "{os.environ['GITHUB_TOKEN']}"
            anthropic_api_key = "{os.environ['ANTHROPIC_API_KEY']}"

            [[repos]]
            owner_repo = "microsoft/agent-framework"
            priority = "high"
            languages = ["python"]

            [[repos]]
            owner_repo = "pydantic/pydantic-ai"
            priority = "normal"
            languages = ["python"]
            """
        ).strip()
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["tick"])
    assert result.exit_code == 0, result.output
    # Ingestion should have happened
    assert "Ingestion:" in result.output
```

- [ ] **Step 3: Verify it skips without keys**

```bash
unset ANTHROPIC_API_KEY GITHUB_TOKEN
uv run pytest tests/e2e/test_smoke.py -v -m e2e
```

Expected: 1 skipped.

- [ ] **Step 4: Verify ALL unit tests still pass together**

```bash
uv run pytest -v --ignore=tests/e2e
```

Expected: all unit tests pass; e2e folder ignored.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/tests/e2e/
git commit -m "test(af-expert): e2e smoke test (manual, gated by env keys)"
```

---

## Task 18: README + setup docs

**Files:**
- Modify: `python/tools/af_expert/README.md`

Replace the bootstrap README with operator-facing docs: install, config, running, troubleshooting, the wave-1-vs-future scope split.

- [ ] **Step 1: Write the full README**

```markdown
# af-expert

Continuously-learning domain expert for OSS agent framework contributions.

af-expert ingests issues/PRs/releases from configured OSS repositories
daily, runs intelligence strategies to surface contribution candidates,
and produces a ranked candidate list you can review.

For end-to-end fixing+PRs of the candidates you select, pipe them to
[af-fix](../af_fix/) via `af-expert candidate export <id>`.

**Status: Wave 1 (core platform + S1 + S8).**
See [spec](../../../docs/superpowers/specs/2026-05-17-af-expert-design.md)
for the full 5-wave plan.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd python/tools/af_expert
uv sync --all-extras
```

## Setup

```bash
af-expert init
$EDITOR ~/.af-expert/config.toml
```

Required fields in `config.toml`:

- `github_token` — GitHub PAT, `public_repo` scope only
- `anthropic_api_key` — Anthropic API key (Opus 4.7 access)
- At least one `[[repos]]` entry with `owner_repo = "owner/name"`

## Run

```bash
# One ingestion + strategy run
af-expert tick

# Same, also run S8 (issue archaeology) on demand
af-expert tick --include-archaeology

# View the digest for the last day
af-expert digest --since 1d

# See ranked candidates
af-expert suggest --top 10

# Drill into one candidate
af-expert candidate show s1-abc123

# Export to a markdown spec for af-fix
af-expert candidate export s1-abc123 > /tmp/spec.md

# Mark a candidate accepted/rejected after review
af-expert candidate accept s1-abc123 --notes "ported to local fork"
af-expert candidate reject s1-abc123 --notes "false positive"

# Conversational query
af-expert ask "what's the state of MCP support across frameworks?"

# Strategy management
af-expert strategy list
af-expert strategy run s8_issue_archaeology --repo microsoft/agent-framework

# Show ingestion cursors
af-expert stats
```

## State layout

```
~/.af-expert/
├── config.toml
├── state.json          # cursors per repo
├── lock                # single-process lock
├── events.db           # SQLite + FTS5 of all ingested events
├── candidates/         # per-day JSONL of candidates
├── digests/            # per-day rendered digest markdown
└── repos/<owner>__<repo>/  # per-repo briefings (Wave 2)
```

## Wave 1 limitations

- Architecture briefings: NOT YET (Wave 2). S1 currently relies on the
  LLM's training-time knowledge of each repo's structure, which means
  lower confidence than after Wave 2 builds proper briefings.
- Strategies S2-S7: NOT YET. See spec.
- No real RAG: by design — corpus fits in Opus 4.7 context.

## Troubleshooting

- `StateLockError`: another `af-expert` process is running, or a previous
  run was killed without cleanup. Remove `~/.af-expert/lock` if no other
  process is active.
- GitHub rate-limit hits: tick will report per-repo failures; rerun the
  next day or shrink your tracked repo list.
- Anthropic 429s: backoff is not yet implemented (Wave 2). For now,
  reduce tracked repos or rerun later.
```

- [ ] **Step 2: Commit**

```bash
git add python/tools/af_expert/README.md
git commit -m "docs(af-expert): operator-facing README for Wave 1"
```

---

## Wave 1 done — verification checklist

Run all checks before declaring Wave 1 complete:

- [ ] `uv run pytest -v --ignore=tests/e2e` — all unit tests pass
- [ ] `uv run af-expert --help` works
- [ ] `uv run af-expert init` creates a config in a fresh `AF_EXPERT_STATE_DIR`
- [ ] `uv run af-expert strategy list` shows both strategies
- [ ] With real keys: `uv run af-expert tick` runs against 2-3 small repos, produces a digest file, and emits at least one S1 candidate within 7 days against ≥20 configured repos (the **Wave 1 validation milestone** from the spec)

## What's NOT in Wave 1 (deferred to later plans)

These are intentional gaps. Each will be its own plan:

| Wave | Plan delivers |
|---|---|
| 2 | Architecture briefings via understand-anything; S4 (Provider release); S6 (maintainer health) |
| 3 | Concept graph + S2 (cross-repo structural) + S7 (feature propagation) |
| 4 | Hypotheses + S3 (active verification) |
| 5 | Spec corpus + S5 (conformance fuzzer) |

These plans get written when Wave 1 ships and its assumptions hold up.

The `--candidate-spec` extension to af-fix is also out of scope for this
plan; it lives in af-fix's own repo of work. Wave 1 produces export
markdown that an operator can manually feed to OpenHands without needing
the af-fix wrapper.
