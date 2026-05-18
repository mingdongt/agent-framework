# af-expert Wave 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Lay the foundation for spec conformance fuzzing — the strongest evidence form for bug candidates. Wave 5 ships **one spec corpus (MCP)** + **one framework adapter (agent-framework)** + **Strategy S5** that runs the corpus through the adapter and emits failing-test-backed candidates. Adding more specs (AG-UI, Anthropic tool_use, OpenAI Responses) and more adapters (LangChain, pydantic-ai, etc.) becomes incremental Wave 5+ work.

**Architecture:**
- `spec_corpus/<spec>/` — directory of property-based test files (one Python module per property)
- `framework_adapter` ABC — minimum interface a framework must implement to be testable (run_property → dict result)
- `s5_spec_conformance.py` — for each (spec, adapter, property), runs the property and emits Candidate if it fails

**Scope discipline:** Wave 5 ships ONE spec (MCP) + ONE adapter (agent-framework) + the strategy + CLI wiring. Other specs/adapters are explicit follow-up work, NOT in scope.

**Validation milestones:**
1. `spec_corpus/mcp/` has ≥3 properties (e.g., duplicate initialize rejected, OAuth refresh omits resource, tool_result format)
2. `agent-framework` adapter runs all MCP properties; results saved to disk
3. S5 emits a candidate when a property fails, including the failing test snippet as `evidence_snippets`

---

## File Structure

```
python/tools/af_expert/src/af_expert/
├── spec_corpus/
│   ├── __init__.py
│   ├── base.py                          # SpecProperty ABC + result types
│   └── mcp/
│       ├── __init__.py
│       ├── duplicate_initialize.py      # property: server rejects duplicate initialize
│       ├── oauth_refresh_no_resource.py # property: refresh-token request omits 'resource' parameter
│       └── tool_result_format.py        # property: tool_result content structure
├── framework_adapters/
│   ├── __init__.py
│   ├── base.py                          # FrameworkAdapter ABC
│   └── agent_framework.py               # adapter that imports + drives agent-framework code
└── strategies/
    └── s5_spec_conformance.py
```

Modified:
- `cli.py` — `--include-conformance` flag on tick; `spec list / run` commands
- `README.md`

---

## Task 1: Spec property ABC + result types

**Files:**
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/__init__.py` (empty)
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/base.py`
- Test: `python/tools/af_expert/tests/test_spec_corpus_base.py`

### Test

```python
from __future__ import annotations

import pytest

from af_expert.spec_corpus.base import (
    PropertyResult,
    SpecProperty,
)


class _GoodProperty(SpecProperty):
    spec = "test"
    name = "always_passes"
    description = "trivially passes"

    def run(self, adapter):
        return PropertyResult(passed=True, message="ok")


class _BadProperty(SpecProperty):
    spec = "test"
    name = "always_fails"
    description = "trivially fails"

    def run(self, adapter):
        return PropertyResult(passed=False, message="boom", repro_snippet="assert 1 == 2")


def test_property_metadata_required() -> None:
    p = _GoodProperty()
    assert p.spec == "test"
    assert p.name == "always_passes"
    assert p.full_id == "test/always_passes"


def test_property_run_returns_passing_result() -> None:
    p = _GoodProperty()
    result = p.run(adapter=None)
    assert result.passed is True
    assert result.message == "ok"


def test_property_run_returns_failing_result_with_repro() -> None:
    p = _BadProperty()
    result = p.run(adapter=None)
    assert result.passed is False
    assert result.repro_snippet == "assert 1 == 2"


def test_property_subclass_must_define_spec_and_name() -> None:
    class Incomplete(SpecProperty):
        description = "missing fields"
        def run(self, adapter):
            return PropertyResult(passed=True, message="")

    with pytest.raises(ValueError):
        Incomplete()
```

### `src/af_expert/spec_corpus/__init__.py` (empty)

### `src/af_expert/spec_corpus/base.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PropertyResult:
    passed: bool
    message: str
    repro_snippet: str | None = None


class SpecProperty(ABC):
    """A property derived from a spec. Subclasses set `spec` + `name` + `description`."""

    spec: str = ""
    name: str = ""
    description: str = ""

    def __init__(self) -> None:
        if not self.spec or not self.name:
            raise ValueError(
                f"{type(self).__name__} must define class attrs `spec` and `name`"
            )

    @property
    def full_id(self) -> str:
        return f"{self.spec}/{self.name}"

    @abstractmethod
    def run(self, adapter: Any) -> PropertyResult: ...
```

### Run + commit

```bash
cd python/tools/af_expert
uv run pytest tests/test_spec_corpus_base.py -v
# Expected: 4 tests pass

git add python/tools/af_expert/src/af_expert/spec_corpus/__init__.py python/tools/af_expert/src/af_expert/spec_corpus/base.py python/tools/af_expert/tests/test_spec_corpus_base.py
git commit -m "feat(af-expert): spec property ABC + result types"
```

---

## Task 2: Framework adapter ABC

**Files:**
- Create: `python/tools/af_expert/src/af_expert/framework_adapters/__init__.py` (empty)
- Create: `python/tools/af_expert/src/af_expert/framework_adapters/base.py`
- Test: `python/tools/af_expert/tests/test_framework_adapter_base.py`

The adapter provides the minimum interface a property needs to exercise framework behavior. For Wave 5, that's:
- `simulate_mcp_initialize(payload) -> dict`
- `simulate_mcp_oauth_refresh_request(payload) -> dict`
- `simulate_mcp_tool_result(payload) -> dict`

These are stub methods; real adapters call into the framework's actual code paths.

### Test

```python
from __future__ import annotations

import pytest

from af_expert.framework_adapters.base import FrameworkAdapter


def test_framework_adapter_has_required_attrs() -> None:
    """Subclasses must define `framework` and at least one simulate_* method."""
    with pytest.raises(TypeError):
        FrameworkAdapter()  # ABC cannot be instantiated directly


def test_concrete_adapter_works() -> None:
    class FakeAdapter(FrameworkAdapter):
        framework = "fake/repo"

        def simulate_mcp_initialize(self, payload):
            return {"ok": True}

        def simulate_mcp_oauth_refresh_request(self, payload):
            return {"omits_resource": True}

        def simulate_mcp_tool_result(self, payload):
            return {"valid": True}

    a = FakeAdapter()
    assert a.framework == "fake/repo"
    assert a.simulate_mcp_initialize({"x": 1}) == {"ok": True}
```

### `src/af_expert/framework_adapters/__init__.py` (empty)

### `src/af_expert/framework_adapters/base.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FrameworkAdapter(ABC):
    """Minimum interface a framework must implement to be testable by S5."""

    framework: str = ""  # owner/repo

    @abstractmethod
    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]: ...
```

### Commit

```bash
uv run pytest tests/test_framework_adapter_base.py -v
# Expected: 2 tests pass

git add python/tools/af_expert/src/af_expert/framework_adapters/__init__.py python/tools/af_expert/src/af_expert/framework_adapters/base.py python/tools/af_expert/tests/test_framework_adapter_base.py
git commit -m "feat(af-expert): framework adapter ABC for spec conformance"
```

---

## Task 3: Three MCP properties

**Files:**
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/mcp/__init__.py`
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/mcp/duplicate_initialize.py`
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/mcp/oauth_refresh_no_resource.py`
- Create: `python/tools/af_expert/src/af_expert/spec_corpus/mcp/tool_result_format.py`
- Test: `python/tools/af_expert/tests/test_spec_corpus_mcp.py`

Each property checks one specific spec invariant against a `FrameworkAdapter`.

### `__init__.py`

```python
from __future__ import annotations

from af_expert.spec_corpus.mcp.duplicate_initialize import DuplicateInitializeProperty
from af_expert.spec_corpus.mcp.oauth_refresh_no_resource import OAuthRefreshNoResourceProperty
from af_expert.spec_corpus.mcp.tool_result_format import ToolResultFormatProperty


MCP_PROPERTIES = [
    DuplicateInitializeProperty(),
    OAuthRefreshNoResourceProperty(),
    ToolResultFormatProperty(),
]
```

### `duplicate_initialize.py`

```python
from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class DuplicateInitializeProperty(SpecProperty):
    spec = "mcp"
    name = "duplicate_initialize_rejected"
    description = "MCP server must reject duplicate `initialize` requests after the first"

    def run(self, adapter: Any) -> PropertyResult:
        # First initialize should succeed
        first = adapter.simulate_mcp_initialize({"client_info": {"name": "test"}})
        if not first.get("accepted"):
            return PropertyResult(
                passed=False,
                message="first initialize was not accepted (precondition failed)",
                repro_snippet=(
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})\n"
                    f"# returned: {first!r}"
                ),
            )
        # Second initialize MUST be rejected
        second = adapter.simulate_mcp_initialize({"client_info": {"name": "test"}})
        if second.get("accepted"):
            return PropertyResult(
                passed=False,
                message="duplicate initialize was accepted; spec requires rejection",
                repro_snippet=(
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})  # first\n"
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})  # second\n"
                    f"# second returned: {second!r}"
                ),
            )
        return PropertyResult(passed=True, message="duplicate initialize correctly rejected")
```

### `oauth_refresh_no_resource.py`

```python
from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class OAuthRefreshNoResourceProperty(SpecProperty):
    spec = "mcp"
    name = "oauth_refresh_no_resource"
    description = (
        "OAuth refresh-token request must NOT include `resource` parameter "
        "(RFC 8707 §2.2; Entra v2.0 rejects requests that do)"
    )

    def run(self, adapter: Any) -> PropertyResult:
        result = adapter.simulate_mcp_oauth_refresh_request({
            "grant_type": "refresh_token",
            "refresh_token": "test-token",
        })
        request = result.get("request") or {}
        if "resource" in request:
            return PropertyResult(
                passed=False,
                message=f"refresh request included 'resource' parameter: {request.get('resource')!r}",
                repro_snippet=(
                    "adapter.simulate_mcp_oauth_refresh_request({\n"
                    "    'grant_type': 'refresh_token', 'refresh_token': 'test-token'\n"
                    "})\n"
                    f"# returned request: {request!r}"
                ),
            )
        return PropertyResult(
            passed=True,
            message="refresh request correctly omits 'resource' parameter",
        )
```

### `tool_result_format.py`

```python
from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class ToolResultFormatProperty(SpecProperty):
    spec = "mcp"
    name = "tool_result_format"
    description = "MCP tool_result must have `content` list and `isError` bool"

    def run(self, adapter: Any) -> PropertyResult:
        result = adapter.simulate_mcp_tool_result({
            "tool_name": "test_tool",
            "output": "hello",
        })
        payload = result.get("payload") or {}
        missing: list[str] = []
        if not isinstance(payload.get("content"), list):
            missing.append("content (must be list)")
        if not isinstance(payload.get("isError"), bool):
            missing.append("isError (must be bool)")
        if missing:
            return PropertyResult(
                passed=False,
                message=f"tool_result payload missing or malformed fields: {', '.join(missing)}",
                repro_snippet=(
                    "adapter.simulate_mcp_tool_result({'tool_name': 'test_tool', 'output': 'hello'})\n"
                    f"# returned payload: {payload!r}"
                ),
            )
        return PropertyResult(passed=True, message="tool_result payload format correct")
```

### Tests (`tests/test_spec_corpus_mcp.py`)

```python
from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.mcp import (
    MCP_PROPERTIES,
    DuplicateInitializeProperty,
    OAuthRefreshNoResourceProperty,
    ToolResultFormatProperty,
)


class _CompliantAdapter:
    framework = "fake/compliant"
    def __init__(self) -> None:
        self.initialize_count = 0

    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize_count += 1
        return {"accepted": self.initialize_count == 1}

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"request": {"grant_type": "refresh_token", "refresh_token": "x"}}

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": {"content": [{"type": "text", "text": "hello"}], "isError": False}}


class _NonCompliantAdapter:
    framework = "fake/buggy"
    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True}  # always accepts → violates duplicate rule

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"request": {"grant_type": "refresh_token", "resource": "https://api/"}}

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": {"content": "not a list", "isError": "not a bool"}}


def test_mcp_properties_count() -> None:
    assert len(MCP_PROPERTIES) == 3


def test_compliant_adapter_passes_all() -> None:
    adapter = _CompliantAdapter()
    for prop in MCP_PROPERTIES:
        r = prop.run(adapter=adapter)
        assert r.passed, f"{prop.full_id} should pass on compliant adapter: {r.message}"


def test_non_compliant_adapter_fails_all() -> None:
    adapter = _NonCompliantAdapter()
    for prop in MCP_PROPERTIES:
        r = prop.run(adapter=adapter)
        assert not r.passed, f"{prop.full_id} should fail on buggy adapter"
        assert r.repro_snippet, f"{prop.full_id} should provide a repro_snippet on failure"


def test_property_full_id_format() -> None:
    assert DuplicateInitializeProperty().full_id == "mcp/duplicate_initialize_rejected"
    assert OAuthRefreshNoResourceProperty().full_id == "mcp/oauth_refresh_no_resource"
    assert ToolResultFormatProperty().full_id == "mcp/tool_result_format"
```

### Commit

```bash
uv run pytest tests/test_spec_corpus_mcp.py -v
# Expected: 4 tests pass

git add python/tools/af_expert/src/af_expert/spec_corpus/mcp/ python/tools/af_expert/tests/test_spec_corpus_mcp.py
git commit -m "feat(af-expert): MCP spec corpus (3 properties)"
```

---

## Task 4: agent-framework adapter (proof of concept)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/framework_adapters/agent_framework.py`
- Test: `python/tools/af_expert/tests/test_adapter_agent_framework.py`

The agent-framework adapter is a STUB for Wave 5 — it returns compliant responses for all three properties. Future work replaces the stubs with real calls into agent-framework's code. The point of Wave 5 is to validate the END-TO-END WIRING: adapter → properties → S5 → candidate. A real adapter is too much engineering for one task.

### Test

```python
from __future__ import annotations

from af_expert.framework_adapters.agent_framework import AgentFrameworkAdapter


def test_adapter_has_framework_name() -> None:
    a = AgentFrameworkAdapter()
    assert a.framework == "microsoft/agent-framework"


def test_adapter_initialize_accepts_first_rejects_second() -> None:
    a = AgentFrameworkAdapter()
    r1 = a.simulate_mcp_initialize({"client_info": {"name": "t"}})
    r2 = a.simulate_mcp_initialize({"client_info": {"name": "t"}})
    assert r1.get("accepted") is True
    assert r2.get("accepted") is False


def test_adapter_oauth_refresh_omits_resource() -> None:
    a = AgentFrameworkAdapter()
    r = a.simulate_mcp_oauth_refresh_request({"grant_type": "refresh_token"})
    assert "resource" not in r.get("request", {})


def test_adapter_tool_result_has_valid_format() -> None:
    a = AgentFrameworkAdapter()
    r = a.simulate_mcp_tool_result({"tool_name": "x", "output": "y"})
    payload = r.get("payload", {})
    assert isinstance(payload.get("content"), list)
    assert isinstance(payload.get("isError"), bool)
```

### `src/af_expert/framework_adapters/agent_framework.py`

```python
from __future__ import annotations

from typing import Any

from af_expert.framework_adapters.base import FrameworkAdapter


class AgentFrameworkAdapter(FrameworkAdapter):
    """Adapter for microsoft/agent-framework.

    Wave 5: stub implementation that returns compliant responses for all three
    MCP properties. Replacing the stubs with real calls into agent-framework's
    code (e.g., the actual MCP client and OAuth helpers) is follow-up work.
    """

    framework = "microsoft/agent-framework"

    def __init__(self) -> None:
        super().__init__()
        self._initialized = False

    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._initialized:
            return {"accepted": False, "reason": "already initialized"}
        self._initialized = True
        return {"accepted": True}

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Compliant: NO `resource` parameter on refresh-token grants
        return {
            "request": {
                "grant_type": "refresh_token",
                "refresh_token": payload.get("refresh_token", ""),
            }
        }

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": {
                "content": [{"type": "text", "text": str(payload.get("output", ""))}],
                "isError": False,
            }
        }
```

### Commit

```bash
uv run pytest tests/test_adapter_agent_framework.py -v
# Expected: 4 tests pass

git add python/tools/af_expert/src/af_expert/framework_adapters/agent_framework.py python/tools/af_expert/tests/test_adapter_agent_framework.py
git commit -m "feat(af-expert): agent-framework adapter (stub, compliant proof-of-concept)"
```

---

## Task 5: Strategy S5 — spec conformance fuzzer

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s5_spec_conformance.py`
- Test: `python/tools/af_expert/tests/test_strategy_s5.py`

S5 iterates (adapter × property), runs each, emits candidate on failure. Adapters are registered in a hardcoded dict for Wave 5.

### Test

```python
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.framework_adapters.base import FrameworkAdapter
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.spec_corpus.base import PropertyResult, SpecProperty
from af_expert.strategies.s5_spec_conformance import SpecConformanceStrategy


class _CompliantAdapter(FrameworkAdapter):
    framework = "fake/compliant"

    def simulate_mcp_initialize(self, payload): return {"accepted": True}
    def simulate_mcp_oauth_refresh_request(self, payload): return {"request": {}}
    def simulate_mcp_tool_result(self, payload):
        return {"payload": {"content": [], "isError": False}}


class _BuggyAdapter(FrameworkAdapter):
    framework = "fake/buggy"

    def simulate_mcp_initialize(self, payload): return {"accepted": True}
    def simulate_mcp_oauth_refresh_request(self, payload): return {"request": {"resource": "x"}}
    def simulate_mcp_tool_result(self, payload):
        return {"payload": {"content": "BAD", "isError": "BAD"}}


class _AlwaysPasses(SpecProperty):
    spec = "test"
    name = "always_passes"
    def run(self, adapter): return PropertyResult(passed=True, message="ok")


class _AlwaysFails(SpecProperty):
    spec = "test"
    name = "always_fails"
    def run(self, adapter):
        return PropertyResult(passed=False, message="boom", repro_snippet="assert 1 == 2")


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_strategy_passes_compliant_adapter_emits_no_candidate(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fake/compliant"])

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={"fake/compliant": _CompliantAdapter()},
        properties=[_AlwaysPasses()],
    )
    produced = strat.on_weekly_tick()
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_failing_property_emits_candidate(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fake/buggy"])

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={"fake/buggy": _BuggyAdapter()},
        properties=[_AlwaysFails()],
    )
    produced = strat.on_weekly_tick()
    assert len(produced) == 1
    c = produced[0]
    assert c.target_repo == "fake/buggy"
    assert c.category == "bug"
    assert "assert 1 == 2" in c.evidence_snippets[0]
    # actionability high because we have a failing test as evidence
    assert c.actionability >= 0.8


def test_strategy_skips_repos_without_adapter(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["unknown/repo"])  # no adapter

    strat = SpecConformanceStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm,
        adapter_registry={},
        properties=[_AlwaysFails()],
    )
    produced = strat.on_weekly_tick()
    assert produced == []
```

### `src/af_expert/strategies/s5_spec_conformance.py`

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.framework_adapters.base import FrameworkAdapter
from af_expert.spec_corpus.base import SpecProperty
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


class SpecConformanceStrategy(Strategy):
    name = "s5_spec_conformance"

    def __init__(
        self,
        *args: Any,
        adapter_registry: dict[str, FrameworkAdapter] | None = None,
        properties: list[SpecProperty] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if adapter_registry is None:
            from af_expert.framework_adapters.agent_framework import AgentFrameworkAdapter
            adapter_registry = {"microsoft/agent-framework": AgentFrameworkAdapter()}
        if properties is None:
            from af_expert.spec_corpus.mcp import MCP_PROPERTIES
            properties = list(MCP_PROPERTIES)
        self.adapter_registry = adapter_registry
        self.properties = properties

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []  # weekly

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:
        if now is None:
            now = datetime.now(tz=timezone.utc)
        produced: list[Candidate] = []
        for repo_cfg in self.config.repos:
            framework = repo_cfg.owner_repo
            adapter = self.adapter_registry.get(framework)
            if adapter is None:
                log.debug("S5 skip %s: no adapter registered", framework)
                continue
            for prop in self.properties:
                try:
                    result = prop.run(adapter=adapter)
                except Exception as e:
                    log.warning("S5 %s on %s raised: %s", prop.full_id, framework, e)
                    continue
                if result.passed:
                    log.info("S5 %s on %s: PASS", prop.full_id, framework)
                    continue
                log.info("S5 %s on %s: FAIL — %s", prop.full_id, framework, result.message)
                candidate = self._build_candidate(framework, prop, result, now)
                self.candidates.append(candidate)
                produced.append(candidate)
        return produced

    def _build_candidate(
        self, framework: str, prop: SpecProperty, result: Any, now: datetime
    ) -> Candidate:
        return Candidate(
            id=f"s5-{uuid.uuid4().hex[:12]}",
            discovered_at=now,
            strategy=self.name,
            target_repo=framework,
            category="bug",
            title=f"Spec conformance failure: {prop.full_id} on {framework}",
            description=(
                f"Spec: {prop.spec}\n"
                f"Property: {prop.name}\n"
                f"Property description: {prop.description}\n\n"
                f"Failure message: {result.message}\n\n"
                "This is a strong-evidence candidate: the failure is reproducible "
                "via the adapter snippet below."
            ),
            suggested_action=(
                f"Investigate the framework code path corresponding to {prop.full_id}. "
                f"Use the snippet below to reproduce the failure locally before fixing."
            ),
            evidence_urls=[f"https://github.com/{framework}"],
            evidence_snippets=[result.repro_snippet or ""],
            confidence=0.95,                # high — backed by a failing test
            novelty=0.6,
            actionability=0.95,             # has repro
            strategy_reputation=0.5,
            status="new",
        )
```

### Commit

```bash
uv run pytest tests/test_strategy_s5.py -v
# Expected: 3 tests pass

git add python/tools/af_expert/src/af_expert/strategies/s5_spec_conformance.py python/tools/af_expert/tests/test_strategy_s5.py
git commit -m "feat(af-expert): S5 spec conformance fuzzer strategy"
```

---

## Task 6: CLI integration + README

Modify `cli.py`:

Add imports:
```python
from af_expert.strategies.s5_spec_conformance import SpecConformanceStrategy
```

Add `--include-conformance` flag to `tick`:
```python
@click.option("--include-conformance", is_flag=True, default=False, help="Run S5 spec conformance")
```

Inside tick body:
```python
if include_conformance:
    s5 = SpecConformanceStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    s5_produced = s5.on_weekly_tick(now=now)
    click.echo(f"S5 (spec conformance) produced {len(s5_produced)} candidates")
    all_produced.extend(s5_produced)
```

Add a `spec` subcommand group:

```python
@cli.group()
def spec() -> None:
    """Spec corpus management."""


@spec.command("list")
def spec_list() -> None:
    from af_expert.spec_corpus.mcp import MCP_PROPERTIES
    click.echo("Spec properties:")
    for p in MCP_PROPERTIES:
        click.echo(f"  {p.full_id}\t{p.description}")


@spec.command("run")
@click.option("--framework", default=None)
def spec_run(framework: str | None) -> None:
    """Run the spec corpus against one (or all) tracked framework(s)."""
    cfg = load_config()
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    strat = SpecConformanceStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    # Filter by framework if provided
    if framework:
        original = strat.adapter_registry
        strat.adapter_registry = {framework: a for f, a in original.items() if f == framework}
    produced = strat.on_weekly_tick()
    click.echo(f"S5: {len(produced)} candidates")
```

Update `strategy list` and `strategy run` to mention S5.

Add CLI tests:
```python
def test_spec_list_command(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["spec", "list"])
    assert result.exit_code == 0
    assert "mcp/duplicate_initialize_rejected" in result.output


def test_tick_with_conformance_flag(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-conformance" in result.output
```

Commit:
```bash
uv run pytest tests/test_cli.py -v
git add python/tools/af_expert/src/af_expert/cli.py python/tools/af_expert/tests/test_cli.py
git commit -m "feat(af-expert): wire S5 + spec subcommand group into CLI"
```

Then README:
- Add "### Wave 5 commands" with spec list/run + tick --include-conformance examples
- Replace "## Wave 4 status" with "## Wave 5 status" describing S5 + spec corpus + adapters
- Note that Wave 5 ships only MCP spec + agent-framework adapter; more spec/adapter combos are follow-up work
- Update state layout (no new state files for Wave 5; conformance state is implicit in candidates)

```bash
git add python/tools/af_expert/README.md
git commit -m "docs(af-expert): document Wave 5 (spec conformance / S5)"
```

---

## Wave 5 done — verification

- All tests pass (~155 expected)
- `af-expert spec list` shows 3 MCP properties
- `af-expert spec run` runs them against agent-framework adapter
- `af-expert tick --include-conformance` integrates into tick
- `af-expert strategy run s5_spec_conformance` works

## Out of scope (follow-up work)

- AG-UI / Anthropic tool_use / OpenAI Responses spec corpora
- Real adapters into agent-framework's actual MCP code paths (Wave 5 ships stub)
- Adapters for LangChain, pydantic-ai, OpenHands, etc.
- Persisting per-adapter conformance results to disk for trend tracking
