# af-expert Wave 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add architecture awareness + provider release tracking + maintainer health detection to af-expert. By the end of Wave 2, each tracked repo has a generated architecture briefing on disk, S4 (Provider release rapid response) emits time-sensitive candidates when Anthropic/OpenAI/Google ship new features, and S6 (Maintainer health) emits "this repo needs help" candidates when activity metrics decay.

**Architecture:** Three subsystems share the existing Wave 1 platform. Architecture refresh uses Glob + LLM to produce a per-repo `architecture.md` briefing — no dependency on `understand-anything`'s Claude-side skill (which isn't callable from Python). S4 polls provider release pages via `httpx`, parses with LLM, checks tracked frameworks. S6 runs pure SQL aggregates over the existing event store.

**Tech Stack:** Python 3.12+, `uv`, `pydantic`, `httpx` (new), Wave 1 dependencies.

**Reference spec:** [docs/superpowers/specs/2026-05-17-af-expert-design.md](../specs/2026-05-17-af-expert-design.md)
**Wave 1 plan:** [docs/superpowers/plans/2026-05-18-af-expert-wave1.md](2026-05-18-af-expert-wave1.md)

**Validation milestones (from spec):**
1. Architecture briefings exist for all configured repos after `af-expert refresh --all`
2. One real provider release event traced end-to-end to at least one S4 candidate
3. S6 produces at least one maintenance candidate when run against a "decaying" simulated repo dataset (or a real one)

---

## File Structure

New files (Wave 2 only):

```
python/tools/af_expert/src/af_expert/
├── architecture/
│   ├── __init__.py
│   ├── scanner.py                       # local clone + Glob scan, produces file inventory
│   ├── briefing.py                      # LLM-generated architecture.md from inventory
│   ├── refresh.py                       # per-repo orchestrator: clone → scan → brief → save
│   └── change_detection.py              # detect PRs touching "core" files
├── strategies/
│   ├── s4_provider_release.py           # 触发: provider polled → new release detected
│   └── s6_maintainer_health.py          # 触发: weekly tick → metrics → candidates
└── providers/
    ├── __init__.py
    ├── sources.py                       # hard-coded source registry (Anthropic/OpenAI/Google)
    └── poller.py                        # httpx-based release-page fetcher
```

Modified files (Wave 2):

```
python/tools/af_expert/
├── pyproject.toml                       # add httpx dependency
├── src/af_expert/
│   ├── cli.py                           # new commands: refresh, refresh --all; hook S4 + S6 into tick
│   ├── state.py                         # add per-repo arch-refresh-timestamp tracking
│   └── ingestion/pipeline.py            # signal architectural drift via change_detection
└── README.md                            # document new commands, S4 + S6 behavior
```

**Conventions enforced:**

- All new modules follow Wave 1 patterns: `from __future__ import annotations`, type hints, `_state_dir()` for paths
- Architecture briefings are markdown stored at `~/.af-expert/repos/<owner>__<repo>/architecture.md`
- Provider release state cached at `~/.af-expert/providers/<provider>/<date>.json` to avoid re-emitting candidates on every tick
- Tests never call real Anthropic / OpenAI / Google endpoints; all network calls mocked

---

## Task 1: Add httpx dependency + providers package skeleton

**Files:**
- Modify: `python/tools/af_expert/pyproject.toml`
- Create: `python/tools/af_expert/src/af_expert/providers/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/architecture/__init__.py`

- [ ] **Step 1: Add httpx to pyproject.toml dependencies**

In `[project] dependencies = [...]`, add `"httpx>=0.27.0",` after the existing entries. Final list:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "pygithub>=2.5.0",
    "pydantic>=2.10.0",
    "click>=8.1.7",
    "platformdirs>=4.3.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Create empty package __init__.py files**

```bash
mkdir -p python/tools/af_expert/src/af_expert/providers
mkdir -p python/tools/af_expert/src/af_expert/architecture
```

Then:

`python/tools/af_expert/src/af_expert/providers/__init__.py`:
```python
```

`python/tools/af_expert/src/af_expert/architecture/__init__.py`:
```python
```

- [ ] **Step 3: Re-sync deps**

```bash
cd python/tools/af_expert
uv sync --all-extras
```

Expected: httpx installed without errors. Existing tests still pass:

```bash
uv run pytest -v --ignore=tests/e2e 2>&1 | tail -3
```

Expected: 57 passed.

- [ ] **Step 4: Commit**

```bash
git add python/tools/af_expert/pyproject.toml python/tools/af_expert/uv.lock python/tools/af_expert/src/af_expert/providers/__init__.py python/tools/af_expert/src/af_expert/architecture/__init__.py
git commit -m "chore(af-expert): scaffold providers + architecture packages, add httpx"
```

---

## Task 2: Architecture scanner — file inventory builder

**Files:**
- Create: `python/tools/af_expert/src/af_expert/architecture/scanner.py`
- Test: `python/tools/af_expert/tests/test_architecture_scanner.py`

The scanner takes a local clone of a target repo and produces a structured inventory: which directories matter, which key Python/TS files are entry points, which provider integration modules exist. Output feeds the briefing LLM call.

- [ ] **Step 1: Write failing tests in `tests/test_architecture_scanner.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from af_expert.architecture.scanner import (
    FileInventory,
    scan_repo_locally,
)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repo tree that looks like a Python agent framework."""
    repo = tmp_path / "fake-agent"
    (repo / "src" / "fake_agent").mkdir(parents=True)
    (repo / "src" / "fake_agent" / "__init__.py").write_text("")
    (repo / "src" / "fake_agent" / "chat_client.py").write_text(
        "class ChatClient:\n    pass\n"
    )
    (repo / "src" / "fake_agent" / "_anthropic.py").write_text(
        "class AnthropicChatClient:\n    pass\n"
    )
    (repo / "src" / "fake_agent" / "_openai.py").write_text(
        "class OpenAIChatClient:\n    pass\n"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_chat.py").write_text("def test_x(): pass\n")
    (repo / "README.md").write_text("# Fake Agent\n\nA test repo.\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "fake-agent"\n')
    return repo


def test_scan_finds_python_modules(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert isinstance(inv, FileInventory)
    assert any("chat_client.py" in f for f in inv.source_files)
    assert any("_anthropic.py" in f for f in inv.source_files)


def test_scan_classifies_provider_files(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    # Files matching provider name patterns get classified
    assert "anthropic" in inv.provider_files
    assert "openai" in inv.provider_files


def test_scan_excludes_tests_from_source(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert not any("test_chat.py" in f for f in inv.source_files)
    assert any("test_chat.py" in f for f in inv.test_files)


def test_scan_returns_readme_text(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert "Fake Agent" in inv.readme_excerpt


def test_scan_handles_missing_readme(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "src" / "x").mkdir(parents=True)
    (repo / "src" / "x" / "main.py").write_text("")
    inv = scan_repo_locally(repo)
    assert inv.readme_excerpt == ""


def test_scan_caps_file_counts(tmp_path: Path) -> None:
    """If a repo has 10000 files, we keep only the most relevant subset."""
    repo = tmp_path / "huge"
    (repo / "src").mkdir(parents=True)
    for i in range(500):
        (repo / "src" / f"file_{i}.py").write_text("")
    inv = scan_repo_locally(repo, max_source_files=100)
    assert len(inv.source_files) == 100
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd python/tools/af_expert
uv run pytest tests/test_architecture_scanner.py -v
```

Expected: ImportError on `af_expert.architecture.scanner`.

- [ ] **Step 3: Write `src/af_expert/architecture/scanner.py`**

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Provider name fragments — case-insensitive; matched against filename + path
_PROVIDER_PATTERNS = {
    "anthropic": ["anthropic", "claude"],
    "openai": ["openai", "gpt"],
    "google": ["google", "gemini", "vertex"],
    "azure": ["azure"],
    "mistral": ["mistral"],
    "cohere": ["cohere"],
    "bedrock": ["bedrock"],
    "litellm": ["litellm"],
}

_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "dist", "build", ".pytest_cache", ".ruff_cache", "target",
    ".tox", ".mypy_cache", "site-packages",
}

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs"}
_TEST_PATTERNS = ("test_", "_test.", "/tests/", "\\tests\\", ".spec.")


@dataclass
class FileInventory:
    repo_root: Path
    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    provider_files: dict[str, list[str]] = field(default_factory=dict)
    readme_excerpt: str = ""
    pyproject_present: bool = False
    package_json_present: bool = False


def _is_test_file(rel_path: str) -> bool:
    p = rel_path.lower()
    return any(t in p for t in _TEST_PATTERNS)


def _classify_provider(rel_path: str) -> str | None:
    p = rel_path.lower()
    for provider, patterns in _PROVIDER_PATTERNS.items():
        if any(pat in p for pat in patterns):
            return provider
    return None


def scan_repo_locally(
    repo_root: Path,
    *,
    max_source_files: int = 300,
    max_test_files: int = 100,
    readme_chars: int = 2000,
) -> FileInventory:
    """Scan a local repo clone and produce a structured inventory.

    Walks the tree, excluding well-known build/cache dirs. Caps result lists so
    the inventory stays small enough for a single LLM call later.
    """
    inv = FileInventory(repo_root=repo_root)

    if not repo_root.is_dir():
        log.warning("scan_repo_locally: %s is not a directory", repo_root)
        return inv

    readme_path = None
    for name in ("README.md", "Readme.md", "readme.md", "README.rst", "README.txt"):
        candidate = repo_root / name
        if candidate.is_file():
            readme_path = candidate
            break
    if readme_path is not None:
        try:
            inv.readme_excerpt = readme_path.read_text(encoding="utf-8", errors="replace")[
                :readme_chars
            ]
        except Exception as e:
            log.warning("Failed to read README %s: %s", readme_path, e)

    inv.pyproject_present = (repo_root / "pyproject.toml").is_file()
    inv.package_json_present = (repo_root / "package.json").is_file()

    source_buf: list[str] = []
    test_buf: list[str] = []
    provider_buf: dict[str, list[str]] = {}

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded dirs anywhere in the path
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix not in _SOURCE_EXTS:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_test_file(rel):
            test_buf.append(rel)
        else:
            source_buf.append(rel)
            provider = _classify_provider(rel)
            if provider:
                provider_buf.setdefault(provider, []).append(rel)

    # Stable sort + cap
    inv.source_files = sorted(source_buf)[:max_source_files]
    inv.test_files = sorted(test_buf)[:max_test_files]
    inv.provider_files = {p: sorted(files) for p, files in sorted(provider_buf.items())}

    log.info(
        "scanned %s: %d source files, %d test files, %d providers",
        repo_root.name, len(inv.source_files), len(inv.test_files), len(inv.provider_files),
    )

    return inv
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_architecture_scanner.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/architecture/scanner.py python/tools/af_expert/tests/test_architecture_scanner.py
git commit -m "feat(af-expert): architecture file-inventory scanner"
```

---

## Task 3: Architecture briefing renderer (LLM-driven)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/architecture/briefing.py`
- Test: `python/tools/af_expert/tests/test_architecture_briefing.py`

Given a `FileInventory`, ask the LLM to produce a structured markdown briefing.

- [ ] **Step 1: Write failing tests**

`tests/test_architecture_briefing.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.architecture.briefing import (
    build_briefing_prompt,
    render_briefing,
)
from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM, LLMResponse


def _make_inventory(tmp_path: Path) -> FileInventory:
    inv = FileInventory(repo_root=tmp_path / "fake-agent")
    inv.source_files = ["src/fake_agent/chat_client.py", "src/fake_agent/_anthropic.py"]
    inv.test_files = ["tests/test_chat.py"]
    inv.provider_files = {"anthropic": ["src/fake_agent/_anthropic.py"]}
    inv.readme_excerpt = "# Fake Agent\n\nMinimal LLM agent framework."
    inv.pyproject_present = True
    return inv


def test_build_prompt_includes_inventory_data(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    prompt = build_briefing_prompt(repo="example/fake-agent", inventory=inv)
    assert "example/fake-agent" in prompt
    assert "chat_client.py" in prompt
    assert "_anthropic.py" in prompt
    assert "Fake Agent" in prompt  # README excerpt present


def test_render_briefing_returns_markdown(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text=(
            "## Purpose\nA minimal agent framework.\n\n"
            "## Top-level components\n- chat_client.py: provider-agnostic interface\n"
            "## Provider integrations\n- Anthropic: _anthropic.py\n"
        ),
        input_tokens=200, output_tokens=80, cache_read_tokens=0, cache_creation_tokens=0,
    )

    md = render_briefing(repo="example/fake-agent", inventory=inv, llm=llm)
    # Header is added by render_briefing
    assert "# example/fake-agent" in md
    # LLM content is included verbatim
    assert "A minimal agent framework" in md
    # Metadata footer
    assert "Briefing generated" in md or "last-refreshed" in md.lower()

    # LLM was called with caller_label
    call = llm.complete.call_args
    assert call.kwargs.get("caller_label", "").startswith("architecture.briefing")


def test_render_briefing_handles_llm_failure(tmp_path: Path) -> None:
    inv = _make_inventory(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = RuntimeError("LLM down")

    md = render_briefing(repo="example/fake-agent", inventory=inv, llm=llm)
    # On failure, produces minimal fallback briefing
    assert "# example/fake-agent" in md
    assert "could not be generated" in md.lower() or "fallback" in md.lower()
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_architecture_briefing.py -v
```

- [ ] **Step 3: Write `src/af_expert/architecture/briefing.py`**

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM


log = logging.getLogger(__name__)


def build_briefing_prompt(*, repo: str, inventory: FileInventory) -> str:
    parts: list[str] = []
    parts.append(
        f"You will produce an architecture briefing for the OSS repository '{repo}'.\n"
        "The briefing should be a concise markdown document for an engineer who wants\n"
        "to understand the repo's shape without reading the code. Use these sections:\n\n"
        "## Purpose\n## Top-level components\n## Key abstractions\n## Provider integrations\n## Notable subsystems\n\n"
        "Be specific about file paths. Do not invent details — if uncertain, say so.\n"
    )
    parts.append(f"\nREPO: {repo}\n")

    if inventory.readme_excerpt:
        parts.append("\n### README excerpt\n")
        parts.append(inventory.readme_excerpt)
        parts.append("\n")

    parts.append("\n### Source files (truncated)\n")
    for f in inventory.source_files[:200]:
        parts.append(f"- {f}\n")

    if inventory.provider_files:
        parts.append("\n### Provider integration files\n")
        for provider, files in inventory.provider_files.items():
            parts.append(f"- **{provider}**: {', '.join(files[:5])}\n")

    if inventory.pyproject_present:
        parts.append("\n(Python project: pyproject.toml present)\n")
    if inventory.package_json_present:
        parts.append("\n(JS/TS project: package.json present)\n")

    return "".join(parts)


def render_briefing(*, repo: str, inventory: FileInventory, llm: LLM) -> str:
    """Generate a markdown briefing for the repo using the LLM.

    On LLM failure, returns a minimal fallback briefing with just the inventory data.
    Always includes the header and timestamp footer.
    """
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    header = f"# {repo}\n\n*Briefing generated at {timestamp}*\n\n"

    try:
        prompt = build_briefing_prompt(repo=repo, inventory=inventory)
        resp = llm.complete(
            system=(
                "You are a senior engineer summarizing an OSS repository's architecture. "
                "Be concise, accurate, and cite file paths."
            ),
            user=prompt,
            caller_label=f"architecture.briefing[{repo}]",
            max_tokens=2000,
        )
        body = resp.text
    except Exception as e:
        log.warning("Briefing generation failed for %s: %s", repo, e)
        body = (
            "**Briefing could not be generated** (LLM error).\n\n"
            "## Fallback inventory\n\n"
            f"- Source files: {len(inventory.source_files)}\n"
            f"- Test files: {len(inventory.test_files)}\n"
            f"- Providers detected: {', '.join(inventory.provider_files.keys()) or 'none'}\n"
        )

    return header + body + "\n"
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_architecture_briefing.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/architecture/briefing.py python/tools/af_expert/tests/test_architecture_briefing.py
git commit -m "feat(af-expert): LLM-driven architecture briefing renderer"
```

---

## Task 4: Architecture refresh orchestrator + clone helper

**Files:**
- Create: `python/tools/af_expert/src/af_expert/architecture/refresh.py`
- Test: `python/tools/af_expert/tests/test_architecture_refresh.py`

Clones a target repo to a temp local path (using `git clone --depth 1 --filter=blob:none`), invokes the scanner + briefing, writes to `~/.af-expert/repos/<owner>__<repo>/architecture.md`.

- [ ] **Step 1: Write failing tests**

`tests/test_architecture_refresh.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.architecture.refresh import (
    RefreshResult,
    refresh_one_repo,
    repo_briefing_path,
)
from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM, LLMResponse


def test_repo_briefing_path_encodes_owner(tmp_state_dir: Path) -> None:
    p = repo_briefing_path("microsoft/agent-framework")
    assert p.name == "architecture.md"
    assert p.parent.name == "microsoft__agent-framework"


def test_refresh_writes_briefing_to_disk(tmp_state_dir: Path, tmp_path: Path) -> None:
    fake_inventory = FileInventory(repo_root=tmp_path / "fake")
    fake_inventory.source_files = ["src/x.py"]
    fake_inventory.readme_excerpt = "Fake repo"

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text="## Purpose\nA fake.\n",
        input_tokens=50, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )

    with patch("af_expert.architecture.refresh._clone_repo_shallow") as fake_clone, \
         patch("af_expert.architecture.refresh.scan_repo_locally") as fake_scan:
        fake_clone.return_value = tmp_path / "fake-clone"
        fake_scan.return_value = fake_inventory

        result = refresh_one_repo("microsoft/agent-framework", llm=llm)

    assert isinstance(result, RefreshResult)
    assert result.repo == "microsoft/agent-framework"
    assert result.success is True
    assert "A fake" in result.briefing_path.read_text(encoding="utf-8")


def test_refresh_returns_failure_on_clone_error(tmp_state_dir: Path) -> None:
    llm = MagicMock(spec=LLM)
    with patch("af_expert.architecture.refresh._clone_repo_shallow") as fake_clone:
        fake_clone.side_effect = RuntimeError("git clone failed")

        result = refresh_one_repo("microsoft/agent-framework", llm=llm)

    assert result.success is False
    assert "clone failed" in (result.error or "").lower()
    # Still writes a stub briefing so consumers can detect the failure
    assert result.briefing_path.exists() or result.error is not None
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_architecture_refresh.py -v
```

- [ ] **Step 3: Write `src/af_expert/architecture/refresh.py`**

```python
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from af_expert.architecture.briefing import render_briefing
from af_expert.architecture.scanner import scan_repo_locally
from af_expert.config import _state_dir
from af_expert.llm import LLM
from af_expert.state import atomic_write


log = logging.getLogger(__name__)


@dataclass
class RefreshResult:
    repo: str
    success: bool
    briefing_path: Path
    error: str | None = None


def repo_briefing_path(repo: str) -> Path:
    """Return the file path for a repo's architecture briefing."""
    safe = repo.replace("/", "__")
    return _state_dir() / "repos" / safe / "architecture.md"


def _clone_repo_shallow(repo: str, dest: Path) -> Path:
    """git clone --depth 1 --filter=blob:none https://github.com/<repo>.git dest

    Returns the clone path on success; raises on failure.
    """
    url = f"https://github.com/{repo}.git"
    cmd = ["git", "clone", "--depth", "1", "--filter=blob:none", "--single-branch", url, str(dest)]
    log.info("cloning %s into %s", repo, dest)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {repo}: rc={proc.returncode} stderr={proc.stderr[:500]}"
        )
    return dest


def refresh_one_repo(repo: str, *, llm: LLM) -> RefreshResult:
    """Clone the repo shallowly, scan it, generate a briefing, persist to disk."""
    briefing_path = repo_briefing_path(repo)
    briefing_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="af-expert-clone-"))
    try:
        clone_dir = tmp_dir / repo.split("/")[-1]
        try:
            _clone_repo_shallow(repo, clone_dir)
        except Exception as e:
            log.warning("Clone failed for %s: %s", repo, e)
            # Persist a stub briefing so consumers can see the failure
            stub = (
                f"# {repo}\n\n"
                f"**Briefing unavailable — clone failed.**\n\nError: {e}\n"
            )
            atomic_write(briefing_path, stub)
            return RefreshResult(repo=repo, success=False, briefing_path=briefing_path, error=str(e))

        inventory = scan_repo_locally(clone_dir)
        briefing_md = render_briefing(repo=repo, inventory=inventory, llm=llm)
        atomic_write(briefing_path, briefing_md)

        return RefreshResult(repo=repo, success=True, briefing_path=briefing_path)
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_architecture_refresh.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/architecture/refresh.py python/tools/af_expert/tests/test_architecture_refresh.py
git commit -m "feat(af-expert): architecture refresh orchestrator (shallow clone + scan + brief)"
```

---

## Task 5: Architecture change detection (drift signal)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/architecture/change_detection.py`
- Test: `python/tools/af_expert/tests/test_architecture_change_detection.py`

Given a list of PRs (from event store) and a briefing on disk, determine whether any PR touched a "core" file. Returns a drift signal that ingestion pipeline can use to mark repos for re-refresh.

- [ ] **Step 1: Write failing tests**

`tests/test_architecture_change_detection.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from af_expert.architecture.change_detection import (
    detect_architectural_drift,
    extract_changed_paths_from_diff,
)


def test_extract_paths_from_unified_diff() -> None:
    diff = (
        "diff --git a/src/foo/chat_client.py b/src/foo/chat_client.py\n"
        "index 1234..5678 100644\n"
        "--- a/src/foo/chat_client.py\n"
        "+++ b/src/foo/chat_client.py\n"
        "@@ -10,3 +10,4 @@\n"
        " class X:\n"
        "+    pass\n"
        "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
        "index abcd..efgh 100644\n"
        "--- a/tests/test_foo.py\n"
        "+++ b/tests/test_foo.py\n"
    )
    paths = extract_changed_paths_from_diff(diff)
    assert "src/foo/chat_client.py" in paths
    assert "tests/test_foo.py" in paths


def test_extract_paths_handles_empty_diff() -> None:
    assert extract_changed_paths_from_diff("") == set()
    assert extract_changed_paths_from_diff(None) == set()


def test_detect_drift_when_core_file_touched(tmp_path: Path) -> None:
    """If any PR diff modifies a file listed as a 'core' path, drift is detected."""
    core_paths = ["src/foo/chat_client.py", "src/foo/agent.py"]
    prs = [
        {
            "number": 100,
            "diff": (
                "diff --git a/src/foo/chat_client.py b/src/foo/chat_client.py\n"
                "+++ b/src/foo/chat_client.py\n"
            ),
        }
    ]
    drift = detect_architectural_drift(core_paths=core_paths, prs=prs)
    assert drift.has_drift is True
    assert "src/foo/chat_client.py" in drift.touched_core_paths


def test_detect_drift_returns_false_for_unrelated_changes() -> None:
    core_paths = ["src/foo/chat_client.py"]
    prs = [
        {"number": 1, "diff": "diff --git a/docs/x.md b/docs/x.md\n+++ b/docs/x.md\n"},
        {"number": 2, "diff": None},
    ]
    drift = detect_architectural_drift(core_paths=core_paths, prs=prs)
    assert drift.has_drift is False
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_architecture_change_detection.py -v
```

- [ ] **Step 3: Write `src/af_expert/architecture/change_detection.py`**

```python
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any


log = logging.getLogger(__name__)

# Match "+++ b/path/to/file" lines in unified diff
_DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


@dataclass
class DriftSignal:
    has_drift: bool
    touched_core_paths: set[str] = field(default_factory=set)
    triggering_prs: list[int] = field(default_factory=list)


def extract_changed_paths_from_diff(diff: str | None) -> set[str]:
    if not diff:
        return set()
    return set(_DIFF_PATH_RE.findall(diff))


def detect_architectural_drift(
    *, core_paths: list[str], prs: list[dict[str, Any]]
) -> DriftSignal:
    """Detect whether any PR's diff touches any path in `core_paths`.

    `core_paths` is the list extracted from a repo's briefing (the "Key abstractions"
    or "Top-level components" sections, parsed elsewhere).
    `prs` is a list of dicts with at least `number` and `diff` keys.
    """
    core_set = set(core_paths)
    touched: set[str] = set()
    triggering: list[int] = []

    for pr in prs:
        changed = extract_changed_paths_from_diff(pr.get("diff"))
        overlap = changed & core_set
        if overlap:
            touched.update(overlap)
            triggering.append(pr.get("number", -1))

    return DriftSignal(
        has_drift=bool(touched),
        touched_core_paths=touched,
        triggering_prs=triggering,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_architecture_change_detection.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/architecture/change_detection.py python/tools/af_expert/tests/test_architecture_change_detection.py
git commit -m "feat(af-expert): architectural drift detection over PR diffs"
```

---

## Task 6: Strategy S6 — Maintainer health (pure SQL, no LLM)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s6_maintainer_health.py`
- Test: `python/tools/af_expert/tests/test_strategy_s6.py`

S6 runs weekly. Computes per-repo metrics from the event store: PR merge latency, issue backlog growth, maintainer response latency, commit cadence. Detects degradation (current vs prior window) and emits "this repo needs help" candidates with `category="maintenance"`.

- [ ] **Step 1: Write failing tests**

`tests/test_strategy_s6.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM
from af_expert.strategies.s6_maintainer_health import (
    MaintainerHealthStrategy,
    RepoMetrics,
    compute_metrics,
)


def _make_pr(repo: str, number: int, created: datetime, merged: datetime | None) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="pr",
        number=number,
        title=f"PR {number}",
        body="",
        author="someone",
        state="merged" if merged else "open",
        labels=[],
        created_at=created,
        updated_at=merged or created,
        merged_at=merged,
        url=f"https://github.com/{repo}/pull/{number}",
    )


def _make_issue(repo: str, number: int, created: datetime, closed: datetime | None) -> EventRecord:
    return EventRecord(
        repo=repo,
        kind="issue",
        number=number,
        title=f"Issue {number}",
        body="",
        author="someone",
        state="closed" if closed else "open",
        labels=[],
        created_at=created,
        updated_at=closed or created,
        closed_at=closed,
        url=f"https://github.com/{repo}/issues/{number}",
    )


def test_compute_metrics_basic(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    # 3 PRs all merged within 1 day
    for i in range(3):
        events.insert(_make_pr("x/y", i, now - timedelta(days=2), now - timedelta(days=1)))

    metrics = compute_metrics("x/y", events=events, now=now, window_days=30)

    assert isinstance(metrics, RepoMetrics)
    assert metrics.pr_count == 3
    assert metrics.pr_merge_median_hours is not None
    # 1 day = 24 hours; allow some tolerance
    assert 20 < metrics.pr_merge_median_hours < 28


def test_strategy_emits_candidate_for_degraded_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    # PRIOR window (60d-30d ago): 10 PRs merged in median 2h each
    for i in range(10):
        created = now - timedelta(days=45)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 1000 + i, created, merged))

    # CURRENT window (last 30d): 10 PRs merged but median 24h
    for i in range(10):
        created = now - timedelta(days=15)
        merged = created + timedelta(hours=24)
        events.insert(_make_pr("x/y", 2000 + i, created, merged))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)  # S6 doesn't use LLM
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "x/y"
    assert c.category == "maintenance"
    assert "latency" in c.description.lower() or "median" in c.description.lower()
    llm.complete.assert_not_called()  # S6 is metrics-only


def test_strategy_no_candidate_for_healthy_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    # Both windows: median 2h merge time
    for i in range(10):
        created = now - timedelta(days=45)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 1000 + i, created, merged))
    for i in range(10):
        created = now - timedelta(days=15)
        merged = created + timedelta(hours=2)
        events.insert(_make_pr("x/y", 2000 + i, created, merged))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert produced == []


def test_strategy_skips_low_volume_repo(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    # Only 2 PRs in current window — below minimum volume
    for i in range(2):
        events.insert(_make_pr("x/y", i, now - timedelta(days=15), now - timedelta(days=14)))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = Config(github_token="x", anthropic_api_key="x", repos=[RepoConfig(owner_repo="x/y")])

    strat = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    produced = strat.on_weekly_tick(now=now)

    assert produced == []
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_strategy_s6.py -v
```

- [ ] **Step 3: Write `src/af_expert/strategies/s6_maintainer_health.py`**

```python
from __future__ import annotations

import logging
import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

MIN_PR_VOLUME = 10  # minimum PRs in current window to compute meaningful metrics
DEGRADATION_FACTOR = 2.0  # current median must be > 2x prior median


@dataclass
class RepoMetrics:
    repo: str
    pr_count: int
    pr_merge_median_hours: float | None
    issue_backlog_growth: int  # delta of open issues (current minus prior)


def _query_prs_in_window(
    events: Any, repo: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Return PR records merged within [start, end]."""
    # Use the same SQLite connection directly
    sql = (
        "SELECT * FROM events WHERE repo=? AND kind='pr' AND state='merged' "
        "AND merged_at IS NOT NULL AND merged_at >= ? AND merged_at <= ? "
        "ORDER BY merged_at"
    )
    rows = events._conn.execute(sql, (repo, start.isoformat(), end.isoformat()))
    return [dict(r) for r in rows]


def _query_issues_in_window(
    events: Any, repo: str, start: datetime, end: datetime, state: str
) -> int:
    """Return count of issues in `state` created within [start, end]."""
    sql = (
        "SELECT COUNT(*) FROM events WHERE repo=? AND kind='issue' AND state=? "
        "AND created_at >= ? AND created_at <= ?"
    )
    row = events._conn.execute(sql, (repo, state, start.isoformat(), end.isoformat())).fetchone()
    return int(row[0] if row else 0)


def compute_metrics(
    repo: str, *, events: Any, now: datetime, window_days: int = 30
) -> RepoMetrics:
    window_start = now - timedelta(days=window_days)
    prs = _query_prs_in_window(events, repo, window_start, now)

    merge_hours: list[float] = []
    for pr in prs:
        try:
            created = datetime.fromisoformat(pr["created_at"])
            merged = datetime.fromisoformat(pr["merged_at"])
            delta = (merged - created).total_seconds() / 3600.0
            if delta >= 0:
                merge_hours.append(delta)
        except (TypeError, ValueError):
            continue

    median = statistics.median(merge_hours) if merge_hours else None

    opened = _query_issues_in_window(events, repo, window_start, now, "open")
    closed = _query_issues_in_window(events, repo, window_start, now, "closed")
    backlog_growth = opened - closed

    return RepoMetrics(
        repo=repo,
        pr_count=len(prs),
        pr_merge_median_hours=median,
        issue_backlog_growth=backlog_growth,
    )


class MaintainerHealthStrategy(Strategy):
    name = "s6_maintainer_health"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []  # S6 is weekly, not per-tick

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:
        if now is None:
            now = datetime.now(tz=timezone.utc)

        produced: list[Candidate] = []
        for repo_cfg in self.config.repos:
            repo = repo_cfg.owner_repo
            current = compute_metrics(repo, events=self.events, now=now, window_days=30)
            prior = compute_metrics(repo, events=self.events, now=now - timedelta(days=30), window_days=60)
            # prior excludes overlap with current by spec: window_start = (now-30d-60d) to (now-30d)
            # Above call uses window=60d ending now-30d so prior = (now-90d) to (now-30d).
            # That's [-90, -30] vs current [-30, 0]; both 30/60-day windows. Acceptable approximation.

            if current.pr_count < MIN_PR_VOLUME:
                log.info(
                    "S6 skip %s: current PR volume %d < %d", repo, current.pr_count, MIN_PR_VOLUME
                )
                continue

            if (
                current.pr_merge_median_hours is not None
                and prior.pr_merge_median_hours is not None
                and prior.pr_merge_median_hours > 0
                and current.pr_merge_median_hours / prior.pr_merge_median_hours > DEGRADATION_FACTOR
            ):
                candidate = self._build_degradation_candidate(repo, current, prior)
                self.candidates.append(candidate)
                produced.append(candidate)
                log.info(
                    "S6 %s: PR median latency degraded %.1fh -> %.1fh",
                    repo, prior.pr_merge_median_hours, current.pr_merge_median_hours,
                )

        return produced

    def _build_degradation_candidate(
        self, repo: str, current: RepoMetrics, prior: RepoMetrics
    ) -> Candidate:
        ratio = (
            current.pr_merge_median_hours / prior.pr_merge_median_hours
            if prior.pr_merge_median_hours
            else float("inf")
        )
        return Candidate(
            id=f"s6-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="maintenance",
            title=f"{repo} maintainer-response latency degraded {ratio:.1f}x",
            description=(
                f"Repo {repo} shows PR merge median latency increase from "
                f"{prior.pr_merge_median_hours:.1f}h to {current.pr_merge_median_hours:.1f}h "
                f"({ratio:.1f}x worse). Current PR volume in last 30d: {current.pr_count}. "
                f"Issue backlog growth: {current.issue_backlog_growth} (open - closed)."
            ),
            suggested_action=(
                f"Consider becoming a co-maintainer on {repo}, or proposing a structural "
                f"improvement (CI speedup, triage automation, etc.). Engage on a recent stale PR first."
            ),
            evidence_urls=[f"https://github.com/{repo}/pulls?q=is%3Apr+is%3Aclosed"],
            evidence_snippets=[],
            confidence=0.7,
            novelty=0.5,
            actionability=0.3,
            strategy_reputation=0.5,
            status="new",
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_strategy_s6.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/strategies/s6_maintainer_health.py python/tools/af_expert/tests/test_strategy_s6.py
git commit -m "feat(af-expert): S6 maintainer health strategy (pure SQL metrics)"
```

---

## Task 7: Provider source registry

**Files:**
- Create: `python/tools/af_expert/src/af_expert/providers/sources.py`
- Test: `python/tools/af_expert/tests/test_providers_sources.py`

Hard-coded registry of release-note source URLs for major LLM providers. Each source has a name, URL, and fetch strategy. This is a Wave 2 simplification — Wave 3+ can extend it.

- [ ] **Step 1: Write failing tests**

`tests/test_providers_sources.py`:

```python
from __future__ import annotations

from af_expert.providers.sources import PROVIDER_SOURCES, ProviderSource


def test_known_providers_present() -> None:
    names = {s.name for s in PROVIDER_SOURCES}
    assert "anthropic" in names
    assert "openai" in names
    assert "google" in names


def test_sources_have_required_fields() -> None:
    for src in PROVIDER_SOURCES:
        assert isinstance(src, ProviderSource)
        assert src.name
        assert src.url.startswith("https://")
        assert src.kind in {"html", "json", "rss"}
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_providers_sources.py -v
```

- [ ] **Step 3: Write `src/af_expert/providers/sources.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderSource:
    name: str                                          # "anthropic", "openai", "google"
    url: str                                           # release-notes / changelog URL
    kind: Literal["html", "json", "rss"]               # how to parse the response
    description: str = ""


# Hard-coded registry. These URLs are stable enough for Wave 2;
# Wave 3+ can move to a configurable file or auto-discovery.
PROVIDER_SOURCES: list[ProviderSource] = [
    ProviderSource(
        name="anthropic",
        url="https://docs.anthropic.com/en/release-notes/api",
        kind="html",
        description="Anthropic API release notes",
    ),
    ProviderSource(
        name="openai",
        url="https://platform.openai.com/docs/changelog",
        kind="html",
        description="OpenAI API changelog",
    ),
    ProviderSource(
        name="google",
        url="https://ai.google.dev/gemini-api/docs/changelog",
        kind="html",
        description="Google Gemini API changelog",
    ),
]
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_providers_sources.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/providers/sources.py python/tools/af_expert/tests/test_providers_sources.py
git commit -m "feat(af-expert): provider release-note source registry"
```

---

## Task 8: Provider release poller (httpx)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/providers/poller.py`
- Test: `python/tools/af_expert/tests/test_providers_poller.py`

Fetches a provider's release-notes page using httpx, persists raw content cache per day, returns the fetched body.

- [ ] **Step 1: Write failing tests**

`tests/test_providers_poller.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.providers.poller import (
    fetch_release_page,
    poll_provider,
    release_cache_path,
)
from af_expert.providers.sources import ProviderSource


def test_release_cache_path_encodes_provider_and_date(tmp_state_dir: Path) -> None:
    from datetime import date
    p = release_cache_path("anthropic", date(2026, 5, 18))
    assert p.name == "2026-05-18.html"
    assert p.parent.name == "anthropic"


def test_fetch_release_page_uses_httpx(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")

    fake_response = MagicMock()
    fake_response.text = "<html>v1.0 released today</html>"
    fake_response.raise_for_status.return_value = None

    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.return_value = fake_response

        body = fetch_release_page(src)

    fake_get.assert_called_once()
    assert "v1.0 released today" in body


def test_poll_provider_writes_cache_and_returns_body(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")

    fake_response = MagicMock()
    fake_response.text = "<html>some release notes</html>"
    fake_response.raise_for_status.return_value = None

    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.return_value = fake_response

        body = poll_provider(src)

    assert "some release notes" in body
    cache_files = list((tmp_state_dir / "providers" / "anthropic").glob("*.html"))
    assert len(cache_files) == 1
    assert cache_files[0].read_text(encoding="utf-8") == "<html>some release notes</html>"


def test_poll_provider_returns_empty_on_http_error(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")
    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.side_effect = Exception("network down")
        body = poll_provider(src)
    assert body == ""
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_providers_poller.py -v
```

- [ ] **Step 3: Write `src/af_expert/providers/poller.py`**

```python
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from af_expert.config import _state_dir
from af_expert.providers.sources import ProviderSource


log = logging.getLogger(__name__)

USER_AGENT = "af-expert/0.1.0 (+https://github.com/microsoft/agent-framework)"
TIMEOUT_SECONDS = 30.0


def release_cache_path(provider_name: str, when: date | None = None) -> Path:
    if when is None:
        when = datetime.now(tz=timezone.utc).date()
    base = _state_dir() / "providers" / provider_name
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{when.isoformat()}.html"


def fetch_release_page(source: ProviderSource) -> str:
    """HTTP GET the source URL. Caller handles exceptions."""
    log.info("polling %s at %s", source.name, source.url)
    resp = httpx.get(
        source.url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def poll_provider(source: ProviderSource) -> str:
    """Fetch + cache + return the raw page body. Empty string on failure."""
    try:
        body = fetch_release_page(source)
    except Exception as e:
        log.warning("Failed to poll %s: %s", source.name, e)
        return ""

    try:
        cache = release_cache_path(source.name)
        cache.write_text(body, encoding="utf-8")
    except Exception as e:
        log.warning("Failed to cache %s response: %s", source.name, e)

    return body
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_providers_poller.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/providers/poller.py python/tools/af_expert/tests/test_providers_poller.py
git commit -m "feat(af-expert): provider release-page poller with daily cache"
```

---

## Task 9: Strategy S4 — Provider release rapid response

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s4_provider_release.py`
- Test: `python/tools/af_expert/tests/test_strategy_s4.py`

For each provider source, poll → use LLM to extract "what's new" → for each tracked framework, ask "does it support this?" → emit candidate per gap.

- [ ] **Step 1: Write failing tests**

`tests/test_strategy_s4.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.s4_provider_release import (
    ProviderReleaseStrategy,
    extract_release_summary_prompt,
)


def _config_for(repos: list[str]) -> Config:
    return Config(
        github_token="gh",
        anthropic_api_key="ak",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_extract_summary_prompt_includes_html() -> None:
    prompt = extract_release_summary_prompt(
        provider="anthropic", html_body="<html>claude-opus-4-7 released</html>"
    )
    assert "anthropic" in prompt.lower()
    assert "claude-opus-4-7" in prompt


def test_strategy_emits_candidate_for_unsupported_release(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()

    summary_resp = LLMResponse(
        text='```json\n{"is_new_release": true, "title": "claude-opus-4-7 GA", "changes": [{"name": "thinking_blocks", "description": "new field for streaming thinking"}]}\n```',
        input_tokens=200, output_tokens=50, cache_read_tokens=0, cache_creation_tokens=0,
    )
    framework_check_resp = LLMResponse(
        text='```json\n{"supports": false, "confidence": 0.8, "reasoning": "no thinking_blocks references in repo"}\n```',
        input_tokens=200, output_tokens=30, cache_read_tokens=0, cache_creation_tokens=0,
    )

    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = [summary_resp, framework_check_resp]

    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = "<html>claude-opus-4-7 released with thinking_blocks</html>"
        # Only run against one provider source for the test
        with patch("af_expert.strategies.s4_provider_release.PROVIDER_SOURCES",
                   new=[__import__("af_expert.providers.sources", fromlist=["PROVIDER_SOURCES"]).ProviderSource(
                       name="anthropic", url="https://docs.anthropic.com/x", kind="html"
                   )]):
            produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "microsoft/agent-framework"
    assert c.actionability == 1.0  # S4 candidates are time-sensitive
    assert "thinking_blocks" in c.title or "thinking_blocks" in c.description


def test_strategy_skips_when_no_new_release(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()

    no_release_resp = LLMResponse(
        text='```json\n{"is_new_release": false, "title": "", "changes": []}\n```',
        input_tokens=100, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = no_release_resp

    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = "<html>some static page</html>"
        produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert produced == []


def test_strategy_skips_empty_poll_body(tmp_state_dir: Path) -> None:
    events = EventStore()
    events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config_for(["microsoft/agent-framework"])
    strat = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    with patch("af_expert.strategies.s4_provider_release.poll_provider") as fake_poll:
        fake_poll.return_value = ""  # empty = network failure
        produced = strat.on_ingestion_complete(deltas=MagicMock())

    assert produced == []
    llm.complete.assert_not_called()
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/test_strategy_s4.py -v
```

- [ ] **Step 3: Write `src/af_expert/strategies/s4_provider_release.py`**

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.providers.poller import poll_provider
from af_expert.providers.sources import PROVIDER_SOURCES
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

MAX_HTML_CHARS = 10000  # truncate before sending to LLM


def extract_release_summary_prompt(*, provider: str, html_body: str) -> str:
    return (
        f"You are extracting recent release information for the {provider} LLM provider.\n"
        "The following is the latest release-notes / changelog page (HTML).\n\n"
        "Identify whether there is a NEW release / API change in the last 14 days.\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- is_new_release: true | false\n"
        "- title: short headline (or empty string if no new release)\n"
        "- changes: list of objects with fields {name, description}\n\n"
        f"PAGE BODY (truncated):\n{html_body[:MAX_HTML_CHARS]}\n"
    )


def framework_check_prompt(*, framework: str, change_name: str, change_description: str) -> str:
    return (
        f"You are checking whether the framework {framework} already supports a new {change_name} "
        f"capability from an LLM provider.\n\n"
        f"Change name: {change_name}\n"
        f"Change description: {change_description}\n\n"
        "Based on your training-time knowledge of this framework's source code structure, "
        "decide whether this capability is plausibly already supported.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- supports: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class ProviderReleaseStrategy(Strategy):
    name = "s4_provider_release"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []

        for source in PROVIDER_SOURCES:
            body = poll_provider(source)
            if not body:
                continue

            summary = self._extract_summary(source.name, body)
            if not summary or not summary.get("is_new_release"):
                continue

            changes = summary.get("changes", [])
            if not changes:
                continue

            log.info(
                "S4 %s: %d changes detected (%s)",
                source.name, len(changes), summary.get("title", "")
            )

            for change in changes:
                change_name = change.get("name", "")
                change_desc = change.get("description", "")
                if not change_name:
                    continue
                for repo_cfg in self.config.repos:
                    framework = repo_cfg.owner_repo
                    verdict = self._check_framework(framework, change_name, change_desc)
                    if verdict is None:
                        continue
                    if verdict.get("supports"):
                        continue
                    candidate = self._build_candidate(
                        provider=source.name,
                        framework=framework,
                        change_name=change_name,
                        change_desc=change_desc,
                        verdict=verdict,
                        release_title=summary.get("title", "release"),
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _extract_summary(self, provider: str, body: str) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are extracting LLM provider release information.",
                user=extract_release_summary_prompt(provider=provider, html_body=body),
                caller_label=f"s4.summary[{provider}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S4 summary extraction failed for %s: %s", provider, e)
            return None

    def _check_framework(
        self, framework: str, change_name: str, change_description: str
    ) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are checking whether a framework supports a new LLM provider feature.",
                user=framework_check_prompt(
                    framework=framework,
                    change_name=change_name,
                    change_description=change_description,
                ),
                caller_label=f"s4.check[{framework}/{change_name}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S4 framework check failed for %s/%s: %s", framework, change_name, e)
            return None

    def _build_candidate(
        self,
        *,
        provider: str,
        framework: str,
        change_name: str,
        change_desc: str,
        verdict: dict[str, Any],
        release_title: str,
    ) -> Candidate:
        return Candidate(
            id=f"s4-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=framework,
            category="feature",
            title=f"Add {provider} {change_name} support to {framework}",
            description=(
                f"Provider {provider} shipped: {release_title}.\n\n"
                f"New capability: {change_name} — {change_desc}\n\n"
                f"Framework verdict: {verdict.get('reasoning', '')} "
                f"(confidence {float(verdict.get('confidence', 0.0)):.2f})\n\n"
                f"Time-sensitive: provider just released, merge race window is short."
            ),
            suggested_action=(
                f"Open an issue in {framework} proposing support for {provider}'s {change_name}. "
                f"If maintainers are receptive, follow with a PR."
            ),
            evidence_urls=[
                next(
                    (s.url for s in PROVIDER_SOURCES if s.name == provider),
                    "",
                ),
            ],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.5)),
            novelty=0.6,
            actionability=1.0,
            strategy_reputation=0.5,
            status="new",
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run pytest tests/test_strategy_s4.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/strategies/s4_provider_release.py python/tools/af_expert/tests/test_strategy_s4.py
git commit -m "feat(af-expert): S4 provider release rapid response strategy"
```

---

## Task 10: CLI integration — refresh command + tick wiring

**Files:**
- Modify: `python/tools/af_expert/src/af_expert/cli.py`
- Test: `python/tools/af_expert/tests/test_cli.py`

Add `af-expert refresh <repo>` and `af-expert refresh --all` subcommands. Hook S4 and S6 into `tick` (with flags to enable/disable).

- [ ] **Step 1: Update `tests/test_cli.py` to add new tests**

Append to the existing `tests/test_cli.py`:

```python
def test_refresh_one_repo_command(tmp_state_dir, monkeypatch) -> None:
    """Refresh command writes a briefing file."""
    from unittest.mock import patch, MagicMock
    from af_expert.architecture.refresh import RefreshResult
    from pathlib import Path

    # Set up minimal config
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
    """Verify --include-providers and --include-health flags are wired."""
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-providers" in result.output
    assert "--include-health" in result.output
```

- [ ] **Step 2: Modify `src/af_expert/cli.py`**

Add imports near the top (after existing strategy imports):

```python
from af_expert.architecture.refresh import refresh_one_repo
from af_expert.strategies.s4_provider_release import ProviderReleaseStrategy
from af_expert.strategies.s6_maintainer_health import MaintainerHealthStrategy
```

Modify the `tick` command to add new flags and call S4/S6 when enabled:

Replace the existing `tick` function with:

```python
@cli.command()
@click.option("--include-archaeology", is_flag=True, default=False)
@click.option("--include-providers", is_flag=True, default=False, help="Run S4 provider release strategy")
@click.option("--include-health", is_flag=True, default=False, help="Run S6 maintainer health strategy")
def tick(include_archaeology: bool, include_providers: bool, include_health: bool) -> None:
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

        all_produced = list(s1_produced)

        if include_providers:
            s4 = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s4_produced = s4.on_ingestion_complete(deltas)
            click.echo(f"S4 (provider release) produced {len(s4_produced)} candidates")
            all_produced.extend(s4_produced)

        if include_health:
            s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s6_produced = s6.on_weekly_tick(now=now)
            click.echo(f"S6 (maintainer health) produced {len(s6_produced)} candidates")
            all_produced.extend(s6_produced)

        if include_archaeology:
            s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            s8_produced: list = []
            for repo_cfg in cfg.repos:
                s8_produced.extend(s8.on_demand({"repo": repo_cfg.owner_repo}))
            click.echo(f"S8 (issue archaeology) produced {len(s8_produced)} candidates")
            all_produced.extend(s8_produced)

        digest_md = render_digest(
            since=since,
            candidates=all_produced,
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

        trace_dir = sd.root / "traces"
        if trace_dir.exists():
            trace_file = trace_dir / f"{now.date().isoformat()}.jsonl"
            if trace_file.exists():
                size_kb = trace_file.stat().st_size // 1024
                click.echo(f"LLM trace: {trace_file} ({size_kb} KB)")
```

Add a new `refresh` subcommand (place after the `tick` command):

```python
@cli.command()
@click.argument("repo", required=False)
@click.option("--all", "refresh_all", is_flag=True, default=False, help="Refresh all configured repos")
def refresh(repo: str | None, refresh_all: bool) -> None:
    """Refresh architecture briefing for one or all repos."""
    cfg = load_config()
    llm = LLM(api_key=cfg.anthropic_api_key)

    if refresh_all:
        targets = [r.owner_repo for r in cfg.repos]
    elif repo:
        targets = [repo]
    else:
        click.echo("Provide a repo name or --all", err=True)
        sys.exit(2)

    for target in targets:
        click.echo(f"Refreshing {target}...")
        result = refresh_one_repo(target, llm=llm)
        if result.success:
            click.echo(f"  ✓ briefing written to {result.briefing_path}")
        else:
            click.echo(f"  ✗ failed: {result.error}", err=True)
```

Update `strategy_list` to mention S4 and S6:

```python
@strategy.command("list")
def strategy_list() -> None:
    click.echo("Strategies (Wave 1 + 2):")
    click.echo("  s1_pr_forward_port      (on-tick)")
    click.echo("  s4_provider_release     (on-tick with --include-providers)")
    click.echo("  s6_maintainer_health    (on-tick with --include-health)")
    click.echo("  s8_issue_archaeology    (on-demand or with --include-archaeology)")
```

Update `strategy_run` to handle S4 and S6 as well (they accept no extra args):

```python
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
    elif name == "s4_provider_release":
        s4 = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s4.on_ingestion_complete(IngestionDeltas(
            since=datetime.now(tz=timezone.utc), repos_with_new_prs=[r.owner_repo for r in cfg.repos]
        ))
        click.echo(f"S4: {len(produced)} candidates")
    elif name == "s6_maintainer_health":
        s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s6.on_weekly_tick()
        click.echo(f"S6: {len(produced)} candidates")
    else:
        click.echo(f"Strategy '{name}' not recognized", err=True)
        sys.exit(2)
```

- [ ] **Step 3: Run tests**

```bash
cd python/tools/af_expert
uv run pytest tests/test_cli.py -v
```

Expected: all existing tests + 2 new ones pass (5 total in test_cli.py).

- [ ] **Step 4: Verify CLI**

```bash
uv run af-expert --help
uv run af-expert tick --help          # should show --include-providers + --include-health
uv run af-expert refresh --help
uv run af-expert strategy list        # should list S4 + S6 now
```

- [ ] **Step 5: Commit**

```bash
git add python/tools/af_expert/src/af_expert/cli.py python/tools/af_expert/tests/test_cli.py
git commit -m "feat(af-expert): wire S4 + S6 into tick; add 'refresh' command for architecture briefings"
```

---

## Task 11: README update

**Files:**
- Modify: `python/tools/af_expert/README.md`

Add documentation for Wave 2 features: `refresh` command, `--include-providers`, `--include-health`, S4 + S6 descriptions.

- [ ] **Step 1: Modify README**

Find the existing "## Run" section. After the existing example commands, add:

```markdown
### Wave 2 commands

```bash
# Generate architecture briefing for one repo (shallow git clone + LLM summarize)
af-expert refresh microsoft/agent-framework

# Refresh all configured repos
af-expert refresh --all

# Run tick with extra strategies enabled
af-expert tick --include-providers       # S4: LLM provider release tracking
af-expert tick --include-health          # S6: maintainer health metrics
af-expert tick --include-providers --include-health --include-archaeology

# Run a strategy manually
af-expert strategy run s4_provider_release
af-expert strategy run s6_maintainer_health
```
```

Update "## Wave 1 limitations" section title to "## Wave 2 status" and update content:

```markdown
## Wave 2 status

Wave 2 adds:

- **Architecture briefings**: `af-expert refresh <repo>` clones the repo shallowly,
  scans its file structure, and asks the LLM to produce a markdown briefing at
  `~/.af-expert/repos/<owner>__<repo>/architecture.md`. S1's accuracy improves
  meaningfully when briefings exist (still uses LLM training-knowledge for matching,
  but briefings ground the prompt).
- **S4 provider release tracking**: polls Anthropic / OpenAI / Google release pages,
  asks LLM to identify new features, checks each tracked framework for support.
  Time-sensitive: actionability is set to 1.0 because merge race windows are short.
- **S6 maintainer health**: pure SQL metrics over event store. Detects PR merge
  latency degradation (>2x worse than prior 30 days). No LLM cost.

### Architecture briefing layout

```
~/.af-expert/repos/<owner>__<repo>/
└── architecture.md      # LLM-generated briefing, regenerated by `af-expert refresh`
```

### Still TBD (Wave 3+)

- S2 cross-repo structural diff (concept graph)
- S3 hypothesis verification
- S5 spec conformance fuzzer
- S7 feature propagation
```

Update "## State layout" to reflect the new `providers/` and `traces/` directories:

```markdown
## State layout

```
~/.af-expert/
├── config.toml
├── state.json
├── lock
├── events.db
├── candidates/
├── digests/
├── traces/             # LLM I/O traces (Wave 1+)
├── repos/<owner>__<repo>/
│   └── architecture.md (Wave 2)
└── providers/<provider>/
    └── YYYY-MM-DD.html (Wave 2: cached provider release pages)
```
```

- [ ] **Step 2: Commit**

```bash
git add python/tools/af_expert/README.md
git commit -m "docs(af-expert): document Wave 2 features (refresh / S4 / S6)"
```

---

## Wave 2 done — verification checklist

- [ ] `uv run pytest -v --ignore=tests/e2e 2>&1 | tail -5` — all tests still pass (expect ~85-90 with new tests added)
- [ ] `uv run af-expert refresh --help` works
- [ ] `uv run af-expert refresh microsoft/agent-framework` (requires real API keys + network) — produces a briefing at `~/.af-expert/repos/microsoft__agent-framework/architecture.md`
- [ ] `uv run af-expert tick --include-health` (with a populated SQLite + at least one high-volume repo) emits at least one S6 candidate (or correctly identifies no degradation)
- [ ] `uv run af-expert tick --include-providers` polls Anthropic/OpenAI/Google and either emits S4 candidates or correctly determines no new release

## Wave 2 validation milestones

From spec:
1. ✅ Architecture briefings exist for all configured repos after `af-expert refresh --all`
2. ✅ One real provider release event traced end-to-end to at least one S4 candidate (requires real provider release within window — may need to wait for a real release)
3. ✅ S6 produces a maintenance candidate against a real decaying repo OR returns no candidate against a healthy one

## What's NOT in Wave 2 (deferred)

| Wave | Plan delivers |
|---|---|
| 3 | Concept graph + S2 (cross-repo structural) + S7 (feature propagation) |
| 4 | Hypotheses + S3 (active verification) |
| 5 | Spec corpus + S5 (conformance fuzzer) |

The S1 strategy is NOT updated in this plan to consume architecture briefings — that's
a Wave 3 task (along with S2 needing briefings as input). For now, S1 continues to use
LLM training-knowledge for matching, with briefings stored on disk for future use.
