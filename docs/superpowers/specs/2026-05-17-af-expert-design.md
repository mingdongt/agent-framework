# af-expert: Continuously-Learning Domain Expert Agent for OSS Agent Frameworks

**Date:** 2026-05-17
**Status:** Design v1 — pending implementation plan
**Scope:** Local CLI + persistent state, multi-repo expert system feeding contribution opportunities into af-fix

## Goal

Build a local, continuously-running expert system that:

1. **Masters the architecture** of every tracked OSS agent framework / LLM repo (via `understand-anything` skill suite)
2. **Ingests daily changes** (issues / PRs / releases / commits) and updates its understanding
3. **Runs 8 intelligence strategies in parallel** to surface bug candidates AND non-bug contribution opportunities
4. **Answers conversational queries** about the ecosystem ("what's the state of MCP support across frameworks?")
5. **Feeds candidates into af-fix** for the candidates the operator chooses to act on

The system is the *upstream* of [af-fix](2026-05-16-af-fix-agent-design.md): af-expert generates contribution candidates, af-fix turns chosen candidates into draft PRs. The two tools are loosely coupled via a documented candidate-spec file format.

## Non-goals

- ❌ Not a chatbot — conversational mode exists but is one of several output surfaces
- ❌ Not a real-time monitor — daily cadence; no webhooks, no streaming
- ❌ Not a published service — local CLI + local state, single operator
- ❌ Not a replacement for `understand-anything` — wraps and orchestrates its skills
- ❌ Not autonomous-PR — never opens issues or PRs; output is local candidates only
- ❌ Not multi-user — single operator, single machine, single state directory
- ❌ Not a knowledge graph database — uses files + SQLite, NOT a graph DB or vector store (Phase 1-3)

## Relationship to af-fix

```
   ┌──────────────────┐    candidate-spec file     ┌──────────────────┐
   │    af-expert     │ ─────────────────────────→ │      af-fix      │
   │  (discovery)     │                            │  (fix + draft PR)│
   └──────────────────┘                            └──────────────────┘
```

- af-expert: continuous, multi-repo, multi-strategy discovery; outputs `~/.af-expert/candidates/`
- af-fix: per-candidate run, single-repo, OpenHands-driven fix → cross-fork draft PR
- Handoff: `af-fix --candidate <id>` reads the candidate spec, scoped to its target repo

## Architecture overview

```
                ┌────────────────────────────────────┐
                │     daily ingestion pipeline       │
                │  (issues / PRs / releases / spec)  │
                └────┬────────────────┬──────────────┘
                     │                │
              architecture       event store
              store (files)      (SQLite + FTS5)
                     │                │
   ┌─────────────────┴────────────────┴────────────────┐
   │                                                    │
   │   8 Intelligence Strategies (independent, parallel)│
   │                                                    │
   │   S1: 跨仓 PR 移植        S5: 规范一致性 fuzzer      │
   │   S2: 跨仓结构对比        S6: 维护活力衰减           │
   │   S3: 主动验证假设        S7: 跨仓功能移植          │
   │   S4: Provider 升级急救   S8: Issue 考古            │
   │           │                       │                │
   │           └───────────┬───────────┘                │
   │                       ↓                            │
   │              candidate store (JSONL)               │
   │                       │                            │
   │                    ranker                          │
   │                       │                            │
   │           ┌───────────┴───────────┐                │
   │           │                       │                │
   │      af-expert ask          af-expert suggest      │
   │           │                       │                │
   │           ↓                       ↓                │
   │   conversational query      daily digest           │
   │           │                       │                │
   └───────────┴───────────┬───────────┴────────────────┘
                           │
                    operator review
                           │
                       af-fix
                           │
                          PR
```

## File layout

```
python/tools/af_expert/
├── pyproject.toml                       # standalone uv project
├── README.md
├── src/af_expert/
│   ├── __init__.py
│   ├── cli.py                           # argparse entry, subcommands
│   ├── config.py                        # ~/.af-expert/config.toml
│   ├── state.py                         # state dir layout + locking
│   ├── github_client.py                 # PyGithub wrapper, multi-repo, rate-limit aware
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pipeline.py                  # daily tick orchestrator
│   │   ├── issues.py                    # fetch + normalize issues
│   │   ├── prs.py                       # fetch + normalize PRs
│   │   ├── releases.py                  # fetch + normalize releases
│   │   ├── providers.py                 # poll model provider channels
│   │   └── store.py                     # SQLite + FTS5 wrapper
│   ├── architecture/
│   │   ├── __init__.py
│   │   ├── refresh.py                   # invoke understand-anything per repo
│   │   ├── briefing.py                  # render briefing markdown
│   │   └── change_detection.py          # detect architectural drift from PR feed
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                      # Strategy ABC + Candidate model
│   │   ├── s1_pr_forward_port.py        # 跨仓 PR 移植
│   │   ├── s2_structural_diff.py        # 跨仓结构对比
│   │   ├── s3_hypothesis_verify.py      # 主动验证假设
│   │   ├── s4_provider_release.py       # Provider 升级急救
│   │   ├── s5_spec_conformance.py       # 规范一致性 fuzzer
│   │   ├── s6_maintainer_health.py      # 维护活力衰减
│   │   ├── s7_feature_propagation.py    # 跨仓功能移植
│   │   └── s8_issue_archaeology.py      # Issue 考古
│   ├── candidate/
│   │   ├── __init__.py
│   │   ├── model.py                     # pydantic Candidate model
│   │   ├── store.py                     # append-only JSONL per day
│   │   └── ranker.py                    # confidence × strategy reputation × novelty
│   ├── query/
│   │   ├── __init__.py
│   │   ├── ask.py                       # conversational query
│   │   └── digest.py                    # daily digest render
│   └── llm.py                           # Claude Opus 4.7 wrapper (Anthropic SDK)
└── tests/
    ├── conftest.py
    ├── test_state.py
    ├── test_config.py
    ├── test_ingestion_pipeline.py
    ├── test_ingestion_issues_prs.py
    ├── test_ingestion_store.py
    ├── test_architecture_refresh.py
    ├── test_strategies_<s1..s8>.py      # one per strategy
    ├── test_candidate_model.py
    ├── test_candidate_ranker.py
    ├── test_query_ask.py
    ├── test_query_digest.py
    └── e2e/test_smoke.py
```

State directory:

```
~/.af-expert/
├── config.toml
├── state.json                                  # cursor positions, last-run times
├── lock                                        # single-process lock
├── repos/<owner>__<repo>/
│   ├── architecture.md                         # narrative + KG summary
│   ├── architecture.kg.json                    # raw understand-anything output (cached)
│   ├── hypotheses.md                           # local hypotheses for this repo
│   └── events.md                               # rolling 30-day digest (rendered)
├── events.db                                   # SQLite + FTS5: issues, PRs, releases, commits
├── concept_graph.json                          # 20-30 concept nodes + per-repo implementation links
├── hypotheses.json                             # active hypothesis list (cross-repo)
├── candidates/YYYY-MM-DD.jsonl                 # append-only daily candidate logs
└── digests/YYYY-MM-DD.md                       # daily digest output
```

## LLM choice

- **Model**: Claude Opus 4.7 (`claude-opus-4-7`) — 1M context, latest generation
- **Provider**: Anthropic API direct via `anthropic` SDK with prompt caching enabled
- **Budget**: unconstrained; token spend is acceptable given the strategy ROI
- **Caching**: aggressive prompt caching on architecture briefings (they change slowly) and concept graph

## Storage decisions (why no RAG)

The full briefing corpus across 30 tracked repos is ~5MB (≈1.5M tokens). It **fits in a single Opus 4.7 context window**. Therefore:

- **Briefings**: plain markdown files, read whole when needed
- **Event history (large, append-only)**: SQLite + FTS5 — structured queries + full-text search in one file, zero ops
- **Concept graph**: JSON file (20-30 nodes, fits in memory)
- **Candidates**: append-only JSONL per day
- **No vector DB, no graph DB** — adding these is the canonical engineering trap when the corpus already fits in context

Add a vector layer only when: (a) tracked repos exceed 100, (b) external sources (arxiv / blogs / social) get pulled in, or (c) sub-second query latency becomes a requirement. Not Phase 1-3.

## Core platform components

### Repo registry (config)

`~/.af-expert/config.toml`:

```toml
github_token = "ghp_..."             # public_repo scope only
anthropic_api_key = "sk-ant-..."

[ingestion]
poll_interval_hours = 24
event_retention_days = 365

[architecture]
refresh_trigger = "drift"            # "drift" | "weekly" | "manual"
refresh_min_days = 7                 # never refresh more often than this

[[repos]]
owner_repo = "microsoft/agent-framework"
priority = "high"                    # high|normal|low — affects ranker weighting
languages = ["python", "csharp"]

[[repos]]
owner_repo = "langchain-ai/langchain"
priority = "high"
languages = ["python"]

# ... 20-30 entries
```

### Ingestion pipeline

Daily tick (`af-expert tick`, also invokable from cron):

1. Load `state.json` to get last-cursor per repo per source
2. For each repo, fetch deltas since cursor:
   - **Issues**: opened / commented-on / closed in window
   - **PRs**: opened / merged / closed in window (include diff for merged)
   - **Releases**: published since cursor
   - **Commits to default branch**: optional, controlled by config
3. Normalize each record → write to `events.db` (SQLite)
4. Update cursors atomically
5. Invoke `architecture.change_detection.detect_drift()` — if a repo's PRs touched core abstractions, mark for architecture refresh
6. Invoke each enabled strategy's `on_ingestion_complete()` hook
7. Run ranker over new candidates
8. Render daily digest → `digests/YYYY-MM-DD.md`

Rate limiting: 5000 req/hr GitHub authenticated. With 30 repos × ~50 records/day = 1500 requests, well within limit. Exponential backoff on 429.

Failure handling: per-repo failures are isolated — one repo failing doesn't block others. State.json records `last_failed_ingestion` per repo for visibility.

### Architecture store

Per-repo briefing:

`~/.af-expert/repos/<owner>__<repo>/architecture.md`

```markdown
# microsoft/agent-framework

**Last refreshed:** 2026-05-15
**KG version:** ua-v0.4
**Drift detected since:** none

## Purpose
[1-paragraph from understand-anything]

## Top-level components
- `python/packages/core/agent_framework/` — Python core agent abstractions
- `dotnet/Microsoft.Extensions.AI.Agents/` — .NET equivalent
- ...

## Key abstractions
- ChatClient: provider-agnostic LLM interface
- Workflow: deterministic multi-step orchestration
- AGUI: agent-UI protocol layer
- ...

## Provider integrations
- Anthropic: `_anthropic_chat_client.py`, supports thinking blocks
- OpenAI: `_openai_chat_client.py`, supports Responses API
- Azure OpenAI: ...
- ...

## Recent architectural changes (30d)
- 2026-05-13: Magentic protocol introduced (PR #5778)
- 2026-05-09: AG-UI event metadata refactor
```

Refresh triggered by:
- **"drift" mode (default)**: PR change_detection flags any commit touching files in `understand-anything`-identified "core" set
- **"weekly"**: scheduled
- **Manual**: `af-expert refresh <repo>`

Each refresh re-runs `understand-anything:understand` on the local clone, regenerates the briefing.

### Event store schema (SQLite)

```sql
CREATE TABLE events (
    id           INTEGER PRIMARY KEY,
    repo         TEXT NOT NULL,            -- "owner/name"
    kind         TEXT NOT NULL,            -- "issue" | "pr" | "release" | "commit"
    number       INTEGER,                  -- issue/PR number, null for releases/commits
    title        TEXT,
    body         TEXT,                     -- issue body, PR description
    diff         TEXT,                     -- PR diff (for merged PRs only)
    author       TEXT,
    state        TEXT,                     -- "open"|"closed"|"merged"|"published"
    labels       TEXT,                     -- JSON array
    created_at   TIMESTAMP,
    updated_at   TIMESTAMP,
    closed_at    TIMESTAMP,
    merged_at    TIMESTAMP,
    url          TEXT,
    raw          TEXT,                     -- full GitHub API JSON for forensics
    ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE events_fts USING fts5(
    title, body, diff, labels,
    content='events', content_rowid='id'
);

CREATE INDEX idx_events_repo_kind_created ON events (repo, kind, created_at);
CREATE INDEX idx_events_merged ON events (kind, merged_at) WHERE kind='pr';
```

### Candidate model

```python
class Candidate(BaseModel):
    id: str                                # uuid4
    discovered_at: datetime
    strategy: str                          # "s1_pr_forward_port" etc.

    # Target of the candidate
    target_repo: str                       # "owner/name"
    target_files: list[str] = []           # paths in target repo
    target_lines: list[tuple[int, int]] = []
    category: Literal["bug", "feature", "maintenance", "consolidation"]

    # Hypothesis
    title: str                             # one-line headline
    description: str                       # 1-3 paragraph explanation
    suggested_action: str                  # one-line PR title / suggestion

    # Evidence
    evidence_urls: list[str] = []          # links to source PR, related issue, spec
    evidence_snippets: list[str] = []      # code snippets, error excerpts

    # Quality signals
    confidence: float                      # 0.0-1.0
    novelty: float                         # 0.0-1.0; how non-obvious
    actionability: float                   # 0.0-1.0; ready to PR vs needs design
    strategy_reputation: float             # 0.0-1.0; rolling avg of this strategy

    # Lifecycle
    status: Literal["new", "reviewed", "accepted", "rejected", "shipped"]
    notes: str = ""                        # operator's annotations
```

### Ranker

Per-candidate score:

```
score = w_conf * confidence
      + w_nov  * novelty
      + w_act  * actionability
      + w_rep  * strategy_reputation
      + w_pri  * priority_weight(target_repo)
```

Default weights: `w_conf=0.35, w_nov=0.20, w_act=0.25, w_rep=0.15, w_pri=0.05`. Tunable in config.

Strategy reputation: rolling 30-day moving average of candidates from this strategy that reached status `accepted` or `shipped`. Decays toward 0.5 for cold-start strategies.

## The 8 Intelligence Strategies

Each strategy is a class deriving from `Strategy`:

```python
class Strategy(ABC):
    name: str
    enabled: bool

    @abstractmethod
    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]: ...

    def on_weekly_tick(self) -> list[Candidate]: ...
    def on_demand(self, args: dict) -> list[Candidate]: ...
```

### S1: 跨仓 PR 移植

**Trigger**: New merged PR in any tracked repo with `kind=pr, state=merged` and labels/title suggesting bug fix.

**Process**:
1. Filter: PR title matches `fix:|fix\(|bug|fixes #`, OR PR has label like `bug` / `fix`
2. Fetch PR diff + body
3. LLM call (Opus 4.7): extract bug pattern → return structured `{pattern_name, failure_mode, code_shape_hints, fix_shape_hints}`
4. For each other tracked repo:
   a. Heuristic narrowing: ripgrep + semantic search on architecture.md for relevant files
   b. LLM call: "given this bug pattern, examine these files; is the same bug present? confidence + lines"
5. For each high-confidence hit, emit Candidate with category="bug"

**Cost**: O(merged_fix_PRs × tracked_repos × LLM_call). Estimated ~30 fix PRs/day × 30 repos × 1 LLM call narrowed = ~900 LLM calls/day. With prompt caching on architecture briefings, effective cost is closer to ~200 fresh calls.

**Failure modes**: false positives from superficial code shape match → filtered by confidence threshold; missed patterns when variable names differ → known limitation; addressed in S2.

### S2: 跨仓结构对比

**Trigger**: Daily, after architecture refreshes complete.

**Process**:
1. Maintain `concept_graph.json`: 20-30 hand-curated concept nodes (MCP, AG-UI, Anthropic.tool_use, OAuth.refresh, Gemini.thinking, streaming.reconnect, ...). Each concept references "implementation evidence" per repo: file paths + function names.
2. After each daily refresh, update concept→implementation links via LLM (only when architecture briefing changed).
3. Cross-repo queries:
   - "Concept X has implementations in N repos; M of them changed in last 30d; identify the (N-M) that didn't."
   - "Concept X was modified in repo A's recent PR with summary Y; do any other repos' implementations match the old shape but not the new one?"
4. Emit Candidate for each "lagging" or "non-conforming" implementation.

**Concept graph schema**:

```json
{
  "version": 1,
  "concepts": {
    "mcp.oauth.refresh": {
      "description": "MCP OAuth refresh-token grant handling",
      "spec_ref": "RFC 8707 §2.2",
      "implementations": {
        "microsoft/agent-framework": {
          "files": ["python/packages/core/agent_framework/_mcp.py"],
          "functions": ["_refresh_token"],
          "last_modified": "2026-05-14",
          "compliant": true
        },
        "modelcontextprotocol/python-sdk": {...},
        "..."
      }
    }
  }
}
```

**Bootstrapping the concept list**: seeded from `understand-anything:understand-domain` run on agent-framework + manual operator curation. ~30 concepts initial. The list grows ONLY by operator action — S4 may *propose* new concepts when providers introduce new APIs/fields, but the operator decides whether to accept. Auto-expansion is explicitly Phase 2+.

**Cost**: cheap query phase; one-time + delta upkeep on concept graph (~10 LLM calls/day amortized).

**Failure modes**: entity disambiguation errors poison queries. Mitigation: concept graph is a hand-curated list of ≤50 concepts, not auto-discovered; every concept has a written `description` and `spec_ref`.

### S3: 主动验证假设

**Trigger**: Daily probe schedule. Operator-or-LLM-proposed hypotheses.

**Process**:
1. Maintain `hypotheses.json`:

```json
{
  "active": [
    {
      "id": "h-001",
      "statement": "MCP OAuth refresh-token grants in most agent frameworks send the `resource` parameter, violating RFC 8707 §2.2",
      "proposed_by": "operator",
      "created_at": "2026-05-17",
      "status": "verifying",
      "verifications": {
        "microsoft/agent-framework": {"date": "2026-05-17", "outcome": "compliant"},
        "modelcontextprotocol/python-sdk": {"date": "2026-05-17", "outcome": "non-compliant"},
      },
      "candidates_produced": ["c-..."]
    }
  ]
}
```

2. Daily, for each active hypothesis, select one unverified tracked repo.
3. LLM call (large context): fetch the repo's relevant code section (guided by concept graph) → "verify hypothesis; output compliant | non-compliant | not-applicable | unclear with reasoning"
4. For `non-compliant`, emit Candidate with strong confidence.
5. After all repos verified, hypothesis transitions to `verified` and is archived.

**Hypothesis seeding**:
- Operator submits via `af-expert hypothesis add "..."`
- Auto-generated: each high-novelty Candidate from S1 can be promoted to a hypothesis (LLM-asked: "is this likely systemic across the ecosystem?")

**Cost**: 1 LLM call per (hypothesis × repo) per day; bounded by hypothesis count × verification budget.

**Failure modes**: bad hypotheses produce nothing useful. Mitigation: per-hypothesis tracking of `signal_yield` (candidates produced); auto-archive hypotheses below threshold after N days.

### S4: Provider 升级急救

**Trigger**: Poll provider sources daily/twice-daily:
- Anthropic: docs changelog, model registry endpoint
- OpenAI: model list endpoint, blog RSS
- Google AI / Vertex: docs changelog
- Azure OpenAI: docs changelog
- (configurable additional providers)

**Process**:
1. Detect new release: model added, API field added, capability change
2. Parse release notes (LLM) → structured `{provider, model_or_api, changes: [{field, kind: added|changed|removed, semantics}]}`
3. For each change, identify "support surfaces" in tracked frameworks (LLM-guided over architecture briefings)
4. For each (change × framework), ask: "Does this framework already support this? Correctly? Are there visible gaps?"
5. Emit Candidate for each gap with `actionability=1.0` (time-sensitive: provider release window is short, maintainers are motivated, merge race is real).

**Cost**: ~1-3 release events/month from major providers; each triggers ~30 framework checks. Bounded.

**Failure modes**: release-note parsing inaccuracy; mitigation: human-readable hypothesis attached to each candidate, easy to dismiss.

### S5: 规范一致性 fuzzer

**Trigger**: Weekly.

**Process**:
1. Maintain a spec test corpus:
   - `spec_corpus/mcp/` — property tests for MCP protocol
   - `spec_corpus/agui/` — for AG-UI
   - `spec_corpus/anthropic_tool_use/`
   - `spec_corpus/openai_responses/`
2. For each tracked framework, a thin **adapter** runs the corpus against the framework's surface (HTTP client, message converter, etc.)
3. Each adapter runs in Docker (reuses `af-fix`'s OpenHands runtime image or a lighter Python sandbox)
4. Failures captured as `{spec, property, repro, output_actual, output_expected}`
5. Emit Candidate with `evidence_snippets` containing the failing test code + actual output. **Strongest evidence form.**

**Adapter requirement**: each framework needs ~50-150 LOC of adapter code (call framework's converter, feed test input, capture output). Building 8-12 adapters is the heaviest single Phase 5 task.

**Cost**: compute-heavy weekly run (~30 minutes); LLM-light (only used for failure interpretation).

**Failure modes**: spec ambiguity → false positives. Mitigation: corpus is curated by the operator; each test cites its spec section.

### S6: 维护活力衰减检测

**Trigger**: Weekly metrics calculation.

**Process**:
1. Per repo, compute over rolling 30/90/180-day windows:
   - PR merge median latency
   - Issue backlog growth rate (open issues delta / day)
   - Maintainer response median latency on issues
   - Commit cadence (commits/week to default branch)
2. Detect inflection: latest 30d vs preceding 90d shows >2x degradation in any metric
3. Emit Candidate with category="maintenance"; suggested_action="consider becoming co-maintainer or proposing structural improvement"

**Cost**: O(repos × 4 metrics × SQL query). Cheap.

**Failure modes**: noisy metrics for low-volume repos. Mitigation: require minimum volume (e.g., ≥10 PRs/month) before computing inflection.

### S7: 跨仓功能移植

**Trigger**: Detect new feature/abstraction in any tracked repo (signal: PR with substantial new files + label "feature" / title prefix "feat:").

**Process**:
1. LLM: read the new feature's PR description + diff → extract "what new capability does this add"
2. For each other tracked repo: check if equivalent capability exists (LLM over architecture briefing)
3. Emit Candidate with category="feature"; suggested_action="propose <feature> for <target_repo>" — clearly marked as **needs RFC/issue first**, not drop-in PR

**Cost**: gated by new-feature event count; ~1-5/week typically.

**Failure modes**: high rejection rate — feature PRs need political/design alignment. Mitigation: actionability score caps at 0.6 for category=feature; operator expectations set accordingly.

### S8: Issue 考古

**Trigger**: Monthly per repo + once on initial ingestion.

**Process**:
1. Query SQLite: closed issues from this repo with labels `wontfix` / `stale` / `not-planned` and `closed_at` between 6-36 months ago
2. For each, LLM call: "given this repo's current architecture and toolchain, is this issue more tractable today than when closed? brief justification"
3. Emit Candidate for tractable ones with `actionability ≤ 0.5` (likely needs reopen-comment first, not immediate PR).

**Cost**: bounded by closed-issue volume; spread over month.

**Failure modes**: many wontfix decisions are correct and unchanged. Mitigation: low default confidence; operator review essential.

## CLI surface

```
af-expert init                              # one-time setup, validate config
af-expert tick                              # run daily ingestion + strategies (idempotent)
af-expert refresh <repo>                    # force-refresh architecture for one repo
af-expert refresh --all                     # refresh all
af-expert digest [--since 1d|7d]            # show daily/weekly digest
af-expert suggest [--strategy s1] [--top N] # show top-N candidates
af-expert ask "<question>"                  # conversational query over briefings+events
af-expert candidate show <id>               # full candidate detail
af-expert candidate accept <id> [--notes]   # mark accepted
af-expert candidate reject <id> [--notes]   # mark rejected
af-expert candidate export <id> > spec.md   # export as af-fix-compatible spec
af-expert hypothesis list
af-expert hypothesis add "<statement>"
af-expert hypothesis show <id>
af-expert strategy list                     # show enabled/disabled per strategy
af-expert strategy enable <name>
af-expert strategy disable <name>
af-expert stats                             # per-strategy reputation, candidate counts
```

## af-fix handoff

`af-expert candidate export <id>` produces:

```markdown
# Candidate <id>

**Repo:** owner/name
**Strategy:** s1_pr_forward_port
**Category:** bug
**Title:** ...

## Description
...

## Target
- Files: [...]
- Lines: [...]

## Evidence
- Source PR: ...
- Spec ref: ...
- Snippets: ...

## Suggested action
...
```

`af-fix --candidate-spec <file>` consumes this and routes to its OpenHands pipeline. The two tools never share code directly; the spec file is the contract.

**af-fix dependency note**: the existing [af-fix design](2026-05-16-af-fix-agent-design.md) reads issues from GitHub; it does NOT yet accept a candidate-spec file. Adding this entry point is a small extension (~50 LOC: a new CLI flag, a spec parser, a path that builds the OpenHands prompt from the spec instead of from an issue body). This extension is in af-expert's Wave 1 scope, NOT a Phase 2 dependency — it must ship with the first usable af-expert version so the loop closes end-to-end.

## Cadence & build wave order

Even targeting the full smart system, build in waves to ship value early:

### Wave 1 (weeks 1-2): Core + cheapest strategies

- `config`, `state`, `ingestion.pipeline`, `ingestion.store` (SQLite), `candidate.model`, `candidate.store`, `candidate.ranker`, `cli` skeleton, `llm` wrapper
- `s1_pr_forward_port` (simplest — uses only PR feed + ripgrep)
- `s8_issue_archaeology` (free signal, bounded cost)
- `query.digest`, `query.ask` (basic)

**Validation milestone**: tick produces ≥1 candidate from S1 within 7 days of running against 20+ repos.

### Wave 2 (weeks 3-4): Architecture awareness + provider hooks

- `architecture.refresh` (invokes understand-anything), `architecture.briefing`, `architecture.change_detection`
- `s4_provider_release` (poll Anthropic/OpenAI/Google docs)
- `s6_maintainer_health` (metrics-only, no LLM)

**Validation milestone**: architecture briefings exist for all configured repos; one provider release event traced end-to-end to candidates.

### Wave 3 (weeks 5-8): Cross-repo structural

- `concept_graph.json` initial curation (~20-30 concepts)
- `s2_structural_diff`
- `s7_feature_propagation` (cheap addition once concept graph exists)

**Validation milestone**: S2 produces at least one "reverse" candidate (a repo NOT updating for a spec change), confirming counterfactual queries work.

### Wave 4 (weeks 9-12): Active probing

- `hypotheses.json`, `s3_hypothesis_verify`
- Hypothesis-to-candidate promotion from S1 outputs

**Validation milestone**: one hypothesis goes from `proposed` → fully verified across ≥10 repos → produces ≥1 high-confidence candidate.

### Wave 5 (weeks 12-20): Spec conformance

- `spec_corpus/` initial: MCP, then AG-UI, then Anthropic tool_use
- Per-framework adapters (8-12 frameworks)
- `s5_spec_conformance`

**Validation milestone**: one spec failure becomes a Candidate with a `repro.py` snippet that an operator can run on bare framework install.

### Phase 2+ (signposted, not designed):

- External sources: arxiv, hackernews, X/Twitter announcements
- Vector layer when corpus > Opus context (>1.5M tokens)
- Multi-operator / shared state
- Web UI for digest / candidate review
- `af-expert serve` daemon mode with webhook ingestion
- LLM-assisted concept graph expansion

## Error handling & failure isolation

| Stage | Error | Handling |
|---|---|---|
| Ingestion | GitHub rate limit / 5xx | Exponential backoff; per-repo cursor stays, next tick resumes |
| Ingestion | Single repo permanently fails | Mark repo `degraded` in state.json; surface in `af-expert stats`; continue others |
| Architecture refresh | understand-anything fails | Keep prior briefing; mark `refresh_failed_at`; continue |
| Strategy | LLM error / timeout | Log + skip candidate; record in strategy_stats |
| Strategy | Strategy class raises | Strategy disabled for rest of tick; surfaces in stats |
| Candidate store | Disk full | Hard error; abort tick before partial write |
| Query | LLM error | Surface to user; no state mutation |

Tick is fully resumable: state.json holds per-repo cursors; partial work is OK; next tick continues. No tick is ever "rolled back."

## Security & trust boundaries

| Risk | Mitigation |
|---|---|
| GitHub token leak | Stored in config.toml (chmod 600); `public_repo` scope only |
| LLM prompt injection from issue body | All inbound text is data, never executed; LLM responses are NOT given tool execution privileges in af-expert |
| af-expert acts on its own (opens PRs) | af-expert NEVER calls `github.create_*` APIs; only `get_*` and `list_*`; enforced by github_client wrapper |
| Concept graph manipulation | concept_graph.json is operator-edited; LLM proposes additions but operator must accept |
| Strategy state corruption | All persistent state has atomic-write semantics (tmp file + rename) |

## Testing strategy

### Layer 1 — Unit tests (no LLM, no network, no disk-write at user paths)

- `state`, `config`: file I/O, locking, atomic write
- `candidate.model`: schema validation
- `candidate.ranker`: scoring math
- `candidate.store`: append + read-back
- `ingestion.store`: SQLite schema, FTS5 queries, cursor management
- Each strategy in isolation with mocked LLM + mocked event store

In CI; runs in seconds.

### Layer 2 — Strategy simulation tests (mock LLM + fake events)

- Build synthetic event sequences (fake PRs) → invoke strategy → assert candidate output shape + count
- Tests strategy logic without depending on real LLM behavior

In CI.

### Layer 3 — End-to-end smoke (real LLM, real GitHub)

`tests/e2e/test_smoke.py`, `@pytest.mark.e2e`:

- `af-expert init --dry-run` against test config with 2 repos
- One full `tick` cycle: assert events ingested, at least one candidate produced
- `af-expert ask` against a known question with deterministic expected substring

Operator-run; requires `~/.af-expert/config.toml` + real keys.

## Open questions deferred to plan stage

- **Concept graph bootstrapping**: which 20-30 concepts seed the initial graph? (Will be a deliverable in Wave 3.)
- **Hypothesis dedup**: when S1 promotes a candidate to hypothesis, how do we ensure no duplicates? (Will be a Wave 4 design decision.)
- **Adapter shape for S5**: per-framework adapter API — what's the minimum interface? (Will be Wave 5 design.)
- **Digest format**: prose summary vs structured table vs hybrid? (Will be Wave 1 design, iterable.)
- **Hypothesis auto-generation from S1**: rules for promoting Candidate → Hypothesis. (Wave 4.)
