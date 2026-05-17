# project-expert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin (`project-expert`) that maintains local git mirrors + LLM-generated knowledge graphs of tracked OSS projects, exposes them via a stdio MCP server, and routes project questions through a subagent that must cite `file:line` references.

**Architecture:** Standalone Python package distributed as a Claude Code plugin. Plugin code lives at `~/projects/project-expert/`; once stable it is symlinked or copied into `~/.claude/plugins/project-expert/`. Plugin code is stateless; user data lives in `~/.config/project-expert/`. MCP server exposes `projects.*` tools backed by ripgrep, AST symbol index, JSON KG, and live GitHub API. Subagent + skills + MCP all auto-register via `plugin.json`.

**Tech Stack:** Python ≥3.11, `mcp` (Anthropic's MCP SDK), `pydantic` v2, `PyGithub`, `tomli` (for 3.10 compat is optional since we require ≥3.11), `ripgrep` binary, system `git`, `understand-anything` plugin (already installed in user environment), pytest + pytest-asyncio.

**Reference spec:** [docs/superpowers/specs/2026-05-18-project-expert-design.md](../specs/2026-05-18-project-expert-design.md)

---

## Path conventions

All paths in this plan are relative to the project root `~/projects/project-expert/` unless otherwise noted. Commands are written for the Bash tool (Claude Code's Bash works on Windows via Git Bash / WSL2; alternatively PowerShell equivalents apply).

User-data paths use `~/.config/project-expert/` which is independent of the plugin code location.

---

## File Structure (locked-in)

```
~/projects/project-expert/
├── pyproject.toml
├── plugin.json
├── README.md
├── mcp/
│   └── server.py
├── agents/
│   └── project-expert.md
├── skills/
│   ├── add/SKILL.md
│   ├── remove/SKILL.md
│   ├── list/SKILL.md
│   ├── refresh/SKILL.md
│   ├── enrich/SKILL.md
│   └── ask/SKILL.md
├── scripts/
│   ├── sync.py
│   ├── kg_refresh.py
│   └── add_project.py
├── src/project_expert/
│   ├── __init__.py
│   ├── config.py
│   ├── state.py
│   ├── models.py
│   ├── mirror.py
│   ├── symbol_index.py
│   ├── search.py
│   ├── github_issues.py
│   ├── kg_runner.py
│   ├── kg_store.py
│   ├── exceptions.py
│   └── tools/
│       ├── __init__.py
│       ├── list_tool.py
│       ├── search_tool.py
│       ├── read_tool.py
│       ├── symbol_tool.py
│       ├── changelog_tool.py
│       ├── kg_tool.py
│       ├── compare_tool.py
│       ├── examples_tool.py
│       ├── issues_tool.py
│       └── refresh_tool.py
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_state.py
    ├── test_models.py
    ├── test_mirror.py
    ├── test_symbol_index.py
    ├── test_search.py
    ├── test_github_issues.py
    ├── test_kg_store.py
    ├── test_kg_runner.py
    ├── test_tool_list.py
    ├── test_tool_search.py
    ├── test_tool_read.py
    ├── test_tool_symbol.py
    ├── test_tool_changelog.py
    ├── test_tool_kg.py
    ├── test_tool_compare.py
    ├── test_tool_examples.py
    ├── test_tool_issues.py
    ├── test_tool_refresh.py
    ├── test_mcp_server.py
    └── e2e/test_smoke.py
```

---

## Task 1: Scaffold standalone package + plugin manifest

**Files:**
- Create: `~/projects/project-expert/pyproject.toml`
- Create: `~/projects/project-expert/plugin.json`
- Create: `~/projects/project-expert/README.md`
- Create: `~/projects/project-expert/src/project_expert/__init__.py`
- Create: `~/projects/project-expert/src/project_expert/exceptions.py`
- Create: `~/projects/project-expert/tests/__init__.py`
- Create: `~/projects/project-expert/tests/test_smoke_import.py`

- [ ] **Step 1: Create project directory and initialize git**

```bash
mkdir -p ~/projects/project-expert
cd ~/projects/project-expert
git init -b main
```

- [ ] **Step 2: Write the failing test**

`tests/test_smoke_import.py`:
```python
def test_package_imports() -> None:
    import project_expert
    assert project_expert.__version__ == "0.1.0"


def test_exception_hierarchy() -> None:
    from project_expert.exceptions import (
        ProjectExpertError,
        ProjectNotTracked,
        MirrorMissing,
        KGMissing,
        UpstreamUnavailable,
    )
    for cls in (ProjectNotTracked, MirrorMissing, KGMissing, UpstreamUnavailable):
        assert issubclass(cls, ProjectExpertError)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_smoke_import.py -v
```
Expected: FAIL — package does not exist yet.

- [ ] **Step 4: Create pyproject.toml**

`pyproject.toml`:
```toml
[project]
name = "project-expert"
version = "0.1.0"
description = "Claude Code plugin: turn Claude into a domain expert on tracked OSS projects."
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "mcp>=1.27.0,<2",
    "pydantic>=2,<3",
    "PyGithub>=2.5.0,<3",
    "rich>=13.7.1,<16.0.0",
]

[project.scripts]
project-expert-sync = "project_expert.scripts.sync:main"
project-expert-kg-refresh = "project_expert.scripts.kg_refresh:main"
project-expert-add = "project_expert.scripts.add_project:main"

[dependency-groups]
dev = [
    "pytest>=9.0.0",
    "pytest-asyncio>=1.3.0",
    "pytest-timeout>=2.4.0",
    "ruff>=0.15.0",
    "mypy>=1.20.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/project_expert"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 60
markers = [
    "e2e: end-to-end tests requiring real LLM and GitHub; skipped by default",
]

[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "S", "RUF", "SIM", "RET", "UP"]
ignore = ["S101"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S"]

[tool.mypy]
strict = true
python_version = "3.11"
```

- [ ] **Step 5: Create plugin.json manifest**

`plugin.json`:
```json
{
  "name": "project-expert",
  "version": "0.1.0",
  "description": "Claude becomes a domain expert on tracked OSS projects via local mirrors, knowledge graphs, and a citation-required subagent.",
  "mcp_servers": {
    "project-expert": {
      "command": "uv",
      "args": ["run", "--project", "~/projects/project-expert", "python", "-m", "project_expert.mcp.server"],
      "env": {}
    }
  },
  "agents": ["agents/project-expert.md"],
  "skills": [
    "skills/add",
    "skills/remove",
    "skills/list",
    "skills/refresh",
    "skills/enrich",
    "skills/ask"
  ]
}
```

- [ ] **Step 6: Create package skeleton**

`src/project_expert/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/project_expert/exceptions.py`:
```python
class ProjectExpertError(Exception):
    """Base exception for project-expert."""


class ProjectNotTracked(ProjectExpertError):
    """Project is not in config; user must `/project-expert:add` first."""


class MirrorMissing(ProjectExpertError):
    """Config has the project but no clone exists yet."""


class KGMissing(ProjectExpertError):
    """Project tier requires KG but none has been generated."""


class UpstreamUnavailable(ProjectExpertError):
    """GitHub API or upstream source temporarily unreachable."""


class ConfigError(ProjectExpertError):
    """Config file missing, malformed, or schema-invalid."""


class MirrorOperationError(ProjectExpertError):
    """git clone / pull / sparse-pull operation failed."""
```

`tests/__init__.py`: (empty)

`README.md`:
```markdown
# project-expert

Claude Code plugin: turn Claude into a domain expert on a configurable set of OSS projects via local mirrors, LLM-generated knowledge graphs, and a citation-required subagent.

See [the design spec](https://github.com/microsoft/agent-framework/blob/main/docs/superpowers/specs/2026-05-18-project-expert-design.md).

## Install

```bash
cd ~/projects/project-expert
uv sync
ln -s ~/projects/project-expert ~/.claude/plugins/project-expert
```

Restart Claude Code; the plugin's MCP server, subagent, and skills are auto-registered via `plugin.json`.
```

- [ ] **Step 7: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv sync && uv run pytest tests/test_smoke_import.py -v
```
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
cd ~/projects/project-expert
git add .
git commit -m "feat: scaffold project-expert plugin package"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/project_expert/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from project_expert.config import Config, ProjectConfig
from project_expert.exceptions import ConfigError


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_minimal_config(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path, """
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"

[[projects]]
repo = "microsoft/agent-framework"
tier = "deep"
""")
    cfg = Config.load(cfg_path)
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.model == "claude-opus-4-7"
    assert len(cfg.projects) == 1
    assert cfg.projects[0].repo == "microsoft/agent-framework"
    assert cfg.projects[0].tier == "deep"


def test_default_settings_applied(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path, """
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"
""")
    cfg = Config.load(cfg_path)
    assert cfg.settings.clone_depth == 200
    assert cfg.refresh.mirrors_max_age_hours == 24
    assert cfg.refresh.kg_max_age_days == 7
    assert cfg.refresh.kg_force_on_drift_commits == 50


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        Config.load(tmp_path / "nope.toml")


def test_invalid_tier_raises(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path, """
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"

[[projects]]
repo = "microsoft/agent-framework"
tier = "bogus"
""")
    with pytest.raises(ConfigError, match="tier"):
        Config.load(cfg_path)


def test_find_project_by_repo_or_nickname(tmp_path: Path) -> None:
    cfg_path = _write_config(tmp_path, """
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"

[[projects]]
repo = "microsoft/agent-framework"
nickname = "af"
tier = "deep"
""")
    cfg = Config.load(cfg_path)
    assert cfg.find_project("microsoft/agent-framework").repo == "microsoft/agent-framework"
    assert cfg.find_project("af").repo == "microsoft/agent-framework"
    assert cfg.find_project("does/not-exist") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_config.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'project_expert.config'`.

- [ ] **Step 3: Implement Config**

`src/project_expert/config.py`:
```python
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from project_expert.exceptions import ConfigError

Tier = Literal["deep", "mirror_only", "docs_only"]
Provider = Literal["anthropic", "openai", "azure_openai"]


class SettingsConfig(BaseModel):
    mirrors_dir: Path = Path("~/.config/project-expert/data/mirrors").expanduser()
    kg_dir: Path = Path("~/.config/project-expert/data/kg").expanduser()
    index_dir: Path = Path("~/.config/project-expert/data/index").expanduser()
    clone_depth: int = 200
    default_branch_fallback: str = "main"


class LLMConfig(BaseModel):
    provider: Provider
    model: str
    api_key_env: str | None = None
    api_key_file: Path | None = None


class RefreshConfig(BaseModel):
    mirrors_max_age_hours: int = 24
    kg_max_age_days: int = 7
    kg_force_on_drift_commits: int = 50


class ProjectConfig(BaseModel):
    repo: str = Field(pattern=r"^[\w.-]+/[\w.-]+$")
    nickname: str | None = None
    languages: list[str] = []
    tier: Tier = "deep"


class Config(BaseModel):
    settings: SettingsConfig = SettingsConfig()
    llm: LLMConfig
    refresh: RefreshConfig = RefreshConfig()
    projects: list[ProjectConfig] = []

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            raise ConfigError(f"config not found at {path}; create it with at least an [llm] section")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
        try:
            return cls(**raw)
        except ValidationError as exc:
            raise ConfigError(f"config schema error: {exc}") from exc

    def find_project(self, key: str) -> ProjectConfig | None:
        for p in self.projects:
            if p.repo == key or p.nickname == key:
                return p
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_config.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/config.py tests/test_config.py
git commit -m "feat: add Config loader with project lookup"
```

---

## Task 3: State persistence

**Files:**
- Create: `src/project_expert/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from project_expert.state import KGStatus, ProjectState, State


def test_load_empty_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = State.load(path)
    assert state.projects == {}
    state.save()
    assert path.exists()


def test_record_pull_creates_entry(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    state.record_pull("microsoft/agent-framework", sha="abc123", now=now)
    entry = state.projects["microsoft/agent-framework"]
    assert entry.last_pulled_at == now
    assert entry.last_pulled_sha == "abc123"
    assert entry.kg_status == KGStatus.MISSING


def test_record_kg_refresh_updates_entry(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    state.record_pull("foo/bar", sha="aaa", now=now)
    state.record_kg_refresh("foo/bar", sha="aaa", now=now)
    entry = state.projects["foo/bar"]
    assert entry.last_kg_refreshed_at == now
    assert entry.last_kg_source_sha == "aaa"
    assert entry.kg_status == KGStatus.OK


def test_round_trip_preserves_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = State.load(path)
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    state.record_pull("foo/bar", sha="aaa", now=now)
    state.save()
    reloaded = State.load(path)
    assert "foo/bar" in reloaded.projects
    assert reloaded.projects["foo/bar"].last_pulled_sha == "aaa"


def test_commits_since_kg_setter(tmp_path: Path) -> None:
    state = State.load(tmp_path / "state.json")
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    state.record_pull("foo/bar", sha="aaa", now=now)
    state.set_commits_since_kg("foo/bar", 47)
    assert state.projects["foo/bar"].commits_since_kg == 47
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_state.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement State**

`src/project_expert/state.py`:
```python
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

STATE_VERSION = 1


class KGStatus(StrEnum):
    OK = "ok"
    STALE = "stale"
    FAILED = "failed"
    RUNNING = "running"
    MISSING = "missing"


class ProjectState(BaseModel):
    last_pulled_at: datetime | None = None
    last_pulled_sha: str | None = None
    last_kg_refreshed_at: datetime | None = None
    last_kg_source_sha: str | None = None
    kg_status: KGStatus = KGStatus.MISSING
    last_error: str | None = None
    commits_since_kg: int = 0


class State(BaseModel):
    path: Path
    projects: dict[str, ProjectState] = {}

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path=path, projects={})
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != STATE_VERSION:
            raise ValueError(f"unsupported state version: {raw.get('version')}")
        projects = {k: ProjectState.model_validate(v) for k, v in raw.get("projects", {}).items()}
        return cls(path=path, projects=projects)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "projects": {k: v.model_dump(mode="json") for k, v in self.projects.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_pull(self, repo: str, *, sha: str, now: datetime) -> None:
        entry = self.projects.get(repo) or ProjectState()
        entry.last_pulled_at = now
        entry.last_pulled_sha = sha
        self.projects[repo] = entry

    def record_kg_refresh(self, repo: str, *, sha: str, now: datetime) -> None:
        entry = self.projects.get(repo) or ProjectState()
        entry.last_kg_refreshed_at = now
        entry.last_kg_source_sha = sha
        entry.kg_status = KGStatus.OK
        entry.commits_since_kg = 0
        self.projects[repo] = entry

    def set_commits_since_kg(self, repo: str, count: int) -> None:
        entry = self.projects.get(repo) or ProjectState()
        entry.commits_since_kg = count
        self.projects[repo] = entry

    def record_failure(self, repo: str, error: str) -> None:
        entry = self.projects.get(repo) or ProjectState()
        entry.kg_status = KGStatus.FAILED
        entry.last_error = error
        self.projects[repo] = entry
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_state.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/state.py tests/test_state.py
git commit -m "feat: add state persistence with pull/KG-refresh tracking"
```

---

## Task 4: Core domain models

**Files:**
- Create: `src/project_expert/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from project_expert.models import ChangelogEntry, KGNode, Snippet, Symbol, ToolError


def test_snippet_construction() -> None:
    s = Snippet(path="foo/bar.py", line=42, snippet="def hello():", score=0.8)
    assert s.path == "foo/bar.py"
    assert s.line == 42


def test_symbol_construction() -> None:
    sym = Symbol(path="foo/bar.py", line=10, kind="function", signature="def hello() -> None", docstring="Says hi.")
    assert sym.kind == "function"


def test_changelog_entry_construction() -> None:
    entry = ChangelogEntry(sha="abc", author="alice", date="2026-05-18T00:00:00Z", subject="fix", files_changed=["a.py"])
    assert entry.sha == "abc"
    assert "a.py" in entry.files_changed


def test_kg_node_construction() -> None:
    node = KGNode(id="n1", label="ChatAgent", kind="class", layer="core", attributes={"path": "a.py", "line": 1})
    assert node.kind == "class"


def test_tool_error_construction() -> None:
    err = ToolError(error="project_not_tracked", message="run /project-expert:add first")
    assert err.error == "project_not_tracked"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_models.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement models**

`src/project_expert/models.py`:
```python
from typing import Any, Literal

from pydantic import BaseModel


class Snippet(BaseModel):
    path: str
    line: int
    snippet: str
    score: float = 0.0


class Symbol(BaseModel):
    path: str
    line: int
    kind: Literal["class", "function", "method", "constant", "other"]
    signature: str | None = None
    docstring: str | None = None


class ChangelogEntry(BaseModel):
    sha: str
    author: str
    date: str
    subject: str
    files_changed: list[str] = []


class KGNode(BaseModel):
    id: str
    label: str
    kind: str
    layer: str | None = None
    attributes: dict[str, Any] = {}


class KGEdge(BaseModel):
    source: str
    target: str
    relation: str
    attributes: dict[str, Any] = {}


class IssueEntry(BaseModel):
    number: int
    title: str
    url: str
    labels: list[str] = []
    comments: int = 0
    created_at: str | None = None
    state: Literal["open", "closed"] = "open"


class ToolError(BaseModel):
    error: Literal[
        "project_not_tracked",
        "mirror_missing",
        "kg_missing",
        "mirror_stale",
        "not_found",
        "upstream_unavailable",
        "invalid_argument",
    ]
    message: str
    retry_after_seconds: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_models.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/models.py tests/test_models.py
git commit -m "feat: add core domain models (Snippet, Symbol, ChangelogEntry, KGNode, ToolError)"
```

---

## Task 5: Mirror manager — clone, pull, drift detection

**Files:**
- Create: `src/project_expert/mirror.py`
- Create: `tests/test_mirror.py`

- [ ] **Step 1: Write the failing test**

`tests/test_mirror.py`:
```python
import subprocess
from pathlib import Path

import pytest

from project_expert.exceptions import MirrorOperationError
from project_expert.mirror import MirrorManager


def _make_upstream(tmp_path: Path) -> Path:
    """Create a local 'upstream' bare-ish repo to clone from."""
    up = tmp_path / "upstream"
    up.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=up, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=up, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=up, check=True)
    (up / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=up, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=up, check=True, capture_output=True)
    return up


def test_clone_creates_mirror(tmp_path: Path) -> None:
    upstream = _make_upstream(tmp_path)
    mirrors_root = tmp_path / "mirrors"
    mgr = MirrorManager(mirrors_root=mirrors_root, clone_depth=10)
    path = mgr.ensure("local/test", remote=str(upstream))
    assert path.exists()
    assert (path / "README.md").read_text(encoding="utf-8") == "hello\n"


def test_pull_updates_existing_mirror(tmp_path: Path) -> None:
    upstream = _make_upstream(tmp_path)
    mirrors_root = tmp_path / "mirrors"
    mgr = MirrorManager(mirrors_root=mirrors_root, clone_depth=10)
    mgr.ensure("local/test", remote=str(upstream))

    (upstream / "new.txt").write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "new.txt"], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=upstream, check=True, capture_output=True)

    mirror_path = mgr.ensure("local/test", remote=str(upstream))
    assert (mirror_path / "new.txt").exists()


def test_head_sha_returns_current_commit(tmp_path: Path) -> None:
    upstream = _make_upstream(tmp_path)
    mgr = MirrorManager(mirrors_root=tmp_path / "mirrors", clone_depth=10)
    mirror = mgr.ensure("local/test", remote=str(upstream))
    sha = mgr.head_sha(mirror)
    assert len(sha) == 40


def test_commits_since_returns_count(tmp_path: Path) -> None:
    upstream = _make_upstream(tmp_path)
    mgr = MirrorManager(mirrors_root=tmp_path / "mirrors", clone_depth=10)
    mirror = mgr.ensure("local/test", remote=str(upstream))
    initial_sha = mgr.head_sha(mirror)

    (upstream / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "a"], cwd=upstream, check=True, capture_output=True)
    (upstream / "b.txt").write_text("b\n", encoding="utf-8")
    subprocess.run(["git", "add", "b.txt"], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "b"], cwd=upstream, check=True, capture_output=True)

    mirror = mgr.ensure("local/test", remote=str(upstream))
    assert mgr.commits_since(mirror, initial_sha) == 2


def test_clone_failure_raises(tmp_path: Path) -> None:
    mgr = MirrorManager(mirrors_root=tmp_path / "mirrors", clone_depth=10)
    with pytest.raises(MirrorOperationError):
        mgr.ensure("nonexistent/repo", remote="file:///does/not/exist")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_mirror.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement MirrorManager**

`src/project_expert/mirror.py`:
```python
import subprocess
from pathlib import Path

from project_expert.exceptions import MirrorOperationError


class MirrorManager:
    def __init__(self, mirrors_root: Path, clone_depth: int = 200) -> None:
        self.mirrors_root = mirrors_root.resolve()
        self.clone_depth = clone_depth
        self.mirrors_root.mkdir(parents=True, exist_ok=True)

    def _mirror_path(self, repo: str) -> Path:
        return self.mirrors_root / repo.replace("/", "__")

    def ensure(self, repo: str, remote: str) -> Path:
        path = self._mirror_path(repo)
        if path.exists() and (path / ".git").exists():
            self._pull(path)
        else:
            self._clone(remote, path)
        return path

    def _clone(self, remote: str, dest: Path) -> None:
        try:
            subprocess.run(  # noqa: S603 — controlled args
                ["git", "clone", "--depth", str(self.clone_depth), remote, str(dest)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise MirrorOperationError(f"clone failed for {remote}: {exc.stderr}") from exc

    def _pull(self, path: Path) -> None:
        try:
            subprocess.run(  # noqa: S603
                ["git", "pull", "--ff-only"],
                cwd=path, check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise MirrorOperationError(f"pull failed at {path}: {exc.stderr}") from exc

    def head_sha(self, path: Path) -> str:
        result = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],
            cwd=path, check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    def commits_since(self, path: Path, sha: str) -> int:
        try:
            result = subprocess.run(  # noqa: S603
                ["git", "rev-list", "--count", f"{sha}..HEAD"],
                cwd=path, check=True, capture_output=True, text=True,
            )
            return int(result.stdout.strip())
        except subprocess.CalledProcessError:
            return -1  # unknown SHA; treat as full drift
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_mirror.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/mirror.py tests/test_mirror.py
git commit -m "feat: add MirrorManager (clone, pull, drift detection)"
```

---

## Task 6: Symbol index (Python AST + multi-language regex fallback)

**Files:**
- Create: `src/project_expert/symbol_index.py`
- Create: `tests/test_symbol_index.py`

- [ ] **Step 1: Write the failing test**

`tests/test_symbol_index.py`:
```python
from pathlib import Path

from project_expert.symbol_index import SymbolIndex, build_index


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "module.py").write_text(
        '''def hello(name: str) -> str:
    """Say hi."""
    return f"hi {name}"


class Greeter:
    """A class."""
    def shout(self) -> str:
        return "HI"
''',
        encoding="utf-8",
    )
    (root / "util.js").write_text(
        "function processData(input) {\n  return input;\n}\n",
        encoding="utf-8",
    )
    return root


def test_build_index_extracts_python_symbols(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    out = tmp_path / "symbols.json"
    build_index(repo_root=root, output=out)

    idx = SymbolIndex.load(out)
    hello_hits = idx.find("hello")
    assert len(hello_hits) == 1
    assert hello_hits[0].path == "module.py"
    assert hello_hits[0].kind == "function"

    greeter_hits = idx.find("Greeter")
    assert len(greeter_hits) == 1
    assert greeter_hits[0].kind == "class"

    shout_hits = idx.find("shout")
    assert len(shout_hits) == 1
    assert shout_hits[0].kind == "method"


def test_build_index_regex_fallback_for_js(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    out = tmp_path / "symbols.json"
    build_index(repo_root=root, output=out)

    idx = SymbolIndex.load(out)
    hits = idx.find("processData")
    assert len(hits) == 1
    assert hits[0].path == "util.js"
    assert hits[0].kind == "function"


def test_find_kind_filter(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    out = tmp_path / "symbols.json"
    build_index(repo_root=root, output=out)

    idx = SymbolIndex.load(out)
    class_hits = idx.find("Greeter", kind="class")
    assert len(class_hits) == 1
    func_hits = idx.find("Greeter", kind="function")
    assert func_hits == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_symbol_index.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement symbol index**

`src/project_expert/symbol_index.py`:
```python
import ast
import json
import re
from pathlib import Path
from typing import Literal

from project_expert.models import Symbol

SymbolKind = Literal["class", "function", "method", "constant", "other"]

# Regex patterns for non-Python languages (light coverage)
_REGEX_PATTERNS: list[tuple[str, str, SymbolKind]] = [
    # JavaScript / TypeScript
    (r"\.(js|jsx|ts|tsx|mjs)$", r"^\s*function\s+(\w+)\s*\(", "function"),
    (r"\.(js|jsx|ts|tsx|mjs)$", r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", "function"),
    (r"\.(js|jsx|ts|tsx|mjs)$", r"^\s*(?:export\s+)?class\s+(\w+)", "class"),
    # Go
    (r"\.go$", r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", "function"),
    (r"\.go$", r"^\s*type\s+(\w+)\s+(?:struct|interface)\s*\{", "class"),
    # Rust
    (r"\.rs$", r"^\s*(?:pub\s+)?fn\s+(\w+)\s*[<(]", "function"),
    (r"\.rs$", r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)", "class"),
    # C#
    (r"\.cs$", r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?class\s+(\w+)", "class"),
    (r"\.cs$", r"^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?\w+\s+(\w+)\s*\([^)]*\)\s*\{", "function"),
]

_PYTHON_EXTS = {".py", ".pyi"}
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache", ".tox"}


class SymbolIndex:
    def __init__(self, symbols: list[Symbol]) -> None:
        self.symbols = symbols
        self._by_name: dict[str, list[Symbol]] = {}
        for s in symbols:
            self._by_name.setdefault(self._symbol_name(s), []).append(s)

    @staticmethod
    def _symbol_name(s: Symbol) -> str:
        return (s.signature or "").split("(")[0].split()[-1] if s.signature else ""

    @classmethod
    def load(cls, path: Path) -> "SymbolIndex":
        raw = json.loads(path.read_text(encoding="utf-8"))
        symbols = [Symbol.model_validate(s) for s in raw["symbols"]]
        return cls(symbols)

    def find(self, name: str, kind: SymbolKind | Literal["any"] = "any") -> list[Symbol]:
        hits = []
        for s in self.symbols:
            if self._symbol_name(s) == name:
                if kind == "any" or s.kind == kind:
                    hits.append(s)
        return hits


def _extract_python(file_path: Path, rel_path: str) -> list[Symbol]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[Symbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out.append(Symbol(
                path=rel_path, line=node.lineno, kind="class",
                signature=f"class {node.name}",
                docstring=ast.get_docstring(node),
            ))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(Symbol(
                        path=rel_path, line=item.lineno, kind="method",
                        signature=f"def {item.name}(...)",
                        docstring=ast.get_docstring(item),
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip methods (already captured above)
            if not _is_inside_class(tree, node):
                out.append(Symbol(
                    path=rel_path, line=node.lineno, kind="function",
                    signature=f"def {node.name}(...)",
                    docstring=ast.get_docstring(node),
                ))
    return out


def _is_inside_class(tree: ast.AST, target: ast.AST) -> bool:
    for parent in ast.walk(tree):
        if isinstance(parent, ast.ClassDef) and target in ast.walk(parent) and parent is not target:
            return True
    return False


def _extract_regex(file_path: Path, rel_path: str) -> list[Symbol]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    suffix_match = re.search(r"\.[^.]+$", file_path.name)
    if not suffix_match:
        return []
    out: list[Symbol] = []
    for ext_pattern, pattern, kind in _REGEX_PATTERNS:
        if not re.search(ext_pattern, file_path.name):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            match = re.search(pattern, line)
            if match:
                name = match.group(1)
                out.append(Symbol(path=rel_path, line=i, kind=kind, signature=f"{kind} {name}"))
    return out


def build_index(repo_root: Path, output: Path) -> None:
    repo_root = repo_root.resolve()
    symbols: list[Symbol] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if path.suffix in _PYTHON_EXTS:
            symbols.extend(_extract_python(path, rel))
        else:
            symbols.extend(_extract_regex(path, rel))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"symbols": [s.model_dump() for s in symbols]}, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_symbol_index.py -v
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/symbol_index.py tests/test_symbol_index.py
git commit -m "feat: add symbol index (Python AST + multi-lang regex fallback)"
```

---

## Task 7: Search — ripgrep wrapper

**Files:**
- Create: `src/project_expert/search.py`
- Create: `tests/test_search.py`

- [ ] **Step 1: Write the failing test**

`tests/test_search.py`:
```python
from pathlib import Path

from project_expert.search import RipgrepSearcher


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def chat_agent():\n    return 'hi'\n", encoding="utf-8")
    (root / "b.py").write_text("# nothing\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("ChatAgent is documented here.\n", encoding="utf-8")
    return root


def test_search_finds_match(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    searcher = RipgrepSearcher(root=root)
    results = searcher.search("chat_agent")
    assert len(results) >= 1
    assert any(r.path == "a.py" and r.line == 1 for r in results)


def test_search_glob_filter(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    searcher = RipgrepSearcher(root=root)
    md_results = searcher.search("ChatAgent", glob="*.md")
    assert len(md_results) == 1
    assert md_results[0].path == "docs/guide.md"


def test_search_no_match_returns_empty(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    searcher = RipgrepSearcher(root=root)
    assert searcher.search("zzzzzz_nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_search.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement RipgrepSearcher**

`src/project_expert/search.py`:
```python
import json
import shutil
import subprocess
from pathlib import Path

from project_expert.models import Snippet


class RipgrepSearcher:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._rg = shutil.which("rg")
        if not self._rg:
            raise RuntimeError(
                "ripgrep (`rg`) is required. Install via your package manager: "
                "`brew install ripgrep` (macOS), `apt install ripgrep` (Debian), "
                "or `winget install BurntSushi.ripgrep.MSVC` (Windows)."
            )

    def search(self, query: str, *, glob: str | None = None, max_results: int = 100) -> list[Snippet]:
        cmd = [self._rg, "--json", "--max-count", str(max_results), query]
        if glob:
            cmd.extend(["--glob", glob])
        cmd.append(str(self.root))
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, check=False,
        )
        if proc.returncode not in (0, 1):  # 1 = no matches
            return []
        results: list[Snippet] = []
        for line in proc.stdout.splitlines():
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "match":
                continue
            data = msg["data"]
            abs_path = Path(data["path"]["text"])
            try:
                rel = abs_path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            line_no = data["line_number"]
            text = data["lines"]["text"].rstrip("\n")
            results.append(Snippet(path=rel, line=line_no, snippet=text, score=1.0))
        return results
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_search.py -v
```
Expected: PASS (3 tests). Requires `rg` installed; if not, tests skip with clear error.

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/search.py tests/test_search.py
git commit -m "feat: add RipgrepSearcher (--json output, glob filter)"
```

---

## Task 8: GitHub issues client

**Files:**
- Create: `src/project_expert/github_issues.py`
- Create: `tests/test_github_issues.py`

- [ ] **Step 1: Write the failing test**

`tests/test_github_issues.py`:
```python
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from project_expert.exceptions import UpstreamUnavailable
from project_expert.github_issues import IssuesClient


def _fake_issue(number: int, title: str, state: str = "open") -> MagicMock:
    m = MagicMock()
    m.number = number
    m.title = title
    m.html_url = f"https://github.com/foo/bar/issues/{number}"
    m.labels = []
    m.comments = 0
    m.created_at = datetime(2026, 1, 1)
    m.state = state
    m.pull_request = None
    return m


def test_search_returns_issues() -> None:
    fake_gh = MagicMock()
    fake_gh.search_issues.return_value = [_fake_issue(1, "bug A"), _fake_issue(2, "bug B")]

    client = IssuesClient(token="fake", gh=fake_gh)
    results = client.search(repo="microsoft/agent-framework", query="bug", state="open", limit=10)
    assert len(results) == 2
    assert results[0].number == 1


def test_search_skips_pull_requests() -> None:
    pr = _fake_issue(99, "actually a PR")
    pr.pull_request = MagicMock()
    fake_gh = MagicMock()
    fake_gh.search_issues.return_value = [_fake_issue(1, "real"), pr, _fake_issue(2, "another")]

    client = IssuesClient(token="fake", gh=fake_gh)
    results = client.search(repo="foo/bar", query="x", state="open", limit=10)
    numbers = [r.number for r in results]
    assert numbers == [1, 2]


def test_rate_limit_raises_upstream_unavailable() -> None:
    from github import RateLimitExceededException

    fake_gh = MagicMock()
    fake_gh.search_issues.side_effect = RateLimitExceededException(403, "rate limited", {})

    client = IssuesClient(token="fake", gh=fake_gh)
    with pytest.raises(UpstreamUnavailable, match="rate"):
        client.search(repo="foo/bar", query="x", state="open", limit=10)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_github_issues.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement IssuesClient**

`src/project_expert/github_issues.py`:
```python
from typing import Any, Literal

from github import Github, RateLimitExceededException

from project_expert.exceptions import UpstreamUnavailable
from project_expert.models import IssueEntry


class IssuesClient:
    def __init__(self, token: str, gh: Any = None) -> None:
        self._gh = gh if gh is not None else Github(token)

    def search(
        self,
        repo: str,
        query: str,
        state: Literal["open", "closed", "all"] = "open",
        limit: int = 20,
    ) -> list[IssueEntry]:
        q_parts = [f"repo:{repo}", "is:issue", query]
        if state != "all":
            q_parts.append(f"state:{state}")
        full_query = " ".join(q_parts)
        try:
            raw = self._gh.search_issues(full_query)
        except RateLimitExceededException as exc:
            raise UpstreamUnavailable(f"GitHub rate-limited: {exc}") from exc
        out: list[IssueEntry] = []
        for item in raw:
            if getattr(item, "pull_request", None) is not None:
                continue
            if len(out) >= limit:
                break
            out.append(IssueEntry(
                number=item.number,
                title=item.title,
                url=item.html_url,
                labels=[lbl.name for lbl in getattr(item, "labels", [])],
                comments=getattr(item, "comments", 0),
                created_at=item.created_at.isoformat() if item.created_at else None,
                state=item.state,
            ))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_github_issues.py -v
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/github_issues.py tests/test_github_issues.py
git commit -m "feat: add GitHub IssuesClient with rate-limit translation"
```

---

## Task 9: KG store + KG runner

**Files:**
- Create: `src/project_expert/kg_store.py`
- Create: `src/project_expert/kg_runner.py`
- Create: `tests/test_kg_store.py`
- Create: `tests/test_kg_runner.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_kg_store.py`:
```python
import json
from pathlib import Path

import pytest

from project_expert.exceptions import KGMissing
from project_expert.kg_store import KGStore


def _write_kg(tmp_path: Path) -> Path:
    kg_dir = tmp_path / "kg" / "foo__bar"
    kg_dir.mkdir(parents=True)
    (kg_dir / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "n1", "label": "ChatAgent", "kind": "class", "layer": "core", "attributes": {"path": "a.py"}},
            {"id": "n2", "label": "FoundryChat", "kind": "class", "layer": "providers", "attributes": {}},
        ],
        "edges": [
            {"source": "n2", "target": "n1", "relation": "extends", "attributes": {}},
        ],
        "layers": ["core", "providers"],
    }), encoding="utf-8")
    return kg_dir.parent


def test_load_returns_full_graph(tmp_path: Path) -> None:
    kg_root = _write_kg(tmp_path)
    store = KGStore(kg_root=kg_root)
    graph = store.load("foo/bar")
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_load_filter_by_layer(tmp_path: Path) -> None:
    kg_root = _write_kg(tmp_path)
    store = KGStore(kg_root=kg_root)
    core_nodes = store.nodes_in_layer("foo/bar", layer="core")
    assert len(core_nodes) == 1
    assert core_nodes[0].label == "ChatAgent"


def test_neighbors_of_node(tmp_path: Path) -> None:
    kg_root = _write_kg(tmp_path)
    store = KGStore(kg_root=kg_root)
    neighbors = store.neighbors("foo/bar", node_id="n1")
    assert len(neighbors) == 1
    assert neighbors[0].id == "n2"


def test_missing_kg_raises(tmp_path: Path) -> None:
    store = KGStore(kg_root=tmp_path / "kg")
    with pytest.raises(KGMissing):
        store.load("nonexistent/project")
```

`tests/test_kg_runner.py`:
```python
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from project_expert.kg_runner import KGRunner


def test_runner_invokes_understand_anything(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    kg_out = tmp_path / "kg" / "foo__bar"

    with patch("subprocess.run") as fake_run:
        fake_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        runner = KGRunner()
        runner.run(repo_root=repo, kg_dir=kg_out, languages=["python"])

    assert fake_run.called
    call_args = fake_run.call_args.args[0]
    assert "claude" in call_args[0] or "understand-anything" in " ".join(call_args)


def test_runner_propagates_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    kg_out = tmp_path / "kg" / "foo__bar"

    with patch("subprocess.run") as fake_run:
        fake_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        runner = KGRunner()
        with pytest.raises(RuntimeError, match="understand-anything"):
            runner.run(repo_root=repo, kg_dir=kg_out, languages=["python"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_kg_store.py tests/test_kg_runner.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement KGStore**

`src/project_expert/kg_store.py`:
```python
import json
from pathlib import Path

from pydantic import BaseModel

from project_expert.exceptions import KGMissing
from project_expert.models import KGEdge, KGNode


class KnowledgeGraph(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
    layers: list[str] = []


class KGStore:
    def __init__(self, kg_root: Path) -> None:
        self.kg_root = kg_root.resolve()

    def _path(self, repo: str) -> Path:
        return self.kg_root / repo.replace("/", "__") / "graph.json"

    def exists(self, repo: str) -> bool:
        return self._path(repo).exists()

    def load(self, repo: str) -> KnowledgeGraph:
        path = self._path(repo)
        if not path.exists():
            raise KGMissing(f"no KG at {path}; run /project-expert:enrich {repo}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return KnowledgeGraph.model_validate(raw)

    def nodes_in_layer(self, repo: str, layer: str) -> list[KGNode]:
        graph = self.load(repo)
        return [n for n in graph.nodes if n.layer == layer]

    def neighbors(self, repo: str, node_id: str) -> list[KGNode]:
        graph = self.load(repo)
        neighbor_ids: set[str] = set()
        for edge in graph.edges:
            if edge.source == node_id:
                neighbor_ids.add(edge.target)
            elif edge.target == node_id:
                neighbor_ids.add(edge.source)
        return [n for n in graph.nodes if n.id in neighbor_ids]
```

- [ ] **Step 4: Implement KGRunner**

`src/project_expert/kg_runner.py`:
```python
import shutil
import subprocess
from pathlib import Path


class KGRunner:
    """Invokes understand-anything's `understand` skill against a project mirror.

    understand-anything must be installed as a Claude Code plugin separately;
    this runner shells out to its CLI entrypoint.
    """

    def __init__(self) -> None:
        self._claude = shutil.which("claude")

    def run(self, repo_root: Path, kg_dir: Path, languages: list[str]) -> None:
        kg_dir.mkdir(parents=True, exist_ok=True)
        # Invoke understand-anything via the `claude` CLI in non-interactive mode.
        # The output lands in repo_root/.understand-anything/; we move it to kg_dir.
        cmd = [
            self._claude or "claude",
            "-p", f"/understand-anything:understand --output {kg_dir}",
            "--allowedTools", "Read,Write,Bash,Glob,Grep",
        ]
        result = subprocess.run(  # noqa: S603
            cmd, cwd=repo_root, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"understand-anything failed (exit {result.returncode}): "
                f"{result.stderr or result.stdout}"
            )
```

> Note: the exact understand-anything CLI invocation may need adjustment based on the installed version. If the test fails because understand-anything's CLI surface differs, update the `cmd` list — the runner contract (subprocess + non-zero raise) stays the same.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_kg_store.py tests/test_kg_runner.py -v
```
Expected: PASS (6 tests total).

- [ ] **Step 6: Commit**

```bash
git add src/project_expert/kg_store.py src/project_expert/kg_runner.py tests/test_kg_store.py tests/test_kg_runner.py
git commit -m "feat: add KGStore and KGRunner (understand-anything wrapper)"
```

---

## Task 10: MCP tool — list + refresh

**Files:**
- Create: `src/project_expert/tools/__init__.py`
- Create: `src/project_expert/tools/list_tool.py`
- Create: `src/project_expert/tools/refresh_tool.py`
- Create: `tests/test_tool_list.py`
- Create: `tests/test_tool_refresh.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tool_list.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from project_expert.config import Config
from project_expert.state import KGStatus, State
from project_expert.tools.list_tool import projects_list


def _make_config_and_state(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("""
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"

[[projects]]
repo = "microsoft/agent-framework"
tier = "deep"

[[projects]]
repo = "huggingface/smolagents"
tier = "mirror_only"
""", encoding="utf-8")
    cfg = Config.load(cfg_path)
    state = State.load(tmp_path / "state.json")
    state.record_pull("microsoft/agent-framework", sha="abc", now=datetime(2026, 5, 18, tzinfo=timezone.utc))
    return cfg, state


def test_list_returns_all_projects(tmp_path: Path) -> None:
    cfg, state = _make_config_and_state(tmp_path)
    out = projects_list(config=cfg, state=state)
    assert len(out) == 2
    repos = {r["repo"] for r in out}
    assert repos == {"microsoft/agent-framework", "huggingface/smolagents"}


def test_list_filter_by_tier(tmp_path: Path) -> None:
    cfg, state = _make_config_and_state(tmp_path)
    out = projects_list(config=cfg, state=state, tier="deep")
    assert len(out) == 1
    assert out[0]["repo"] == "microsoft/agent-framework"


def test_list_includes_state_fields(tmp_path: Path) -> None:
    cfg, state = _make_config_and_state(tmp_path)
    out = projects_list(config=cfg, state=state)
    af = next(r for r in out if r["repo"] == "microsoft/agent-framework")
    assert af["last_pulled_at"] is not None
    assert af["kg_status"] == KGStatus.MISSING.value
```

`tests/test_tool_refresh.py`:
```python
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from project_expert.config import Config
from project_expert.state import State
from project_expert.tools.refresh_tool import projects_refresh


def test_refresh_calls_mirror_manager(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="claude-opus-4-7", api_key_env="X"),
        projects=[dict(repo="microsoft/agent-framework", tier="mirror_only")],
    )
    state = State.load(tmp_path / "state.json")

    mirror_mgr = MagicMock()
    mirror_mgr.ensure.return_value = tmp_path / "mirror"
    mirror_mgr.head_sha.return_value = "deadbeef" + "0" * 32

    out = projects_refresh(
        config=cfg, state=state,
        mirror_manager=mirror_mgr, kg_runner=MagicMock(),
        project="microsoft/agent-framework", force_kg=False,
    )
    assert mirror_mgr.ensure.called
    assert out["mirror_status"] == "ok"


def test_refresh_unknown_project_returns_error(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="claude-opus-4-7", api_key_env="X"),
        projects=[],
    )
    state = State.load(tmp_path / "state.json")
    out = projects_refresh(
        config=cfg, state=state,
        mirror_manager=MagicMock(), kg_runner=MagicMock(),
        project="unknown/repo", force_kg=False,
    )
    assert out.get("error") == "project_not_tracked"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_list.py tests/test_tool_refresh.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement tools/list_tool.py**

`src/project_expert/tools/__init__.py`: (empty)

`src/project_expert/tools/list_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.state import State


def projects_list(*, config: Config, state: State, tier: str | None = None) -> list[dict[str, Any]]:
    out = []
    for p in config.projects:
        if tier is not None and p.tier != tier:
            continue
        s = state.projects.get(p.repo)
        out.append({
            "repo": p.repo,
            "nickname": p.nickname,
            "tier": p.tier,
            "last_pulled_at": s.last_pulled_at.isoformat() if s and s.last_pulled_at else None,
            "last_kg_refreshed_at": s.last_kg_refreshed_at.isoformat() if s and s.last_kg_refreshed_at else None,
            "kg_status": (s.kg_status if s else "missing").value if s else "missing",
            "commits_since_kg": s.commits_since_kg if s else 0,
        })
    return out
```

- [ ] **Step 4: Implement tools/refresh_tool.py**

`src/project_expert/tools/refresh_tool.py`:
```python
from datetime import datetime, timezone
from typing import Any

from project_expert.config import Config
from project_expert.state import State


def projects_refresh(
    *,
    config: Config,
    state: State,
    mirror_manager: Any,
    kg_runner: Any,
    project: str,
    force_kg: bool = False,
) -> dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}

    now = datetime.now(timezone.utc)
    try:
        mirror_path = mirror_manager.ensure(proj.repo, remote=f"https://github.com/{proj.repo}")
        sha = mirror_manager.head_sha(mirror_path)
        state.record_pull(proj.repo, sha=sha, now=now)
    except Exception as exc:  # noqa: BLE001
        state.record_failure(proj.repo, str(exc))
        return {"error": "mirror_operation", "message": str(exc), "mirror_status": "failed"}

    if force_kg and proj.tier == "deep":
        try:
            kg_dir = config.settings.kg_dir / proj.repo.replace("/", "__")
            kg_runner.run(repo_root=mirror_path, kg_dir=kg_dir, languages=proj.languages)
            state.record_kg_refresh(proj.repo, sha=sha, now=now)
        except Exception as exc:  # noqa: BLE001
            state.record_failure(proj.repo, str(exc))
            return {"mirror_status": "ok", "kg_status": "failed", "error": "kg_failed", "message": str(exc)}

    state.save()
    return {"mirror_status": "ok", "kg_status": state.projects[proj.repo].kg_status.value}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_list.py tests/test_tool_refresh.py -v
```
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/project_expert/tools/ tests/test_tool_list.py tests/test_tool_refresh.py
git commit -m "feat: add projects.list and projects.refresh MCP tools"
```

---

## Task 11: MCP tool — search + read

**Files:**
- Create: `src/project_expert/tools/search_tool.py`
- Create: `src/project_expert/tools/read_tool.py`
- Create: `tests/test_tool_search.py`
- Create: `tests/test_tool_read.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tool_search.py`:
```python
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.search_tool import projects_search


def _make_setup(tmp_path: Path):
    mirror = tmp_path / "mirror" / "foo__bar"
    mirror.mkdir(parents=True)
    (mirror / "a.py").write_text("def chat_agent():\n    pass\n", encoding="utf-8")

    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "mirror"), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path / "idx")),
    )
    state = State.load(tmp_path / "state.json")
    return cfg, state


def test_search_finds_hit(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_search(config=cfg, state=state, project="foo/bar", query="chat_agent")
    assert isinstance(out, list)
    assert any(r["snippet"].startswith("def chat_agent") for r in out)


def test_search_unknown_project_returns_error(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_search(config=cfg, state=state, project="nope/nope", query="x")
    assert isinstance(out, dict)
    assert out["error"] == "project_not_tracked"
```

`tests/test_tool_read.py`:
```python
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.read_tool import projects_read


def _make_setup(tmp_path: Path):
    mirror = tmp_path / "mirror" / "foo__bar"
    mirror.mkdir(parents=True)
    (mirror / "module.py").write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "mirror"), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path / "idx")),
    )
    state = State.load(tmp_path / "state.json")
    return cfg, state


def test_read_full_file(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_read(config=cfg, state=state, project="foo/bar", path="module.py")
    assert "line1" in out["content"]
    assert out["lines"] == 5


def test_read_line_range(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_read(config=cfg, state=state, project="foo/bar", path="module.py", line_range=[2, 3])
    assert out["content"] == "line2\nline3"


def test_read_escape_attempt_rejected(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_read(config=cfg, state=state, project="foo/bar", path="../../etc/passwd")
    assert out["error"] == "invalid_argument"


def test_read_missing_file(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_read(config=cfg, state=state, project="foo/bar", path="missing.py")
    assert out["error"] == "not_found"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_search.py tests/test_tool_read.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement search_tool.py**

`src/project_expert/tools/search_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.search import RipgrepSearcher
from project_expert.state import State


def projects_search(
    *,
    config: Config,
    state: State,
    project: str,
    query: str,
    kind: str = "code",
    glob: str | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    mirror = config.settings.mirrors_dir / proj.repo.replace("/", "__")
    if not mirror.exists():
        return {"error": "mirror_missing", "message": f"run /project-expert:refresh {proj.repo}"}
    if kind == "docs":
        glob = glob or "*.{md,rst,txt}"
    elif kind == "samples":
        glob = glob or "{samples,examples,tutorials,getting-started,cookbook}/**/*"
    try:
        searcher = RipgrepSearcher(root=mirror)
        snippets = searcher.search(query, glob=glob, max_results=max_results)
    except RuntimeError as exc:
        return {"error": "upstream_unavailable", "message": str(exc)}
    return [s.model_dump() for s in snippets]
```

- [ ] **Step 4: Implement read_tool.py**

`src/project_expert/tools/read_tool.py`:
```python
import subprocess
from typing import Any

from project_expert.config import Config
from project_expert.state import State


def projects_read(
    *,
    config: Config,
    state: State,
    project: str,
    path: str,
    ref: str = "HEAD",
    line_range: list[int] | None = None,
) -> dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    mirror = (config.settings.mirrors_dir / proj.repo.replace("/", "__")).resolve()
    if not mirror.exists():
        return {"error": "mirror_missing", "message": f"run /project-expert:refresh {proj.repo}"}

    target = (mirror / path).resolve()
    try:
        target.relative_to(mirror)
    except ValueError:
        return {"error": "invalid_argument", "message": f"path escapes mirror: {path!r}"}

    if ref == "HEAD":
        if not target.exists():
            return {"error": "not_found", "message": f"{path} not in mirror"}
        content = target.read_text(encoding="utf-8")
    else:
        try:
            content = subprocess.run(  # noqa: S603
                ["git", "show", f"{ref}:{path}"],
                cwd=mirror, check=True, capture_output=True, text=True,
            ).stdout
        except subprocess.CalledProcessError:
            return {"error": "not_found", "message": f"{path}@{ref} not in mirror"}

    lines = content.splitlines()
    if line_range is not None:
        start = max(1, line_range[0])
        end = min(len(lines), line_range[1])
        content = "\n".join(lines[start - 1 : end])

    return {"content": content, "lines": len(lines), "sha": ref}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_search.py tests/test_tool_read.py -v
```
Expected: PASS (6 tests total).

- [ ] **Step 6: Commit**

```bash
git add src/project_expert/tools/search_tool.py src/project_expert/tools/read_tool.py tests/test_tool_search.py tests/test_tool_read.py
git commit -m "feat: add projects.search and projects.read tools"
```

---

## Task 12: MCP tool — symbol + changelog

**Files:**
- Create: `src/project_expert/tools/symbol_tool.py`
- Create: `src/project_expert/tools/changelog_tool.py`
- Create: `tests/test_tool_symbol.py`
- Create: `tests/test_tool_changelog.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tool_symbol.py`:
```python
import json
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.symbol_tool import projects_symbol


def _make_setup(tmp_path: Path):
    idx_dir = tmp_path / "idx" / "foo__bar"
    idx_dir.mkdir(parents=True)
    (idx_dir / "symbols.json").write_text(json.dumps({
        "symbols": [
            {"path": "a.py", "line": 1, "kind": "function", "signature": "def hello"},
            {"path": "b.py", "line": 5, "kind": "class", "signature": "class Foo"},
        ],
    }), encoding="utf-8")

    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path / "idx")),
    )
    state = State.load(tmp_path / "state.json")
    return cfg, state


def test_symbol_finds_function(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_symbol(config=cfg, state=state, project="foo/bar", name="hello")
    assert len(out) == 1
    assert out[0]["kind"] == "function"


def test_symbol_kind_filter(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_symbol(config=cfg, state=state, project="foo/bar", name="Foo", kind="class")
    assert len(out) == 1


def test_symbol_missing_index_returns_error(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="other/proj", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path), kg_dir=str(tmp_path), index_dir=str(tmp_path / "no_idx")),
    )
    state = State.load(tmp_path / "state.json")
    out = projects_symbol(config=cfg, state=state, project="other/proj", name="x")
    assert isinstance(out, dict) and out["error"] == "mirror_missing"
```

`tests/test_tool_changelog.py`:
```python
import subprocess
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.changelog_tool import projects_changelog


def _make_setup_with_history(tmp_path: Path):
    mirror = tmp_path / "m" / "foo__bar"
    mirror.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=mirror, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=mirror, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=mirror, check=True)
    for i in range(3):
        (mirror / f"f{i}.txt").write_text(f"v{i}\n", encoding="utf-8")
        subprocess.run(["git", "add", f"f{i}.txt"], cwd=mirror, check=True)
        subprocess.run(["git", "commit", "-m", f"feat: add f{i}"], cwd=mirror, check=True, capture_output=True)

    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path), index_dir=str(tmp_path)),
    )
    state = State.load(tmp_path / "state.json")
    return cfg, state


def test_changelog_returns_commits(tmp_path: Path) -> None:
    cfg, state = _make_setup_with_history(tmp_path)
    out = projects_changelog(config=cfg, state=state, project="foo/bar", since="1970-01-01", limit=10)
    assert len(out) == 3
    assert out[0]["subject"].startswith("feat: add f")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_symbol.py tests/test_tool_changelog.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement symbol_tool.py**

`src/project_expert/tools/symbol_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.state import State
from project_expert.symbol_index import SymbolIndex


def projects_symbol(
    *,
    config: Config,
    state: State,
    project: str,
    name: str,
    kind: str = "any",
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    idx_path = config.settings.index_dir / proj.repo.replace("/", "__") / "symbols.json"
    if not idx_path.exists():
        return {"error": "mirror_missing", "message": f"symbol index missing; run /project-expert:refresh {proj.repo}"}
    idx = SymbolIndex.load(idx_path)
    hits = idx.find(name, kind=kind)  # type: ignore[arg-type]
    return [h.model_dump() for h in hits]
```

- [ ] **Step 4: Implement changelog_tool.py**

`src/project_expert/tools/changelog_tool.py`:
```python
import subprocess
from typing import Any

from project_expert.config import Config
from project_expert.state import State


def projects_changelog(
    *,
    config: Config,
    state: State,
    project: str,
    since: str,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    mirror = config.settings.mirrors_dir / proj.repo.replace("/", "__")
    if not mirror.exists():
        return {"error": "mirror_missing", "message": f"run /project-expert:refresh {proj.repo}"}

    cmd = ["git", "log", f"--since={since}", f"-n{limit}", "--pretty=format:%H%x09%an%x09%aI%x09%s", "--name-only"]
    result = subprocess.run(  # noqa: S603
        cmd, cwd=mirror, check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {"error": "upstream_unavailable", "message": result.stderr}

    entries = []
    current: dict[str, Any] | None = None
    for line in result.stdout.splitlines():
        if "\t" in line:
            if current:
                entries.append(current)
            parts = line.split("\t", 3)
            if len(parts) == 4:
                current = {"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3], "files_changed": []}
        elif line and current:
            current["files_changed"].append(line)
    if current:
        entries.append(current)
    return entries
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_symbol.py tests/test_tool_changelog.py -v
```
Expected: PASS (4 tests total).

- [ ] **Step 6: Commit**

```bash
git add src/project_expert/tools/symbol_tool.py src/project_expert/tools/changelog_tool.py tests/test_tool_symbol.py tests/test_tool_changelog.py
git commit -m "feat: add projects.symbol and projects.changelog tools"
```

---

## Task 13: MCP tool — kg + compare + examples

**Files:**
- Create: `src/project_expert/tools/kg_tool.py`
- Create: `src/project_expert/tools/compare_tool.py`
- Create: `src/project_expert/tools/examples_tool.py`
- Create: `tests/test_tool_kg.py`
- Create: `tests/test_tool_compare.py`
- Create: `tests/test_tool_examples.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tool_kg.py`:
```python
import json
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.kg_tool import projects_kg


def _make_kg(tmp_path: Path):
    kg_dir = tmp_path / "kg" / "foo__bar"
    kg_dir.mkdir(parents=True)
    (kg_dir / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "n1", "label": "ChatAgent", "kind": "class", "layer": "core", "attributes": {}},
            {"id": "n2", "label": "FoundryChat", "kind": "class", "layer": "providers", "attributes": {}},
        ],
        "edges": [{"source": "n2", "target": "n1", "relation": "extends", "attributes": {}}],
        "layers": ["core", "providers"],
    }), encoding="utf-8")
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="deep")],
        settings=dict(mirrors_dir=str(tmp_path), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path)),
    )
    return cfg, State.load(tmp_path / "state.json")


def test_kg_returns_full_graph(tmp_path: Path) -> None:
    cfg, state = _make_kg(tmp_path)
    out = projects_kg(config=cfg, state=state, project="foo/bar")
    assert len(out["nodes"]) == 2
    assert len(out["edges"]) == 1


def test_kg_layer_filter(tmp_path: Path) -> None:
    cfg, state = _make_kg(tmp_path)
    out = projects_kg(config=cfg, state=state, project="foo/bar", layer="core")
    assert len(out["nodes"]) == 1


def test_kg_node_neighbors(tmp_path: Path) -> None:
    cfg, state = _make_kg(tmp_path)
    out = projects_kg(config=cfg, state=state, project="foo/bar", node_id="n1")
    assert len(out["neighbors"]) == 1
    assert out["neighbors"][0]["id"] == "n2"
```

`tests/test_tool_compare.py`:
```python
import json
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.compare_tool import projects_compare


def _make_setup(tmp_path: Path):
    for repo, content in [("foo__bar", "class ChatAgent:\n    pass\n"), ("baz__qux", "class Agent:\n    pass\n")]:
        mirror = tmp_path / "m" / repo
        mirror.mkdir(parents=True)
        (mirror / "x.py").write_text(content, encoding="utf-8")
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[
            ProjectConfig(repo="foo/bar", tier="mirror_only"),
            ProjectConfig(repo="baz/qux", tier="mirror_only"),
        ],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path), index_dir=str(tmp_path)),
    )
    return cfg, State.load(tmp_path / "state.json")


def test_compare_across_projects(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_compare(config=cfg, state=state, concept="Agent", projects=["foo/bar", "baz/qux"])
    assert len(out) == 2
    for entry in out:
        assert "snippets" in entry
```

`tests/test_tool_examples.py`:
```python
from pathlib import Path

from project_expert.config import Config, ProjectConfig
from project_expert.state import State
from project_expert.tools.examples_tool import projects_examples


def _make_setup(tmp_path: Path):
    mirror = tmp_path / "m" / "foo__bar"
    (mirror / "samples").mkdir(parents=True)
    (mirror / "samples" / "intro.py").write_text("# Use ChatAgent for X\n", encoding="utf-8")
    (mirror / "src").mkdir()
    (mirror / "src" / "core.py").write_text("# Don't pick up impl files\nChatAgent\n", encoding="utf-8")

    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path), index_dir=str(tmp_path)),
    )
    return cfg, State.load(tmp_path / "state.json")


def test_examples_only_picks_sample_dirs(tmp_path: Path) -> None:
    cfg, state = _make_setup(tmp_path)
    out = projects_examples(config=cfg, state=state, project="foo/bar", concept="ChatAgent")
    paths = {r["path"] for r in out}
    assert "samples/intro.py" in paths
    assert "src/core.py" not in paths
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_kg.py tests/test_tool_compare.py tests/test_tool_examples.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement kg_tool.py**

`src/project_expert/tools/kg_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.exceptions import KGMissing
from project_expert.kg_store import KGStore
from project_expert.state import State


def projects_kg(
    *,
    config: Config,
    state: State,
    project: str,
    layer: str | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    store = KGStore(kg_root=config.settings.kg_dir)
    try:
        graph = store.load(proj.repo)
    except KGMissing as exc:
        return {"error": "kg_missing", "message": str(exc)}

    if node_id is not None:
        neighbors = store.neighbors(proj.repo, node_id=node_id)
        node = next((n for n in graph.nodes if n.id == node_id), None)
        if node is None:
            return {"error": "not_found", "message": f"node {node_id!r} not in graph"}
        return {"node": node.model_dump(), "neighbors": [n.model_dump() for n in neighbors]}

    if layer is not None:
        nodes = store.nodes_in_layer(proj.repo, layer=layer)
        return {"nodes": [n.model_dump() for n in nodes], "edges": [], "layers": [layer]}

    return graph.model_dump()
```

- [ ] **Step 4: Implement compare_tool.py**

`src/project_expert/tools/compare_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.search import RipgrepSearcher
from project_expert.state import State


def projects_compare(
    *,
    config: Config,
    state: State,
    concept: str,
    projects: list[str],
) -> list[dict[str, Any]]:
    out = []
    for project in projects:
        proj = config.find_project(project)
        if proj is None:
            out.append({"project": project, "error": "project_not_tracked", "snippets": []})
            continue
        mirror = config.settings.mirrors_dir / proj.repo.replace("/", "__")
        if not mirror.exists():
            out.append({"project": project, "error": "mirror_missing", "snippets": []})
            continue
        try:
            searcher = RipgrepSearcher(root=mirror)
            snippets = searcher.search(concept, max_results=5)
        except RuntimeError:
            snippets = []
        out.append({
            "project": proj.repo,
            "snippets": [s.model_dump() for s in snippets],
            "idiomatic_example": snippets[0].model_dump() if snippets else None,
        })
    return out
```

- [ ] **Step 5: Implement examples_tool.py**

`src/project_expert/tools/examples_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.search import RipgrepSearcher
from project_expert.state import State

_SAMPLE_GLOBS = "{samples,examples,tutorials,getting-started,cookbook,docs/examples}/**/*"


def projects_examples(
    *,
    config: Config,
    state: State,
    project: str,
    concept: str,
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    mirror = config.settings.mirrors_dir / proj.repo.replace("/", "__")
    if not mirror.exists():
        return {"error": "mirror_missing", "message": f"run /project-expert:refresh {proj.repo}"}
    try:
        searcher = RipgrepSearcher(root=mirror)
        snippets = searcher.search(concept, glob=_SAMPLE_GLOBS, max_results=10)
    except RuntimeError as exc:
        return {"error": "upstream_unavailable", "message": str(exc)}
    return [s.model_dump() for s in snippets]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_kg.py tests/test_tool_compare.py tests/test_tool_examples.py -v
```
Expected: PASS (5 tests total).

- [ ] **Step 7: Commit**

```bash
git add src/project_expert/tools/kg_tool.py src/project_expert/tools/compare_tool.py src/project_expert/tools/examples_tool.py tests/test_tool_kg.py tests/test_tool_compare.py tests/test_tool_examples.py
git commit -m "feat: add projects.kg, projects.compare, projects.examples tools"
```

---

## Task 14: MCP tool — issues

**Files:**
- Create: `src/project_expert/tools/issues_tool.py`
- Create: `tests/test_tool_issues.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tool_issues.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock

from project_expert.config import Config, ProjectConfig
from project_expert.models import IssueEntry
from project_expert.state import State
from project_expert.tools.issues_tool import projects_issues


def test_issues_returns_results(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
    )
    state = State.load(tmp_path / "state.json")
    fake_client = MagicMock()
    fake_client.search.return_value = [
        IssueEntry(number=1, title="bug", url="x", state="open"),
        IssueEntry(number=2, title="bug2", url="y", state="open"),
    ]
    out = projects_issues(config=cfg, state=state, issues_client=fake_client, project="foo/bar", query="bug")
    assert isinstance(out, list)
    assert len(out) == 2


def test_issues_unknown_project(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[],
    )
    state = State.load(tmp_path / "state.json")
    out = projects_issues(config=cfg, state=state, issues_client=MagicMock(), project="nope/nope", query="x")
    assert out["error"] == "project_not_tracked"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_issues.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement issues_tool.py**

`src/project_expert/tools/issues_tool.py`:
```python
from typing import Any

from project_expert.config import Config
from project_expert.exceptions import UpstreamUnavailable
from project_expert.state import State


def projects_issues(
    *,
    config: Config,
    state: State,
    issues_client: Any,
    project: str,
    query: str,
    state_filter: str = "open",
    limit: int = 20,
) -> list[dict[str, Any]] | dict[str, Any]:
    proj = config.find_project(project)
    if proj is None:
        return {"error": "project_not_tracked", "message": f"{project} not in config"}
    try:
        results = issues_client.search(repo=proj.repo, query=query, state=state_filter, limit=limit)
    except UpstreamUnavailable as exc:
        return {"error": "upstream_unavailable", "message": str(exc)}
    return [r.model_dump() for r in results]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_tool_issues.py -v
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/project_expert/tools/issues_tool.py tests/test_tool_issues.py
git commit -m "feat: add projects.issues tool"
```

---

## Task 15: MCP server (stdio, tool registration)

**Files:**
- Create: `mcp/__init__.py`
- Create: `mcp/server.py`
- Create: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

`tests/test_mcp_server.py`:
```python
from project_expert.mcp.server import build_server


def test_server_registers_all_tools() -> None:
    server = build_server()
    tool_names = set(server.list_tool_names())
    assert "projects.list" in tool_names
    assert "projects.search" in tool_names
    assert "projects.read" in tool_names
    assert "projects.symbol" in tool_names
    assert "projects.changelog" in tool_names
    assert "projects.kg" in tool_names
    assert "projects.compare" in tool_names
    assert "projects.examples" in tool_names
    assert "projects.issues" in tool_names
    assert "projects.refresh" in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_mcp_server.py -v
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement MCP server**

`mcp/__init__.py`: (empty)

`mcp/server.py`:
```python
"""MCP stdio server entrypoint.

Run with: `uv run python -m project_expert.mcp.server`

This module re-exports the server factory so the plugin manifest can launch it
via `python -m project_expert.mcp.server`.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from project_expert.config import Config
from project_expert.github_issues import IssuesClient
from project_expert.kg_runner import KGRunner
from project_expert.mirror import MirrorManager
from project_expert.state import State
from project_expert.tools.changelog_tool import projects_changelog
from project_expert.tools.compare_tool import projects_compare
from project_expert.tools.examples_tool import projects_examples
from project_expert.tools.issues_tool import projects_issues
from project_expert.tools.kg_tool import projects_kg
from project_expert.tools.list_tool import projects_list
from project_expert.tools.read_tool import projects_read
from project_expert.tools.refresh_tool import projects_refresh
from project_expert.tools.search_tool import projects_search
from project_expert.tools.symbol_tool import projects_symbol


CONFIG_PATH = Path("~/.config/project-expert/config.toml").expanduser()
STATE_PATH = Path("~/.config/project-expert/state.json").expanduser()


class ServerFacade:
    """Wraps Server with a flat `list_tool_names()` for tests."""

    def __init__(self, server: Server, tool_names: list[str]) -> None:
        self._server = server
        self._tool_names = tool_names

    def list_tool_names(self) -> list[str]:
        return list(self._tool_names)

    @property
    def server(self) -> Server:
        return self._server


def _load_or_bootstrap() -> tuple[Config, State]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            '[llm]\nprovider = "anthropic"\nmodel = "claude-opus-4-7"\napi_key_env = "ANTHROPIC_API_KEY"\n',
            encoding="utf-8",
        )
    cfg = Config.load(CONFIG_PATH)
    state = State.load(STATE_PATH)
    return cfg, state


def _issues_client(cfg: Config) -> IssuesClient | None:
    if cfg.llm.api_key_env and os.environ.get("GITHUB_TOKEN"):
        return IssuesClient(token=os.environ["GITHUB_TOKEN"])
    return None


def build_server() -> ServerFacade:
    server = Server("project-expert")
    cfg, state = _load_or_bootstrap()
    mirror_mgr = MirrorManager(mirrors_root=cfg.settings.mirrors_dir, clone_depth=cfg.settings.clone_depth)
    kg_runner = KGRunner()
    issues_client = _issues_client(cfg)

    tool_specs: list[tuple[str, dict[str, Any], Any]] = [
        ("projects.list", {"tier": str}, lambda **kw: projects_list(config=cfg, state=state, **kw)),
        ("projects.search", {"project": str, "query": str, "kind": str, "glob": str, "max_results": int},
         lambda **kw: projects_search(config=cfg, state=state, **kw)),
        ("projects.read", {"project": str, "path": str, "ref": str, "line_range": list},
         lambda **kw: projects_read(config=cfg, state=state, **kw)),
        ("projects.symbol", {"project": str, "name": str, "kind": str},
         lambda **kw: projects_symbol(config=cfg, state=state, **kw)),
        ("projects.changelog", {"project": str, "since": str, "limit": int},
         lambda **kw: projects_changelog(config=cfg, state=state, **kw)),
        ("projects.kg", {"project": str, "layer": str, "node_id": str},
         lambda **kw: projects_kg(config=cfg, state=state, **kw)),
        ("projects.compare", {"concept": str, "projects": list},
         lambda **kw: projects_compare(config=cfg, state=state, **kw)),
        ("projects.examples", {"project": str, "concept": str},
         lambda **kw: projects_examples(config=cfg, state=state, **kw)),
        ("projects.issues", {"project": str, "query": str, "state_filter": str, "limit": int},
         lambda **kw: projects_issues(config=cfg, state=state, issues_client=issues_client, **kw)
         if issues_client else {"error": "upstream_unavailable", "message": "GITHUB_TOKEN not set"}),
        ("projects.refresh", {"project": str, "force_kg": bool},
         lambda **kw: projects_refresh(config=cfg, state=state, mirror_manager=mirror_mgr, kg_runner=kg_runner, **kw)),
    ]

    tool_names = [spec[0] for spec in tool_specs]

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=name,
                description=f"See spec for projects.{name.split('.')[-1]}",
                inputSchema={"type": "object", "properties": {k: {"type": "string"} for k in schema.keys()}},
            )
            for name, schema, _ in tool_specs
        ]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        impl = next((fn for n, _, fn in tool_specs if n == name), None)
        if impl is None:
            return [TextContent(type="text", text=f'{{"error": "unknown_tool", "message": "{name}"}}')]
        result = impl(**arguments)
        import json
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return ServerFacade(server, tool_names)


async def _main() -> None:
    facade = build_server()
    async with stdio_server() as (reader, writer):
        await facade.server.run(reader, writer, facade.server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/test_mcp_server.py -v
```
Expected: PASS (1 test). Test confirms all 10 tools are registered.

- [ ] **Step 5: Commit**

```bash
git add mcp/ tests/test_mcp_server.py
git commit -m "feat: add MCP stdio server with all 10 projects.* tools registered"
```

---

## Task 16: Subagent definition

**Files:**
- Create: `agents/project-expert.md`

- [ ] **Step 1: Create the subagent file**

`agents/project-expert.md`:
```markdown
---
name: project-expert
description: Use for any in-depth question about a tracked open-source project's
  architecture, APIs, internals, idioms, version differences, or how to express
  a concept in that project's style. MUST consult projects.* MCP tools and cite
  file:line references before answering. Do NOT rely on training-data knowledge
  for current API surfaces.
tools:
  - mcp__project-expert__projects.list
  - mcp__project-expert__projects.search
  - mcp__project-expert__projects.read
  - mcp__project-expert__projects.symbol
  - mcp__project-expert__projects.changelog
  - mcp__project-expert__projects.kg
  - mcp__project-expert__projects.compare
  - mcp__project-expert__projects.examples
  - mcp__project-expert__projects.issues
  - WebSearch
  - WebFetch
  - Read
  - Grep
  - Glob
---

You are an expert on the user's tracked open-source projects.

# Workflow

1. Identify the project(s) the question concerns. If unclear, call projects.list
   and infer from context. If still ambiguous, ask once.

2. For "what does X look like" / API questions:
   - projects.symbol to locate the entity
   - projects.read to fetch the source
   - Cite file:line in the answer

3. For "how is X implemented internally" mechanism questions:
   - projects.kg for architectural context
   - projects.search for call sites / related modules
   - projects.read for the actual implementation
   - Cite file:line for each load-bearing claim

4. For "what changed" questions:
   - projects.changelog with since=<date or version>
   - Optionally projects.issues for related discussion

5. For "how does X compare across projects":
   - projects.compare or parallel projects.symbol calls
   - Present a clear comparison table

6. For "is this still current" sanity checks:
   - Check projects.list for last_pulled_at
   - If stale, mention it and suggest /project-expert:refresh

# Rules

- NEVER assert current API behavior without a corresponding projects.read or
  projects.symbol citation.
- If the answer requires data the tools cannot provide (unreleased features,
  community discussion), WebSearch first; if nothing useful, say so explicitly.
- Output structure: lead with the answer, then evidence (cited snippets), then
  nuances/caveats.
- Length: match the question. Don't pad with subsections.
```

- [ ] **Step 2: Commit**

```bash
git add agents/project-expert.md
git commit -m "feat: add project-expert subagent definition"
```

---

## Task 17: Skills — add + remove + list

**Files:**
- Create: `skills/add/SKILL.md`
- Create: `skills/remove/SKILL.md`
- Create: `skills/list/SKILL.md`

- [ ] **Step 1: Create add skill**

`skills/add/SKILL.md`:
```markdown
---
name: add
description: Track a new GitHub project. Usage `/project-expert:add owner/repo` or
  `/project-expert:add https://github.com/owner/repo`. Clones the mirror immediately;
  queues KG generation for the next refresh tick.
---

# Add a project to tracking

1. Parse the user's argument. Accept `owner/repo`, `github.com/owner/repo`, or `https://github.com/owner/repo`.
2. Validate the repo exists on GitHub via the `gh api repos/<owner>/<repo>` command. Fail clearly if not.
3. Append a `[[projects]]` block to `~/.config/project-expert/config.toml` with `tier = "deep"`.
4. Run `project-expert-sync --project <owner>/<repo>` to clone the mirror immediately.
5. Report: project added, mirror cloned at <path>, KG queued for next refresh.

Default tier is `deep`. To change, the user can edit config.toml directly or
pass `--tier mirror_only`.
```

- [ ] **Step 2: Create remove skill**

`skills/remove/SKILL.md`:
```markdown
---
name: remove
description: Stop tracking a project. Usage `/project-expert:remove owner/repo`.
  Deletes the mirror, KG, and symbol-index data after confirmation.
---

# Remove a project from tracking

1. Parse the user's argument.
2. Confirm with the user: list the data directories that will be deleted (mirror, KG, index).
3. Remove the `[[projects]]` block from `~/.config/project-expert/config.toml`.
4. Delete `~/.config/project-expert/data/mirrors/<owner>__<repo>/`,
   `~/.config/project-expert/data/kg/<owner>__<repo>/`,
   `~/.config/project-expert/data/index/<owner>__<repo>/`.
5. Update state.json to drop the entry.
6. Report what was removed.
```

- [ ] **Step 3: Create list skill**

`skills/list/SKILL.md`:
```markdown
---
name: list
description: Show all tracked projects with their mirror and KG status.
  Usage `/project-expert:list`.
---

# List tracked projects

Call the `projects.list` MCP tool and render the result as a table:

| Project | Tier | Last pulled | KG status | Drift (commits) |
|---------|------|-------------|-----------|-----------------|

Highlight rows where last_pulled_at > 24h ago, or kg_status != "ok".
Suggest /project-expert:refresh if anything is stale.
```

- [ ] **Step 4: Commit**

```bash
git add skills/add/ skills/remove/ skills/list/
git commit -m "feat: add /project-expert:add, :remove, :list skills"
```

---

## Task 18: Skills — refresh + enrich + ask

**Files:**
- Create: `skills/refresh/SKILL.md`
- Create: `skills/enrich/SKILL.md`
- Create: `skills/ask/SKILL.md`

- [ ] **Step 1: Create refresh skill**

`skills/refresh/SKILL.md`:
```markdown
---
name: refresh
description: Pull latest source for tracked projects and refresh symbol indexes.
  Usage `/project-expert:refresh [--project owner/repo] [--force-kg]`.
---

# Refresh tracked projects

1. Parse args. If `--project` is given, refresh that one. Otherwise refresh all.
2. Run `project-expert-sync` with appropriate args.
3. If `--force-kg`, also run `project-expert-kg-refresh` for the affected projects.
4. Report what happened for each project (pulled <sha>, KG status).
```

- [ ] **Step 2: Create enrich skill**

`skills/enrich/SKILL.md`:
```markdown
---
name: enrich
description: Force a knowledge-graph rebuild for one project. Usage
  `/project-expert:enrich owner/repo`. Expensive — invokes understand-anything.
---

# Force KG enrichment

1. Parse the user's argument.
2. Confirm project is tracked with `tier = "deep"`. If not, suggest editing config.
3. Call `project-expert-kg-refresh --project <repo> --force`.
4. Report the result.
```

- [ ] **Step 3: Create ask skill**

`skills/ask/SKILL.md`:
```markdown
---
name: ask
description: Explicitly delegate a project question to the project-expert
  subagent. Usage `/project-expert:ask <question>`. Use this when the main
  conversation should not handle the question directly.
---

# Ask the project-expert subagent

Dispatch the user's question via the Task tool to the `project-expert` subagent.
Return its response verbatim.

The subagent will consult projects.* MCP tools and cite file:line references.
```

- [ ] **Step 4: Commit**

```bash
git add skills/refresh/ skills/enrich/ skills/ask/
git commit -m "feat: add /project-expert:refresh, :enrich, :ask skills"
```

---

## Task 19: Scripts — sync + kg_refresh + add_project

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/sync.py`
- Create: `scripts/kg_refresh.py`
- Create: `scripts/add_project.py`
- Update: `src/project_expert/scripts/__init__.py` (re-export for CLI scripts entrypoints)

- [ ] **Step 1: Create scripts module structure**

Move the actual implementations into the package so `pyproject.toml`'s `[project.scripts]` entry points work:

```bash
mkdir -p ~/projects/project-expert/src/project_expert/scripts
touch ~/projects/project-expert/src/project_expert/scripts/__init__.py
```

- [ ] **Step 2: Implement sync.py**

`src/project_expert/scripts/sync.py`:
```python
"""Daily sync entrypoint.

Run via `project-expert-sync` (from pyproject scripts) or scheduled by cron.

Examples:
  project-expert-sync                           # all projects
  project-expert-sync --project microsoft/agent-framework
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from project_expert.config import Config
from project_expert.mirror import MirrorManager
from project_expert.state import State
from project_expert.symbol_index import build_index


CONFIG_PATH = Path("~/.config/project-expert/config.toml").expanduser()
STATE_PATH = Path("~/.config/project-expert/state.json").expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(prog="project-expert-sync")
    parser.add_argument("--project", help="Sync only this project (owner/repo or nickname).")
    args = parser.parse_args()

    cfg = Config.load(CONFIG_PATH)
    state = State.load(STATE_PATH)
    mirror_mgr = MirrorManager(mirrors_root=cfg.settings.mirrors_dir, clone_depth=cfg.settings.clone_depth)

    projects = cfg.projects
    if args.project:
        proj = cfg.find_project(args.project)
        if proj is None:
            print(f"Unknown project: {args.project}")
            return 1
        projects = [proj]

    now = datetime.now(timezone.utc)
    for proj in projects:
        print(f"[{proj.repo}] pulling...")
        try:
            mirror_path = mirror_mgr.ensure(proj.repo, remote=f"https://github.com/{proj.repo}")
            sha = mirror_mgr.head_sha(mirror_path)
            state.record_pull(proj.repo, sha=sha, now=now)
            print(f"[{proj.repo}] HEAD={sha[:12]}")

            print(f"[{proj.repo}] indexing symbols...")
            idx_path = cfg.settings.index_dir / proj.repo.replace("/", "__") / "symbols.json"
            build_index(repo_root=mirror_path, output=idx_path)

            # Update drift count
            entry = state.projects[proj.repo]
            if entry.last_kg_source_sha:
                state.set_commits_since_kg(proj.repo, mirror_mgr.commits_since(mirror_path, entry.last_kg_source_sha))
        except Exception as exc:  # noqa: BLE001
            state.record_failure(proj.repo, str(exc))
            print(f"[{proj.repo}] FAILED: {exc}")
            continue

    state.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Implement kg_refresh.py**

`src/project_expert/scripts/kg_refresh.py`:
```python
"""Weekly KG refresh entrypoint.

Skips projects whose drift since last KG is below `kg_force_on_drift_commits`
unless --force is set.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from project_expert.config import Config
from project_expert.kg_runner import KGRunner
from project_expert.mirror import MirrorManager
from project_expert.state import State


CONFIG_PATH = Path("~/.config/project-expert/config.toml").expanduser()
STATE_PATH = Path("~/.config/project-expert/state.json").expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(prog="project-expert-kg-refresh")
    parser.add_argument("--project", help="Refresh only this project.")
    parser.add_argument("--force", action="store_true", help="Ignore drift threshold.")
    args = parser.parse_args()

    cfg = Config.load(CONFIG_PATH)
    state = State.load(STATE_PATH)
    mirror_mgr = MirrorManager(mirrors_root=cfg.settings.mirrors_dir, clone_depth=cfg.settings.clone_depth)
    runner = KGRunner()

    projects = [p for p in cfg.projects if p.tier == "deep"]
    if args.project:
        projects = [p for p in projects if p.repo == args.project or p.nickname == args.project]

    now = datetime.now(timezone.utc)
    for proj in projects:
        entry = state.projects.get(proj.repo)
        drift = entry.commits_since_kg if entry else 0
        if not args.force and drift < cfg.refresh.kg_force_on_drift_commits:
            print(f"[{proj.repo}] skip (drift={drift} < threshold)")
            continue

        mirror_path = cfg.settings.mirrors_dir / proj.repo.replace("/", "__")
        if not mirror_path.exists():
            print(f"[{proj.repo}] no mirror; run sync first")
            continue

        kg_dir = cfg.settings.kg_dir / proj.repo.replace("/", "__")
        print(f"[{proj.repo}] enriching KG...")
        try:
            runner.run(repo_root=mirror_path, kg_dir=kg_dir, languages=proj.languages)
            sha = mirror_mgr.head_sha(mirror_path)
            state.record_kg_refresh(proj.repo, sha=sha, now=now)
            print(f"[{proj.repo}] KG ok")
        except Exception as exc:  # noqa: BLE001
            state.record_failure(proj.repo, str(exc))
            print(f"[{proj.repo}] KG FAILED: {exc}")

    state.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Implement add_project.py**

`src/project_expert/scripts/add_project.py`:
```python
"""Add a project to config.

Used by the `/project-expert:add` skill but also runnable as `project-expert-add owner/repo`.
"""
import argparse
import re
import subprocess
from pathlib import Path


CONFIG_PATH = Path("~/.config/project-expert/config.toml").expanduser()


def _parse(arg: str) -> str:
    m = re.search(r"(?:https?://github\.com/)?([\w.-]+/[\w.-]+?)(?:\.git)?/?$", arg.strip())
    if not m:
        raise ValueError(f"cannot parse {arg!r} as owner/repo")
    return m.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(prog="project-expert-add")
    parser.add_argument("repo", help="owner/repo or full GitHub URL")
    parser.add_argument("--tier", default="deep", choices=["deep", "mirror_only", "docs_only"])
    parser.add_argument("--nickname", default=None)
    args = parser.parse_args()

    repo = _parse(args.repo)
    print(f"Adding {repo}...")

    # Validate repo exists.
    try:
        subprocess.run(  # noqa: S603
            ["gh", "api", f"repos/{repo}"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Cannot verify repo {repo} via gh CLI: {exc}")
        print("(Proceeding anyway — gh may not be installed; sync will fail loudly if repo is wrong.)")

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else (
        '[llm]\nprovider = "anthropic"\nmodel = "claude-opus-4-7"\napi_key_env = "ANTHROPIC_API_KEY"\n'
    )

    if f'repo = "{repo}"' in existing:
        print(f"{repo} already tracked.")
        return 0

    block = f'\n[[projects]]\nrepo = "{repo}"\ntier = "{args.tier}"\n'
    if args.nickname:
        block += f'nickname = "{args.nickname}"\n'
    CONFIG_PATH.write_text(existing + block, encoding="utf-8")
    print(f"Added {repo} to config. Run `project-expert-sync --project {repo}` to clone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Smoke-test scripts**

```bash
cd ~/projects/project-expert
uv sync
uv run project-expert-add --help    # exit 0, prints usage
uv run project-expert-sync --help   # exit 0
uv run project-expert-kg-refresh --help   # exit 0
```

- [ ] **Step 6: Commit**

```bash
git add src/project_expert/scripts/
git commit -m "feat: add sync, kg_refresh, and add_project CLI scripts"
```

---

## Task 20: Documentation + e2e scaffold

**Files:**
- Modify: `README.md`
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/test_smoke.py`

- [ ] **Step 1: Polish README**

Replace `README.md`:

````markdown
# project-expert

Claude Code plugin: turn Claude into a domain expert on tracked OSS projects via local mirrors, LLM-generated knowledge graphs, and a citation-required subagent.

See [the design spec](https://github.com/microsoft/agent-framework/blob/main/docs/superpowers/specs/2026-05-18-project-expert-design.md).

## Prerequisites

- Python ≥ 3.11
- `uv` (https://docs.astral.sh/uv/)
- `git`
- `ripgrep` — install via `brew install ripgrep` (macOS), `apt install ripgrep` (Linux), or `winget install BurntSushi.ripgrep.MSVC` (Windows)
- `gh` CLI (optional, only used by `/project-expert:add` for repo validation)
- Claude Code with the `understand-anything` plugin installed (for KG generation)

## Install

```bash
cd ~/projects
git clone <this-repo> project-expert
cd project-expert
uv sync
ln -s ~/projects/project-expert ~/.claude/plugins/project-expert
```

Restart Claude Code. The plugin's MCP server, the `project-expert` subagent, and six slash commands (`/project-expert:add`, `:remove`, `:list`, `:refresh`, `:enrich`, `:ask`) are auto-registered.

## Configure

Create `~/.config/project-expert/config.toml`:

```toml
[llm]
provider = "anthropic"
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"

[[projects]]
repo = "microsoft/agent-framework"
tier = "deep"
```

Set environment variables:

- `ANTHROPIC_API_KEY` — for KG generation
- `GITHUB_TOKEN` — for `projects.issues` (recommended; without it, that one tool returns `upstream_unavailable`)

## Scheduling

The plugin provides commands; you wire them into your OS scheduler.

### Linux / macOS — cron

```bash
crontab -e
```

Add:

```
0 3 * * * /usr/local/bin/uv run --project ~/projects/project-expert project-expert-sync >> /tmp/project-expert-sync.log 2>&1
0 4 * * 0 /usr/local/bin/uv run --project ~/projects/project-expert project-expert-kg-refresh >> /tmp/project-expert-kg.log 2>&1
```

### macOS — launchd

Create `~/Library/LaunchAgents/com.projectexpert.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.projectexpert.sync</string>
  <key>ProgramArguments</key>
    <array>
      <string>/usr/local/bin/uv</string>
      <string>run</string>
      <string>--project</string>
      <string>/Users/YOU/projects/project-expert</string>
      <string>project-expert-sync</string>
    </array>
  <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
</dict>
</plist>
```

Then `launchctl load ~/Library/LaunchAgents/com.projectexpert.sync.plist`.

### Windows — Task Scheduler

```powershell
$action = New-ScheduledTaskAction -Execute "uv" -Argument "run --project $HOME\projects\project-expert project-expert-sync"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "ProjectExpertSync"
```

## Usage

```
/project-expert:add NVIDIA/NeMo-Agent-Toolkit
/project-expert:refresh --project NVIDIA/NeMo-Agent-Toolkit --force-kg
/project-expert:ask How does NAT route function calls into a workflow?
```

The `project-expert` subagent will consult MCP tools and answer with `file:line` citations.

## Lazy fallback

If you never set up scheduling, the MCP tools still work — they detect stale mirrors and trigger pulls on demand. You'll just pay the pull cost in your first query of the day.
````

- [ ] **Step 2: Create e2e test scaffold**

`tests/e2e/__init__.py`: (empty)

`tests/e2e/test_smoke.py`:
```python
"""End-to-end smoke tests. Real LLM, real GitHub. Never in CI.

Run with:
    cd ~/projects/project-expert
    uv run pytest tests/e2e -m e2e -v

Requires:
- ~/.config/project-expert/config.toml with at least one project
- ANTHROPIC_API_KEY env var
- GITHUB_TOKEN env var (optional but recommended)
- ripgrep installed
- understand-anything Claude Code plugin installed
"""
import os
from pathlib import Path

import pytest


@pytest.mark.e2e
def test_config_loads() -> None:
    from project_expert.config import Config
    cfg = Config.load(Path("~/.config/project-expert/config.toml").expanduser())
    assert len(cfg.projects) > 0, "config has no tracked projects"


@pytest.mark.e2e
def test_sync_runs_for_first_project() -> None:
    from project_expert.config import Config
    from project_expert.mirror import MirrorManager

    cfg = Config.load(Path("~/.config/project-expert/config.toml").expanduser())
    proj = cfg.projects[0]
    mgr = MirrorManager(mirrors_root=cfg.settings.mirrors_dir, clone_depth=cfg.settings.clone_depth)
    path = mgr.ensure(proj.repo, remote=f"https://github.com/{proj.repo}")
    assert path.exists()


@pytest.mark.e2e
def test_mcp_server_lists_tools() -> None:
    from project_expert.mcp.server import build_server
    facade = build_server()
    tool_names = facade.list_tool_names()
    assert len(tool_names) == 10
```

- [ ] **Step 3: Verify full unit + integration suite passes**

```bash
cd ~/projects/project-expert && uv run pytest tests/ -v --ignore=tests/e2e
```
Expected: all tests pass. E2E tests not collected (no `-m e2e` flag).

- [ ] **Step 4: Run lint and typecheck**

```bash
cd ~/projects/project-expert && uv run ruff check src/ && uv run mypy src/
```
Expected: clean (or fix issues).

- [ ] **Step 5: Commit**

```bash
git add README.md tests/e2e/
git commit -m "docs: add README with platform scheduling examples and e2e smoke scaffold"
```

---

## Final verification

```bash
cd ~/projects/project-expert
uv sync
uv run pytest tests/ -v --ignore=tests/e2e   # all green
uv run ruff check src/                       # clean
uv run mypy src/                             # clean
uv run python -m project_expert.mcp.server </dev/null   # starts MCP server on stdio (will idle)
```

If all four pass, the plugin is ready for symlinking into `~/.claude/plugins/`. Restart Claude Code and verify:

1. `/project-expert:list` runs without error.
2. `/project-expert:add microsoft/agent-framework` adds a project.
3. `/project-expert:refresh --project microsoft/agent-framework` populates the mirror.
4. `/project-expert:ask How does AgentSession persist messages?` produces a subagent answer with `file:line` citations.

---

## Phase 2 signposting (NOT in this plan)

- Embedding / vector index for semantic search alongside ripgrep
- Cross-project memory store ("LangGraph 0.3 deprecated X")
- Release watcher (GitHub releases poll → notification)
- Web dashboard reusing understand-anything's UI
- Per-project LLM overrides
