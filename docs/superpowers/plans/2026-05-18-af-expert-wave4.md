# af-expert Wave 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a hypothesis tracker and Strategy S3 (active hypothesis verification). Operator (or LLM) can submit hypotheses like "MCP OAuth refresh is non-compliant in most frameworks"; the strategy verifies each hypothesis against one tracked repo per day, accumulating evidence.

**Architecture:** Hypotheses stored as JSON at `~/.af-expert/hypotheses.json`. S3 selects one unverified (hypothesis × repo) pair per tick, fetches that repo's relevant code via Glob+Grep on existing architecture briefing, asks LLM to judge compliance. Verified pairs cached; once all repos in a hypothesis are verified, the hypothesis is archived. Non-compliant verifications emit candidates.

**Validation milestones:**
1. `af-expert hypothesis add "..."` creates a hypothesis in `hypotheses.json`
2. `af-expert hypothesis list` shows active + archived
3. S3 verifies one hypothesis-repo pair per `tick --include-hypotheses` run, emits candidate on non-compliant verdict

---

## File Structure

```
python/tools/af_expert/src/af_expert/
├── hypothesis/
│   ├── __init__.py
│   ├── model.py             # Hypothesis + Verification pydantic models
│   └── store.py             # JSON-file store with atomic writes
└── strategies/
    └── s3_hypothesis_verify.py
```

Modified:
- `cli.py` — add `hypothesis` subcommand group + `--include-hypotheses` flag on tick
- `README.md`

---

## Task 1: Hypothesis model + store

**Files:**
- Create: `python/tools/af_expert/src/af_expert/hypothesis/__init__.py` (empty)
- Create: `python/tools/af_expert/src/af_expert/hypothesis/model.py`
- Create: `python/tools/af_expert/src/af_expert/hypothesis/store.py`
- Test: `python/tools/af_expert/tests/test_hypothesis_model.py`
- Test: `python/tools/af_expert/tests/test_hypothesis_store.py`

### Tests for model (`tests/test_hypothesis_model.py`)

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.hypothesis.model import Hypothesis, Verification


def test_verification_minimal() -> None:
    v = Verification(
        repo="microsoft/agent-framework",
        verified_at="2026-05-18",
        outcome="compliant",
        reasoning="checked _mcp.py",
    )
    assert v.outcome == "compliant"


def test_hypothesis_minimal() -> None:
    h = Hypothesis(
        id="h-001",
        statement="MCP OAuth refresh-token grants in most frameworks send the resource parameter, violating RFC 8707 §2.2",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    assert h.id == "h-001"
    assert h.status == "active"
    assert h.verifications == {}


def test_hypothesis_outcome_validation() -> None:
    with pytest.raises(ValueError):
        Verification(
            repo="x/y",
            verified_at="2026-05-18",
            outcome="invalid-outcome",
            reasoning="...",
        )


def test_hypothesis_roundtrip() -> None:
    h = Hypothesis(
        id="h-001",
        statement="...",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        verifications={
            "x/y": Verification(
                repo="x/y", verified_at="2026-05-18", outcome="non_compliant", reasoning="..."
            ),
        },
    )
    raw = h.model_dump_json()
    h2 = Hypothesis.model_validate_json(raw)
    assert h2 == h
```

### `src/af_expert/hypothesis/__init__.py` (empty)

```python
```

### `src/af_expert/hypothesis/model.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


VerificationOutcome = Literal["compliant", "non_compliant", "not_applicable", "unclear"]
HypothesisStatus = Literal["active", "verified", "archived"]


class Verification(BaseModel):
    repo: str
    verified_at: str           # ISO date
    outcome: VerificationOutcome
    reasoning: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    candidate_id: str | None = None


class Hypothesis(BaseModel):
    id: str
    statement: str
    proposed_by: str           # "operator" | "s1_promotion" | etc.
    created_at: datetime
    status: HypothesisStatus = "active"
    tags: list[str] = Field(default_factory=list)
    verifications: dict[str, Verification] = Field(default_factory=dict)
    notes: str = ""
```

### Tests for store (`tests/test_hypothesis_store.py`)

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore


def _make_h(hid: str = "h-001") -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement="MCP OAuth grants violate RFC 8707",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )


def test_empty_store(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    assert s.list_active() == []


def test_add_and_get(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    s.upsert(_make_h("h-001"))
    fetched = s.get("h-001")
    assert fetched is not None
    assert fetched.statement == "MCP OAuth grants violate RFC 8707"


def test_attach_verification(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    s.upsert(_make_h("h-001"))
    v = Verification(repo="x/y", verified_at="2026-05-18", outcome="non_compliant", reasoning="...")
    s.attach_verification("h-001", v)

    h = s.get("h-001")
    assert "x/y" in h.verifications


def test_list_active_excludes_archived(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    h1 = _make_h("h-001"); h1.status = "active"
    h2 = _make_h("h-002"); h2.status = "archived"
    s.upsert(h1)
    s.upsert(h2)
    active = s.list_active()
    assert len(active) == 1
    assert active[0].id == "h-001"


def test_unverified_repos(tmp_state_dir: Path) -> None:
    s = HypothesisStore()
    h = _make_h("h-001")
    h.verifications["x/y"] = Verification(
        repo="x/y", verified_at="2026-05-18", outcome="compliant", reasoning="ok"
    )
    s.upsert(h)

    unverified = s.unverified_repos("h-001", all_repos=["x/y", "a/b", "c/d"])
    assert "x/y" not in unverified
    assert set(unverified) == {"a/b", "c/d"}
```

### `src/af_expert/hypothesis/store.py`

```python
from __future__ import annotations

import json
from pathlib import Path

from af_expert.config import _state_dir
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.state import atomic_write


class HypothesisStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "hypotheses.json"

    def _load(self) -> dict[str, Hypothesis]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {hid: Hypothesis.model_validate(d) for hid, d in raw.get("hypotheses", {}).items()}

    def _save(self, hs: dict[str, Hypothesis]) -> None:
        payload = {
            "version": 1,
            "hypotheses": {hid: h.model_dump() for hid, h in hs.items()},
        }
        atomic_write(self.path, json.dumps(payload, indent=2, sort_keys=True, default=str))

    def list_all(self) -> list[Hypothesis]:
        return list(self._load().values())

    def list_active(self) -> list[Hypothesis]:
        return [h for h in self._load().values() if h.status == "active"]

    def get(self, hid: str) -> Hypothesis | None:
        return self._load().get(hid)

    def upsert(self, h: Hypothesis) -> None:
        hs = self._load()
        hs[h.id] = h
        self._save(hs)

    def attach_verification(self, hid: str, v: Verification) -> None:
        hs = self._load()
        if hid not in hs:
            raise KeyError(f"Hypothesis {hid!r} not found")
        hs[hid].verifications[v.repo] = v
        self._save(hs)

    def unverified_repos(self, hid: str, *, all_repos: list[str]) -> list[str]:
        hs = self._load()
        if hid not in hs:
            return all_repos
        verified = set(hs[hid].verifications.keys())
        return [r for r in all_repos if r not in verified]

    def archive(self, hid: str) -> None:
        hs = self._load()
        if hid in hs:
            hs[hid].status = "archived"
            self._save(hs)
```

### Run + commit

```bash
cd python/tools/af_expert
uv run pytest tests/test_hypothesis_model.py tests/test_hypothesis_store.py -v
# Expected: 4 + 5 = 9 tests pass

git add python/tools/af_expert/src/af_expert/hypothesis/ python/tools/af_expert/tests/test_hypothesis_model.py python/tools/af_expert/tests/test_hypothesis_store.py
git commit -m "feat(af-expert): hypothesis model + JSON-file store"
```

---

## Task 2: Strategy S3 — Hypothesis verification

**Files:**
- Create: `python/tools/af_expert/src/af_expert/strategies/s3_hypothesis_verify.py`
- Test: `python/tools/af_expert/tests/test_strategy_s3.py`

S3 picks one unverified `(hypothesis × repo)` per `on_ingestion_complete`. Asks LLM to verify against that repo's architecture briefing if present, else against LLM training-knowledge. Persists verification + emits candidate on `non_compliant`.

### Test (`tests/test_strategy_s3.py`)

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from af_expert.candidate.store import CandidateStore
from af_expert.config import Config, RepoConfig
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM, LLMResponse
from af_expert.strategies.base import IngestionDeltas
from af_expert.strategies.s3_hypothesis_verify import HypothesisVerifyStrategy


def _config(repos: list[str]) -> Config:
    return Config(
        github_token="x", anthropic_api_key="x",
        repos=[RepoConfig(owner_repo=r) for r in repos],
    )


def _h(hid: str = "h-001") -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement="MCP OAuth refresh-token grants violate RFC 8707",
        proposed_by="operator",
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )


def test_strategy_picks_one_unverified_pair(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    hs.upsert(_h("h-001"))

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"outcome": "non_compliant", "reasoning": "checks fail", "confidence": 0.8}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    cfg = _config(["microsoft/agent-framework", "langchain-ai/langchain"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    deltas = IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    )
    produced = strat.on_ingestion_complete(deltas)
    # Exactly one verification per tick
    assert llm.complete.call_count == 1
    # non_compliant verdict -> emits candidate
    assert len(produced) == 1
    assert produced[0].category == "bug"


def test_strategy_skips_when_all_verified(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    h = _h("h-001")
    h.verifications["x/y"] = Verification(
        repo="x/y", verified_at="2026-05-18", outcome="compliant", reasoning="ok"
    )
    hs.upsert(h)

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["x/y"])  # only one repo, already verified
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_skips_archived_hypotheses(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    h = _h("h-001"); h.status = "archived"
    hs.upsert(h)

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    cfg = _config(["x/y"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    assert produced == []
    llm.complete.assert_not_called()


def test_strategy_compliant_verdict_no_candidate(tmp_state_dir: Path) -> None:
    hs = HypothesisStore()
    hs.upsert(_h("h-001"))

    events = EventStore(); events.ensure_schema()
    candidates = CandidateStore()
    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text='```json\n{"outcome": "compliant", "reasoning": "implementation passes spec", "confidence": 0.9}\n```',
        input_tokens=100, output_tokens=20, cache_read_tokens=0, cache_creation_tokens=0,
    )
    cfg = _config(["x/y"])
    strat = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hs
    )

    produced = strat.on_ingestion_complete(IngestionDeltas(
        since=datetime.now(tz=timezone.utc), repos_with_new_prs=[]
    ))
    # No candidate for compliant verdict but verification IS recorded
    assert produced == []
    assert hs.get("h-001").verifications.get("x/y") is not None
    assert hs.get("h-001").verifications["x/y"].outcome == "compliant"
```

### `src/af_expert/strategies/s3_hypothesis_verify.py`

```python
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


def verify_prompt(*, hypothesis: Hypothesis, repo: str, briefing: str | None) -> str:
    parts: list[str] = [
        f"You are verifying a hypothesis against the OSS repository '{repo}'.\n\n"
        f"Hypothesis (id={hypothesis.id}): {hypothesis.statement}\n\n"
        "Decide whether this repo's implementation is compliant, non_compliant, "
        "not_applicable (concept doesn't exist in this repo), or unclear.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- outcome: \"compliant\" | \"non_compliant\" | \"not_applicable\" | \"unclear\"\n"
        "- reasoning: 2-3 sentences citing specific files / behaviors if possible\n"
        "- confidence: float 0.0-1.0\n\n"
    ]
    if briefing:
        parts.append("### Architecture briefing\n")
        parts.append(briefing[:6000])
        parts.append("\n")
    else:
        parts.append(
            "(No architecture briefing available — base your decision on training-time "
            "knowledge of this repo.)\n"
        )
    return "".join(parts)


def _load_briefing(repo: str) -> str | None:
    from af_expert.architecture.refresh import repo_briefing_path
    p = repo_briefing_path(repo)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


class HypothesisVerifyStrategy(Strategy):
    name = "s3_hypothesis_verify"

    def __init__(self, *args: Any, hypothesis_store: HypothesisStore, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hypothesis_store = hypothesis_store

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        active = self.hypothesis_store.list_active()
        if not active:
            return []

        all_repos = [r.owner_repo for r in self.config.repos]
        if not all_repos:
            return []

        # Pick one (hypothesis, repo) pair to verify this tick
        for h in active:
            unverified = self.hypothesis_store.unverified_repos(h.id, all_repos=all_repos)
            if not unverified:
                continue
            target_repo = unverified[0]  # take first; could randomize in future
            return self._verify_one(h, target_repo)

        return []

    def _verify_one(self, h: Hypothesis, repo: str) -> list[Candidate]:
        briefing = _load_briefing(repo)
        try:
            resp = self.llm.complete(
                system="You are verifying an architectural hypothesis against an OSS repo.",
                user=verify_prompt(hypothesis=h, repo=repo, briefing=briefing),
                caller_label=f"s3.verify[{h.id}->{repo}]",
            )
            data = parse_json_block(resp.text)
        except Exception as e:
            log.warning("S3 verification failed for %s -> %s: %s", h.id, repo, e)
            return []

        outcome = data.get("outcome", "unclear")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.5))

        v = Verification(
            repo=repo,
            verified_at=datetime.now(tz=timezone.utc).date().isoformat(),
            outcome=outcome,
            reasoning=reasoning,
            confidence=confidence,
        )
        self.hypothesis_store.attach_verification(h.id, v)

        log.info("S3 %s -> %s: %s (conf %.2f)", h.id, repo, outcome, confidence)

        if outcome != "non_compliant":
            return []

        candidate = self._build_candidate(h=h, repo=repo, v=v)
        self.candidates.append(candidate)
        v.candidate_id = candidate.id
        self.hypothesis_store.attach_verification(h.id, v)
        return [candidate]

    def _build_candidate(self, *, h: Hypothesis, repo: str, v: Verification) -> Candidate:
        return Candidate(
            id=f"s3-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="bug",
            title=f"Hypothesis verified non-compliant: {h.id}",
            description=(
                f"Hypothesis: {h.statement}\n\n"
                f"Verification reasoning: {v.reasoning}\n\n"
                f"Confidence: {v.confidence:.2f}"
            ),
            suggested_action=(
                f"Review {repo}'s implementation against the hypothesis. "
                f"If genuinely non-compliant, propose a fix PR."
            ),
            evidence_urls=[f"https://github.com/{repo}"],
            evidence_snippets=[],
            confidence=v.confidence,
            novelty=0.7,
            actionability=0.5,
            strategy_reputation=0.5,
            status="new",
        )
```

### Run + commit

```bash
uv run pytest tests/test_strategy_s3.py -v
# Expected: 4 tests pass

git add python/tools/af_expert/src/af_expert/strategies/s3_hypothesis_verify.py python/tools/af_expert/tests/test_strategy_s3.py
git commit -m "feat(af-expert): S3 active hypothesis verification strategy"
```

---

## Task 3: CLI integration + README

### Modify `cli.py`

Add imports:
```python
from af_expert.hypothesis.model import Hypothesis
from af_expert.hypothesis.store import HypothesisStore
from af_expert.strategies.s3_hypothesis_verify import HypothesisVerifyStrategy
import uuid
```

Add `--include-hypotheses` flag to `tick` (same pattern as the other flags). Inside tick body:

```python
if include_hypotheses:
    hyp_store = HypothesisStore()
    s3 = HypothesisVerifyStrategy(
        config=cfg, events=events, candidates=candidates, llm=llm, hypothesis_store=hyp_store
    )
    s3_produced = s3.on_ingestion_complete(deltas)
    click.echo(f"S3 (hypothesis verify) produced {len(s3_produced)} candidates")
    all_produced.extend(s3_produced)
```

Add the `hypothesis` subcommand group:

```python
@cli.group()
def hypothesis() -> None:
    """Active hypothesis management."""


@hypothesis.command("add")
@click.argument("statement")
def hypothesis_add(statement: str) -> None:
    store = HypothesisStore()
    new_id = f"h-{uuid.uuid4().hex[:8]}"
    h = Hypothesis(
        id=new_id,
        statement=statement,
        proposed_by="operator",
        created_at=datetime.now(tz=timezone.utc),
    )
    store.upsert(h)
    click.echo(f"Added {new_id}")


@hypothesis.command("list")
@click.option("--archived", is_flag=True, default=False)
def hypothesis_list(archived: bool) -> None:
    store = HypothesisStore()
    items = store.list_all() if archived else store.list_active()
    if not items:
        click.echo("(no hypotheses)")
        return
    for h in items:
        verified = len(h.verifications)
        click.echo(f"  {h.id}\t[{h.status}]\t{verified} verified\t{h.statement[:80]}")


@hypothesis.command("show")
@click.argument("hid")
def hypothesis_show(hid: str) -> None:
    store = HypothesisStore()
    h = store.get(hid)
    if h is None:
        click.echo(f"hypothesis {hid!r} not found", err=True)
        sys.exit(2)
    click.echo(h.model_dump_json(indent=2))


@hypothesis.command("archive")
@click.argument("hid")
def hypothesis_archive(hid: str) -> None:
    store = HypothesisStore()
    store.archive(hid)
    click.echo(f"Archived {hid}")
```

Update `strategy list` to mention S3. Update `strategy run` to handle s3.

Add tests for `hypothesis add / list` commands following the pattern of Wave 3's concept tests.

### Commit + README

After CLI changes:
```bash
git add python/tools/af_expert/src/af_expert/cli.py python/tools/af_expert/tests/test_cli.py
git commit -m "feat(af-expert): wire S3 + hypothesis subcommand group into CLI"
```

Then README:
- Add "### Wave 4 commands" subsection with hypothesis add/list/show/archive examples
- Add "## Wave 4 status" section describing S3 + hypothesis tracker
- Update state layout to add `hypotheses.json`
- Update "Still TBD" to remove S3

```bash
git add python/tools/af_expert/README.md
git commit -m "docs(af-expert): document Wave 4 (hypothesis tracker / S3)"
```

---

## Wave 4 done — verification

- All tests pass (~135 expected)
- `af-expert hypothesis add "..."` creates a hypothesis
- `af-expert hypothesis list` shows it
- `af-expert tick --include-hypotheses` verifies one (h × repo) pair per run

## What's NOT in Wave 4

| Wave | Plan delivers |
|---|---|
| 5 | Spec corpus + S5 conformance fuzzer |
