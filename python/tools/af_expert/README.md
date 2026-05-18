# af-expert

Continuously-learning domain expert that ingests agent framework activity daily, runs 8 intelligence strategies, and surfaces contribution candidates for microsoft/agent-framework.

> Part of the **microsoft/agent-framework ecosystem-engineering initiative**
> — internal tooling supporting MAF (Microsoft's next-generation unified
> agent framework) through competitive ecosystem mapping, high-leverage
> opportunity identification, and accelerated contribution execution.
>
> Sibling tools: [af-watch](../af_watch/) (weekly editorial briefing) · [af-fix](../af_fix/) (issue → draft-PR executor)

## What it does

- **Daily ingestion**: pulls issues / PRs / releases from ~10 tracked agent framework repos into a local event store (SQLite + FTS5).
- **8 independent intelligence strategies** running over the event store:
  - **S1** — pattern extraction (cross-repo bug-shape recurrence)
  - **S2** — structural diff (concept-implementation drift across repos)
  - **S3** — hypothesis verification (operator-submitted invariants checked against per-repo architecture briefings)
  - **S4** — provider release rapid response (Anthropic / OpenAI / Google changelog → adaptation surface)
  - **S5** — spec conformance fuzzer (property-based tests over MCP, AG-UI, tool-use protocols)
  - **S6** — maintainer health (pure-SQL metrics: PR throughput, response time, churn)
  - **S7** — cross-repo feature propagation (new feature in one repo → propagation candidates for sister repos)
  - **S8** — issue archaeology (long-tail open issues clustered by failure mode)
- **30-concept agent/LLM domain graph** (hand-curated, JSON-backed) linking abstract concepts (e.g. `mcp.oauth.refresh`) to per-repo implementation sites.
- **Hypothesis tracker** for operator-submitted falsifiable claims, verified incrementally as architecture briefings accumulate.
- **Architecture briefings** generated per-repo via shallow git clone + LLM summarization.
- **Output**: ranked `Candidate` records with status overlay (new / accepted / rejected) — pipe-able to af-fix via `af-expert candidate export <id>`.

## Quick start

```bash
cd python/tools/af_expert
uv sync --all-extras

af-expert init
$EDITOR ~/.af-expert/config.toml   # github_token + anthropic_api_key + [[repos]]

# One-time per repo: generate architecture briefing
af-expert refresh microsoft/agent-framework

# Run the pipeline (defaults to S1 + S8)
af-expert tick

# Run with all strategies enabled
af-expert tick \
  --include-providers --include-health --include-archaeology \
  --include-structural --include-propagation \
  --include-hypotheses --include-conformance

# See ranked candidates
af-expert suggest --top 10
af-expert candidate show s4-abc123
af-expert candidate export s4-abc123 > /tmp/spec.md   # → pipe to af-fix
```

For the full command surface (concept graph management, hypothesis lifecycle, spec corpus, strategy debugging, ad-hoc conversational queries via `af-expert ask`), see `af-expert --help`.

## How it fits

```
af-expert  ──→  candidate JSONL store  ──→  af-fix  ──→  upstream draft PR
```

af-expert is the **always-on intelligence** layer: many cheap automated strategies accumulating evidence over time, producing high-confidence candidate records. Complementary to af-watch (which produces a weekly _editorial_ briefing for human deliberation), af-expert is the steady-state machinery.

## State layout

```
~/.af-expert/
├── config.toml
├── state.json            # ingestion cursors, run history
├── lock                  # single-process file lock
├── events.db             # SQLite + FTS5: PR/issue/release events
├── candidates/           # JSONL store, one per strategy
├── digests/              # daily ingestion summaries
├── traces/<date>.jsonl   # LLM I/O trace (caller, model, prompt preview, tokens)
├── concept_graph.json    # 30 concepts + per-repo implementation links
├── hypotheses.json       # operator-submitted hypotheses + verification results
├── repos/<owner>__<repo>/architecture.md
└── providers/<provider>/<date>.html
```

## Tech

Python 3.12 · `agent-framework-core` · `anthropic` SDK (Opus 4.7 + Haiku 4.5) · SQLite + FTS5 · `pydantic` v2 · GitHub REST · `pytest` · `ruff` / `mypy --strict`

Verbose logging: `AF_EXPERT_LOG_LEVEL=DEBUG`. Per-call LLM trace at `~/.af-expert/traces/<date>.jsonl`; disable with `AF_EXPERT_TRACE_DISABLED=1`.

## Status

5 waves shipped:

- **Wave 1** — core platform + S1 pattern extraction + S8 issue archaeology
- **Wave 2** — architecture briefings (shallow clone + LLM summary) + S4 provider release + S6 maintainer health
- **Wave 3** — 30-concept domain graph + S2 structural diff + S7 feature propagation
- **Wave 4** — hypothesis tracker + S3 hypothesis verification
- **Wave 5** — spec conformance corpus (MCP) + framework adapters + S5 spec fuzzer

Adding more spec corpora (AG-UI, Anthropic tool_use, OpenAI Responses) and more framework adapters (LangChain, pydantic-ai, etc.) is explicit follow-up work.
