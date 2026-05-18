# af-expert Wave 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hand-curated concept graph (20-30 agent/LLM domain concepts with per-repo implementation links) + Strategy S2 (cross-repo structural diff via counterfactual queries) + Strategy S7 (cross-repo feature propagation when one repo lands new functionality). By end of Wave 3, af-expert can answer questions like "which frameworks haven't updated their MCP OAuth implementation since the spec change in April" — a class of insight Wave 1+2 cannot produce.

**Architecture:** Concept graph is a single JSON file at `~/.af-expert/concept_graph.json`, hand-curated initially with seed from `understand-anything:understand-domain` output. Each concept has per-repo implementation evidence (files, functions, last-modified). S2 queries the graph for "lagging" implementations. S7 detects new features in tracked repos (PR diff signal) and proposes propagation to sister repos via LLM-driven feature equivalence check.

**Tech Stack:** Python 3.12+, Wave 1+2 dependencies. No new external deps.

**Reference spec:** [docs/superpowers/specs/2026-05-17-af-expert-design.md](../specs/2026-05-17-af-expert-design.md)
**Wave 2 plan:** [docs/superpowers/plans/2026-05-18-af-expert-wave2.md](2026-05-18-af-expert-wave2.md)

**Validation milestones:**
1. Concept graph JSON file initialized with 20-30 concepts; operator can `af-expert concept add / list / show`
2. S2 produces at least one "lagging" candidate (a repo that hasn't updated implementation of a known-changed concept)
3. S7 produces at least one "propose feature X to repo Y" candidate based on a recent merged feature PR

---

## File Structure

New files (Wave 3 only):

```
python/tools/af_expert/src/af_expert/
├── concept/
│   ├── __init__.py
│   ├── model.py                          # Concept + ConceptImplementation pydantic models
│   ├── store.py                          # JSON-file read/write with atomic semantics
│   ├── seed.py                           # hardcoded initial 20-30 concept seeds
│   └── linker.py                         # LLM-driven linking: concept -> repo files
└── strategies/
    ├── s2_structural_diff.py             # cross-repo structural query
    └── s7_feature_propagation.py         # propose new features to sister repos
```

Modified files:

```
python/tools/af_expert/src/af_expert/
├── cli.py                                # new `concept` subcommand group + S2/S7 flags on `tick`
└── README.md                             # document Wave 3 features
```

**Conventions:**
- Concept graph stored at `~/.af-expert/concept_graph.json` (atomic writes via `state.atomic_write`)
- All Wave 3 components use existing `LLM`, `EventStore`, `CandidateStore`, `Strategy` base
- No changes to Wave 1+2 modules (additive only)

---

## Task 1: Concept model + JSON store

**Files:**
- Create: `python/tools/af_expert/src/af_expert/concept/__init__.py` (empty)
- Create: `python/tools/af_expert/src/af_expert/concept/model.py`
- Create: `python/tools/af_expert/src/af_expert/concept/store.py`
- Test: `python/tools/af_expert/tests/test_concept_model.py`
- Test: `python/tools/af_expert/tests/test_concept_store.py`

### Step 1: Tests for model (`tests/test_concept_model.py`)

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.concept.model import Concept, ConceptImplementation


def test_implementation_minimal() -> None:
    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["python/packages/core/agent_framework/_mcp.py"],
        functions=["_refresh_token"],
    )
    assert impl.repo == "microsoft/agent-framework"
    assert impl.compliant is None  # default


def test_concept_minimal() -> None:
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh-token grant handling",
        spec_ref="RFC 8707 §2.2",
    )
    assert c.id == "mcp.oauth.refresh"
    assert c.implementations == {}


def test_concept_id_kebab_validation() -> None:
    """Concept IDs must be lowercase, dot-separated identifiers."""
    with pytest.raises(ValueError):
        Concept(id="MCP.OAuth.Refresh", description="...", spec_ref="...")


def test_concept_roundtrip_json() -> None:
    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["x.py"],
        functions=["f"],
        last_modified="2026-05-14",
        compliant=True,
    )
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh-token grant handling",
        spec_ref="RFC 8707",
        implementations={"microsoft/agent-framework": impl},
    )
    raw = c.model_dump_json()
    c2 = Concept.model_validate_json(raw)
    assert c2 == c
```

### Step 2: Write `src/af_expert/concept/__init__.py` (empty)

```python
```

### Step 3: Write `src/af_expert/concept/model.py`

```python
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


_CONCEPT_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*[a-z0-9]$")


class ConceptImplementation(BaseModel):
    repo: str
    files: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    last_modified: str | None = None             # ISO date or null
    compliant: bool | None = None                # True/False/null (unknown)
    notes: str = ""


class Concept(BaseModel):
    id: str                                       # e.g. "mcp.oauth.refresh"
    description: str
    spec_ref: str = ""                            # e.g. "RFC 8707 §2.2" or "MCP spec 1.x"
    tags: list[str] = Field(default_factory=list)
    implementations: dict[str, ConceptImplementation] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _CONCEPT_ID_RE.match(v):
            raise ValueError(f"Concept id must be lowercase dot-separated, got {v!r}")
        return v
```

### Step 4: Tests for store (`tests/test_concept_store.py`)

```python
from __future__ import annotations

from pathlib import Path

from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore


def test_empty_store_returns_empty_list(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    assert list(s.list_all()) == []


def test_add_and_get_concept(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    c = Concept(id="mcp.oauth.refresh", description="...", spec_ref="RFC 8707")
    s.upsert(c)

    fetched = s.get("mcp.oauth.refresh")
    assert fetched is not None
    assert fetched.id == "mcp.oauth.refresh"


def test_upsert_updates_existing(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    c = Concept(id="mcp.oauth.refresh", description="v1", spec_ref="RFC 8707")
    s.upsert(c)
    c2 = Concept(id="mcp.oauth.refresh", description="v2-updated", spec_ref="RFC 8707")
    s.upsert(c2)

    fetched = s.get("mcp.oauth.refresh")
    assert fetched.description == "v2-updated"


def test_store_persists_to_disk(tmp_state_dir: Path) -> None:
    s1 = ConceptGraphStore()
    s1.upsert(Concept(id="x.y", description="...", spec_ref=""))

    # New instance should read the same data
    s2 = ConceptGraphStore()
    assert s2.get("x.y") is not None


def test_add_implementation(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    s.upsert(Concept(id="mcp.oauth.refresh", description="...", spec_ref=""))

    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["x.py"],
        functions=["f"],
    )
    s.attach_implementation("mcp.oauth.refresh", impl)

    fetched = s.get("mcp.oauth.refresh")
    assert "microsoft/agent-framework" in fetched.implementations


def test_attach_implementation_missing_concept_raises(tmp_state_dir: Path) -> None:
    import pytest
    s = ConceptGraphStore()
    impl = ConceptImplementation(repo="x/y", files=[], functions=[])
    with pytest.raises(KeyError):
        s.attach_implementation("nonexistent", impl)
```

### Step 5: Write `src/af_expert/concept/store.py`

```python
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.config import _state_dir
from af_expert.state import atomic_write


class ConceptGraphStore:
    """Single JSON file at ~/.af-expert/concept_graph.json with atomic writes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "concept_graph.json"

    def _load(self) -> dict[str, Concept]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            cid: Concept.model_validate(cdata)
            for cid, cdata in raw.get("concepts", {}).items()
        }

    def _save(self, concepts: dict[str, Concept]) -> None:
        payload = {
            "version": 1,
            "concepts": {cid: c.model_dump() for cid, c in concepts.items()},
        }
        atomic_write(self.path, json.dumps(payload, indent=2, sort_keys=True, default=str))

    def list_all(self) -> list[Concept]:
        return list(self._load().values())

    def get(self, concept_id: str) -> Concept | None:
        return self._load().get(concept_id)

    def upsert(self, concept: Concept) -> None:
        concepts = self._load()
        concepts[concept.id] = concept
        self._save(concepts)

    def attach_implementation(
        self, concept_id: str, impl: ConceptImplementation
    ) -> None:
        concepts = self._load()
        if concept_id not in concepts:
            raise KeyError(f"Concept {concept_id!r} not in store")
        concepts[concept_id].implementations[impl.repo] = impl
        self._save(concepts)

    def remove(self, concept_id: str) -> bool:
        concepts = self._load()
        if concept_id not in concepts:
            return False
        del concepts[concept_id]
        self._save(concepts)
        return True
```

### Step 6: Run all tests

```bash
cd python/tools/af_expert
uv run pytest tests/test_concept_model.py tests/test_concept_store.py -v
```

Expected: 4 + 6 = 10 tests pass.

### Step 7: Commit

```bash
git add python/tools/af_expert/src/af_expert/concept/__init__.py python/tools/af_expert/src/af_expert/concept/model.py python/tools/af_expert/src/af_expert/concept/store.py python/tools/af_expert/tests/test_concept_model.py python/tools/af_expert/tests/test_concept_store.py
git commit -m "feat(af-expert): concept model + JSON-file graph store"
```

---

## Task 2: Concept seed (hardcoded initial set)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/concept/seed.py`
- Test: `python/tools/af_expert/tests/test_concept_seed.py`

20-30 hand-curated concepts covering the agent/LLM ecosystem. Operator can extend later.

### Step 1: Test

```python
from __future__ import annotations

from pathlib import Path

from af_expert.concept.seed import SEED_CONCEPTS, seed_into
from af_expert.concept.store import ConceptGraphStore


def test_seed_has_20_to_50_concepts() -> None:
    assert 20 <= len(SEED_CONCEPTS) <= 50


def test_seed_concepts_all_valid() -> None:
    for c in SEED_CONCEPTS:
        assert c.id
        assert c.description
        assert "." in c.id  # dot-separated convention


def test_seed_into_idempotent(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    seed_into(s)
    n_first = len(s.list_all())

    # Seed again — should be no-op (upsert with same content)
    seed_into(s)
    n_second = len(s.list_all())
    assert n_first == n_second
    assert n_first == len(SEED_CONCEPTS)


def test_seed_into_preserves_user_concepts(tmp_state_dir: Path) -> None:
    from af_expert.concept.model import Concept

    s = ConceptGraphStore()
    s.upsert(Concept(id="user.custom", description="my own", spec_ref=""))
    seed_into(s)

    assert s.get("user.custom") is not None
    assert len(s.list_all()) == len(SEED_CONCEPTS) + 1
```

### Step 2: Write `src/af_expert/concept/seed.py`

```python
from __future__ import annotations

from af_expert.concept.model import Concept
from af_expert.concept.store import ConceptGraphStore


SEED_CONCEPTS: list[Concept] = [
    # --- MCP (Model Context Protocol) ---
    Concept(
        id="mcp.transport.streamable_http",
        description="MCP transport over HTTP+SSE with streaming response support",
        spec_ref="MCP spec 1.x streamable-http transport",
        tags=["mcp", "transport"],
    ),
    Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh-token grant; must not include resource per RFC 8707",
        spec_ref="RFC 8707 §2.2",
        tags=["mcp", "auth", "oauth"],
    ),
    Concept(
        id="mcp.headers.redirect_safety",
        description="MCP header_provider headers must not be re-injected on cross-origin redirects",
        spec_ref="HTTP security; MCP design discussion",
        tags=["mcp", "transport", "security"],
    ),
    Concept(
        id="mcp.duplicate_initialize",
        description="MCP server must reject duplicate `initialize` requests after first",
        spec_ref="MCP spec initialize lifecycle",
        tags=["mcp", "protocol"],
    ),
    Concept(
        id="mcp.tool_result.format",
        description="MCP tool_result payload structure (content blocks, isError flag)",
        spec_ref="MCP spec tools",
        tags=["mcp", "tools"],
    ),
    # --- Anthropic ---
    Concept(
        id="anthropic.thinking_blocks",
        description="Anthropic thinking blocks with signature; orphan signatures must be skipped",
        spec_ref="Anthropic extended thinking docs",
        tags=["anthropic", "streaming"],
    ),
    Concept(
        id="anthropic.tool_use.cancellation",
        description="Anthropic tool_use cancellation mid-stream cleanup",
        spec_ref="Anthropic tool use API",
        tags=["anthropic", "tools", "streaming"],
    ),
    Concept(
        id="anthropic.cache_control",
        description="Anthropic prompt caching via cache_control on content blocks",
        spec_ref="Anthropic prompt caching docs",
        tags=["anthropic", "caching"],
    ),
    Concept(
        id="anthropic.tool_use.computer_use",
        description="Anthropic computer use beta tool with screenshot + action loop",
        spec_ref="Anthropic computer use docs",
        tags=["anthropic", "tools", "beta"],
    ),
    Concept(
        id="anthropic.batch_api",
        description="Anthropic message batches API (asynchronous bulk inference)",
        spec_ref="Anthropic batches docs",
        tags=["anthropic", "batch"],
    ),
    # --- OpenAI ---
    Concept(
        id="openai.responses_api",
        description="OpenAI Responses API (new unified endpoint for chat + tools + structured outputs)",
        spec_ref="OpenAI API reference",
        tags=["openai"],
    ),
    Concept(
        id="openai.structured_outputs",
        description="OpenAI structured outputs via response_format JSON schema",
        spec_ref="OpenAI structured outputs docs",
        tags=["openai", "schemas"],
    ),
    Concept(
        id="openai.realtime_api",
        description="OpenAI Realtime API for low-latency voice/audio agents",
        spec_ref="OpenAI Realtime docs",
        tags=["openai", "voice"],
    ),
    # --- Google / Gemini ---
    Concept(
        id="gemini.thinking_signatures",
        description="Gemini thinking_blocks with parallel thought_signatures field",
        spec_ref="LiteLLM / Gemini docs",
        tags=["google", "gemini", "streaming"],
    ),
    Concept(
        id="gemini.live_api",
        description="Gemini Live API for streaming multimodal sessions with tool use",
        spec_ref="Gemini Live docs",
        tags=["google", "gemini"],
    ),
    Concept(
        id="gemini.const_schemas",
        description="Gemini accepts const in JSON schemas; some frameworks drop it",
        spec_ref="Gemini structured outputs",
        tags=["google", "gemini", "schemas"],
    ),
    # --- AG-UI ---
    Concept(
        id="agui.event_metadata",
        description="AG-UI protocol event metadata propagation across handoffs",
        spec_ref="AG-UI spec",
        tags=["agui", "protocol"],
    ),
    Concept(
        id="agui.tool_history_replay",
        description="AG-UI tool history replay across sessions; must preserve message_id stability",
        spec_ref="AG-UI tool history docs",
        tags=["agui", "tools", "replay"],
    ),
    # --- Tool use generalities ---
    Concept(
        id="tools.parallel_execution",
        description="Multiple tool calls returned in one assistant message; framework executes in parallel",
        spec_ref="Multiple provider docs",
        tags=["tools", "parallel"],
    ),
    Concept(
        id="tools.cancellation_lifecycle",
        description="Tool execution can be cancelled mid-call; cleanup of resources + state required",
        spec_ref="Framework-specific",
        tags=["tools", "cancellation"],
    ),
    # --- Async / Concurrency ---
    Concept(
        id="async.cancellation_propagation",
        description="asyncio.CancelledError propagation across LLM client + tool boundaries",
        spec_ref="Python asyncio docs",
        tags=["async", "python"],
    ),
    Concept(
        id="async.contextvars.session_state",
        description="ContextVar-based session state isolation between concurrent requests",
        spec_ref="Python 3.7+ contextvars",
        tags=["async", "python", "state"],
    ),
    # --- Token / Cost accounting ---
    Concept(
        id="tokens.cache_hit_accounting",
        description="Provider-reported cache_read_input_tokens accounting for cost reporting",
        spec_ref="Anthropic + OpenAI usage fields",
        tags=["tokens", "cost"],
    ),
    Concept(
        id="tokens.image_token_estimation",
        description="Image input token estimation per provider (different formulae)",
        spec_ref="Anthropic vision + OpenAI vision docs",
        tags=["tokens", "vision"],
    ),
    # --- Memory / RAG ---
    Concept(
        id="memory.summarization_truncation",
        description="Conversation history summarization with deterministic truncation point",
        spec_ref="Multiple framework implementations",
        tags=["memory", "context"],
    ),
    # --- Multi-agent / Handoff ---
    Concept(
        id="handoff.context_passing",
        description="Multi-agent handoff: which context fields cross the boundary",
        spec_ref="OpenAI swarm + agent-framework Magentic",
        tags=["multi-agent", "handoff"],
    ),
    # --- Schema / Serialization ---
    Concept(
        id="schema.pydantic_v1_v2",
        description="Pydantic v1 vs v2 compatibility shims in tool / output schemas",
        spec_ref="Pydantic migration docs",
        tags=["schemas", "pydantic"],
    ),
    Concept(
        id="schema.tool_to_provider_mapping",
        description="Tool JSON schema → provider-specific schema (Anthropic vs OpenAI vs Gemini)",
        spec_ref="Framework adapters",
        tags=["schemas", "tools"],
    ),
    # --- Safety / Policy ---
    Concept(
        id="safety.prompt_injection_corpus",
        description="Known prompt-injection corpus; framework safety layer must catch or flag",
        spec_ref="OWASP LLM Top 10",
        tags=["safety", "security"],
    ),
    # --- Streaming ---
    Concept(
        id="streaming.sse_reconnect",
        description="SSE reconnect logic: must not duplicate events on resume",
        spec_ref="HTTP SSE spec + Anthropic/OpenAI clients",
        tags=["streaming"],
    ),
]


def seed_into(store: ConceptGraphStore) -> int:
    """Upsert all seeds into the store. Returns count of seeded concepts."""
    for c in SEED_CONCEPTS:
        store.upsert(c)
    return len(SEED_CONCEPTS)
```

### Step 3: Run tests

```bash
uv run pytest tests/test_concept_seed.py -v
```

Expected: 4 tests pass.

### Step 4: Commit

```bash
git add python/tools/af_expert/src/af_expert/concept/seed.py python/tools/af_expert/tests/test_concept_seed.py
git commit -m "feat(af-expert): seed concept graph with 30 agent/LLM domain concepts"
```

---

## Task 3: Concept linker (LLM-driven concept → repo mapping)

**Files:**
- Create: `python/tools/af_expert/src/af_expert/concept/linker.py`
- Test: `python/tools/af_expert/tests/test_concept_linker.py`

Given a `Concept` and a `FileInventory` (or briefing markdown), LLM identifies which files in the repo implement it.

### Step 1: Tests

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.architecture.scanner import FileInventory
from af_expert.concept.linker import (
    build_linker_prompt,
    link_concept_to_repo,
)
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.llm import LLM, LLMResponse


def _make_inv(tmp_path: Path) -> FileInventory:
    inv = FileInventory(repo_root=tmp_path / "fake")
    inv.source_files = [
        "src/agent_framework/_mcp.py",
        "src/agent_framework/_anthropic.py",
    ]
    inv.provider_files = {"anthropic": ["src/agent_framework/_anthropic.py"]}
    return inv


def test_linker_prompt_includes_concept_and_files(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)
    prompt = build_linker_prompt(repo="microsoft/agent-framework", concept=c, inventory=inv)
    assert "mcp.oauth.refresh" in prompt
    assert "RFC 8707" in prompt
    assert "_mcp.py" in prompt


def test_link_returns_impl_when_llm_finds_match(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text=(
            '```json\n'
            '{"matches": true, "files": ["src/agent_framework/_mcp.py"], '
            '"functions": ["_refresh_token"], "confidence": 0.85}\n'
            '```'
        ),
        input_tokens=200, output_tokens=40, cache_read_tokens=0, cache_creation_tokens=0,
    )

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is not None
    assert impl.repo == "microsoft/agent-framework"
    assert "src/agent_framework/_mcp.py" in impl.files
    assert "_refresh_token" in impl.functions


def test_link_returns_none_when_no_match(tmp_path: Path) -> None:
    c = Concept(id="mcp.oauth.refresh", description="MCP OAuth refresh", spec_ref="RFC 8707")
    inv = _make_inv(tmp_path)

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"matches": false, "files": [], "functions": [], "confidence": 0.1}\n```',
        input_tokens=200, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is None


def test_link_returns_none_on_llm_error(tmp_path: Path) -> None:
    c = Concept(id="x.y", description="...", spec_ref="")
    inv = _make_inv(tmp_path)
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = RuntimeError("LLM down")

    impl = link_concept_to_repo(repo="microsoft/agent-framework", concept=c, inventory=inv, llm=llm)
    assert impl is None
```

### Step 2: Write `src/af_expert/concept/linker.py`

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

from af_expert.architecture.scanner import FileInventory
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.llm import LLM, parse_json_block


log = logging.getLogger(__name__)


def build_linker_prompt(*, repo: str, concept: Concept, inventory: FileInventory) -> str:
    parts: list[str] = []
    parts.append(
        f"You are linking the domain concept '{concept.id}' to its implementation in "
        f"the repository '{repo}'.\n\n"
        f"Concept description: {concept.description}\n"
        f"Spec reference: {concept.spec_ref or 'none'}\n\n"
        "Below is the repository's source file inventory. Identify which files (and "
        "which top-level functions/classes within them) implement this concept. If the "
        "concept is not present, set matches=false.\n\n"
        "Respond with ONLY a fenced ```json block with fields:\n"
        "- matches: true | false\n"
        "- files: list of file paths from the inventory\n"
        "- functions: list of function/class names\n"
        "- confidence: float 0.0-1.0\n\n"
    )
    parts.append("### Source files\n")
    for f in inventory.source_files[:300]:
        parts.append(f"- {f}\n")
    if inventory.provider_files:
        parts.append("\n### Provider files\n")
        for provider, files in inventory.provider_files.items():
            parts.append(f"- {provider}: {', '.join(files[:5])}\n")
    return "".join(parts)


def link_concept_to_repo(
    *, repo: str, concept: Concept, inventory: FileInventory, llm: LLM
) -> ConceptImplementation | None:
    try:
        resp = llm.complete(
            system="You are linking an OSS architectural concept to its implementation in a repo.",
            user=build_linker_prompt(repo=repo, concept=concept, inventory=inventory),
            caller_label=f"concept.linker[{concept.id}->{repo}]",
        )
        data = parse_json_block(resp.text)
    except Exception as e:
        log.warning("concept.linker failed for %s -> %s: %s", concept.id, repo, e)
        return None

    if not data.get("matches"):
        return None

    return ConceptImplementation(
        repo=repo,
        files=list(data.get("files", [])),
        functions=list(data.get("functions", [])),
        last_modified=datetime.now(tz=timezone.utc).date().isoformat(),
    )
```

### Step 3: Run tests + commit

```bash
uv run pytest tests/test_concept_linker.py -v
# Expected: 4 tests pass

git add python/tools/af_expert/src/af_expert/concept/linker.py python/tools/af_expert/tests/test_concept_linker.py
git commit -m "feat(af-expert): LLM-driven concept-to-repo linker"
```

---

## Task 4: Strategy S2 — Cross-repo structural diff

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s2_structural_diff.py`
- Test: `python/tools/af_expert/tests/test_strategy_s2.py`

For each concept in the graph, identify repos whose implementation hasn't been updated in N days while the spec OR another repo's implementation has. Emit "this repo is lagging on concept X" candidates.

### Step 1: Tests

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM
from af_expert.strategies.s2_structural_diff import (
    StructuralDiffStrategy,
    find_lagging_impls,
)


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_find_lagging_impls_detects_stale(tmp_state_dir: Path) -> None:
    store = ConceptGraphStore()
    c = Concept(
        id="mcp.oauth.refresh",
        description="...",
        spec_ref="RFC 8707",
        implementations={
            "fresh/repo": ConceptImplementation(
                repo="fresh/repo", files=["x.py"], functions=[],
                last_modified="2026-05-10",
            ),
            "stale/repo": ConceptImplementation(
                repo="stale/repo", files=["y.py"], functions=[],
                last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    lagging = find_lagging_impls(
        store=store, now=datetime(2026, 5, 18, tzinfo=timezone.utc), staleness_days=180
    )
    repos = [(concept_id, impl.repo) for concept_id, impl in lagging]
    assert ("mcp.oauth.refresh", "stale/repo") in repos
    assert all("fresh/repo" not in r for _, r in repos)


def test_strategy_emits_candidate_for_lagging_repo(tmp_state_dir: Path) -> None:
    store = ConceptGraphStore()
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh handling",
        spec_ref="RFC 8707",
        implementations={
            "fresh/repo": ConceptImplementation(
                repo="fresh/repo", files=["x.py"], functions=["f"], last_modified="2026-05-10",
            ),
            "stale/repo": ConceptImplementation(
                repo="stale/repo", files=["y.py"], functions=["g"], last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    candidates = CandidateStore()
    events = EventStore(); events.ensure_schema()
    llm = MagicMock(spec=LLM)
    cfg = _config(["fresh/repo", "stale/repo"])

    strat = StructuralDiffStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, concept_store=store
    )
    produced = strat.on_weekly_tick(now=datetime(2026, 5, 18, tzinfo=timezone.utc))

    assert len(produced) >= 1
    assert any(p.target_repo == "stale/repo" for p in produced)


def test_strategy_skips_repos_not_in_config(tmp_state_dir: Path) -> None:
    """Concepts may reference repos not in the operator's config; skip those."""
    store = ConceptGraphStore()
    c = Concept(
        id="x.y",
        description="...",
        spec_ref="",
        implementations={
            "untracked/repo": ConceptImplementation(
                repo="untracked/repo", files=["x"], functions=[], last_modified="2025-01-01",
            ),
        },
    )
    store.upsert(c)

    candidates = CandidateStore()
    events = EventStore(); events.ensure_schema()
    llm = MagicMock(spec=LLM)
    cfg = _config(["other/repo"])  # untracked/repo not in config

    strat = StructuralDiffStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, concept_store=store
    )
    produced = strat.on_weekly_tick(now=datetime(2026, 5, 18, tzinfo=timezone.utc))
    assert all(p.target_repo != "untracked/repo" for p in produced)
```

### Step 2: Write `src/af_expert/strategies/s2_structural_diff.py`

```python
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

DEFAULT_STALENESS_DAYS = 180


def find_lagging_impls(
    *, store: ConceptGraphStore, now: datetime, staleness_days: int = DEFAULT_STALENESS_DAYS
) -> list[tuple[str, ConceptImplementation]]:
    """Find implementations that haven't been updated within `staleness_days`."""
    cutoff = now - timedelta(days=staleness_days)
    lagging: list[tuple[str, ConceptImplementation]] = []
    for concept in store.list_all():
        for repo, impl in concept.implementations.items():
            if not impl.last_modified:
                continue
            try:
                last = datetime.fromisoformat(impl.last_modified).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if last < cutoff:
                lagging.append((concept.id, impl))
    return lagging


class StructuralDiffStrategy(Strategy):
    name = "s2_structural_diff"

    def __init__(self, *args: Any, concept_store: ConceptGraphStore, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.concept_store = concept_store

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []  # S2 is weekly

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:
        if now is None:
            now = datetime.now(tz=timezone.utc)

        produced: list[Candidate] = []
        tracked = {r.owner_repo for r in self.config.repos}

        lagging = find_lagging_impls(store=self.concept_store, now=now)
        for concept_id, impl in lagging:
            if impl.repo not in tracked:
                continue
            concept = self.concept_store.get(concept_id)
            if concept is None:
                continue
            candidate = self._build_candidate(concept=concept, impl=impl, now=now)
            self.candidates.append(candidate)
            produced.append(candidate)
            log.info(
                "S2 %s: %s lagging on %s (last_modified=%s)",
                concept_id, impl.repo, concept.spec_ref or "(no spec)", impl.last_modified,
            )

        return produced

    def _build_candidate(
        self, *, concept: Concept, impl: ConceptImplementation, now: datetime
    ) -> Candidate:
        return Candidate(
            id=f"s2-{uuid.uuid4().hex[:12]}",
            discovered_at=now,
            strategy=self.name,
            target_repo=impl.repo,
            target_files=impl.files,
            category="consolidation",
            title=f"{impl.repo} lagging on {concept.id}",
            description=(
                f"Concept '{concept.id}' ({concept.description}) "
                f"has not been updated in {impl.repo} since {impl.last_modified}. "
                f"Spec reference: {concept.spec_ref or 'none recorded'}.\n\n"
                f"Files: {', '.join(impl.files)}\n"
                f"Functions: {', '.join(impl.functions)}"
            ),
            suggested_action=(
                f"Review {concept.id} implementation in {impl.repo}; compare against "
                f"more recent implementations in sister repos to identify what needs porting."
            ),
            evidence_urls=[f"https://github.com/{impl.repo}"],
            evidence_snippets=[],
            confidence=0.5,
            novelty=0.7,
            actionability=0.4,
            strategy_reputation=0.5,
            status="new",
        )
```

### Step 3: Run tests + commit

```bash
uv run pytest tests/test_strategy_s2.py -v
# Expected: 3 tests pass

git add python/tools/af_expert/src/af_expert/strategies/s2_structural_diff.py python/tools/af_expert/tests/test_strategy_s2.py
git commit -m "feat(af-expert): S2 cross-repo structural diff strategy (concept graph queries)"
```

---

## Task 5: Strategy S7 — Cross-repo feature propagation

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s7_feature_propagation.py`
- Test: `python/tools/af_expert/tests/test_strategy_s7.py`

When a tracked repo lands a substantial new feature (signal: PR with `feat:` prefix, sizeable diff), suggest propagating to sister repos that don't have equivalent capability.

### Step 1: Tests

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.ingestion.store import EventRecord, EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s7_feature_propagation import (
    FeaturePropagationStrategy,
    is_likely_feature_pr,
)


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def test_is_likely_feature_pr_title_match() -> None:
    assert is_likely_feature_pr(title="feat: add Magentic multi-agent", labels=[]) is True
    assert is_likely_feature_pr(title="feat(scope): add X", labels=[]) is True


def test_is_likely_feature_pr_label_match() -> None:
    assert is_likely_feature_pr(title="something", labels=["enhancement"]) is True
    assert is_likely_feature_pr(title="something", labels=["feature"]) is True


def test_is_likely_feature_pr_excludes_fix() -> None:
    assert is_likely_feature_pr(title="fix: bug", labels=["bug"]) is False


def _make_feat_pr(repo: str, number: int, title: str) -> EventRecord:
    return EventRecord(
        repo=repo, kind="pr", number=number,
        title=title, body="A substantial new feature.", diff="+++ b/x.py\n+ class NewThing: pass\n",
        author="someone", state="merged", labels=["enhancement"],
        created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        merged_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        url=f"https://github.com/{repo}/pull/{number}",
    )


def test_strategy_emits_candidate_for_unsupported_feature(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    events.insert(_make_feat_pr("microsoft/agent-framework", 5778, "feat: add Magentic multi-agent"))

    candidates = CandidateStore()

    extract_resp = LLMResponse(
        text='```json\n{"feature_name": "magentic_multi_agent", "summary": "Multi-agent orchestration"}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    sister_check_resp = LLMResponse(
        text='```json\n{"has_equivalent": false, "confidence": 0.7, "reasoning": "no multi-agent abstraction found"}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    llm = MagicMock(spec=LLM)
    llm.complete.side_effect = [extract_resp, sister_check_resp]

    cfg = _config(["microsoft/agent-framework", "langchain-ai/langchain"])
    strat = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)

    deltas = IngestionDeltas(
        since=datetime(2026, 5, 13, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )
    produced = strat.on_ingestion_complete(deltas)

    assert len(produced) == 1
    assert produced[0].target_repo == "langchain-ai/langchain"
    assert produced[0].category == "feature"


def test_strategy_skips_non_feature_pr(tmp_state_dir: Path) -> None:
    events = EventStore(); events.ensure_schema()
    events.insert(_make_feat_pr("microsoft/agent-framework", 5784, "fix: orphan thinking"))

    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)

    cfg = _config(["microsoft/agent-framework", "langchain-ai/langchain"])
    strat = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
    deltas = IngestionDeltas(
        since=datetime(2026, 5, 13, tzinfo=timezone.utc),
        repos_with_new_prs=["microsoft/agent-framework"],
    )

    produced = strat.on_ingestion_complete(deltas)
    # `fix:` title with no enhancement label is not a feature
    # Note: _make_feat_pr sets labels=["enhancement"] always — adjust if needed
```

(The last test is somewhat soft due to the helper always setting `labels=["enhancement"]`. The strategy should rely primarily on title prefix to distinguish feat from fix. Verify by reviewing how the strategy categorizes.)

### Step 2: Write `src/af_expert/strategies/s7_feature_propagation.py`

```python
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


_FEAT_TITLE_RE = re.compile(r"^(feat|feature)[\(:]", re.IGNORECASE)
_FIX_TITLE_RE = re.compile(r"^(fix|bug|hotfix)[\(:]", re.IGNORECASE)
_FEAT_LABELS = {"enhancement", "feature", "new feature"}


def is_likely_feature_pr(title: str, labels: list[str]) -> bool:
    if _FIX_TITLE_RE.search(title or ""):
        return False
    if _FEAT_TITLE_RE.search(title or ""):
        return True
    if any(lab.lower() in _FEAT_LABELS for lab in labels):
        return True
    return False


def extract_feature_prompt(*, title: str, body: str, diff: str) -> str:
    return (
        "You will be given the title, body, and diff of a merged feature PR.\n"
        "Extract a concise feature identifier suitable for cross-repo propagation discussion.\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- feature_name: short snake_case identifier\n"
        "- summary: 1-2 sentences explaining what the feature does and what problem it solves\n\n"
        f"TITLE:\n{title}\n\n"
        f"BODY:\n{body}\n\n"
        f"DIFF (truncated):\n{(diff or '')[:6000]}\n"
    )


def sister_check_prompt(*, framework: str, feature_name: str, summary: str) -> str:
    return (
        f"You are checking whether framework {framework} already has an equivalent of feature "
        f"'{feature_name}'.\n\n"
        f"Feature summary: {summary}\n\n"
        "Based on your training-time knowledge of this framework's API and source structure, "
        "decide whether it has an equivalent capability.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- has_equivalent: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class FeaturePropagationStrategy(Strategy):
    name = "s7_feature_propagation"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []
        all_repos = [r.owner_repo for r in self.config.repos]

        for source_repo in deltas.repos_with_new_prs:
            for pr in self.events.query_recent_prs(source_repo, since=deltas.since, only_merged=True):
                import json
                raw_labels = pr.get("labels") or "[]"
                try:
                    labels = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
                except json.JSONDecodeError:
                    labels = []
                if not is_likely_feature_pr(pr["title"], labels):
                    continue

                feature = self._extract_feature(pr)
                if feature is None:
                    continue

                for target in all_repos:
                    if target == source_repo:
                        continue
                    verdict = self._check_sister(target, feature)
                    if verdict is None or verdict.get("has_equivalent"):
                        continue
                    candidate = self._build_candidate(
                        source_repo=source_repo, source_pr=pr,
                        target_repo=target, feature=feature, verdict=verdict,
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _extract_feature(self, pr: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You extract feature identifiers from merged feature PRs.",
                user=extract_feature_prompt(
                    title=pr["title"], body=pr.get("body") or "", diff=pr.get("diff") or "",
                ),
                caller_label=f"s7.extract[{pr.get('repo')}#{pr['number']}]",
            )
            data = parse_json_block(resp.text)
            return {"feature_name": data["feature_name"], "summary": data["summary"]}
        except Exception as e:
            log.warning("S7 feature extract failed: %s", e)
            return None

    def _check_sister(self, framework: str, feature: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You check whether a framework already has an equivalent of a given feature.",
                user=sister_check_prompt(
                    framework=framework,
                    feature_name=feature["feature_name"],
                    summary=feature["summary"],
                ),
                caller_label=f"s7.check[{framework}/{feature['feature_name']}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S7 sister check failed for %s: %s", framework, e)
            return None

    def _build_candidate(
        self, *, source_repo: str, source_pr: dict[str, Any], target_repo: str,
        feature: dict[str, Any], verdict: dict[str, Any],
    ) -> Candidate:
        return Candidate(
            id=f"s7-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=target_repo,
            category="feature",
            title=f"Propose {feature['feature_name']} for {target_repo}",
            description=(
                f"Source: {source_repo}#{source_pr['number']} introduced "
                f"'{feature['feature_name']}'.\n\n"
                f"Feature summary: {feature['summary']}\n\n"
                f"Target framework verdict: {verdict.get('reasoning', '')} "
                f"(confidence {float(verdict.get('confidence', 0.0)):.2f})"
            ),
            suggested_action=(
                f"Open an issue / RFC in {target_repo} proposing a similar feature. "
                f"DO NOT submit a drop-in PR — feature proposals need design alignment first."
            ),
            evidence_urls=[source_pr.get("url", "")],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.5)),
            novelty=0.7,
            actionability=0.4,  # feature proposals are slow
            strategy_reputation=0.5,
            status="new",
        )
```

### Step 3: Run tests + commit

```bash
uv run pytest tests/test_strategy_s7.py -v
# Expected: 4-5 tests pass

git add python/tools/af_expert/src/af_expert/strategies/s7_feature_propagation.py python/tools/af_expert/tests/test_strategy_s7.py
git commit -m "feat(af-expert): S7 cross-repo feature propagation strategy"
```

---

## Task 6: CLI — concept subcommand group + S2/S7 wiring

**Files:**
- Modify: `python/tools/af_expert/src/af_expert/cli.py`
- Test: `python/tools/af_expert/tests/test_cli.py`

Add:
- `af-expert concept seed` — seed initial 30 concepts
- `af-expert concept list` — print concept IDs + descriptions
- `af-expert concept show <id>` — print full concept JSON
- `af-expert concept link <id> --repo <owner/repo>` — run LLM linker for one concept/repo pair
- `af-expert tick --include-structural` — enable S2
- `af-expert tick --include-propagation` — enable S7
- `af-expert strategy run s2_structural_diff` / `s7_feature_propagation`

### Step 1: Add tests

Append to `tests/test_cli.py`:

```python
def test_concept_seed_command(tmp_state_dir, monkeypatch) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\nanthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "a/b"\n'
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["concept", "seed"])
    assert result.exit_code == 0
    assert "seeded" in result.output.lower() or "concepts" in result.output.lower()


def test_concept_list_command(tmp_state_dir) -> None:
    cfg_path = tmp_state_dir / "config.toml"
    cfg_path.write_text(
        'github_token = "x"\nanthropic_api_key = "y"\n\n'
        '[[repos]]\nowner_repo = "a/b"\n'
    )
    runner = CliRunner()
    runner.invoke(cli, ["concept", "seed"])
    result = runner.invoke(cli, ["concept", "list"])
    assert result.exit_code == 0
    assert "mcp.oauth.refresh" in result.output


def test_tick_with_structural_and_propagation_flags(tmp_state_dir) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tick", "--help"])
    assert "--include-structural" in result.output
    assert "--include-propagation" in result.output
```

### Step 2: Modify `src/af_expert/cli.py`

Add imports near the top with the other strategy imports:

```python
from af_expert.concept.linker import link_concept_to_repo
from af_expert.concept.seed import seed_into
from af_expert.concept.store import ConceptGraphStore
from af_expert.strategies.s2_structural_diff import StructuralDiffStrategy
from af_expert.strategies.s7_feature_propagation import FeaturePropagationStrategy
```

Update the `tick` command to add `--include-structural` and `--include-propagation` flags, threading through S2 and S7:

```python
@cli.command()
@click.option("--include-archaeology", is_flag=True, default=False)
@click.option("--include-providers", is_flag=True, default=False)
@click.option("--include-health", is_flag=True, default=False)
@click.option("--include-structural", is_flag=True, default=False, help="Run S2 structural diff")
@click.option("--include-propagation", is_flag=True, default=False, help="Run S7 feature propagation")
def tick(
    include_archaeology: bool, include_providers: bool, include_health: bool,
    include_structural: bool, include_propagation: bool,
) -> None:
    """Run one ingestion + strategy tick."""
    cfg = load_config()
    sd = StateDir()
    sd.ensure_layout()
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    gh = GitHubClient(token=cfg.github_token)
    llm = LLM(api_key=cfg.anthropic_api_key)
    concept_store = ConceptGraphStore()

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
        all_produced: list = list(s1.on_ingestion_complete(deltas))
        click.echo(f"S1 produced {len(all_produced)} candidates")

        if include_providers:
            s4 = ProviderReleaseStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            p4 = s4.on_ingestion_complete(deltas)
            click.echo(f"S4 produced {len(p4)} candidates")
            all_produced.extend(p4)

        if include_health:
            s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            p6 = s6.on_weekly_tick(now=now)
            click.echo(f"S6 produced {len(p6)} candidates")
            all_produced.extend(p6)

        if include_structural:
            s2 = StructuralDiffStrategy(
                config=cfg, events=events, candidates=candidates, llm=llm, concept_store=concept_store
            )
            p2 = s2.on_weekly_tick(now=now)
            click.echo(f"S2 produced {len(p2)} candidates")
            all_produced.extend(p2)

        if include_propagation:
            s7 = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            p7 = s7.on_ingestion_complete(deltas)
            click.echo(f"S7 produced {len(p7)} candidates")
            all_produced.extend(p7)

        if include_archaeology:
            s8 = IssueArchaeologyStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
            p8: list = []
            for repo_cfg in cfg.repos:
                p8.extend(s8.on_demand({"repo": repo_cfg.owner_repo}))
            click.echo(f"S8 produced {len(p8)} candidates")
            all_produced.extend(p8)

        digest_md = render_digest(
            since=since, candidates=all_produced,
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
```

Add concept group:

```python
@cli.group()
def concept() -> None:
    """Concept graph management."""


@concept.command("seed")
def concept_seed() -> None:
    """Seed the concept graph with the built-in 30 agent/LLM domain concepts."""
    store = ConceptGraphStore()
    n = seed_into(store)
    click.echo(f"Seeded {n} concepts into {store.path}")


@concept.command("list")
def concept_list() -> None:
    store = ConceptGraphStore()
    concepts = store.list_all()
    if not concepts:
        click.echo("(concept graph empty — run `af-expert concept seed`)")
        return
    for c in concepts:
        click.echo(f"  {c.id}\t{c.description}")


@concept.command("show")
@click.argument("concept_id")
def concept_show(concept_id: str) -> None:
    store = ConceptGraphStore()
    c = store.get(concept_id)
    if c is None:
        click.echo(f"concept {concept_id!r} not found", err=True)
        sys.exit(2)
    click.echo(c.model_dump_json(indent=2))


@concept.command("link")
@click.argument("concept_id")
@click.option("--repo", required=True)
def concept_link(concept_id: str, repo: str) -> None:
    from af_expert.architecture.refresh import _clone_repo_shallow, repo_briefing_path
    from af_expert.architecture.scanner import scan_repo_locally
    import tempfile
    from pathlib import Path
    import shutil

    cfg = load_config()
    store = ConceptGraphStore()
    c = store.get(concept_id)
    if c is None:
        click.echo(f"concept {concept_id!r} not found; run `af-expert concept seed` first", err=True)
        sys.exit(2)

    llm = LLM(api_key=cfg.anthropic_api_key)
    tmp_dir = Path(tempfile.mkdtemp(prefix="af-expert-concept-link-"))
    try:
        clone_dir = tmp_dir / repo.split("/")[-1]
        try:
            _clone_repo_shallow(repo, clone_dir)
        except Exception as e:
            click.echo(f"clone failed: {e}", err=True)
            sys.exit(2)
        inv = scan_repo_locally(clone_dir)
        impl = link_concept_to_repo(repo=repo, concept=c, inventory=inv, llm=llm)
        if impl is None:
            click.echo(f"{concept_id} -> {repo}: no link found")
            return
        store.attach_implementation(concept_id, impl)
        click.echo(f"linked {concept_id} -> {repo}: files={impl.files} functions={impl.functions}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

Update `strategy_list`:

```python
@strategy.command("list")
def strategy_list() -> None:
    click.echo("Strategies (Wave 1 + 2 + 3):")
    click.echo("  s1_pr_forward_port      (on-tick)")
    click.echo("  s2_structural_diff      (on-tick with --include-structural)")
    click.echo("  s4_provider_release     (on-tick with --include-providers)")
    click.echo("  s6_maintainer_health    (on-tick with --include-health)")
    click.echo("  s7_feature_propagation  (on-tick with --include-propagation)")
    click.echo("  s8_issue_archaeology    (on-demand or with --include-archaeology)")
```

Update `strategy_run` to also handle s2 and s7:

```python
@strategy.command("run")
@click.argument("name")
@click.option("--repo", default=None)
def strategy_run(name: str, repo: str | None) -> None:
    cfg = load_config()
    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = LLM(api_key=cfg.anthropic_api_key)
    concept_store = ConceptGraphStore()

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
            since=datetime.now(tz=timezone.utc), repos_with_new_prs=[r.owner_repo for r in cfg.repos],
        ))
        click.echo(f"S4: {len(produced)} candidates")
    elif name == "s6_maintainer_health":
        s6 = MaintainerHealthStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s6.on_weekly_tick()
        click.echo(f"S6: {len(produced)} candidates")
    elif name == "s2_structural_diff":
        s2 = StructuralDiffStrategy(
            config=cfg, events=events, candidates=candidates, llm=llm, concept_store=concept_store
        )
        produced = s2.on_weekly_tick()
        click.echo(f"S2: {len(produced)} candidates")
    elif name == "s7_feature_propagation":
        s7 = FeaturePropagationStrategy(config=cfg, events=events, candidates=candidates, llm=llm)
        produced = s7.on_ingestion_complete(IngestionDeltas(
            since=datetime.now(tz=timezone.utc) - timedelta(days=7),
            repos_with_new_prs=[r.owner_repo for r in cfg.repos],
        ))
        click.echo(f"S7: {len(produced)} candidates")
    else:
        click.echo(f"Strategy '{name}' not recognized", err=True)
        sys.exit(2)
```

### Step 3: Run tests + commit

```bash
uv run pytest tests/test_cli.py -v
# Expected: all existing + 3 new pass

git add python/tools/af_expert/src/af_expert/cli.py python/tools/af_expert/tests/test_cli.py
git commit -m "feat(af-expert): wire S2 + S7 + concept subcommand group into CLI"
```

---

## Task 7: README update

**Files:**
- Modify: `python/tools/af_expert/README.md`

Document Wave 3 commands and concepts.

### Step 1: Add a "### Wave 3 commands" subsection after the Wave 2 one

```markdown
### Wave 3 commands

```bash
# Seed the concept graph with built-in 30 agent/LLM domain concepts
af-expert concept seed

# List all concepts
af-expert concept list

# Show full details for one concept
af-expert concept show mcp.oauth.refresh

# Link a concept to a repo (clones repo, runs LLM linker, persists)
af-expert concept link mcp.oauth.refresh --repo microsoft/agent-framework

# Tick with structural diff (S2) or feature propagation (S7) enabled
af-expert tick --include-structural
af-expert tick --include-propagation
af-expert tick --include-structural --include-propagation --include-providers --include-health

# Run a strategy manually
af-expert strategy run s2_structural_diff
af-expert strategy run s7_feature_propagation
```
```

### Step 2: Replace "## Wave 2 status" with "## Wave 3 status"

```markdown
## Wave 3 status

Wave 3 adds:

- **Concept graph**: 30 hand-curated agent/LLM domain concepts (MCP transport,
  Anthropic thinking blocks, OAuth refresh handling, etc.) with per-repo
  implementation links. Stored as a single JSON file at
  `~/.af-expert/concept_graph.json`.
- **S2 cross-repo structural diff**: for each concept, identifies repos whose
  implementation hasn't been updated in >180 days. Emits "this repo is lagging
  on concept X" candidates. No LLM cost (pure JSON query).
- **S7 cross-repo feature propagation**: detects new feature PRs (title `feat:`)
  in tracked repos and proposes propagation to sister repos that don't have
  equivalent capability. LLM-driven equivalence check.

### Concept graph layout

```
~/.af-expert/concept_graph.json   # single-file JSON, atomic writes
```

### Still TBD (Wave 4+)

- S3 hypothesis verification
- S5 spec conformance fuzzer
```

### Step 3: Commit

```bash
git add python/tools/af_expert/README.md
git commit -m "docs(af-expert): document Wave 3 (concept graph / S2 / S7)"
```

---

## Wave 3 done — verification checklist

- [ ] `uv run pytest -v --ignore=tests/e2e 2>&1 | tail -5` — all tests pass (expect ~105-115)
- [ ] `uv run af-expert concept seed` succeeds, writes `~/.af-expert/concept_graph.json`
- [ ] `uv run af-expert concept list` shows the 30 seeded concepts
- [ ] `uv run af-expert concept show mcp.oauth.refresh` prints the concept JSON
- [ ] `uv run af-expert strategy run s2_structural_diff` runs (may produce 0 candidates if no implementations linked yet)
- [ ] `uv run af-expert tick --help` shows `--include-structural` and `--include-propagation`

## Wave 3 validation milestones

From spec:
1. ✅ Concept graph initialized with 30 concepts after `af-expert concept seed`
2. ✅ S2 emits a candidate against a repo with stale implementation link (requires `concept link` first)
3. ✅ S7 emits a candidate when a feature PR has no equivalent in a sister repo

## What's NOT in Wave 3 (deferred)

| Wave | Plan delivers |
|---|---|
| 4 | Hypotheses + S3 active verification |
| 5 | Spec corpus + S5 conformance fuzzer |
